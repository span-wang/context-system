from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from contextlib import suppress
from socket import gethostname
from typing import Any
from uuid import uuid4

from deps import get_db


TaskHandler = Callable[[dict[str, Any]], Awaitable[None]]

_handlers: dict[str, TaskHandler] = {}
_scheduler_task: asyncio.Task | None = None
_worker_id = f"{gethostname()}:{uuid4()}"
_stop_event: asyncio.Event | None = None
_wake_event: asyncio.Event | None = None
_semaphore: asyncio.Semaphore | None = None
_active: set[asyncio.Task] = set()
_max_concurrency = 2


def register_task_handler(task_type: str, handler: TaskHandler) -> None:
    _handlers[task_type] = handler


def enqueue_background_task(task_type: str, payload: dict[str, Any], *, max_attempts: int = 3) -> str:
    if task_type not in _handlers:
        raise ValueError(f"unknown background task type: {task_type}")
    task_id = get_db().enqueue_task(task_type, payload, max_attempts=max_attempts)
    _wake_scheduler()
    return task_id


async def start_background_worker(*, max_concurrency: int = 2) -> None:
    global _max_concurrency, _scheduler_task, _semaphore, _stop_event, _wake_event
    _max_concurrency = max(1, max_concurrency)
    if _scheduler_task and not _scheduler_task.done():
        return

    _stop_event = asyncio.Event()
    _wake_event = asyncio.Event()
    _semaphore = asyncio.Semaphore(_max_concurrency)
    recovered = await asyncio.to_thread(get_db().recover_active_tasks)
    _scheduler_task = asyncio.create_task(_scheduler_loop(), name="background-task-scheduler")
    if recovered:
        _wake_scheduler()


async def stop_background_worker() -> None:
    global _scheduler_task
    if _stop_event:
        _stop_event.set()
    if _wake_event:
        _wake_event.set()
    if _scheduler_task:
        _scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await _scheduler_task
        _scheduler_task = None
    for task in list(_active):
        task.cancel()
    if _active:
        await asyncio.gather(*_active, return_exceptions=True)
    _active.clear()


async def _scheduler_loop() -> None:
    assert _stop_event is not None
    assert _wake_event is not None
    while not _stop_event.is_set():
        _wake_event.clear()
        launched = await _launch_available_tasks()
        if not launched:
            try:
                await asyncio.wait_for(_wake_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass


async def _launch_available_tasks() -> bool:
    assert _semaphore is not None
    launched = False
    while len(_active) < _max_concurrency:
        task_record = await asyncio.to_thread(get_db().claim_next_task, _worker_id)
        if not task_record:
            break
        await _semaphore.acquire()
        task = asyncio.create_task(_execute_task(task_record), name=f"background-task:{task_record['id']}")
        _active.add(task)
        task.add_done_callback(_active.discard)
        launched = True
    return launched


async def _execute_task(task_record: dict[str, Any]) -> None:
    assert _semaphore is not None
    try:
        task_type = task_record["task_type"]
        handler = _handlers.get(task_type)
        if not handler:
            raise RuntimeError(f"no handler registered for background task type: {task_type}")
        result = handler(task_record["payload"])
        if inspect.isawaitable(result):
            await result
        await asyncio.to_thread(get_db().complete_task, task_record["id"])
    except asyncio.CancelledError:
        await asyncio.to_thread(get_db().fail_task, task_record["id"], "worker shutdown", retry_delay_seconds=0)
        raise
    except Exception as exc:
        delay = min(300, 10 * int(task_record["attempts"] or 1))
        await asyncio.to_thread(get_db().fail_task, task_record["id"], str(exc), retry_delay_seconds=delay)
    finally:
        _semaphore.release()
        _wake_scheduler()


def _wake_scheduler() -> None:
    if _wake_event:
        _wake_event.set()

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.db.bootstrap import initialize_database
from app.db.session import SessionLocal
from app.job_recovery import fail_interrupted_analysis_jobs, sync_paper_parse_job_statuses
from app.middleware.audit import FailedRequestAuditMiddleware
from background import start_background_worker, stop_background_worker
from deps import get_db, get_storage
from routers import generate_router, history_router, library_router, system_router, tasks_router, workflow_router
from settings import get_settings


settings = get_settings()
app = FastAPI(title=settings.app.name, version="0.1.0")


def _allowed_origins() -> list[str]:
    defaults = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    raw_values = [
        os.getenv("APP_CORS_ORIGINS"),
        os.getenv("PUBLIC_WEB_URL"),
        os.getenv("PUBLIC_WEB_ORIGIN"),
    ]
    extras: list[str] = []
    for raw in raw_values:
        if not raw:
            continue
        for item in raw.replace("\n", ",").split(","):
            value = item.strip()
            if not value:
                continue
            if "://" not in value:
                value = f"https://{value}"
            extras.append(value.rstrip("/"))
    return list(dict.fromkeys([*defaults, *extras]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(FailedRequestAuditMiddleware)

app.include_router(library_router)
app.include_router(generate_router)
app.include_router(history_router)
app.include_router(workflow_router)
app.include_router(system_router)
app.include_router(tasks_router)

# New professional platform APIs are mounted under a dedicated namespace
# so the original product remains the default entry point.
app.include_router(api_router, prefix="/platform")


@app.on_event("startup")
async def startup() -> None:
    get_db()
    get_storage()
    initialize_database()
    with SessionLocal() as session:
        fail_interrupted_analysis_jobs(session)
    with SessionLocal() as session:
        sync_paper_parse_job_statuses(session)
    await start_background_worker()


@app.on_event("shutdown")
async def shutdown() -> None:
    await stop_background_worker()

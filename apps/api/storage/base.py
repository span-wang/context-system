from typing import Protocol


class Storage(Protocol):
    async def put(self, key: str, data: bytes) -> str: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...


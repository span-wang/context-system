from pathlib import Path


class LocalFSStorage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _full_path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in path.parents and path != root:
            raise ValueError("Storage key resolves outside of storage root.")
        return path

    async def put(self, key: str, data: bytes) -> str:
        path = self._full_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        return key

    async def get(self, key: str) -> bytes:
        return self._full_path(key).read_bytes()

    async def delete(self, key: str) -> None:
        path = self._full_path(key)
        if path.exists():
            path.unlink()


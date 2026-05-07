from functools import lru_cache

from library.service import LibraryService
from rag.ragflow import RAGFlowProvider
from settings import get_settings
from storage.db import Database
from storage.local import LocalFSStorage


@lru_cache
def get_db() -> Database:
    return Database()


@lru_cache
def get_storage() -> LocalFSStorage:
    settings = get_settings()
    return LocalFSStorage(settings.storage.root_path)


@lru_cache
def get_library_service() -> LibraryService:
    return LibraryService(get_db(), get_storage())


@lru_cache
def get_ragflow_provider() -> RAGFlowProvider:
    return RAGFlowProvider(get_settings().ragflow)

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


def _find_project_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "config.yaml").exists() or (candidate / "apps").exists():
            return candidate
    return here


PROJECT_ROOT = _find_project_root()


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([A-Z0-9_]+)\}")
        return pattern.sub(lambda m: os.getenv(m.group(1), ""), value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def _resolve_path(path: str | Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = PROJECT_ROOT / resolved
    return resolved


class AppConfig(BaseModel):
    name: str = "exam-kit"
    context_token_limit: int = 900_000


class LLMEndpointConfig(BaseModel):
    provider: str = "local_template"
    model: str = "local-template"
    max_tokens: int = 8192
    base_url: str | None = None
    api_key: str | None = None


class LLMPresetConfig(LLMEndpointConfig):
    name: str


class LLMConfig(BaseModel):
    generator: LLMEndpointConfig = Field(default_factory=LLMEndpointConfig)
    reviewer: LLMEndpointConfig = Field(
        default_factory=lambda: LLMEndpointConfig(provider="local_rules", model="local-rules")
    )
    presets: list[LLMPresetConfig] = Field(default_factory=list)


class StorageConfig(BaseModel):
    type: str = "local"
    root: str = "./data"
    bucket: str | None = None
    region: str | None = None

    @property
    def root_path(self) -> Path:
        return _resolve_path(self.root)


class DBConfig(BaseModel):
    url: str = "sqlite:///./data/app.db"

    @property
    def sqlite_path(self) -> Path:
        if not self.url.startswith("sqlite:///"):
            raise ValueError("Only sqlite:/// URLs are supported by the local MVP.")
        return _resolve_path(self.url.replace("sqlite:///", "", 1))


class RAGFlowConfig(BaseModel):
    enabled: bool = True
    base_url: str = "http://localhost:9380"
    api_key: str | None = None


class ReviewConfig(BaseModel):
    strict_when_sources_present: bool = True
    max_retry: int = 2
    unverified_warning: str = "本次生成未提供权威资料，内容基于模型知识。请核对官方资料后再使用。"


class SubjectConfig(BaseModel):
    id: str
    name: str
    categories: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    db: DBConfig = Field(default_factory=DBConfig)
    ragflow: RAGFlowConfig = Field(default_factory=RAGFlowConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    subjects: list[SubjectConfig] = Field(default_factory=list)


def normalize_subject_name(subject: str) -> str | None:
    value = subject.strip()
    if not value:
        return None
    value_lower = value.lower()
    for configured in get_settings().subjects:
        if value == configured.name or value == configured.id or value_lower == configured.id.lower():
            return configured.name
    return None


def is_known_subject(subject: str) -> bool:
    return normalize_subject_name(subject) is not None


@lru_cache
def get_settings() -> Settings:
    config_path = PROJECT_ROOT / "config.yaml"
    raw: dict[str, Any] = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    settings = Settings.model_validate(_expand_env(raw))
    settings.storage.root_path.mkdir(parents=True, exist_ok=True)
    settings.db.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    return settings

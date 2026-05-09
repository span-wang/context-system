from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


def _find_project_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "config.yaml").exists() or (candidate / "apps").exists():
            return candidate
    return here


PROJECT_ROOT = _find_project_root()
DEFAULT_MYSQL_URL = "mysql+pymysql://examkit:examkit123@127.0.0.1:3309/exam_kit_migrate_20260509?charset=utf8mb4"
MYSQL_URL_HINT = (
    "Only MySQL is supported. Set DB_URL to "
    f"{DEFAULT_MYSQL_URL}"
)


_DOTENV_FILENAMES = (".evn", ".env", ".env.local")
LLMTarget = Literal["generator", "reviewer"]
_INITIAL_ENV_KEYS = set(os.environ)
_DOTENV_MANAGED_KEYS: set[str] = set()


def _parse_dotenv_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if line.startswith("export "):
            line = line[7:].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key] = value
    return values


def _load_dotenv() -> None:
    loaded: dict[str, str] = {}
    for filename in _DOTENV_FILENAMES:
        loaded.update(_parse_dotenv_file(PROJECT_ROOT / filename))

    for key in list(_DOTENV_MANAGED_KEYS - set(loaded)):
        if key not in _INITIAL_ENV_KEYS:
            os.environ.pop(key, None)
        _DOTENV_MANAGED_KEYS.discard(key)

    for key, value in loaded.items():
        if key in _INITIAL_ENV_KEYS and key not in _DOTENV_MANAGED_KEYS:
            continue
        os.environ[key] = value
        _DOTENV_MANAGED_KEYS.add(key)


_load_dotenv()


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


def _normalize_mysql_url(url: str) -> str:
    candidate = url.strip()
    if candidate.startswith("mysql+pymysql://") or candidate.startswith("mysql+"):
        return candidate
    if candidate.startswith("mysql://"):
        return f"mysql+pymysql://{candidate.removeprefix('mysql://')}"
    raise ValueError(MYSQL_URL_HINT)


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
    url: str = DEFAULT_MYSQL_URL

    @property
    def resolved_url(self) -> str:
        return _normalize_mysql_url(self.url)


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
    platform_id: int | None = None


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    db: DBConfig = Field(default_factory=DBConfig)
    ragflow: RAGFlowConfig = Field(default_factory=RAGFlowConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    subjects: list[SubjectConfig] = Field(default_factory=list)


def list_subject_configs() -> list[SubjectConfig]:
    platform_subjects = _load_platform_subject_configs()
    if platform_subjects:
        return platform_subjects
    return get_settings().subjects


def normalize_subject_name(subject: str) -> str | None:
    value = subject.strip()
    if not value:
        return None
    value_lower = value.lower()
    for configured in list_subject_configs():
        if (
            value == configured.name
            or value == configured.id
            or value_lower == configured.id.lower()
            or (configured.platform_id is not None and value == str(configured.platform_id))
        ):
            return configured.name
    return None


def is_known_subject(subject: str) -> bool:
    return normalize_subject_name(subject) is not None


def resolve_llm_api_key(endpoint: LLMEndpointConfig, target: LLMTarget | None = None) -> str | None:
    _load_dotenv()
    if endpoint.api_key:
        return endpoint.api_key
    for env_key in llm_api_key_env_candidates(endpoint, target):
        value = os.getenv(env_key)
        if value:
            return value
    return None


def llm_api_key_env_candidates(endpoint: LLMEndpointConfig, target: LLMTarget | None = None) -> tuple[str, ...]:
    candidates: list[str] = []
    provider = endpoint.provider.strip()
    base_url = (endpoint.base_url or "").lower()
    is_deepseek = provider == "deepseek" or "api.deepseek.com" in base_url
    if provider == "anthropic":
        candidates.append("ANTHROPIC_API_KEY")
    elif is_deepseek:
        if target == "generator":
            candidates.append("DEEPSEEK_GENERATOR_API_KEY")
        elif target == "reviewer":
            candidates.append("DEEPSEEK_REVIEWER_API_KEY")
        candidates.extend(("DEEPSEEK_API_KEY", "OPENAI_API_KEY"))
    elif provider == "openai_compat":
        candidates.append("OPENAI_API_KEY")

    return tuple(dict.fromkeys(key for key in candidates if key))


@lru_cache
def get_settings() -> Settings:
    _load_dotenv()
    config_path = PROJECT_ROOT / "config.yaml"
    raw: dict[str, Any] = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8-sig")) or {}
    if os.getenv("DB_URL"):
        raw.setdefault("db", {})["url"] = os.getenv("DB_URL")
    if os.getenv("STORAGE_ROOT"):
        raw.setdefault("storage", {})["root"] = os.getenv("STORAGE_ROOT")
    settings = Settings.model_validate(_expand_env(raw))
    settings.db.resolved_url
    settings.storage.root_path.mkdir(parents=True, exist_ok=True)
    return settings


def _load_platform_subject_configs() -> list[SubjectConfig]:
    try:
        from sqlalchemy import select

        from app.db.session import SessionLocal
        from app.models import Subject, SubjectCategory
    except Exception:
        return []

    try:
        with SessionLocal() as session:
            subjects = session.scalars(select(Subject).order_by(Subject.id.asc())).all()
            categories = session.scalars(
                select(SubjectCategory).order_by(
                    SubjectCategory.subject_id.asc(),
                    SubjectCategory.sort_order.asc(),
                    SubjectCategory.id.asc(),
                )
            ).all()
    except Exception:
        return []

    if not subjects:
        return []

    categories_by_subject: dict[int, list[str]] = {}
    for category in categories:
        values = categories_by_subject.setdefault(int(category.subject_id), [])
        if category.name not in values:
            values.append(category.name)

    return [
        SubjectConfig(
            id=(subject.code or str(subject.id)).strip(),
            name=subject.name,
            categories=categories_by_subject.get(int(subject.id), []),
            platform_id=int(subject.id),
        )
        for subject in subjects
        if str(subject.name).strip()
    ]

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import AliasChoices, BaseModel, Field


def _find_project_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "config.yaml").exists() or (candidate / "apps").exists():
            return candidate
    return here


PROJECT_ROOT = _find_project_root()
_DOTENV_FILENAMES = (".env.local", ".env", ".evn")
_INITIAL_ENV_KEYS = set(os.environ)
_DOTENV_MANAGED_KEYS: set[str] = set()
DEFAULT_MYSQL_URL = "mysql+pymysql://examkit:examkit123@127.0.0.1:3309/exam_kit_migrate_20260509?charset=utf8mb4"
MYSQL_URL_HINT = (
    "Only MySQL is supported. Set DB_URL to "
    f"{DEFAULT_MYSQL_URL}"
)


def _parse_dotenv_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
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


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        pattern = re.compile(r"\$\{([A-Z0-9_]+)\}")
        return pattern.sub(lambda match: os.getenv(match.group(1), ""), value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def _resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate


def _normalize_mysql_url(url: str) -> str:
    candidate = url.strip()
    if candidate.startswith("mysql+pymysql://") or candidate.startswith("mysql+"):
        return candidate
    if candidate.startswith("mysql://"):
        return f"mysql+pymysql://{candidate.removeprefix('mysql://')}"
    raise ValueError(MYSQL_URL_HINT)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv_list(value: str) -> list[str]:
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def _set_nested(raw: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    cursor = raw
    for key in path[:-1]:
        next_value = cursor.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[key] = next_value
        cursor = next_value
    cursor[path[-1]] = value


def _apply_env_overrides(raw: dict[str, Any]) -> dict[str, Any]:
    overrides: tuple[tuple[str, tuple[str, ...], Any], ...] = (
        ("APP_ENVIRONMENT", ("app", "environment"), str),
        ("APP_CORS_ORIGINS", ("app", "cors_origins"), _parse_csv_list),
        ("DB_URL", ("db", "url"), str),
        ("DB_ECHO", ("db", "echo"), _parse_bool),
        ("DB_POOL_SIZE", ("db", "pool_size"), int),
        ("DB_MAX_OVERFLOW", ("db", "max_overflow"), int),
        ("DB_AUTO_MIGRATE", ("db", "auto_migrate"), _parse_bool),
        ("DB_SEED_ON_STARTUP", ("db", "seed_on_startup"), _parse_bool),
        ("DB_MIGRATION_TARGET", ("db", "migration_target"), str),
        ("STORAGE_ROOT", ("storage", "root"), str),
        ("OCR_CACHE_SWEEP_ENABLED", ("ocr_cache_sweep", "enabled"), _parse_bool),
        ("OCR_CACHE_SWEEP_INTERVAL_SECONDS", ("ocr_cache_sweep", "interval_seconds"), int),
        ("OCR_CACHE_SWEEP_RUN_ON_STARTUP", ("ocr_cache_sweep", "run_on_startup"), _parse_bool),
        ("SECURITY_SECRET_KEY", ("security", "secret_key"), str),
        (
            "SECURITY_ACCESS_TOKEN_EXPIRES_MINUTES",
            ("security", "access_token_expires_minutes"),
            int,
        ),
        (
            "SECURITY_REFRESH_TOKEN_EXPIRES_DAYS",
            ("security", "refresh_token_expires_days"),
            int,
        ),
    )

    merged = dict(raw)
    for env_key, path, parser in overrides:
        raw_value = os.getenv(env_key)
        if raw_value is None or raw_value == "":
            continue
        _set_nested(merged, path, parser(raw_value))
    return merged


class AppConfig(BaseModel):
    name: str = "pro-edu-platform"
    version: str = "0.2.0"
    environment: str = "development"
    default_tenant_code: str = "default"
    default_tenant_name: str = "默认租户"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ]
    )


class DatabaseConfig(BaseModel):
    url: str = DEFAULT_MYSQL_URL
    echo: bool = False
    pool_size: int = 10
    max_overflow: int = 20
    auto_migrate: bool = True
    seed_on_startup: bool = True
    migration_target: str = "head"

    @property
    def resolved_url(self) -> str:
        return _normalize_mysql_url(self.url)


class StorageConfig(BaseModel):
    type: str = "local"
    root: str = "./data"

    @property
    def root_path(self) -> Path:
        return _resolve_path(self.root)


class RedisConfig(BaseModel):
    url: str = "redis://127.0.0.1:6379/0"


class CeleryConfig(BaseModel):
    broker_url: str = "redis://127.0.0.1:6379/0"
    result_backend: str = "redis://127.0.0.1:6379/1"


class SecurityConfig(BaseModel):
    secret_key: str = Field(default="dev-only-change-me", validation_alias=AliasChoices("secret_key", "SECRET_KEY"))
    access_token_expires_minutes: int = 60 * 12
    refresh_token_expires_days: int = 14


class OCRCacheSweepConfig(BaseModel):
    enabled: bool = True
    interval_seconds: int = 1800
    run_on_startup: bool = True


class SubjectSeedConfig(BaseModel):
    code: str = Field(validation_alias=AliasChoices("code", "id"))
    name: str
    categories: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    celery: CeleryConfig = Field(default_factory=CeleryConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    ocr_cache_sweep: OCRCacheSweepConfig = Field(default_factory=OCRCacheSweepConfig)
    subjects: list[SubjectSeedConfig] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    _load_dotenv()
    raw: dict[str, Any] = {}
    config_path = PROJECT_ROOT / "config.yaml"
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8-sig")) or {}

    settings = Settings.model_validate(_expand_env(_apply_env_overrides(raw)))
    settings.db.resolved_url
    for env_name in ("PUBLIC_WEB_URL", "PUBLIC_WEB_ORIGIN"):
        raw_origin = os.getenv(env_name)
        if not raw_origin:
            continue
        for item in _parse_csv_list(raw_origin):
            origin = item if "://" in item else f"https://{item}"
            if origin not in settings.app.cors_origins:
                settings.app.cors_origins.append(origin)
    settings.storage.root_path.mkdir(parents=True, exist_ok=True)
    return settings

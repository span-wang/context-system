from __future__ import annotations

import hashlib
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

_MODEL_LIBRARY_FEATURE_LABELS = {
    "generator": "生成模型",
    "reviewer": "审查模型",
    "paper_ai_cleanup": "试卷 AI 切题",
    "question_ai_standardizer": "题目补全与标准化",
    "question_auto_tagger": "题目自动考点标注",
}


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
    disable_thinking: bool = False


class ModelLibraryItemConfig(LLMEndpointConfig):
    id: str
    name: str


class LLMEndpointSelectionConfig(LLMEndpointConfig):
    model_id: str | None = None


class PaperAICleanupConfig(LLMEndpointSelectionConfig):
    enabled: bool = True
    provider: str = "openai_compat"
    model: str = "qwen3.5:9b"
    max_tokens: int = 12000
    base_url: str | None = "http://127.0.0.1:11434/v1"
    disable_thinking: bool = True
    system_prompt: str = (
        "你是严谨的中文试卷 OCR 清噪、切题与结构化助手，只返回 JSON。\n"
        "你的职责不是自由总结，而是把 OCR 文本整理成可直接入库的题目结构。\n"
        "你必须先清噪，再切题，再抽取并标准化题号、题型、题干、选项、答案、解析；若原文未提供答案或解析，可以留空，不要自行解题补全。\n"
        "不要漏题，不要合并多题，不要臆造不存在的信息；输出结果必须是最终切题结果，后续解题会单独处理。\n"
        "输出必须严格符合用户给定的 JSON 结构。"
    )


class QuestionAIStandardizerConfig(LLMEndpointSelectionConfig):
    enabled: bool = True
    provider: str = "openai_compat"
    model: str = "qwen3.5:9b"
    max_tokens: int = 4800
    base_url: str | None = "http://127.0.0.1:11434/v1"
    disable_thinking: bool = True


class QuestionAutoTaggerConfig(LLMEndpointSelectionConfig):
    enabled: bool = True
    provider: str = "openai_compat"
    model: str = "qwen3.5:9b"
    max_tokens: int = 320
    base_url: str | None = "http://127.0.0.1:11434/v1"
    disable_thinking: bool = True


class LLMConfig(BaseModel):
    generator: LLMEndpointSelectionConfig = Field(default_factory=LLMEndpointSelectionConfig)
    reviewer: LLMEndpointSelectionConfig = Field(
        default_factory=lambda: LLMEndpointSelectionConfig(provider="openai_compat", model="deepseek-v4-flash")
    )
    models: list[ModelLibraryItemConfig] = Field(default_factory=list)


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
    paper_ai_cleanup: PaperAICleanupConfig = Field(default_factory=PaperAICleanupConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    db: DBConfig = Field(default_factory=DBConfig)
    ragflow: RAGFlowConfig = Field(default_factory=RAGFlowConfig)
    review: ReviewConfig = Field(default_factory=ReviewConfig)
    question_ai_standardizer: QuestionAIStandardizerConfig = Field(default_factory=QuestionAIStandardizerConfig)
    question_auto_tagger: QuestionAutoTaggerConfig = Field(default_factory=QuestionAutoTaggerConfig)
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
        if "minimax" in base_url:
            candidates.append("MINIMAX_API_KEY")
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
    normalized_raw = _normalize_model_library_config(raw)
    settings = Settings.model_validate(_expand_env(normalized_raw))
    settings = _resolve_selected_models(settings)
    settings.db.resolved_url
    settings.storage.root_path.mkdir(parents=True, exist_ok=True)
    return settings


def _normalize_model_library_config(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(raw)
    llm_raw = dict(normalized.get("llm") or {}) if isinstance(normalized.get("llm"), dict) else {}
    llm_raw["models"] = _normalized_model_library_items(normalized)
    normalized["llm"] = llm_raw
    return normalized


def _normalized_model_library_items(raw: dict[str, Any]) -> list[dict[str, Any]]:
    llm_raw = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
    explicit_models = llm_raw.get("models") if isinstance(llm_raw.get("models"), list) else []
    legacy_presets = llm_raw.get("presets") if isinstance(llm_raw.get("presets"), list) else []
    candidates: list[tuple[dict[str, Any], str | None]] = []
    for item in explicit_models:
        if isinstance(item, dict):
            candidates.append((item, None))
    for item in legacy_presets:
        if isinstance(item, dict):
            candidates.append((item, None))
    for feature_name, label in _MODEL_LIBRARY_FEATURE_LABELS.items():
        feature_raw = _feature_model_candidate(raw, feature_name)
        if feature_raw:
            candidates.append((feature_raw, label))

    normalized_items: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    seen_signatures: set[tuple[str, str, int, str, str]] = set()
    for item, fallback_name in candidates:
        normalized = _normalize_model_library_item(item, fallback_name, used_ids)
        if not normalized:
            continue
        signature = _model_signature(normalized)
        if signature in seen_signatures:
            continue
        normalized_items.append(normalized)
        seen_signatures.add(signature)
    return normalized_items


def _feature_model_candidate(raw: dict[str, Any], feature_name: str) -> dict[str, Any] | None:
    if feature_name in {"generator", "reviewer"}:
        llm_raw = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
        feature_raw = llm_raw.get(feature_name)
    else:
        feature_raw = raw.get(feature_name)
    return dict(feature_raw) if isinstance(feature_raw, dict) else None


def _normalize_model_library_item(
    item: dict[str, Any],
    fallback_name: str | None,
    used_ids: set[str],
) -> dict[str, Any] | None:
    provider = str(item.get("provider") or "").strip()
    model = str(item.get("model") or "").strip()
    if not provider or not model:
        return None

    normalized: dict[str, Any] = {
        "provider": provider,
        "model": model,
        "max_tokens": _safe_int(item.get("max_tokens"), 8192),
    }
    base_url = str(item.get("base_url") or "").strip()
    api_key = str(item.get("api_key") or "").strip()
    if base_url:
        normalized["base_url"] = base_url
    if api_key:
        normalized["api_key"] = api_key

    name = str(item.get("name") or fallback_name or f"{provider} / {model}").strip()
    normalized["name"] = name

    raw_id = str(item.get("id") or "").strip()
    model_id = _unique_model_identifier(raw_id or name, used_ids)
    normalized["id"] = model_id
    return normalized


def _unique_model_identifier(value: str, used_ids: set[str]) -> str:
    base = _model_identifier_base(value)
    candidate = base
    suffix = 2
    while candidate.casefold() in used_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    used_ids.add(candidate.casefold())
    return candidate


def _model_identifier_base(value: str) -> str:
    base = re.sub(r"[^0-9a-zA-Z]+", "_", value.strip()).strip("_").lower()
    if base:
        return base
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    return f"model_{digest}"


def _safe_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _resolve_selected_models(settings: Settings) -> Settings:
    models_by_id = {item.id: item for item in settings.llm.models}
    resolved_llm = settings.llm.model_copy(
        update={
            "generator": _resolve_selected_endpoint(settings.llm.generator, settings.llm.models, models_by_id),
            "reviewer": _resolve_selected_endpoint(settings.llm.reviewer, settings.llm.models, models_by_id),
        }
    )
    return settings.model_copy(
        update={
            "llm": resolved_llm,
            "paper_ai_cleanup": _resolve_selected_endpoint(settings.paper_ai_cleanup, settings.llm.models, models_by_id),
            "question_ai_standardizer": _resolve_selected_endpoint(
                settings.question_ai_standardizer,
                settings.llm.models,
                models_by_id,
            ),
            "question_auto_tagger": _resolve_selected_endpoint(
                settings.question_auto_tagger,
                settings.llm.models,
                models_by_id,
            ),
        }
    )


def _resolve_selected_endpoint(
    endpoint: LLMEndpointSelectionConfig,
    models: list[ModelLibraryItemConfig],
    models_by_id: dict[str, ModelLibraryItemConfig],
) -> LLMEndpointSelectionConfig:
    matched_model = None
    if endpoint.model_id and endpoint.model_id in models_by_id:
        matched_model = models_by_id[endpoint.model_id]
    else:
        matched_model = _find_matching_model(endpoint, models)

    if not matched_model:
        return endpoint

    return endpoint.model_copy(
        update={
            "model_id": matched_model.id,
            "provider": matched_model.provider,
            "model": matched_model.model,
            "max_tokens": matched_model.max_tokens,
            "base_url": matched_model.base_url,
            "api_key": matched_model.api_key,
        }
    )


def _find_matching_model(
    endpoint: LLMEndpointConfig,
    models: list[ModelLibraryItemConfig],
) -> ModelLibraryItemConfig | None:
    signature = _model_signature(
        {
            "provider": endpoint.provider,
            "model": endpoint.model,
            "max_tokens": endpoint.max_tokens,
            "base_url": endpoint.base_url,
            "api_key": endpoint.api_key,
        }
    )
    for item in models:
        if _model_signature(item.model_dump()) == signature:
            return item
    return None


def _model_signature(item: dict[str, Any]) -> tuple[str, str, int, str, str]:
    return (
        str(item.get("provider") or "").strip(),
        str(item.get("model") or "").strip(),
        _safe_int(item.get("max_tokens"), 8192),
        str(item.get("base_url") or "").strip(),
        str(item.get("api_key") or "").strip(),
    )


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

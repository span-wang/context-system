from __future__ import annotations

import hashlib
import re
from typing import Literal

import httpx
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from deps import get_db
from library.parse_options import get_parse_capability_payload
from llm.providers import get_llm_provider
from rag.ragflow import RAGFlowAPIError, RAGFlowProvider
from settings import (
    PROJECT_ROOT,
    LLMEndpointConfig,
    LLMTarget,
    get_settings,
    list_subject_configs,
    resolve_llm_api_key,
)


router = APIRouter(prefix="/api/system", tags=["system"])

SUPPORTED_LLM_PROVIDERS = {"local_template", "local_rules", "openai_compat", "deepseek", "anthropic"}
REMOTE_ONLY_MODEL_TARGETS = {"paper_ai_cleanup", "question_ai_standardizer", "question_auto_tagger"}
MODEL_TARGET_LABELS = {
    "generator": "生成模型",
    "reviewer": "审查模型",
    "paper_ai_cleanup": "试卷 AI 切题",
    "question_ai_standardizer": "题目补全与标准化",
    "question_auto_tagger": "题目自动考点标注",
}


class LLMEndpointUpdate(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    max_tokens: int = Field(ge=1, le=200_000)
    base_url: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False


class LLMModelSelectionUpdate(BaseModel):
    model_id: str = Field(min_length=1)


class LLMConfigUpdate(BaseModel):
    generator: LLMModelSelectionUpdate
    reviewer: LLMModelSelectionUpdate


class PaperAICleanupUpdate(LLMModelSelectionUpdate):
    enabled: bool = True
    disable_thinking: bool = True
    system_prompt: str = Field(min_length=1)


class AIFeatureEndpointUpdate(LLMModelSelectionUpdate):
    enabled: bool = True
    disable_thinking: bool = True


class SystemConfigUpdate(BaseModel):
    llm: LLMConfigUpdate
    paper_ai_cleanup: PaperAICleanupUpdate | None = None
    question_ai_standardizer: AIFeatureEndpointUpdate | None = None
    question_auto_tagger: AIFeatureEndpointUpdate | None = None


class SubjectUpdate(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1)
    categories: list[str] = Field(default_factory=list)


ConfigEndpointTarget = Literal["generator", "reviewer", "paper_ai_cleanup", "question_ai_standardizer", "question_auto_tagger"]


class LLMTestRequest(BaseModel):
    target: ConfigEndpointTarget = "generator"
    live: bool = False


class LLMModelUpdate(LLMEndpointUpdate):
    id: str | None = None
    name: str = Field(min_length=1)


class LLMPresetUpdate(LLMModelUpdate):
    pass


class LLMPresetApplyRequest(BaseModel):
    target: Literal["generator", "reviewer"]


class RAGFlowDataset(BaseModel):
    id: str
    name: str
    description: str | None = None
    document_count: int | None = None
    chunk_count: int | None = None
    token_num: int | None = None
    status: str | None = None
    permission: str | None = None
    embedding_model: str | None = None
    chunk_method: str | None = None
    unstart_count: int | None = None
    running_count: int | None = None
    cancel_count: int | None = None
    done_count: int | None = None
    fail_count: int | None = None


@router.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "name": get_settings().app.name}


@router.get("/parse-capability")
def parse_capability() -> dict:
    return get_parse_capability_payload()


@router.get("/config")
def config() -> dict:
    settings = get_settings()
    public_models = [_public_llm_model(model) for model in settings.llm.models]
    return {
        "app": settings.app.model_dump(),
        "llm": {
            "generator": _public_llm_endpoint(settings.llm.generator, "generator", settings.llm.models),
            "reviewer": _public_llm_endpoint(settings.llm.reviewer, "reviewer", settings.llm.models),
            "models": public_models,
            "presets": public_models,
        },
        "paper_ai_cleanup": _public_paper_ai_cleanup(settings.paper_ai_cleanup, settings.llm.models),
        "question_ai_standardizer": _public_ai_feature_endpoint(settings.question_ai_standardizer, settings.llm.models),
        "question_auto_tagger": _public_ai_feature_endpoint(settings.question_auto_tagger, settings.llm.models),
        "storage": {"type": settings.storage.type},
        "ragflow": {
            "enabled": settings.ragflow.enabled,
            "base_url": settings.ragflow.base_url,
            "has_api_key": bool(settings.ragflow.api_key),
        },
        "subjects": [subject.model_dump() for subject in list_subject_configs()],
    }


@router.post("/config")
def update_config(request: SystemConfigUpdate) -> dict:
    raw = _read_config_file()
    llm_raw = dict(raw.get("llm") or {}) if isinstance(raw.get("llm"), dict) else {}
    models_raw = _current_models_raw(raw)

    _ensure_model_exists(models_raw, request.llm.generator.model_id, "generator")
    _ensure_model_exists(models_raw, request.llm.reviewer.model_id, "reviewer")
    if request.paper_ai_cleanup is not None:
        _ensure_model_exists(models_raw, request.paper_ai_cleanup.model_id, "paper_ai_cleanup")
    if request.question_ai_standardizer is not None:
        _ensure_model_exists(models_raw, request.question_ai_standardizer.model_id, "question_ai_standardizer")
    if request.question_auto_tagger is not None:
        _ensure_model_exists(models_raw, request.question_auto_tagger.model_id, "question_auto_tagger")

    llm_raw["models"] = models_raw
    llm_raw["generator"] = {"model_id": request.llm.generator.model_id.strip()}
    llm_raw["reviewer"] = {"model_id": request.llm.reviewer.model_id.strip()}
    llm_raw.pop("parser", None)
    llm_raw.pop("presets", None)
    raw["llm"] = llm_raw
    if request.paper_ai_cleanup is not None:
        raw["paper_ai_cleanup"] = {
            "model_id": request.paper_ai_cleanup.model_id.strip(),
            "enabled": bool(request.paper_ai_cleanup.enabled),
            "disable_thinking": bool(request.paper_ai_cleanup.disable_thinking),
            "system_prompt": request.paper_ai_cleanup.system_prompt.strip(),
        }
    if request.question_ai_standardizer is not None:
        raw["question_ai_standardizer"] = {
            "model_id": request.question_ai_standardizer.model_id.strip(),
            "enabled": bool(request.question_ai_standardizer.enabled),
            "disable_thinking": bool(request.question_ai_standardizer.disable_thinking),
        }
    if request.question_auto_tagger is not None:
        raw["question_auto_tagger"] = {
            "model_id": request.question_auto_tagger.model_id.strip(),
            "enabled": bool(request.question_auto_tagger.enabled),
            "disable_thinking": bool(request.question_auto_tagger.disable_thinking),
        }
    _write_config_file(raw)
    get_settings.cache_clear()
    return config()


@router.post("/subjects")
def upsert_subject(request: SubjectUpdate) -> dict:
    subject_name = request.name.strip()
    if not subject_name:
        raise HTTPException(status_code=422, detail="subject name is required")

    raw = _read_config_file()
    subjects_raw = raw.get("subjects") if isinstance(raw.get("subjects"), list) else []
    categories = _clean_string_list(request.categories)

    requested_id = request.id.strip() if request.id else ""
    normalized_name = subject_name.casefold()
    normalized_id = (requested_id or _subject_id_base(subject_name)).casefold()
    replaced = False
    next_subjects = []
    rename_pairs: list[tuple[str, str]] = []
    existing_ids = {
        str(item.get("id", "")).strip().casefold()
        for item in subjects_raw
        if isinstance(item, dict)
    }

    for item in subjects_raw:
        if not isinstance(item, dict):
            continue
        current_name = str(item.get("name", "")).strip()
        current_id = str(item.get("id", "")).strip()
        is_match = current_name.casefold() == normalized_name or current_id.casefold() == normalized_id
        if is_match:
            if current_name:
                rename_pairs.append((current_name, subject_name))
            next_subjects.append(
                {
                    "id": current_id or requested_id or _unique_subject_id(subject_name, existing_ids),
                    "name": subject_name,
                    "categories": categories,
                }
            )
            replaced = True
        else:
            next_subjects.append(item)

    if not replaced:
        subject_id = requested_id or _unique_subject_id(subject_name, existing_ids)
        next_subjects.append({"id": subject_id, "name": subject_name, "categories": categories})

    raw["subjects"] = next_subjects
    _write_config_file(raw)
    for old_subject, new_subject in rename_pairs:
        get_db().rename_library_subject(old_subject, new_subject)
    get_settings.cache_clear()
    return config()


@router.post("/llm-models")
def upsert_llm_model(request: LLMModelUpdate) -> dict:
    _ensure_supported_provider(request.provider)
    raw = _read_config_file()
    llm_raw = dict(raw.get("llm") or {}) if isinstance(raw.get("llm"), dict) else {}
    models_raw = _current_models_raw(raw)
    normalized_name = request.name.strip()
    requested_id = request.id.strip() if request.id else ""

    match_index = _find_model_index(models_raw, requested_id, normalized_name)
    existing_ids = {
        str(item.get("id", "")).strip().casefold()
        for item in models_raw
        if isinstance(item, dict)
    }
    if any(
        _model_name(item) == normalized_name.casefold()
        and (
            match_index is None
            or index != match_index
        )
        for index, item in enumerate(models_raw)
    ):
        raise HTTPException(status_code=409, detail=f"模型名称已存在：{normalized_name}")

    if match_index is not None:
        current = dict(models_raw[match_index])
        next_model = _merge_llm_endpoint(current, request)
        next_model["id"] = str(current.get("id") or requested_id or _unique_model_id(normalized_name, existing_ids)).strip()
        next_model["name"] = normalized_name
        models_raw[match_index] = next_model
    else:
        next_model = _merge_llm_endpoint({}, request)
        next_model["id"] = requested_id or _unique_model_id(normalized_name, existing_ids)
        next_model["name"] = normalized_name
        models_raw.append(next_model)

    llm_raw["models"] = models_raw
    llm_raw.pop("presets", None)
    raw["llm"] = llm_raw
    _write_config_file(raw)
    get_settings.cache_clear()
    return config()


@router.delete("/llm-models/{model_id}")
def delete_llm_model(model_id: str) -> dict:
    raw = _read_config_file()
    llm_raw = dict(raw.get("llm") or {}) if isinstance(raw.get("llm"), dict) else {}
    models_raw = _current_models_raw(raw)
    normalized_id = model_id.strip()
    usage_targets = _model_usage_targets(raw, normalized_id)
    if usage_targets:
        raise HTTPException(
            status_code=409,
            detail=f"模型正在被使用：{', '.join(MODEL_TARGET_LABELS[target] for target in usage_targets)}",
        )

    next_models = [
        item
        for item in models_raw
        if not (isinstance(item, dict) and str(item.get("id", "")).strip() == normalized_id)
    ]
    if len(next_models) == len(models_raw):
        raise HTTPException(status_code=404, detail=f"llm model not found: {model_id}")

    llm_raw["models"] = next_models
    llm_raw.pop("presets", None)
    raw["llm"] = llm_raw
    _write_config_file(raw)
    get_settings.cache_clear()
    return config()


@router.post("/llm-presets")
def upsert_llm_preset(request: LLMPresetUpdate) -> dict:
    return upsert_llm_model(request)


@router.post("/llm-presets/{preset_name}/apply")
def apply_llm_preset(preset_name: str, request: LLMPresetApplyRequest) -> dict:
    raw = _read_config_file()
    llm_raw = dict(raw.get("llm") or {}) if isinstance(raw.get("llm"), dict) else {}
    models_raw = _current_models_raw(raw)
    match = next(
        (
            item
            for item in models_raw
            if isinstance(item, dict) and str(item.get("name", "")).strip() == preset_name.strip()
        ),
        None,
    )
    if not match:
        raise HTTPException(status_code=404, detail=f"llm preset not found: {preset_name}")

    _ensure_model_supported_for_target(match, request.target)
    llm_raw["models"] = models_raw
    llm_raw[request.target] = {"model_id": str(match.get("id", "")).strip()}
    llm_raw.pop("presets", None)
    raw["llm"] = llm_raw
    _write_config_file(raw)
    get_settings.cache_clear()
    return config()


@router.delete("/llm-presets/{preset_name}")
def delete_llm_preset(preset_name: str) -> dict:
    raw = _read_config_file()
    models_raw = _current_models_raw(raw)
    match = next(
        (
            item
            for item in models_raw
            if isinstance(item, dict) and str(item.get("name", "")).strip() == preset_name.strip()
        ),
        None,
    )
    if not match:
        raise HTTPException(status_code=404, detail=f"llm preset not found: {preset_name}")
    return delete_llm_model(str(match.get("id", "")).strip())


@router.post("/test-llm")
async def test_llm(request: LLMTestRequest | None = None) -> dict:
    settings = get_settings()
    target = request.target if request else "generator"
    endpoint = _endpoint_for_test_target(settings, target)
    key_target: LLMTarget | None = target if target in {"generator", "reviewer"} else "reviewer"
    has_key = _has_llm_api_key(endpoint, key_target)

    if getattr(endpoint, "enabled", True) is False:
        return {
            "ok": False,
            "provider": endpoint.provider,
            "model": endpoint.model,
            "message": "该功能当前已关闭",
        }

    if endpoint.provider in {"local_template", "local_rules"}:
        return {
            "ok": True,
            "provider": endpoint.provider,
            "model": endpoint.model,
            "message": "local provider is available",
        }

    if endpoint.provider in {"openai_compat", "deepseek"}:
        if not has_key:
            return {
                "ok": False,
                "provider": endpoint.provider,
                "model": endpoint.model,
                "message": "provider api key or endpoint api_key is not configured; set it in /settings, .env.local/.env/.evn, or config.yaml",
            }
        if request and request.live:
            return await _live_llm_test(endpoint, key_target)
        return {
            "ok": True,
            "provider": endpoint.provider,
            "model": endpoint.model,
            "message": "在线模型凭据已配置",
        }

    if endpoint.provider == "anthropic":
        if not has_key:
            return {
                "ok": False,
                "provider": endpoint.provider,
                "model": endpoint.model,
                "message": "ANTHROPIC_API_KEY or endpoint api_key is not configured",
            }
        if request and request.live:
            return await _live_llm_test(endpoint, key_target)
        return {
            "ok": True,
            "provider": endpoint.provider,
            "model": endpoint.model,
            "message": "Anthropic credentials are configured",
        }

    return {
        "ok": False,
        "provider": endpoint.provider,
        "model": endpoint.model,
        "message": "unsupported provider",
    }


@router.post("/test-ragflow")
async def test_ragflow() -> dict:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{settings.ragflow.base_url.rstrip('/')}/")
        return {"ok": response.status_code < 500, "status_code": response.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/ragflow/datasets")
async def list_ragflow_datasets() -> dict:
    settings = get_settings()
    try:
        payload = await RAGFlowProvider(settings.ragflow).list_datasets()
    except RAGFlowAPIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"拉取 RAGFlow dataset 清单失败：{exc}") from exc

    datasets = [RAGFlowDataset.model_validate(item).model_dump() for item in payload["datasets"]]
    return {"datasets": datasets, "total": payload["total"]}


async def _live_llm_test(endpoint: LLMEndpointConfig, target: LLMTarget) -> dict:
    try:
        text = await get_llm_provider(endpoint, target=target).chat(
            [
                {"role": "system", "content": "只回复 OK。"},
                {"role": "user", "content": "测试连通性"},
            ],
            max_tokens=16,
        )
        return {
            "ok": True,
            "provider": endpoint.provider,
            "model": endpoint.model,
            "message": f"live test passed: {text.strip()[:40] or 'OK'}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": endpoint.provider,
            "model": endpoint.model,
            "message": str(exc),
        }


def _endpoint_for_test_target(settings: object, target: ConfigEndpointTarget) -> LLMEndpointConfig:
    if target == "generator":
        return settings.llm.generator
    if target == "reviewer":
        return settings.llm.reviewer
    if target == "paper_ai_cleanup":
        return settings.paper_ai_cleanup
    if target == "question_ai_standardizer":
        return settings.question_ai_standardizer
    if target == "question_auto_tagger":
        return settings.question_auto_tagger
    raise HTTPException(status_code=422, detail=f"unsupported llm target: {target}")


def _public_llm_endpoint(
    endpoint: LLMEndpointConfig,
    target: LLMTarget | None = None,
    models: list[LLMEndpointConfig] | None = None,
) -> dict:
    data = endpoint.model_dump(exclude={"api_key", "disable_thinking"})
    data["has_api_key"] = _has_llm_api_key(endpoint, target)
    matched_model = _match_public_model(endpoint, models)
    if matched_model is not None:
        data["model_id"] = str(getattr(matched_model, "id", "") or "")
        data["model_name"] = str(getattr(matched_model, "name", "") or "")
    return data


def _public_llm_model(model: LLMEndpointConfig) -> dict:
    data = model.model_dump(exclude={"api_key", "disable_thinking"})
    data["has_api_key"] = _has_any_llm_api_key(model)
    data["id"] = str(getattr(model, "id", "") or "")
    data["name"] = str(getattr(model, "name", "") or "")
    return data


def _public_paper_ai_cleanup(endpoint: LLMEndpointConfig, models: list[LLMEndpointConfig] | None = None) -> dict:
    data = _public_llm_endpoint(endpoint, "reviewer", models)
    data["enabled"] = bool(getattr(endpoint, "enabled", True))
    data["disable_thinking"] = bool(getattr(endpoint, "disable_thinking", True))
    data["system_prompt"] = str(getattr(endpoint, "system_prompt", "") or "")
    return data


def _public_ai_feature_endpoint(endpoint: LLMEndpointConfig, models: list[LLMEndpointConfig] | None = None) -> dict:
    data = _public_llm_endpoint(endpoint, "reviewer", models)
    data["enabled"] = bool(getattr(endpoint, "enabled", True))
    data["disable_thinking"] = bool(getattr(endpoint, "disable_thinking", True))
    return data


def _has_llm_api_key(endpoint: LLMEndpointConfig, target: LLMTarget | None = None) -> bool:
    return bool(resolve_llm_api_key(endpoint, target))


def _has_any_llm_api_key(endpoint: LLMEndpointConfig) -> bool:
    if endpoint.api_key:
        return True
    return any(_has_llm_api_key(endpoint, target) for target in ("generator", "reviewer", None))


def _ensure_supported_provider(provider: str) -> None:
    if provider.strip() not in SUPPORTED_LLM_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"unsupported llm provider: {provider}")


def _config_path():
    return PROJECT_ROOT / "config.yaml"


def _read_config_file() -> dict:
    path = _config_path()
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}


def _write_config_file(raw: dict) -> None:
    _config_path().write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def _clean_string_list(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        key = item.casefold()
        if item and key not in seen:
            cleaned.append(item)
            seen.add(key)
    return cleaned


def _subject_id_base(name: str) -> str:
    base = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip()).strip("_").lower()
    if base:
        return base
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    return f"subject_{digest}"


def _unique_subject_id(name: str, existing_ids: set[str]) -> str:
    base = _subject_id_base(name)
    candidate = base
    suffix = 2
    while candidate.casefold() in existing_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    existing_ids.add(candidate.casefold())
    return candidate


def _model_id_base(name: str) -> str:
    base = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip()).strip("_").lower()
    if base:
        return base
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
    return f"model_{digest}"


def _unique_model_id(name: str, existing_ids: set[str]) -> str:
    base = _model_id_base(name)
    candidate = base
    suffix = 2
    while candidate.casefold() in existing_ids:
        candidate = f"{base}_{suffix}"
        suffix += 1
    existing_ids.add(candidate.casefold())
    return candidate


def _safe_int(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _current_models_raw(raw: dict) -> list[dict]:
    llm_raw = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
    explicit_models = llm_raw.get("models") if isinstance(llm_raw.get("models"), list) else []
    legacy_presets = llm_raw.get("presets") if isinstance(llm_raw.get("presets"), list) else []
    candidates: list[tuple[dict, str | None]] = []
    for item in explicit_models:
        if isinstance(item, dict):
            candidates.append((item, None))
    for item in legacy_presets:
        if isinstance(item, dict):
            candidates.append((item, None))
    for target in MODEL_TARGET_LABELS:
        feature_raw = _feature_model_candidate(raw, target)
        if feature_raw:
            candidates.append((feature_raw, MODEL_TARGET_LABELS[target]))

    models: list[dict] = []
    used_ids: set[str] = set()
    seen_signatures: set[tuple[str, str, int, str, str]] = set()
    for item, fallback_name in candidates:
        normalized = _normalize_model_raw_item(item, fallback_name, used_ids)
        if not normalized:
            continue
        signature = _model_signature(normalized)
        if signature in seen_signatures:
            continue
        models.append(normalized)
        seen_signatures.add(signature)
    return models


def _feature_model_candidate(raw: dict, target: str) -> dict | None:
    if target in {"generator", "reviewer"}:
        llm_raw = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
        feature_raw = llm_raw.get(target)
    else:
        feature_raw = raw.get(target)
    return dict(feature_raw) if isinstance(feature_raw, dict) else None


def _normalize_model_raw_item(item: dict, fallback_name: str | None, used_ids: set[str]) -> dict | None:
    provider = str(item.get("provider") or "").strip()
    model = str(item.get("model") or "").strip()
    if not provider or not model:
        return None

    normalized = {
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

    normalized["name"] = str(item.get("name") or fallback_name or f"{provider} / {model}").strip()
    raw_id = str(item.get("id") or "").strip()
    normalized["id"] = _unique_model_id(raw_id or normalized["name"], used_ids)
    return normalized


def _model_signature(item: dict) -> tuple[str, str, int, str, str]:
    return (
        str(item.get("provider") or "").strip(),
        str(item.get("model") or "").strip(),
        _safe_int(item.get("max_tokens"), 8192),
        str(item.get("base_url") or "").strip(),
        str(item.get("api_key") or "").strip(),
    )


def _find_model_index(models_raw: list[dict], model_id: str, model_name: str) -> int | None:
    normalized_id = model_id.casefold()
    normalized_name = model_name.casefold()
    for index, item in enumerate(models_raw):
        current_id = str(item.get("id", "")).strip().casefold()
        current_name = _model_name(item)
        if normalized_id and current_id == normalized_id:
            return index
        if not normalized_id and current_name == normalized_name:
            return index
    return None


def _model_name(item: dict) -> str:
    return str(item.get("name", "")).strip().casefold()


def _ensure_model_exists(models_raw: list[dict], model_id: str, target: ConfigEndpointTarget) -> None:
    model = _find_model_by_id(models_raw, model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"{MODEL_TARGET_LABELS[target]}未找到所选模型：{model_id}")
    _ensure_model_supported_for_target(model, target)


def _ensure_model_supported_for_target(model: dict, target: ConfigEndpointTarget) -> None:
    if target in REMOTE_ONLY_MODEL_TARGETS and str(model.get("provider", "")).strip() in {"local_template", "local_rules"}:
        raise HTTPException(status_code=422, detail=f"{MODEL_TARGET_LABELS[target]}不支持本地模板/本地规则")


def _find_model_by_id(models_raw: list[dict], model_id: str) -> dict | None:
    normalized_id = model_id.strip()
    for item in models_raw:
        if isinstance(item, dict) and str(item.get("id", "")).strip() == normalized_id:
            return item
    return None


def _model_usage_targets(raw: dict, model_id: str) -> list[ConfigEndpointTarget]:
    normalized_id = model_id.strip()
    targets: list[ConfigEndpointTarget] = []
    llm_raw = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
    for target in ("generator", "reviewer"):
        feature_raw = llm_raw.get(target) if isinstance(llm_raw.get(target), dict) else {}
        if str(feature_raw.get("model_id", "")).strip() == normalized_id:
            targets.append(target)
    for target in ("paper_ai_cleanup", "question_ai_standardizer", "question_auto_tagger"):
        feature_raw = raw.get(target) if isinstance(raw.get(target), dict) else {}
        if str(feature_raw.get("model_id", "")).strip() == normalized_id:
            targets.append(target)
    return targets


def _match_public_model(endpoint: LLMEndpointConfig, models: list[LLMEndpointConfig] | None) -> LLMEndpointConfig | None:
    if not models:
        return None
    endpoint_model_id = str(getattr(endpoint, "model_id", "") or "").strip()
    if endpoint_model_id:
        for model in models:
            if str(getattr(model, "id", "") or "").strip() == endpoint_model_id:
                return model
    endpoint_signature = _model_signature(
        {
            "provider": endpoint.provider,
            "model": endpoint.model,
            "max_tokens": endpoint.max_tokens,
            "base_url": endpoint.base_url,
            "api_key": endpoint.api_key,
        }
    )
    for model in models:
        if _model_signature(model.model_dump()) == endpoint_signature:
            return model
    return None


def _merge_llm_endpoint(previous: dict, update: LLMEndpointUpdate) -> dict:
    merged = dict(previous)
    merged["provider"] = update.provider.strip()
    merged["model"] = update.model.strip()
    merged["max_tokens"] = update.max_tokens

    base_url = update.base_url.strip() if update.base_url else ""
    if base_url:
        merged["base_url"] = base_url
    else:
        merged.pop("base_url", None)

    api_key = update.api_key.strip() if update.api_key else ""
    if update.clear_api_key:
        merged.pop("api_key", None)
    elif api_key:
        merged["api_key"] = api_key

    return merged

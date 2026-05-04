from __future__ import annotations

import os
import hashlib
import re
from typing import Literal

import httpx
import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from llm.providers import get_llm_provider
from settings import PROJECT_ROOT, LLMEndpointConfig, get_settings


router = APIRouter(prefix="/api/system", tags=["system"])

SUPPORTED_LLM_PROVIDERS = {"local_template", "local_rules", "openai_compat", "deepseek", "anthropic"}
PROVIDER_ENV_KEYS = {
    "openai_compat": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


class LLMEndpointUpdate(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    max_tokens: int = Field(ge=1, le=200_000)
    base_url: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False


class LLMConfigUpdate(BaseModel):
    generator: LLMEndpointUpdate
    reviewer: LLMEndpointUpdate


class SystemConfigUpdate(BaseModel):
    llm: LLMConfigUpdate


class SubjectUpdate(BaseModel):
    name: str = Field(min_length=1)
    categories: list[str] = Field(default_factory=list)


class LLMTestRequest(BaseModel):
    target: Literal["generator", "reviewer"] = "generator"
    live: bool = False


class LLMPresetUpdate(LLMEndpointUpdate):
    name: str = Field(min_length=1)


class LLMPresetApplyRequest(BaseModel):
    target: Literal["generator", "reviewer"]


@router.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "name": get_settings().app.name}


@router.get("/config")
def config() -> dict:
    settings = get_settings()
    return {
        "app": settings.app.model_dump(),
        "llm": {
            "generator": _public_llm_endpoint(settings.llm.generator),
            "reviewer": _public_llm_endpoint(settings.llm.reviewer),
            "presets": [_public_llm_preset(preset) for preset in settings.llm.presets],
        },
        "storage": {"type": settings.storage.type},
        "ragflow": {
            "enabled": settings.ragflow.enabled,
            "base_url": settings.ragflow.base_url,
            "has_api_key": bool(settings.ragflow.api_key),
        },
        "subjects": [subject.model_dump() for subject in settings.subjects],
    }


@router.post("/config")
def update_config(request: SystemConfigUpdate) -> dict:
    _ensure_supported_provider(request.llm.generator.provider)
    _ensure_supported_provider(request.llm.reviewer.provider)

    raw = _read_config_file()
    llm_raw = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
    generator_raw = llm_raw.get("generator") if isinstance(llm_raw.get("generator"), dict) else {}
    reviewer_raw = llm_raw.get("reviewer") if isinstance(llm_raw.get("reviewer"), dict) else {}

    llm_raw["generator"] = _merge_llm_endpoint(generator_raw, request.llm.generator)
    llm_raw["reviewer"] = _merge_llm_endpoint(reviewer_raw, request.llm.reviewer)
    raw["llm"] = llm_raw
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

    normalized_name = subject_name.casefold()
    normalized_id = _subject_id_base(subject_name).casefold()
    replaced = False
    next_subjects = []
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
            current_categories = _clean_string_list(item.get("categories", []))
            next_subjects.append(
                {
                    "id": current_id or _unique_subject_id(subject_name, existing_ids),
                    "name": subject_name,
                    "categories": _clean_string_list([*current_categories, *categories]),
                }
            )
            replaced = True
        else:
            next_subjects.append(item)

    if not replaced:
        subject_id = _unique_subject_id(subject_name, existing_ids)
        next_subjects.append({"id": subject_id, "name": subject_name, "categories": categories})

    raw["subjects"] = next_subjects
    _write_config_file(raw)
    get_settings.cache_clear()
    return config()


@router.post("/llm-presets")
def upsert_llm_preset(request: LLMPresetUpdate) -> dict:
    _ensure_supported_provider(request.provider)
    raw = _read_config_file()
    llm_raw = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
    presets_raw = llm_raw.get("presets") if isinstance(llm_raw.get("presets"), list) else []

    normalized_name = request.name.strip()
    next_preset = _merge_llm_endpoint({}, request)
    next_preset["name"] = normalized_name

    replaced = False
    merged_presets = []
    for item in presets_raw:
        if not isinstance(item, dict):
            continue
        if str(item.get("name", "")).strip() == normalized_name:
            merged_presets.append(next_preset)
            replaced = True
        else:
            merged_presets.append(item)
    if not replaced:
        merged_presets.append(next_preset)

    llm_raw["presets"] = merged_presets
    raw["llm"] = llm_raw
    _write_config_file(raw)
    get_settings.cache_clear()
    return config()


@router.post("/llm-presets/{preset_name}/apply")
def apply_llm_preset(preset_name: str, request: LLMPresetApplyRequest) -> dict:
    raw = _read_config_file()
    llm_raw = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
    presets_raw = llm_raw.get("presets") if isinstance(llm_raw.get("presets"), list) else []
    match = None
    for item in presets_raw:
        if isinstance(item, dict) and str(item.get("name", "")).strip() == preset_name.strip():
            match = dict(item)
            break
    if not match:
        raise HTTPException(status_code=404, detail=f"llm preset not found: {preset_name}")

    match.pop("name", None)
    current_raw = llm_raw.get(request.target) if isinstance(llm_raw.get(request.target), dict) else {}
    llm_raw[request.target] = _merge_endpoint_dict(current_raw, match)
    raw["llm"] = llm_raw
    _write_config_file(raw)
    get_settings.cache_clear()
    return config()


@router.delete("/llm-presets/{preset_name}")
def delete_llm_preset(preset_name: str) -> dict:
    raw = _read_config_file()
    llm_raw = raw.get("llm") if isinstance(raw.get("llm"), dict) else {}
    presets_raw = llm_raw.get("presets") if isinstance(llm_raw.get("presets"), list) else []
    llm_raw["presets"] = [
        item for item in presets_raw if not (isinstance(item, dict) and str(item.get("name", "")).strip() == preset_name.strip())
    ]
    raw["llm"] = llm_raw
    _write_config_file(raw)
    get_settings.cache_clear()
    return config()


@router.post("/test-llm")
async def test_llm(request: LLMTestRequest | None = None) -> dict:
    settings = get_settings()
    target = request.target if request else "generator"
    endpoint = getattr(settings.llm, target)
    has_key = _has_llm_api_key(endpoint)

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
                "message": "provider api key or endpoint api_key is not configured",
            }
        if request and request.live:
            return await _live_llm_test(endpoint)
        return {
            "ok": True,
            "provider": endpoint.provider,
            "model": endpoint.model,
            "message": "OpenAI-compatible credentials are configured",
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
            return await _live_llm_test(endpoint)
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


async def _live_llm_test(endpoint: LLMEndpointConfig) -> dict:
    try:
        text = await get_llm_provider(endpoint).chat(
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


def _public_llm_endpoint(endpoint: LLMEndpointConfig) -> dict:
    data = endpoint.model_dump(exclude={"api_key"})
    data["has_api_key"] = _has_llm_api_key(endpoint)
    return data


def _public_llm_preset(preset: LLMEndpointConfig) -> dict:
    data = _public_llm_endpoint(preset)
    data["name"] = getattr(preset, "name", "")
    return data


def _has_llm_api_key(endpoint: LLMEndpointConfig) -> bool:
    env_key = PROVIDER_ENV_KEYS.get(endpoint.provider)
    return bool(endpoint.api_key) or bool(env_key and os.getenv(env_key))


def _ensure_supported_provider(provider: str) -> None:
    if provider.strip() not in SUPPORTED_LLM_PROVIDERS:
        raise HTTPException(status_code=422, detail=f"unsupported llm provider: {provider}")


def _config_path():
    return PROJECT_ROOT / "config.yaml"


def _read_config_file() -> dict:
    path = _config_path()
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


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


def _merge_endpoint_dict(previous: dict, payload: dict) -> dict:
    merged = dict(previous)
    for key in ("provider", "model", "max_tokens", "base_url", "api_key"):
        if key in payload:
            value = payload.get(key)
            if value in (None, "") and key in {"base_url", "api_key"}:
                merged.pop(key, None)
            else:
                merged[key] = value
    return merged

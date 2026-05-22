from __future__ import annotations

import asyncio
import json
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any

from llm.providers import get_llm_provider
from settings import LLMEndpointConfig
from settings import get_settings as get_llm_settings
from app.services.paper_review_ai import normalize_analysis


DEFAULT_LOCAL_AI_CLEANUP_MODEL = "qwen3.5:9b"
DEFAULT_LOCAL_AI_CLEANUP_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_AI_CLEANUP_CHUNK_CHARS = 16000
DEFAULT_AI_CLEANUP_MAX_TOKENS = 12000
_QUESTION_START_PATTERN = re.compile(
    r"(?m)^\s*(?:#+\s*)?(?:第\s*)?(?:[0-9]{1,3}|[一二三四五六七八九十百]{1,6})\s*(?:题|[\.、．)])\s*"
)
_TEXT_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
_DEFAULT_SYSTEM_PROMPT = (
    "你是严谨的中文试卷 OCR 清噪、切题与结构化助手，只返回 JSON。"
    "你的职责不是自由总结，而是把 OCR 文本整理成可直接入库的题目结构。"
    "你必须先清噪，再切题，再抽取并标准化题号、题型、题干、选项、答案、解析；"
    "若原文未提供答案或解析，可以留空，不要自行解题补全。不要输出无关文字。"
)


@dataclass(slots=True)
class PaperAICleanupResult:
    ai_source_text: str
    ai_sections: list[dict[str, Any]] = field(default_factory=list)
    ai_prediction: dict[str, Any] = field(default_factory=dict)
    debug_payload: dict[str, Any] = field(default_factory=dict)
    used_ai: bool = False
    model: str | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)
    cleanup_report: dict[str, Any] = field(default_factory=dict)


def clean_and_structure_paper_source(
    source_text: str,
    *,
    raw_source_text: str | None = None,
    paper_name: str | None = None,
    subject_name: str | None = None,
    category_name: str | None = None,
) -> PaperAICleanupResult:
    normalized_source = _normalize_source_text(source_text)
    if not normalized_source:
        return PaperAICleanupResult(ai_source_text="", warnings=["AI 清噪跳过：源文本为空"])
    endpoint = _local_ai_cleanup_endpoint()
    if not _env_bool("PAPER_AI_CLEANUP_ENABLED", bool(getattr(endpoint, "enabled", True))):
        return PaperAICleanupResult(
            ai_source_text=normalized_source,
            warnings=["AI 清噪已关闭"],
            cleanup_report={"fallback": "disabled"},
        )

    try:
        provider = get_llm_provider(endpoint, target="reviewer")
    except Exception as exc:
        return PaperAICleanupResult(
            ai_source_text=normalized_source,
            model=endpoint.model,
            error=str(exc)[:200],
            warnings=[f"AI 清噪不可用，已回退 source.txt：{str(exc)[:120]}"],
            cleanup_report={"fallback": "provider_unavailable"},
        )

    chunks = _split_cleanup_chunks(normalized_source, _env_int("PAPER_AI_CLEANUP_CHUNK_CHARS", DEFAULT_AI_CLEANUP_CHUNK_CHARS))
    cleaned_chunks: list[str] = []
    ai_sections: list[dict[str, Any]] = []
    ai_prediction_sections: list[dict[str, Any]] = []
    debug_chunks: list[dict[str, Any]] = []
    warnings: list[str] = []
    used_chunk_count = 0
    first_error: str | None = None
    for index, chunk in enumerate(chunks, start=1):
        try:
            payload = _run_async(
                _request_ai_cleanup(
                    provider,
                    chunk,
                    endpoint=endpoint,
                    paper_name=paper_name,
                    subject_name=subject_name,
                    category_name=category_name,
                    chunk_index=index,
                    chunk_count=len(chunks),
                )
            )
            cleaned = _normalize_ai_text(str(payload.get("clean_text") or ""))
            prediction_document = _normalize_ai_prediction_document(payload.get("prediction"))
            if not prediction_document.get("sections"):
                prediction_document = build_prediction_from_ai_sections(_normalize_ai_prediction_sections(payload.get("sections")))
            section_payloads = _normalize_ai_sections_payload(payload.get("prediction") or payload.get("sections"))
            rebuilt_cleaned = _build_clean_text_from_section_payloads(section_payloads)
            chunk_warnings = payload.get("warnings")
            if isinstance(chunk_warnings, list):
                warnings.extend(str(item).strip() for item in chunk_warnings if str(item).strip())
            if not cleaned and rebuilt_cleaned:
                cleaned = rebuilt_cleaned
                warnings.append(f"AI 清噪第 {index}/{len(chunks)} 段未返回 clean_text，已根据 prediction 重建文本")
            elif (
                rebuilt_cleaned
                and rebuilt_cleaned != cleaned
                and not _passes_quality_gate(chunk, cleaned)
                and _passes_quality_gate(chunk, rebuilt_cleaned)
            ):
                cleaned = rebuilt_cleaned
                warnings.append(f"AI 清噪第 {index}/{len(chunks)} 段 clean_text 未通过校验，已改用 prediction 重建文本")
            if not _passes_quality_gate(chunk, cleaned):
                raise ValueError("AI 清噪结果未通过长度或题号保留校验")
            cleaned_chunks.append(cleaned)
            ai_sections.extend(section_payloads)
            ai_prediction_sections.extend(prediction_document.get("sections") or [])
            debug_chunks.append(
                {
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                    "input_text": chunk,
                    "parsed_payload": payload,
                    "normalized_clean_text": cleaned,
                    "normalized_section_count": len(section_payloads),
                    "normalized_question_count": sum(len(section.get("questions") or []) for section in (prediction_document.get("sections") or [])),
                    "error": None,
                }
            )
            used_chunk_count += 1
        except Exception as exc:
            first_error = first_error or str(exc)[:200]
            warnings.append(f"AI 清噪第 {index}/{len(chunks)} 段失败，已回退规则清噪：{str(exc)[:120]}")
            cleaned_chunks.append(chunk)
            debug_chunks.append(
                {
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                    "input_text": chunk,
                    "parsed_payload": None,
                    "normalized_clean_text": chunk,
                    "normalized_section_count": 0,
                    "normalized_question_count": 0,
                    "error": str(exc),
                }
            )

    ai_source = _normalize_source_text("\n\n".join(part for part in cleaned_chunks if part))
    if not ai_source:
        ai_source = normalized_source
    used_ai = used_chunk_count > 0
    report = {
        "source": "ai_source.txt" if used_ai else "source.txt",
        "model": endpoint.model,
        "disable_thinking": bool(getattr(endpoint, "disable_thinking", True)),
        "ai_section_count": len(ai_sections),
        "ai_question_count": sum(len(section.get("questions") or []) for section in ai_prediction_sections),
        "chunk_count": len(chunks),
        "used_chunk_count": used_chunk_count,
        "input_chars": len(normalized_source),
        "output_chars": len(ai_source),
        "raw_source_chars": len(raw_source_text or ""),
        "fallback_chunk_count": max(0, len(chunks) - used_chunk_count),
    }
    return PaperAICleanupResult(
        ai_source_text=ai_source,
        ai_sections=ai_sections,
        ai_prediction=build_prediction_from_ai_sections(ai_prediction_sections),
        debug_payload={
            "model": endpoint.model,
            "system_prompt": system_prompt_preview(endpoint),
            "chunk_count": len(chunks),
            "chunks": debug_chunks,
        },
        used_ai=used_ai,
        model=endpoint.model,
        error=first_error if used_chunk_count < len(chunks) else None,
        warnings=warnings[:20],
        cleanup_report=report,
    )


async def _request_ai_cleanup(
    provider: Any,
    text: str,
    *,
    endpoint: LLMEndpointConfig,
    paper_name: str | None,
    subject_name: str | None,
    category_name: str | None,
    chunk_index: int,
    chunk_count: int,
) -> dict[str, Any]:
    system_prompt = str(getattr(endpoint, "system_prompt", "") or _DEFAULT_SYSTEM_PROMPT)
    prompt = (
        "请对下面的中文试卷 OCR 文本做二次清噪、切题、抽取与标准化，直接输出可入库的结构化结果。\n"
        "要求：\n"
        "1. 删除页眉、页脚、页码、水印、版权、公众号、二维码、广告、重复残片和明显乱码。\n"
        "2. 修复错误换行，保持阅读顺序；按大题标题、题号、题干、选项、答案、解析组织文本。\n"
        "3. 保留原题信息，不要漏题，不要合并多题，不要擅自改题；只整理原文已有答案与解析，原文缺失时保持留空，不要自行解题补全。\n"
        "4. 保留公式、数字、金额、日期、选项字母和图片引用；含 <img> 或 imgs/ 的引用必须原样保留。\n"
        "5. 每道题尽量使用独立块：题号行、题干、选项行、答案行、解析行。\n"
        "6. 同时完成切题，并输出 `prediction` 对象；该对象必须与系统当前 `prediction.json` 结构保持一致，并且内容就是当前抽取后的最终切题结果。\n"
        "7. `prediction` 必须包含：`version`、`source_format`、`section_count`、`question_count`、`sections`。\n"
        "8. `sections[]` 必须包含：`title`、`section_type`、`sort_order`、`question_count`、`questions`。\n"
        "9. 普通独立题使用 `node_role=standalone`；材料题、案例题、英语阅读这类一个大题下多个小题的，必须输出一个 `node_role=group` 的父题，并把小问放进 `subquestions[]`。\n"
        "10. 题组父题必须尽量拆出 `group_stem` 和 `material_text`；子问只保留自己的 `stem_text`、`options`、`answer_text`、`analysis_text`，不要把整段材料重复塞进每个子问。\n"
        "11. `questions[]` 必须包含：`order`、`question_no`、`question_type`、`node_role`、`stem_text`、`options`、`answer_text`、`analysis_text`、`subquestion_count`、`quality_score`、`quality_issues`；题组父题额外输出 `group_stem`、`material_text`、`subquestions`。\n"
        "12. 题型使用以下英文值：single_choice、multiple_choice、judge、fill_blank、short_answer、calculation、case_analysis、composite、material_analysis、mixed。\n"
        "13. 客观题若原文已有答案，只返回选项字母；判断题返回“正确”或“错误”；原文缺失则留空。\n"
        "14. 若原文未提供答案或解析，可留空字符串；不要基于题干、选项或材料自行推导并补全。\n"
        "15. 若原文已有答案与解析，需保持彼此一致；解析可以做去噪和分段整理，但不要凭空扩写新结论。\n"
        "16. 若题目有选项，只有在原文本身给出逐项解析时才保留相应信息；不要为了补全而新写每个选项的判断。\n"
        "17. `analysis_text` 只整理原文已有解析；可以做结构化排版，但不要引入原文没有的推理步骤、知识点总结或套路扩展。\n"
        "18. `clean_text` 也要同步反映当前抽取后的标准化结果；若原文没有答案或解析，`clean_text` 与 `prediction` 中对应字段保持留空。\n"
        "19. 返回 JSON 结构示例：{\"sections\":[{\"title\":\"阅读理解\",\"section_type\":\"material_analysis\",\"questions\":[{\"node_role\":\"group\",\"question_no\":\"41-43\",\"group_stem\":\"Read the following passage...\",\"material_text\":\"...\",\"subquestions\":[{\"node_role\":\"subquestion\",\"question_no\":\"41\",\"question_type\":\"single_choice\",\"stem_text\":\"...\",\"options\":[\"A. ...\"],\"answer_text\":\"B\",\"analysis_text\":\"原文解析整理后内容\"}]}]}]}。\n"
        "20. 只返回 JSON，不要 Markdown 代码块。\n\n"
        f"试卷：{paper_name or '未填写'}\n"
        f"学科：{subject_name or '未填写'}\n"
        f"类目：{category_name or '未填写'}\n"
        f"文本分段：{chunk_index}/{chunk_count}\n\n"
        f"待处理文本：\n{text}"
    )
    schema = {
        "type": "object",
        "properties": {
            "clean_text": {"type": "string"},
            "prediction": {
                "type": "object",
                "properties": {
                    "version": {"type": "number"},
                    "source_format": {"type": "string"},
                    "section_count": {"type": "number"},
                    "question_count": {"type": "number"},
                    "sections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "section_type": {"type": "string"},
                                "sort_order": {"type": "number"},
                                "question_count": {"type": "number"},
                                "shared_stem": {"type": "string"},
                                "questions": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "order": {"type": "number"},
                                            "question_no": {"type": "string"},
                                            "node_role": {"type": "string"},
                                            "question_type": {"type": "string"},
                                            "group_stem": {"type": "string"},
                                            "material_text": {"type": "string"},
                                            "stem_text": {"type": "string"},
                                            "options": {"type": "array", "items": {"type": "string"}},
                                            "answer_text": {"type": "string"},
                                            "analysis_text": {"type": "string"},
                                            "subquestion_count": {"type": "number"},
                                            "quality_score": {"type": "number"},
                                            "quality_issues": {"type": "array", "items": {"type": "string"}},
                                            "shared_stem": {"type": "string"},
                                            "subquestions": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "order": {"type": "number"},
                                                        "question_no": {"type": "string"},
                                                        "node_role": {"type": "string"},
                                                        "question_type": {"type": "string"},
                                                        "stem_text": {"type": "string"},
                                                        "options": {"type": "array", "items": {"type": "string"}},
                                                        "answer_text": {"type": "string"},
                                                        "analysis_text": {"type": "string"},
                                                        "subquestion_count": {"type": "number"},
                                                        "quality_score": {"type": "number"},
                                                        "quality_issues": {"type": "array", "items": {"type": "string"}}
                                                    },
                                                    "required": ["order", "question_no", "question_type", "stem_text", "options", "answer_text", "analysis_text", "subquestion_count", "quality_score", "quality_issues"]
                                                }
                                            }
                                        },
                                        "required": ["order", "question_no", "question_type", "stem_text", "options", "answer_text", "analysis_text", "subquestion_count", "quality_score", "quality_issues"]
                                    }
                                }
                            },
                            "required": ["title", "section_type", "sort_order", "question_count", "questions"]
                        }
                    }
                },
                "required": ["version", "source_format", "section_count", "question_count", "sections"]
            },
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["clean_text"],
    }
    text_response = ""
    try:
        payload = await provider.chat_json(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            schema,
            max_tokens=endpoint.max_tokens,
        )
    except json.JSONDecodeError:
        text_response = await provider.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=endpoint.max_tokens,
        )
        try:
            payload = json.loads(_extract_json_object(text_response))
        except Exception as exc:
            raise RuntimeError(f"invalid_json_response: {_preview_text(text_response, 1200)}") from exc
    if isinstance(payload, dict) and text_response:
        payload["__raw_text_response"] = text_response
    return payload if isinstance(payload, dict) else {}


def _local_ai_cleanup_endpoint() -> LLMEndpointConfig:
    try:
        configured = get_llm_settings().paper_ai_cleanup
    except Exception:
        configured = LLMEndpointConfig(
            provider="openai_compat",
            model=DEFAULT_LOCAL_AI_CLEANUP_MODEL,
            max_tokens=DEFAULT_AI_CLEANUP_MAX_TOKENS,
            base_url=DEFAULT_LOCAL_AI_CLEANUP_BASE_URL,
        )
    return configured.model_copy(
        update={
            "model": os.getenv("PAPER_AI_CLEANUP_MODEL") or configured.model,
            "max_tokens": _env_int("PAPER_AI_CLEANUP_MAX_TOKENS", configured.max_tokens),
            "base_url": os.getenv("PAPER_AI_CLEANUP_BASE_URL") or configured.base_url,
            "api_key": os.getenv("PAPER_AI_CLEANUP_API_KEY") or configured.api_key,
        }
    )


def system_prompt_preview(endpoint: LLMEndpointConfig) -> str:
    return str(getattr(endpoint, "system_prompt", "") or _DEFAULT_SYSTEM_PROMPT)


def _split_cleanup_chunks(text: str, max_chars: int) -> list[str]:
    max_chars = max(4000, max_chars)
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for block in re.split(r"\n{2,}", text):
        normalized = block.strip()
        if not normalized:
            continue
        if current and current_len + len(normalized) + 2 > max_chars:
            chunks.append("\n\n".join(current).strip())
            current = []
            current_len = 0
        if len(normalized) > max_chars:
            chunks.extend(_split_long_block(normalized, max_chars))
            continue
        current.append(normalized)
        current_len += len(normalized) + 2
    if current:
        chunks.append("\n\n".join(current).strip())
    return [chunk for chunk in chunks if chunk.strip()] or [text]


def _split_long_block(text: str, max_chars: int) -> list[str]:
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            split_at = max(text.rfind("\n", start, end), text.rfind("。", start, end), text.rfind("；", start, end))
            if split_at > start + max_chars // 2:
                end = split_at + 1
        parts.append(text[start:end].strip())
        start = end
    return [part for part in parts if part]


def _build_clean_text_from_section_payloads(sections: list[dict[str, Any]] | None) -> str:
    parts: list[str] = []
    for index, section in enumerate(sections or [], start=1):
        if not isinstance(section, dict):
            continue
        title = _normalize_source_text(str(section.get("title") or ""))
        blocks = section.get("blocks")
        rendered_blocks: list[str] = []
        last_stem_prefix = ""
        if isinstance(blocks, list):
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                stem_prefix = _normalize_source_text(str(block.get("stem_prefix") or ""))
                raw_text = _normalize_source_text(str(block.get("raw_text") or ""))
                if stem_prefix and stem_prefix != last_stem_prefix and stem_prefix not in raw_text:
                    rendered_blocks.append(stem_prefix)
                    last_stem_prefix = stem_prefix
                if raw_text:
                    rendered_blocks.append(raw_text)
        if not rendered_blocks:
            continue
        if title and title not in {"自动切题", f"分区 {index}"}:
            parts.append(title)
        parts.extend(rendered_blocks)
    return _normalize_source_text("\n\n".join(parts))


def _passes_quality_gate(source: str, cleaned: str) -> bool:
    if not cleaned or not _TEXT_CHAR_PATTERN.search(cleaned):
        return False
    if len(source) >= 200 and len(cleaned) < max(80, int(len(source) * 0.25)):
        return False
    source_count = len(_QUESTION_START_PATTERN.findall(source))
    cleaned_count = len(_QUESTION_START_PATTERN.findall(cleaned))
    if source_count >= 3 and cleaned_count < max(1, int(source_count * 0.5)):
        return False
    return True


def _normalize_source_text(text: str | None) -> str:
    value = str(text or "").replace("\ufeff", "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _preview_text(text: str, limit: int) -> str:
    normalized = _normalize_source_text(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit]


def _normalize_ai_text(text: str) -> str:
    cleaned = _extract_json_fenced_text(text)
    return _normalize_source_text(cleaned)


def _normalize_ai_sections_payload(value: Any) -> list[dict[str, Any]]:
    prediction = _normalize_ai_prediction_document(value)
    if prediction.get("sections"):
        normalized: list[dict[str, Any]] = []
        for section in prediction.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_shared_stem = _normalize_source_text(str(section.get("shared_stem") or ""))
            blocks: list[dict[str, Any]] = []
            for question in section.get("questions") or []:
                if not isinstance(question, dict):
                    continue
                question_shared_stem = _normalize_source_text(str(question.get("shared_stem") or "")) or section_shared_stem
                question_source_raw_text = _normalize_source_text(str(question.get("source_raw_text") or ""))
                if question_source_raw_text:
                    raw_text = question_source_raw_text
                else:
                    raw_text = _compose_source_raw_text(question)
                if not raw_text:
                    continue
                blocks.append(
                    {
                        "raw_text": raw_text,
                        "question_no_override": str(question.get("question_no") or "").strip() or None,
                        "stem_prefix": question_shared_stem if question_shared_stem and question_shared_stem not in raw_text else None,
                    }
                )
            if blocks:
                normalized.append(
                    {
                        "title": str(section.get("title") or "").strip() or "自动切题",
                        "section_type": str(section.get("section_type") or "mixed").strip() or "mixed",
                        "sort_order": int(section.get("sort_order") or 0),
                        "blocks": blocks,
                    }
                )
        return normalized
    return []


def _normalize_ai_prediction_sections(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip() or f"分区 {index}"
        section_type = str(item.get("section_type") or "mixed").strip() or "mixed"
        section_shared_stem = _normalize_source_text(str(item.get("shared_stem") or ""))
        raw_questions = item.get("questions")
        if not isinstance(raw_questions, list):
            continue
        questions: list[dict[str, Any]] = []
        for order, question in enumerate(raw_questions, start=1):
            if not isinstance(question, dict):
                continue
            node_role = str(question.get("node_role") or "").strip() or (
                "group" if isinstance(question.get("subquestions"), list) and (question.get("subquestions") or []) else "standalone"
            )
            question_shared_stem = _normalize_source_text(
                str(question.get("group_stem") or question.get("shared_stem") or "")
            ) or section_shared_stem
            material_text = _normalize_source_text(str(question.get("material_text") or ""))
            source_raw_text = _normalize_source_text(str(question.get("source_raw_text") or ""))
            stem_text = _normalize_source_text(str(question.get("stem_text") or ""))
            if node_role == "group":
                subquestions = _normalize_ai_prediction_subquestions(
                    question.get("subquestions"),
                    inherited_group_stem=question_shared_stem,
                    inherited_material_text=material_text,
                )
                stem_text = stem_text or question_shared_stem or material_text
                if not source_raw_text:
                    source_raw_text = _compose_source_raw_text(
                        {
                            "question_no": str(question.get("question_no") or "").strip(),
                            "node_role": "group",
                            "group_stem": question_shared_stem,
                            "material_text": material_text,
                            "stem_text": stem_text,
                            "subquestions": subquestions,
                        }
                    )
                if not stem_text:
                    continue
                questions.append(
                    {
                        "order": order,
                        "question_no": str(question.get("question_no") or "").strip(),
                        "node_role": "group",
                        "question_type": str(question.get("question_type") or "material_analysis").strip() or "material_analysis",
                        "group_stem": question_shared_stem or "",
                        "material_text": material_text or "",
                        "stem_text": stem_text,
                        "options": [],
                        "answer_text": "",
                        "analysis_text": "",
                        "source_raw_text": source_raw_text,
                        "shared_stem": question_shared_stem or None,
                        "subquestion_count": len(subquestions),
                        "quality_score": 0.0,
                        "quality_issues": [],
                        "subquestions": subquestions,
                    }
                )
                continue
            if not stem_text:
                continue
            options = [_normalize_source_text(str(item)) for item in (question.get("options") or []) if _normalize_source_text(str(item))]
            if not source_raw_text:
                normalized_analysis = normalize_analysis(question.get("analysis_text")) or ""
                source_raw_text = _compose_source_raw_text(
                    {
                        "question_no": str(question.get("question_no") or "").strip(),
                        "stem_text": stem_text,
                        "options": options,
                        "answer_text": _normalize_source_text(str(question.get("answer_text") or "")) or "",
                        "analysis_text": normalized_analysis,
                    }
                )
            questions.append(
                {
                    "order": order,
                    "question_no": str(question.get("question_no") or "").strip(),
                    "node_role": "standalone",
                    "question_type": str(question.get("question_type") or "mixed").strip() or "mixed",
                    "group_stem": question_shared_stem or "",
                    "material_text": material_text or "",
                    "stem_text": stem_text,
                    "options": options,
                    "answer_text": _normalize_source_text(str(question.get("answer_text") or "")) or None,
                    "analysis_text": normalize_analysis(question.get("analysis_text")),
                    "source_raw_text": source_raw_text,
                    "shared_stem": question_shared_stem or None,
                    "subquestion_count": 0,
                    "quality_score": 0.0,
                    "quality_issues": [],
                    "subquestions": [],
                }
            )
        if questions:
            normalized.append(
                {
                    "section_id": item.get("section_id"),
                    "title": title,
                    "section_type": section_type,
                    "sort_order": index,
                    "shared_stem": section_shared_stem or None,
                    "questions": questions,
                }
            )
    return normalized


def _normalize_ai_prediction_document(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("sections"), list):
        sections_payload: list[dict[str, Any]] = []
        total_question_count = 0
        for index, item in enumerate(value.get("sections") or [], start=1):
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("section_title") or "").strip() or f"分区 {index}"
            section_type = str(item.get("section_type") or "mixed").strip() or "mixed"
            section_shared_stem = _normalize_source_text(str(item.get("shared_stem") or ""))
            raw_questions = item.get("questions")
            if not isinstance(raw_questions, list):
                continue
            questions: list[dict[str, Any]] = []
            for order, question in enumerate(raw_questions, start=1):
                if not isinstance(question, dict):
                    continue
                question_shared_stem = _normalize_source_text(
                    str(question.get("group_stem") or question.get("shared_stem") or "")
                ) or section_shared_stem
                material_text = _normalize_source_text(str(question.get("material_text") or ""))
                node_role = str(question.get("node_role") or "").strip() or (
                    "group" if isinstance(question.get("subquestions"), list) and (question.get("subquestions") or []) else "standalone"
                )
                stem_text = _normalize_source_text(str(question.get("stem_text") or ""))
                if node_role == "group":
                    subquestions = _normalize_ai_prediction_subquestions(
                        question.get("subquestions"),
                        inherited_group_stem=question_shared_stem,
                        inherited_material_text=material_text,
                    )
                    stem_text = stem_text or question_shared_stem or material_text
                    source_raw_text = _normalize_source_text(str(question.get("source_raw_text") or "")) or _compose_source_raw_text(
                        {
                            "question_no": str(question.get("question_no") or "").strip(),
                            "node_role": "group",
                            "group_stem": question_shared_stem,
                            "material_text": material_text,
                            "stem_text": stem_text,
                            "subquestions": subquestions,
                        }
                    )
                    if not stem_text:
                        continue
                    questions.append(
                        {
                            "order": _to_int(question.get("order"), order),
                            "question_no": str(question.get("question_no") or "").strip(),
                            "node_role": "group",
                            "question_type": str(question.get("question_type") or "material_analysis").strip() or "material_analysis",
                            "group_stem": question_shared_stem or "",
                            "material_text": material_text or "",
                            "stem_text": stem_text,
                            "options": [],
                            "answer_text": "",
                            "analysis_text": "",
                            "subquestion_count": len(subquestions),
                            "quality_score": _to_float(question.get("quality_score"), 0.0),
                            "quality_issues": [str(issue).strip() for issue in (question.get("quality_issues") or []) if str(issue).strip()],
                            "shared_stem": question_shared_stem or "",
                            "source_raw_text": source_raw_text,
                            "subquestions": subquestions,
                        }
                    )
                    total_question_count += len(subquestions)
                    continue
                if not stem_text:
                    continue
                options = [_normalize_source_text(str(option)) for option in (question.get("options") or []) if _normalize_source_text(str(option))]
                normalized_analysis = normalize_analysis(question.get("analysis_text")) or ""
                source_raw_text = _normalize_source_text(str(question.get("source_raw_text") or "")) or _compose_source_raw_text(
                    {
                        "question_no": str(question.get("question_no") or "").strip(),
                        "stem_text": stem_text,
                        "options": options,
                        "answer_text": _normalize_source_text(str(question.get("answer_text") or "")) or "",
                        "analysis_text": normalized_analysis,
                    }
                )
                questions.append(
                    {
                        "order": _to_int(question.get("order"), order),
                        "question_no": str(question.get("question_no") or "").strip(),
                        "node_role": "standalone",
                        "question_type": str(question.get("question_type") or "mixed").strip() or "mixed",
                        "group_stem": question_shared_stem or "",
                        "material_text": material_text or "",
                        "stem_text": stem_text,
                        "options": options,
                        "answer_text": _normalize_source_text(str(question.get("answer_text") or "")) or "",
                        "analysis_text": normalized_analysis,
                        "subquestion_count": 0,
                        "quality_score": _to_float(question.get("quality_score"), 0.0),
                        "quality_issues": [str(issue).strip() for issue in (question.get("quality_issues") or []) if str(issue).strip()],
                        "shared_stem": question_shared_stem or "",
                        "source_raw_text": source_raw_text,
                        "subquestions": [],
                    }
                )
                total_question_count += 1
            sections_payload.append(
                {
                    "section_id": item.get("section_id"),
                    "title": title,
                    "section_type": section_type,
                    "sort_order": _to_int(item.get("sort_order") or item.get("section_no"), index),
                    "question_count": _to_int(item.get("question_count"), len(questions)),
                    "shared_stem": section_shared_stem or "",
                    "questions": questions,
                }
            )
        return {
            "version": _to_int(value.get("version"), 2),
            "source_format": str(value.get("source_format") or "ai_structured_question_groups"),
            "section_count": _to_int(value.get("section_count"), len(sections_payload)),
            "question_count": _to_int(value.get("question_count"), total_question_count),
            "sections": sections_payload,
        }
    return {}


def build_prediction_from_ai_sections(sections: list[dict[str, Any]] | None) -> dict[str, Any]:
    payload_sections: list[dict[str, Any]] = []
    total_question_count = 0
    for index, section in enumerate(sections or [], start=1):
        if not isinstance(section, dict):
            continue
        questions = section.get("questions") if isinstance(section.get("questions"), list) else []
        total_question_count += sum(
            len(question.get("subquestions") or []) if str(question.get("node_role") or "") == "group" else 1
            for question in questions
            if isinstance(question, dict)
        )
        payload_sections.append(
            {
                "section_id": section.get("section_id"),
                "title": str(section.get("title") or "").strip() or f"分区 {index}",
                "section_type": str(section.get("section_type") or "mixed").strip() or "mixed",
                "sort_order": int(section.get("sort_order") or index),
                "shared_stem": _normalize_source_text(str(section.get("shared_stem") or "")) or "",
                "question_count": len(questions),
                "questions": questions,
            }
        )
    return {
        "version": 2,
        "source_format": "ai_structured_question_groups",
        "section_count": len(payload_sections),
        "question_count": total_question_count,
        "sections": payload_sections,
    }


def _compose_source_raw_text(question: dict[str, Any]) -> str:
    parts: list[str] = []
    question_no = str(question.get("question_no") or "").strip()
    node_role = str(question.get("node_role") or "").strip()
    group_stem = _normalize_source_text(str(question.get("group_stem") or question.get("shared_stem") or ""))
    material_text = _normalize_source_text(str(question.get("material_text") or ""))
    if node_role == "group" and group_stem:
        parts.append(group_stem)
    if node_role == "group" and material_text:
        parts.append(material_text)
    stem_text = _normalize_source_text(str(question.get("stem_text") or ""))
    if stem_text:
        prefix = f"{question_no}. " if question_no else ""
        parts.append(f"{prefix}{stem_text}".strip() if node_role != "group" else stem_text)
    for option in question.get("options") or []:
        option_text = _normalize_source_text(str(option))
        if option_text:
            parts.append(option_text)
    answer_text = _normalize_source_text(str(question.get("answer_text") or ""))
    if answer_text:
        parts.append(f"答案：{answer_text}")
    analysis_text = normalize_analysis(question.get("analysis_text")) or ""
    if analysis_text:
        parts.append(f"解析：{analysis_text}")
    for child in question.get("subquestions") or []:
        if isinstance(child, dict):
            child_raw = _compose_source_raw_text(child)
            if child_raw:
                parts.append(child_raw)
    return "\n".join(parts).strip()


def _normalize_ai_prediction_subquestions(
    value: Any,
    *,
    inherited_group_stem: str,
    inherited_material_text: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for order, question in enumerate(value, start=1):
        if not isinstance(question, dict):
            continue
        stem_text = _normalize_source_text(str(question.get("stem_text") or ""))
        if not stem_text:
            continue
        options = [_normalize_source_text(str(option)) for option in (question.get("options") or []) if _normalize_source_text(str(option))]
        normalized_analysis = normalize_analysis(question.get("analysis_text")) or ""
        source_raw_text = _normalize_source_text(str(question.get("source_raw_text") or "")) or _compose_source_raw_text(
            {
                "question_no": str(question.get("question_no") or "").strip(),
                "stem_text": stem_text,
                "options": options,
                "answer_text": _normalize_source_text(str(question.get("answer_text") or "")) or "",
                "analysis_text": normalized_analysis,
            }
        )
        normalized.append(
            {
                "order": _to_int(question.get("order"), order),
                "question_no": str(question.get("question_no") or "").strip(),
                "node_role": "subquestion",
                "question_type": str(question.get("question_type") or "mixed").strip() or "mixed",
                "group_stem": inherited_group_stem or "",
                "material_text": inherited_material_text or "",
                "stem_text": stem_text,
                "options": options,
                "answer_text": _normalize_source_text(str(question.get("answer_text") or "")) or "",
                "analysis_text": normalized_analysis,
                "subquestion_count": 0,
                "quality_score": _to_float(question.get("quality_score"), 0.0),
                "quality_issues": [str(issue).strip() for issue in (question.get("quality_issues") or []) if str(issue).strip()],
                "source_raw_text": source_raw_text,
                "subquestions": [],
            }
        )
    return normalized


def _to_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except Exception:
        try:
            return int(float(str(value).strip()))
        except Exception:
            return default


def _to_float(value: Any, default: float) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _extract_json_fenced_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json|markdown|text)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned


def _extract_json_object(text: str) -> str:
    cleaned = _extract_json_fenced_text(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        return cleaned[start : end + 1]
    return cleaned


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except Exception as exc:
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default

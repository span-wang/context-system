from schemas.context import GenerationContext
from schemas.generation import GenerationResult
from schemas.review import ReviewItem, ReviewMode, ReviewReport, make_review_item_id
from settings import ReviewConfig

from .citation import check_citations
from .llm import llm_review
from .nli import local_nli_check
from .numeric import check_numerics
from .version import check_versions


async def review_result(
    result: GenerationResult,
    context: GenerationContext,
    config: ReviewConfig,
    mode: ReviewMode = "hybrid",
    llm_provider=None,
    llm_max_tokens: int | None = None,
) -> ReviewReport:
    document_mode = mode in {"document_only", "hybrid"}
    strict = document_mode and config.strict_when_sources_present and bool(context.sources)
    citation_check = check_citations(result, context, strict=strict) if document_mode else _skipped_check()
    nli_results = local_nli_check(result, context) if strict else []
    version_conflicts = check_versions(result, context) if document_mode else []
    numeric_checks = check_numerics(result, context) if document_mode else []

    issues: list[str] = []
    suggestions: list[str] = []
    llm_items: list[dict] = []
    llm_used = False

    if mode == "document_only" and not context.sources:
        issues.append("文档审查模式未提供审查依据文档，无法判断内容是否被依据支持。")
        suggestions.append("请先上传教材、规范、法规、真题等审查依据文档，或改用纯大模型/混合审查。")
    if mode == "llm_only" and llm_provider is None:
        issues.append("纯大模型审查需要先在模型配置页配置可用的审查模型。")
        suggestions.append("请为审查模型配置 DeepSeek、OpenAI 兼容接口或 Anthropic 后重新审查。")

    if strict and not citation_check["pass"]:
        issues.append("存在缺失引用或无效引用的 claim。")
        suggestions.append("重新生成时要求每个事实点引用素材库或 RAGFlow 返回的来源。")
    failed_nli = [item for item in nli_results if not item["entailed"]]
    if failed_nli:
        issues.append(f"{len(failed_nli)} 条 claim 未被本地 NLI 回溯充分支持。")
        suggestions.append("降低表达强度，或补充更权威、更贴近章节的资料。")
    if version_conflicts:
        issues.append("结果中的年份/版本号与来源资料存在不一致。")
        suggestions.append("按考试年度、教材版本、规范版本重新过滤资料。")
    missing_numbers = [item for item in numeric_checks if not item["found_in_sources"]]
    if strict and missing_numbers:
        issues.append(f"{len(missing_numbers)} 个数值未在来源资料中找到。")
        suggestions.append("核对税率、年限、条文号、公式系数等数值后再使用。")

    if llm_provider is not None and mode in {"llm_only", "document_only", "hybrid"}:
        llm_result = await llm_review(
            llm_provider,
            result,
            context,
            mode,
            max_tokens=llm_max_tokens or 4096,
        )
        llm_used = True
        issues.extend(llm_result["issues"])
        issues.extend(item["issue"] for item in llm_result.get("items", []) if item.get("issue"))
        if not llm_result["pass_overall"] and not llm_result["issues"] and not llm_result.get("items"):
            issues.append("审查模型判断整体不通过，但未返回具体问题。")
        suggestions.extend(llm_result["suggestions"])
        llm_items.extend(llm_result.get("items", []))

    warning = None
    if mode == "llm_only":
        warning = "本次为纯大模型审查，未使用审查依据文档；涉及教材、法规、年份、税率、条文等内容仍建议人工核对。"
    elif not strict:
        warning = config.unverified_warning
        if not context.sources and mode != "document_only":
            issues.append("本次生成没有权威资料来源，结果已标记为未核验。")
            suggestions.append("上传教材、规范、法规或真题后可启用严格审查。")

    issues = _dedupe(issues)
    suggestions = _dedupe(suggestions)
    items = _review_items(issues, suggestions, llm_items)

    return ReviewReport(
        pass_overall=len(issues) == 0,
        strict_mode=strict,
        mode=mode,
        evidence_policy=_evidence_policy(mode),
        llm_used=llm_used,
        evidence_source_count=len(context.sources) if document_mode else 0,
        citation_check=citation_check,
        nli_results=nli_results,
        version_conflicts=version_conflicts,
        numeric_checks=numeric_checks,
        issues=issues,
        suggestions=suggestions,
        items=items,
        unverified_warning=warning,
    )


def _skipped_check() -> dict:
    return {
        "pass": True,
        "missing_claims": [],
        "invalid_citations": [],
        "checked_claims": 0,
        "skipped": True,
    }


def _evidence_policy(mode: ReviewMode) -> str:
    return {
        "llm_only": "model_only",
        "document_only": "documents_only",
        "hybrid": "model_and_documents",
    }[mode]


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item.strip()))


def _review_items(issues: list[str], suggestions: list[str], llm_items: list[dict]) -> list[ReviewItem]:
    llm_item_by_issue = {
        str(item.get("issue", "")).strip(): item
        for item in llm_items
        if str(item.get("issue", "")).strip()
    }
    items: list[ReviewItem] = []
    for index, issue in enumerate(issues):
        llm_item = llm_item_by_issue.get(issue) or {}
        suggestion = (
            str(llm_item.get("suggestion") or "").strip()
            or (suggestions[index] if index < len(suggestions) else None)
        )
        items.append(
            ReviewItem(
                id=make_review_item_id(issue, suggestion, index),
                issue=issue,
                suggestion=suggestion or None,
                original_text=str(llm_item.get("original_text") or "").strip() or None,
                replacement_text=str(llm_item.get("replacement_text") or "").strip() or None,
            )
        )
    return items

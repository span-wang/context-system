from schemas.generation import GenerationJob


MODE_LABELS = {
    "llm_only": "纯大模型",
    "document_only": "仅依据文档",
    "hybrid": "混合审查",
}


def export_markdown(job: GenerationJob) -> str:
    if not job.result:
        return "# 生成尚未完成\n"
    report_lines = []
    if job.review:
        status = "通过" if job.review.pass_overall else "需复核"
        report_lines.extend(
            [
                "",
                "---",
                "",
                "## 审查摘要",
                "",
                f"- 总体结论：{status}",
                f"- 审查模式：{MODE_LABELS.get(job.review.mode, job.review.mode)}",
                f"- 严格模式：{'是' if job.review.strict_mode else '否'}",
                f"- 使用审查模型：{'是' if job.review.llm_used else '否'}",
                f"- 依据文档数：{job.review.evidence_source_count}",
            ]
        )
        for issue in job.review.issues:
            report_lines.append(f"- 问题：{issue}")
        for suggestion in job.review.suggestions:
            report_lines.append(f"- 建议：{suggestion}")
    return job.result.raw_markdown.rstrip() + "\n" + "\n".join(report_lines).rstrip() + "\n"

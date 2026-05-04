import re

from schemas.context import GenerationContext
from schemas.generation import GenerationResult


def check_versions(result: GenerationResult, context: GenerationContext) -> list[dict]:
    result_years = set(re.findall(r"(?:19|20)\d{2}", result.raw_markdown))
    source_years = set()
    version_text = []
    for source in context.sources:
        source_years.update(re.findall(r"(?:19|20)\d{2}", source.text))
        if source.source_label:
            version_text.append(source.source_label)
    conflicts = []
    if result_years and source_years and not result_years.issubset(source_years):
        conflicts.append(
            {
                "type": "year_not_found_in_sources",
                "result_years": sorted(result_years),
                "source_years": sorted(source_years)[:20],
            }
        )
    return conflicts


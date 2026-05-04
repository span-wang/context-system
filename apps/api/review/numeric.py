import re

from schemas.context import GenerationContext
from schemas.generation import GenerationResult


def check_numerics(result: GenerationResult, context: GenerationContext) -> list[dict]:
    if not context.sources:
        return []
    source_text = "\n".join(source.text for source in context.sources)
    claim_text = "\n".join(claim.text for claim in result.claims)
    numbers = re.findall(r"\d+(?:\.\d+)?%?|\d+/\d+", claim_text)
    checks = []
    for number in list(dict.fromkeys(numbers))[:80]:
        checks.append({"value": number, "found_in_sources": number in source_text})
    return checks

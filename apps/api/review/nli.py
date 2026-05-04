import re

from schemas.context import GenerationContext
from schemas.generation import GenerationResult


def local_nli_check(result: GenerationResult, context: GenerationContext) -> list[dict]:
    source_text = "\n".join(source.text for source in context.sources)
    results = []
    for claim in result.claims:
        keywords = _keywords(claim.text)
        if not keywords:
            score = 0.0
        else:
            hits = sum(1 for keyword in keywords if keyword in source_text)
            score = hits / len(keywords)
        results.append(
            {
                "claim": claim.text,
                "entailed": score >= 0.35,
                "score": round(score, 2),
                "method": "local_keyword_overlap",
            }
        )
    return results


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z0-9]{3,}", text)
    return list(dict.fromkeys(words[:12]))


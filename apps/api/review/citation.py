from schemas.context import GenerationContext
from schemas.generation import GenerationResult


def check_citations(result: GenerationResult, context: GenerationContext, strict: bool) -> dict:
    valid_labels = {source.source_label for source in context.sources}
    valid_file_ids = {source.file_id for source in context.sources if source.file_id}
    valid_chunk_ids = {source.chunk_id for source in context.sources if source.chunk_id}
    missing = []
    invalid = []
    for claim in result.claims:
        if strict and not claim.citations:
            missing.append(claim.text)
        for citation in claim.citations:
            label_ok = citation.source_label in valid_labels
            file_ok = citation.file_id is None or citation.file_id in valid_file_ids
            chunk_ok = citation.chunk_id is None or citation.chunk_id in valid_chunk_ids
            if not (label_ok and file_ok and chunk_ok):
                invalid.append({"claim": claim.text, "citation": citation.model_dump()})
    return {
        "pass": not missing and not invalid,
        "missing_claims": missing,
        "invalid_citations": invalid,
        "checked_claims": len(result.claims),
    }


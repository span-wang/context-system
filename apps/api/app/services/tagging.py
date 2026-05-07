from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import ExamQuestion, KnowledgePoint, QuestionKnowledgeLink


@dataclass(frozen=True)
class KnowledgeCandidate:
    point: KnowledgePoint
    confidence: float
    evidence: str


def rank_knowledge_candidates(points: list[KnowledgePoint], text: str, limit: int = 3) -> list[KnowledgeCandidate]:
    normalized_text = text.lower()
    candidates: list[KnowledgeCandidate] = []
    for point in points:
        score = 0.0
        evidence_parts: list[str] = []
        if point.name and point.name.lower() in normalized_text:
            score += 0.38
            evidence_parts.append(point.name)
        for keyword in point.keywords_json or []:
            keyword_text = str(keyword).strip()
            if keyword_text and keyword_text.lower() in normalized_text:
                score += 0.2
                evidence_parts.append(keyword_text)
        if score <= 0:
            continue
        confidence = min(0.96, 0.55 + score)
        candidates.append(
            KnowledgeCandidate(
                point=point,
                confidence=round(confidence, 2),
                evidence="、".join(dict.fromkeys(evidence_parts))[:120],
            )
        )

    candidates.sort(key=lambda item: item.confidence, reverse=True)
    return candidates[:limit]


def apply_rule_tags(
    session: Session,
    question: ExamQuestion,
    points: list[KnowledgePoint],
    tenant_id: int,
    operator_id: int | None = None,
) -> list[QuestionKnowledgeLink]:
    text = "\n".join(
        part
        for part in (
            question.stem_text,
            "\n".join(question.options_json or []),
            question.answer_text or "",
            question.analysis_text or "",
        )
        if part
    )
    candidates = rank_knowledge_candidates(points, text)
    if not candidates:
        return []

    existing_point_ids = {
        row[0]
        for row in session.query(QuestionKnowledgeLink.knowledge_point_id)
        .filter(QuestionKnowledgeLink.question_id == question.id)
        .all()
    }
    created: list[QuestionKnowledgeLink] = []
    for index, candidate in enumerate(candidates):
        if candidate.point.id in existing_point_ids:
            continue
        link = QuestionKnowledgeLink(
            tenant_id=tenant_id,
            question_id=question.id,
            question_layer="raw",
            knowledge_point_id=candidate.point.id,
            link_type="rule_candidate",
            confidence_score=candidate.confidence,
            evidence_text=candidate.evidence or question.stem_text[:80],
            tag_source="rule_keyword",
            is_primary=index == 0,
            review_status="pending",
            created_by=operator_id,
            updated_by=operator_id,
        )
        session.add(link)
        created.append(link)
    if created:
        session.flush()
    return created

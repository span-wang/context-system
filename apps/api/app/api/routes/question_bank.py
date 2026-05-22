from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from urllib.parse import quote

from app.api.deps import get_session
from app.schemas.question_bank import (
    QuestionBankDeleteResponse,
    QuestionBankKnowledgeAnalysisResponse,
    QuestionBankExportPaperOptionResponse,
    QuestionBankItemResponse,
    QuestionBankItemUpdateRequest,
    QuestionBankListResponse,
    QuestionBankPaperExportRequest,
    QuestionBankSourceResponse,
    QuestionBankSyncResponse,
)
from app.services.audit import AuditService
from app.services.question_bank import QuestionBankService


router = APIRouter(prefix="/api/question-bank", tags=["question-bank"])


@router.get("/analysis/knowledge-report", response_model=QuestionBankKnowledgeAnalysisResponse)
def get_question_bank_knowledge_report(
    subject_id: int | None = Query(None),
    category_id: int | None = Query(None),
    start_year: int | None = Query(None),
    end_year: int | None = Query(None),
    session: Session = Depends(get_session),
) -> QuestionBankKnowledgeAnalysisResponse:
    return QuestionBankService(session).get_knowledge_analysis(
        subject_id=subject_id,
        category_id=category_id,
        start_year=start_year,
        end_year=end_year,
    )


@router.get("/questions", response_model=QuestionBankListResponse)
def list_question_bank_items(
    subject_id: int | None = Query(None),
    category_id: int | None = Query(None),
    status: str | None = Query(None),
    question_type: str | None = Query(None),
    keyword: str | None = Query(None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> QuestionBankListResponse:
    return QuestionBankService(session).list_questions(
        subject_id=subject_id,
        category_id=category_id,
        status=status or None,
        question_type=question_type or None,
        keyword=keyword or None,
        limit=limit,
        offset=offset,
    )


@router.get("/export/papers", response_model=list[QuestionBankExportPaperOptionResponse])
def list_question_bank_export_papers(
    subject_id: int | None = Query(None),
    category_id: int | None = Query(None),
    status: str | None = Query(None),
    question_type: str | None = Query(None),
    keyword: str | None = Query(None),
    session: Session = Depends(get_session),
) -> list[QuestionBankExportPaperOptionResponse]:
    return QuestionBankService(session).list_export_papers(
        subject_id=subject_id,
        category_id=category_id,
        status=status or None,
        question_type=question_type or None,
        keyword=keyword or None,
    )


@router.post("/export")
def export_question_bank_items(
    payload: QuestionBankPaperExportRequest,
    session: Session = Depends(get_session),
) -> PlainTextResponse:
    content, filename = QuestionBankService(session).export_questions_by_paper(payload)
    AuditService(session).log(
        None,
        module="question_bank",
        action="export",
        target_type="paper",
        target_id=payload.paper_id,
        payload=payload.model_dump(),
    )
    quoted = quote(filename)
    ascii_fallback = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._") or "question-bank-export.md"
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quoted}'},
    )


@router.get("/questions/{question_id}", response_model=QuestionBankItemResponse)
def get_question_bank_item(question_id: int, session: Session = Depends(get_session)) -> QuestionBankItemResponse:
    return QuestionBankService(session).get_question(question_id)


@router.patch("/questions/{question_id}", response_model=QuestionBankItemResponse)
def update_question_bank_item(
    question_id: int,
    payload: QuestionBankItemUpdateRequest,
    session: Session = Depends(get_session),
) -> QuestionBankItemResponse:
    result = QuestionBankService(session).update_question(question_id, payload)
    AuditService(session).log(
        None,
        module="question_bank",
        action="update",
        target_type="question_bank_item",
        target_id=question_id,
        payload=payload.model_dump(),
    )
    return result


@router.post("/questions/{question_id}/activate", response_model=QuestionBankItemResponse)
def activate_question_bank_item(question_id: int, session: Session = Depends(get_session)) -> QuestionBankItemResponse:
    result = QuestionBankService(session).update_question(
        question_id,
        QuestionBankItemUpdateRequest(status="active"),
    )
    AuditService(session).log(
        None,
        module="question_bank",
        action="activate",
        target_type="question_bank_item",
        target_id=question_id,
        payload={"status": "active"},
    )
    return result


@router.post("/questions/{question_id}/deactivate", response_model=QuestionBankItemResponse)
def deactivate_question_bank_item(question_id: int, session: Session = Depends(get_session)) -> QuestionBankItemResponse:
    result = QuestionBankService(session).update_question(
        question_id,
        QuestionBankItemUpdateRequest(status="inactive"),
    )
    AuditService(session).log(
        None,
        module="question_bank",
        action="deactivate",
        target_type="question_bank_item",
        target_id=question_id,
        payload={"status": "inactive"},
    )
    return result


@router.delete("/questions/{question_id}", response_model=QuestionBankDeleteResponse)
def delete_question_bank_item(question_id: int, session: Session = Depends(get_session)) -> QuestionBankDeleteResponse:
    result = QuestionBankService(session).delete_question(question_id)
    AuditService(session).log(
        None,
        module="question_bank",
        action="delete",
        target_type="question_bank_item",
        target_id=question_id,
        payload={
            "question_uid": result.question_uid,
            "removed_source_link_count": result.removed_source_link_count,
            "message": result.message,
        },
    )
    return result


@router.get("/questions/{question_id}/sources", response_model=list[QuestionBankSourceResponse])
def list_question_bank_sources(question_id: int, session: Session = Depends(get_session)) -> list[QuestionBankSourceResponse]:
    return QuestionBankService(session).list_sources(question_id)


@router.post("/sync/review-questions/{question_id}", response_model=QuestionBankSyncResponse)
def sync_review_question_to_bank(question_id: int, session: Session = Depends(get_session)) -> QuestionBankSyncResponse:
    result = QuestionBankService(session).sync_from_review_question(question_id)
    AuditService(session).log(
        None,
        module="question_bank",
        action="sync_from_review",
        target_type="paper_review_question",
        target_id=question_id,
        payload=result.model_dump(),
    )
    return result

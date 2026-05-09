from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.knowledge import (
    BatchDeleteRequest,
    ChapterDeleteResponse,
    ChapterBatchDeleteResponse,
    ChapterMarkdownImportRequest,
    ChapterMarkdownImportResponse,
    ChapterResponse,
    ChapterUpsertRequest,
    KnowledgePointMarkdownImportRequest,
    KnowledgePointMarkdownImportResponse,
    KnowledgePointResponse,
    KnowledgePointUpsertRequest,
    SubjectCategoryResponse,
    SubjectCategoryUpsertRequest,
    SubjectBatchDeleteResponse,
    SubjectDeleteResponse,
    SubjectResponse,
    SubjectUpsertRequest,
    TextbookAutoBuildRequest,
    TextbookAutoBuildResponse,
    TextbookResponse,
    TextbookUpsertRequest,
)
from app.services.audit import AuditService
from app.services.knowledge import KnowledgeTreeService


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/subjects", response_model=list[SubjectResponse])
def list_subjects(session: Session = Depends(get_session)) -> list[SubjectResponse]:
    return KnowledgeTreeService(session).list_subjects()


@router.post("/subjects", response_model=SubjectResponse)
def create_subject(
    payload: SubjectUpsertRequest,
    session: Session = Depends(get_session),
) -> SubjectResponse:
    result = KnowledgeTreeService(session).create_subject(payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="create_subject",
        target_type="subject",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.patch("/subjects/{subject_id}", response_model=SubjectResponse)
def update_subject(
    subject_id: int,
    payload: SubjectUpsertRequest,
    session: Session = Depends(get_session),
) -> SubjectResponse:
    result = KnowledgeTreeService(session).update_subject(subject_id, payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="update_subject",
        target_type="subject",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.delete("/subjects/{subject_id}", response_model=SubjectDeleteResponse)
def delete_subject(
    subject_id: int,
    session: Session = Depends(get_session),
) -> SubjectDeleteResponse:
    result = KnowledgeTreeService(session).delete_subject(subject_id)
    AuditService(session).log(
        None,
        module="knowledge",
        action="delete_subject",
        target_type="subject",
        target_id=result.id,
        payload={"name": result.name},
    )
    return result


@router.post("/subjects/batch-delete", response_model=SubjectBatchDeleteResponse)
def batch_delete_subjects(
    payload: BatchDeleteRequest,
    session: Session = Depends(get_session),
) -> SubjectBatchDeleteResponse:
    result = KnowledgeTreeService(session).batch_delete_subjects(payload)
    AuditService(session).log(
        None,
        module="knowledge",
        action="batch_delete_subjects",
        target_type="subject",
        target_id="batch",
        payload={
            "ids": payload.ids,
            "deleted_count": result.deleted_count,
            "skipped_count": result.skipped_count,
        },
    )
    return result


@router.get("/categories", response_model=list[SubjectCategoryResponse])
def list_categories(
    subject_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[SubjectCategoryResponse]:
    return KnowledgeTreeService(session).list_categories(subject_id)


@router.post("/categories", response_model=SubjectCategoryResponse)
def create_category(
    payload: SubjectCategoryUpsertRequest,
    session: Session = Depends(get_session),
) -> SubjectCategoryResponse:
    result = KnowledgeTreeService(session).create_category(payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="create_category",
        target_type="subject_category",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.patch("/categories/{category_id}", response_model=SubjectCategoryResponse)
def update_category(
    category_id: int,
    payload: SubjectCategoryUpsertRequest,
    session: Session = Depends(get_session),
) -> SubjectCategoryResponse:
    result = KnowledgeTreeService(session).update_category(category_id, payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="update_category",
        target_type="subject_category",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.get("/chapters", response_model=list[ChapterResponse])
def list_chapters(
    subject_id: int | None = Query(default=None),
    category_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[ChapterResponse]:
    return KnowledgeTreeService(session).list_chapters(subject_id, category_id)


@router.post("/chapters", response_model=ChapterResponse)
def create_chapter(
    payload: ChapterUpsertRequest,
    session: Session = Depends(get_session),
) -> ChapterResponse:
    result = KnowledgeTreeService(session).create_chapter(payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="create_chapter",
        target_type="chapter",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.post("/chapters/import-markdown", response_model=ChapterMarkdownImportResponse)
def import_chapters_from_markdown(
    payload: ChapterMarkdownImportRequest,
    session: Session = Depends(get_session),
) -> ChapterMarkdownImportResponse:
    result = KnowledgeTreeService(session).import_chapters_from_markdown(payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="import_chapters_markdown",
        target_type="subject",
        target_id=result.subject_id,
        payload={
            "subject_id": payload.subject_id,
            "chapter_created": result.chapter_created,
            "chapter_skipped": result.chapter_skipped,
        },
    )
    return result


@router.patch("/chapters/{chapter_id}", response_model=ChapterResponse)
def update_chapter(
    chapter_id: int,
    payload: ChapterUpsertRequest,
    session: Session = Depends(get_session),
) -> ChapterResponse:
    result = KnowledgeTreeService(session).update_chapter(chapter_id, payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="update_chapter",
        target_type="chapter",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.delete("/chapters/{chapter_id}", response_model=ChapterDeleteResponse)
def delete_chapter(
    chapter_id: int,
    session: Session = Depends(get_session),
) -> ChapterDeleteResponse:
    result = KnowledgeTreeService(session).delete_chapter(chapter_id)
    AuditService(session).log(
        None,
        module="knowledge",
        action="delete_chapter",
        target_type="chapter",
        target_id=result.id,
        payload={
            "name": result.name,
            "removed_chapter_count": result.removed_chapter_count,
            "unbound_point_count": result.unbound_point_count,
        },
    )
    return result


@router.post("/chapters/batch-delete", response_model=ChapterBatchDeleteResponse)
def batch_delete_chapters(
    payload: BatchDeleteRequest,
    session: Session = Depends(get_session),
) -> ChapterBatchDeleteResponse:
    result = KnowledgeTreeService(session).batch_delete_chapters(payload)
    AuditService(session).log(
        None,
        module="knowledge",
        action="batch_delete_chapters",
        target_type="chapter",
        target_id="batch",
        payload={
            "ids": payload.ids,
            "removed_chapter_count": result.removed_chapter_count,
            "unbound_point_count": result.unbound_point_count,
            "missing_count": result.missing_count,
        },
    )
    return result


@router.get("/points", response_model=list[KnowledgePointResponse])
def list_points(
    subject_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[KnowledgePointResponse]:
    return KnowledgeTreeService(session).list_points(subject_id)


@router.post("/points", response_model=KnowledgePointResponse)
def create_point(
    payload: KnowledgePointUpsertRequest,
    session: Session = Depends(get_session),
) -> KnowledgePointResponse:
    result = KnowledgeTreeService(session).create_point(payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="create_point",
        target_type="knowledge_point",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.post("/points/import-markdown", response_model=KnowledgePointMarkdownImportResponse)
def import_points_from_markdown(
    payload: KnowledgePointMarkdownImportRequest,
    session: Session = Depends(get_session),
) -> KnowledgePointMarkdownImportResponse:
    result = KnowledgeTreeService(session).import_points_from_markdown(payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="import_points_markdown",
        target_type="subject",
        target_id=result.subject_id,
        payload={
            "subject_id": payload.subject_id,
            "import_mode": payload.import_mode,
            "point_created": result.point_created,
            "point_skipped": result.point_skipped,
        },
    )
    return result


@router.patch("/points/{point_id}", response_model=KnowledgePointResponse)
def update_point(
    point_id: int,
    payload: KnowledgePointUpsertRequest,
    session: Session = Depends(get_session),
) -> KnowledgePointResponse:
    result = KnowledgeTreeService(session).update_point(point_id, payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="update_point",
        target_type="knowledge_point",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.get("/textbooks", response_model=list[TextbookResponse])
def list_textbooks(
    subject_id: int | None = Query(default=None),
    session: Session = Depends(get_session),
) -> list[TextbookResponse]:
    return KnowledgeTreeService(session).list_textbooks(subject_id)


@router.post("/textbooks", response_model=TextbookResponse)
def create_textbook(
    payload: TextbookUpsertRequest,
    session: Session = Depends(get_session),
) -> TextbookResponse:
    result = KnowledgeTreeService(session).create_textbook(payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="create_textbook",
        target_type="textbook",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.patch("/textbooks/{textbook_id}", response_model=TextbookResponse)
def update_textbook(
    textbook_id: int,
    payload: TextbookUpsertRequest,
    session: Session = Depends(get_session),
) -> TextbookResponse:
    result = KnowledgeTreeService(session).update_textbook(textbook_id, payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="update_textbook",
        target_type="textbook",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.post("/textbooks/{textbook_id}/auto-build-outline", response_model=TextbookAutoBuildResponse)
def auto_build_textbook_outline(
    textbook_id: int,
    payload: TextbookAutoBuildRequest | None = None,
    session: Session = Depends(get_session),
) -> TextbookAutoBuildResponse:
    effective_payload = payload or TextbookAutoBuildRequest()
    result = KnowledgeTreeService(session).auto_build_textbook_outline(textbook_id, effective_payload, operator_id=None)
    AuditService(session).log(
        None,
        module="knowledge",
        action="auto_build_textbook_outline",
        target_type="textbook",
        target_id=textbook_id,
        payload={**effective_payload.model_dump(), "chapter_created": result.chapter_created, "point_created": result.point_created},
    )
    return result

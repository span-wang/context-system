from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session, require_roles
from app.schemas.auth import CurrentUserResponse
from app.schemas.knowledge import (
    ChapterResponse,
    ChapterUpsertRequest,
    KnowledgePointResponse,
    KnowledgePointUpsertRequest,
    SubjectCategoryResponse,
    SubjectCategoryUpsertRequest,
    SubjectResponse,
    SubjectUpsertRequest,
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
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> SubjectResponse:
    result = KnowledgeTreeService(session).create_subject(payload, operator_id=current_user.id)
    AuditService(session).log(
        current_user,
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
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> SubjectResponse:
    result = KnowledgeTreeService(session).update_subject(subject_id, payload, operator_id=current_user.id)
    AuditService(session).log(
        current_user,
        module="knowledge",
        action="update_subject",
        target_type="subject",
        target_id=result.id,
        payload=payload.model_dump(),
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
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> SubjectCategoryResponse:
    result = KnowledgeTreeService(session).create_category(payload, operator_id=current_user.id)
    AuditService(session).log(
        current_user,
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
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> SubjectCategoryResponse:
    result = KnowledgeTreeService(session).update_category(category_id, payload, operator_id=current_user.id)
    AuditService(session).log(
        current_user,
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
    session: Session = Depends(get_session),
) -> list[ChapterResponse]:
    return KnowledgeTreeService(session).list_chapters(subject_id)


@router.post("/chapters", response_model=ChapterResponse)
def create_chapter(
    payload: ChapterUpsertRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> ChapterResponse:
    result = KnowledgeTreeService(session).create_chapter(payload, operator_id=current_user.id)
    AuditService(session).log(
        current_user,
        module="knowledge",
        action="create_chapter",
        target_type="chapter",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.patch("/chapters/{chapter_id}", response_model=ChapterResponse)
def update_chapter(
    chapter_id: int,
    payload: ChapterUpsertRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> ChapterResponse:
    result = KnowledgeTreeService(session).update_chapter(chapter_id, payload, operator_id=current_user.id)
    AuditService(session).log(
        current_user,
        module="knowledge",
        action="update_chapter",
        target_type="chapter",
        target_id=result.id,
        payload=payload.model_dump(),
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
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> KnowledgePointResponse:
    result = KnowledgeTreeService(session).create_point(payload, operator_id=current_user.id)
    AuditService(session).log(
        current_user,
        module="knowledge",
        action="create_point",
        target_type="knowledge_point",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result


@router.patch("/points/{point_id}", response_model=KnowledgePointResponse)
def update_point(
    point_id: int,
    payload: KnowledgePointUpsertRequest,
    session: Session = Depends(get_session),
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> KnowledgePointResponse:
    result = KnowledgeTreeService(session).update_point(point_id, payload, operator_id=current_user.id)
    AuditService(session).log(
        current_user,
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
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> TextbookResponse:
    result = KnowledgeTreeService(session).create_textbook(payload, operator_id=current_user.id)
    AuditService(session).log(
        current_user,
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
    current_user: CurrentUserResponse = Depends(require_roles("admin", "teacher", "operator")),
) -> TextbookResponse:
    result = KnowledgeTreeService(session).update_textbook(textbook_id, payload, operator_id=current_user.id)
    AuditService(session).log(
        current_user,
        module="knowledge",
        action="update_textbook",
        target_type="textbook",
        target_id=result.id,
        payload=payload.model_dump(),
    )
    return result

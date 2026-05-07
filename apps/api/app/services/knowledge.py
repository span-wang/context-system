from __future__ import annotations

import hashlib
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, Chapter, KnowledgePoint, Subject, SubjectCategory
from app.repositories.knowledge import KnowledgeRepository
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


class KnowledgeTreeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = KnowledgeRepository(session)

    def list_subjects(self) -> list[SubjectResponse]:
        return [SubjectResponse.model_validate(item) for item in self.repository.list_subjects()]

    def create_subject(self, payload: SubjectUpsertRequest, operator_id: int | None = None) -> SubjectResponse:
        tenant_id = self._default_tenant_id()
        subject = self.repository.create_subject(
            Subject(
                tenant_id=tenant_id,
                code=_required_text(payload.code, "学科编码"),
                name=_required_text(payload.name, "学科名称"),
                status=_normalized_status(payload.status),
                created_by=operator_id,
                updated_by=operator_id,
            )
        )
        self.session.commit()
        return SubjectResponse.model_validate(subject)

    def update_subject(self, subject_id: int, payload: SubjectUpsertRequest, operator_id: int | None = None) -> SubjectResponse:
        subject = self.repository.get_subject(subject_id)
        if subject is None:
            raise HTTPException(status_code=404, detail="学科不存在")
        subject.code = _required_text(payload.code, "学科编码")
        subject.name = _required_text(payload.name, "学科名称")
        subject.status = _normalized_status(payload.status)
        subject.updated_by = operator_id
        self.session.commit()
        return SubjectResponse.model_validate(subject)

    def list_categories(self, subject_id: int | None = None) -> list[SubjectCategoryResponse]:
        return [SubjectCategoryResponse.model_validate(item) for item in self.repository.list_categories(subject_id)]

    def create_category(
        self,
        payload: SubjectCategoryUpsertRequest,
        operator_id: int | None = None,
    ) -> SubjectCategoryResponse:
        subject = self._require_subject(payload.subject_id)
        category = self.repository.create_category(
            SubjectCategory(
                tenant_id=subject.tenant_id,
                subject_id=subject.id,
                name=_required_text(payload.name, "类目名称"),
                sort_order=payload.sort_order,
                created_by=operator_id,
                updated_by=operator_id,
            )
        )
        self.session.commit()
        return SubjectCategoryResponse.model_validate(category)

    def update_category(
        self,
        category_id: int,
        payload: SubjectCategoryUpsertRequest,
        operator_id: int | None = None,
    ) -> SubjectCategoryResponse:
        category = self.repository.get_category(category_id)
        if category is None:
            raise HTTPException(status_code=404, detail="类目不存在")
        self._require_subject(payload.subject_id)
        category.subject_id = payload.subject_id
        category.name = _required_text(payload.name, "类目名称")
        category.sort_order = payload.sort_order
        category.updated_by = operator_id
        self.session.commit()
        return SubjectCategoryResponse.model_validate(category)

    def list_chapters(self, subject_id: int | None = None) -> list[ChapterResponse]:
        return [ChapterResponse.model_validate(item) for item in self.repository.list_chapters(subject_id)]

    def create_chapter(self, payload: ChapterUpsertRequest, operator_id: int | None = None) -> ChapterResponse:
        subject = self._require_subject(payload.subject_id)
        parent = self._optional_chapter(payload.parent_id, subject.id)
        name = _required_text(payload.name, "章节名称")
        level = payload.level or ((parent.level + 1) if parent else 1)
        path = _normalized_path(payload.path, name, parent.path if parent else None)
        chapter = self.repository.create_chapter(
            Chapter(
                tenant_id=subject.tenant_id,
                subject_id=subject.id,
                parent_id=parent.id if parent else None,
                name=name,
                level=level,
                path=path,
                sort_order=payload.sort_order,
                created_by=operator_id,
                updated_by=operator_id,
            )
        )
        self.session.commit()
        return ChapterResponse.model_validate(chapter)

    def update_chapter(self, chapter_id: int, payload: ChapterUpsertRequest, operator_id: int | None = None) -> ChapterResponse:
        chapter = self.repository.get_chapter(chapter_id)
        if chapter is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        subject = self._require_subject(payload.subject_id)
        parent = self._optional_chapter(payload.parent_id, subject.id, exclude_id=chapter_id)
        name = _required_text(payload.name, "章节名称")
        chapter.subject_id = subject.id
        chapter.parent_id = parent.id if parent else None
        chapter.name = name
        chapter.level = payload.level or ((parent.level + 1) if parent else 1)
        chapter.path = _normalized_path(payload.path, name, parent.path if parent else None)
        chapter.sort_order = payload.sort_order
        chapter.updated_by = operator_id
        self.session.commit()
        return ChapterResponse.model_validate(chapter)

    def list_points(self, subject_id: int | None = None) -> list[KnowledgePointResponse]:
        return [KnowledgePointResponse.model_validate(item) for item in self.repository.list_knowledge_points(subject_id)]

    def create_point(self, payload: KnowledgePointUpsertRequest, operator_id: int | None = None) -> KnowledgePointResponse:
        subject = self._require_subject(payload.subject_id)
        category = self._optional_category(payload.category_id, subject.id)
        chapter = self._optional_chapter(payload.chapter_id, subject.id)
        parent = self._optional_point(payload.parent_id, subject.id)
        name = _required_text(payload.name, "知识点名称")
        level = payload.level or ((parent.level + 1) if parent else 1)
        path = _normalized_path(payload.path, name, parent.path if parent else (chapter.path if chapter else None))
        point = self.repository.create_knowledge_point(
            KnowledgePoint(
                tenant_id=subject.tenant_id,
                subject_id=subject.id,
                category_id=category.id if category else None,
                chapter_id=chapter.id if chapter else None,
                parent_id=parent.id if parent else None,
                name=name,
                level=level,
                path=path,
                description=_optional_text(payload.description),
                keywords_json=_normalized_keywords(payload.keywords_json),
                status=_normalized_status(payload.status),
                sort_order=payload.sort_order,
                created_by=operator_id,
                updated_by=operator_id,
            )
        )
        self.session.commit()
        return KnowledgePointResponse.model_validate(point)

    def update_point(
        self,
        point_id: int,
        payload: KnowledgePointUpsertRequest,
        operator_id: int | None = None,
    ) -> KnowledgePointResponse:
        point = self.repository.get_knowledge_point(point_id)
        if point is None:
            raise HTTPException(status_code=404, detail="知识点不存在")
        subject = self._require_subject(payload.subject_id)
        category = self._optional_category(payload.category_id, subject.id)
        chapter = self._optional_chapter(payload.chapter_id, subject.id)
        parent = self._optional_point(payload.parent_id, subject.id, exclude_id=point_id)
        name = _required_text(payload.name, "知识点名称")
        point.subject_id = subject.id
        point.category_id = category.id if category else None
        point.chapter_id = chapter.id if chapter else None
        point.parent_id = parent.id if parent else None
        point.name = name
        point.level = payload.level or ((parent.level + 1) if parent else 1)
        point.path = _normalized_path(payload.path, name, parent.path if parent else (chapter.path if chapter else None))
        point.description = _optional_text(payload.description)
        point.keywords_json = _normalized_keywords(payload.keywords_json)
        point.status = _normalized_status(payload.status)
        point.sort_order = payload.sort_order
        point.updated_by = operator_id
        self.session.commit()
        return KnowledgePointResponse.model_validate(point)

    def list_textbooks(self, subject_id: int | None = None) -> list[TextbookResponse]:
        return [TextbookResponse.model_validate(self._textbook_payload(item)) for item in self.repository.list_textbooks(subject_id)]

    def create_textbook(self, payload: TextbookUpsertRequest, operator_id: int | None = None) -> TextbookResponse:
        subject = self._require_subject(payload.subject_id)
        category = self._optional_category(payload.category_id, subject.id)
        title = _required_text(payload.source_title, "教材名称")
        filename = _optional_text(payload.filename) or title
        tags = _textbook_tags(category.name if category else None, payload.source_version, payload.tags_json)
        sha_seed = f"textbook:{subject.id}:{title}:{filename}:{payload.year or ''}:{payload.source_version or ''}:{uuid.uuid4().hex}"
        asset = Asset(
            tenant_id=subject.tenant_id,
            subject_id=subject.id,
            asset_type="textbook",
            source_type="textbook",
            source_title=title,
            filename=filename,
            mime_type="application/octet-stream",
            storage_path=f"metadata/textbooks/{hashlib.sha1(sha_seed.encode('utf-8')).hexdigest()[:16]}",
            sha256=hashlib.sha256(sha_seed.encode("utf-8")).hexdigest(),
            file_size=0,
            parse_status=_optional_text(payload.parse_status) or "metadata",
            ocr_status="metadata",
            token_count=payload.token_count,
            year=payload.year,
            region=_optional_text(payload.region),
            tags_json=tags,
            created_by=operator_id,
            updated_by=operator_id,
        )
        self.session.add(asset)
        self.session.commit()
        return TextbookResponse.model_validate(self._textbook_payload(asset))

    def update_textbook(
        self,
        textbook_id: int,
        payload: TextbookUpsertRequest,
        operator_id: int | None = None,
    ) -> TextbookResponse:
        textbook = self.repository.get_textbook(textbook_id)
        if textbook is None:
            raise HTTPException(status_code=404, detail="教材不存在")
        subject = self._require_subject(payload.subject_id)
        category = self._optional_category(payload.category_id, subject.id)
        title = _required_text(payload.source_title, "教材名称")
        textbook.subject_id = subject.id
        textbook.source_title = title
        textbook.filename = _optional_text(payload.filename) or title
        textbook.asset_type = "textbook"
        textbook.source_type = "textbook"
        textbook.parse_status = _optional_text(payload.parse_status) or textbook.parse_status
        textbook.token_count = payload.token_count
        textbook.year = payload.year
        textbook.region = _optional_text(payload.region)
        textbook.tags_json = _textbook_tags(category.name if category else None, payload.source_version, payload.tags_json)
        textbook.updated_by = operator_id
        self.session.commit()
        return TextbookResponse.model_validate(self._textbook_payload(textbook))

    def _default_tenant_id(self) -> int:
        settings = get_settings()
        tenant = self.repository.get_default_tenant(settings.app.default_tenant_code)
        if tenant is None:
            raise HTTPException(status_code=500, detail="默认租户尚未初始化")
        return tenant.id

    def _require_subject(self, subject_id: int) -> Subject:
        subject = self.repository.get_subject(subject_id)
        if subject is None:
            raise HTTPException(status_code=404, detail="学科不存在")
        return subject

    def _optional_category(self, category_id: int | None, subject_id: int) -> SubjectCategory | None:
        if category_id is None:
            return None
        category = self.repository.get_category(category_id)
        if category is None:
            raise HTTPException(status_code=404, detail="类目不存在")
        if category.subject_id != subject_id:
            raise HTTPException(status_code=422, detail="类目不属于当前学科")
        return category

    def _optional_chapter(self, chapter_id: int | None, subject_id: int, exclude_id: int | None = None) -> Chapter | None:
        if chapter_id is None:
            return None
        chapter = self.repository.get_chapter(chapter_id)
        if chapter is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        if chapter.subject_id != subject_id:
            raise HTTPException(status_code=422, detail="章节不属于当前学科")
        if exclude_id is not None and chapter.id == exclude_id:
            raise HTTPException(status_code=422, detail="不能把节点自身设为父级")
        return chapter

    def _optional_point(self, point_id: int | None, subject_id: int, exclude_id: int | None = None) -> KnowledgePoint | None:
        if point_id is None:
            return None
        point = self.repository.get_knowledge_point(point_id)
        if point is None:
            raise HTTPException(status_code=404, detail="父级知识点不存在")
        if point.subject_id != subject_id:
            raise HTTPException(status_code=422, detail="父级知识点不属于当前学科")
        if exclude_id is not None and point.id == exclude_id:
            raise HTTPException(status_code=422, detail="不能把节点自身设为父级")
        return point

    def _textbook_payload(self, textbook: Asset) -> dict[str, object]:
        category_id = _category_id_from_tags(textbook.tags_json, self.repository.list_categories(textbook.subject_id))
        return {
            **textbook.__dict__,
            "category_id": category_id,
            "source_version": _tag_value(textbook.tags_json, "version:"),
        }


def _required_text(value: str | None, label: str) -> str:
    text = (value or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail=f"{label}不能为空")
    return text


def _optional_text(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _normalized_status(value: str | None) -> str:
    text = (value or "active").strip()
    return text or "active"


def _normalized_keywords(values: list[str] | None) -> list[str]:
    return [item for item in dict.fromkeys(str(value).strip() for value in values or []) if item]


def _normalized_path(path: str | None, name: str, parent_path: str | None = None) -> str:
    text = (path or "").strip().strip("/")
    if text:
        return text
    parent = (parent_path or "").strip().strip("/")
    return f"{parent}/{name}" if parent else name


def _textbook_tags(category_name: str | None, source_version: str | None, tags: list[str] | None) -> list[str]:
    values = []
    if category_name:
        values.append(f"category:{category_name}")
    if source_version:
        values.append(f"version:{source_version.strip()}")
    values.extend(str(tag).strip() for tag in tags or [])
    return [item for item in dict.fromkeys(values) if item]


def _tag_value(tags: list[str] | None, prefix: str) -> str | None:
    for tag in tags or []:
        if isinstance(tag, str) and tag.startswith(prefix):
            value = tag.removeprefix(prefix).strip()
            return value or None
    return None


def _category_id_from_tags(tags: list[str] | None, categories: list[SubjectCategory]) -> int | None:
    category_name = _tag_value(tags, "category:")
    if not category_name:
        return None
    for category in categories:
        if category.name == category_name:
            return category.id
    return None

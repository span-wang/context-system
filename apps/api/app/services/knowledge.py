from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Asset, Chapter, KnowledgePoint, ReviewTask, Subject, SubjectCategory
from app.repositories.knowledge import KnowledgeRepository
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
    SubjectDeleteSkippedItem,
    SubjectResponse,
    SubjectUpsertRequest,
    TextbookAutoBuildRequest,
    TextbookAutoBuildResponse,
    TextbookResponse,
    TextbookUpsertRequest,
)
from app.services.textbook_outline import (
    auto_keywords,
    auto_point_description,
    build_textbook_outline,
    normalized_entity_key,
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

    def delete_subject(self, subject_id: int) -> SubjectDeleteResponse:
        subject = self.repository.get_subject(subject_id)
        if subject is None:
            raise HTTPException(status_code=404, detail="学科不存在")
        response = SubjectDeleteResponse(id=subject.id, name=subject.name, deleted=True)
        self.repository.delete_subject_tree(subject.id)
        self.session.commit()
        return response

    def batch_delete_subjects(self, payload: BatchDeleteRequest) -> SubjectBatchDeleteResponse:
        deleted: list[SubjectDeleteResponse] = []
        skipped: list[SubjectDeleteSkippedItem] = []
        for subject_id in dict.fromkeys(payload.ids):
            subject = self.repository.get_subject(subject_id)
            if subject is None:
                skipped.append(SubjectDeleteSkippedItem(id=subject_id, reason="学科不存在"))
                continue
            deleted.append(SubjectDeleteResponse(id=subject.id, name=subject.name, deleted=True))
            self.repository.delete_subject_tree(subject.id)
        self.session.commit()
        return SubjectBatchDeleteResponse(
            requested_count=len(payload.ids),
            deleted_count=len(deleted),
            skipped_count=len(skipped),
            deleted=deleted,
            skipped=skipped,
            message=f"已删除 {len(deleted)} 个学科，跳过 {len(skipped)} 个。",
        )

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

    def list_chapters(self, subject_id: int | None = None, category_id: int | None = None) -> list[ChapterResponse]:
        return [ChapterResponse.model_validate(item) for item in self.repository.list_chapters(subject_id, category_id)]

    def create_chapter(self, payload: ChapterUpsertRequest, operator_id: int | None = None) -> ChapterResponse:
        subject = self._require_subject(payload.subject_id)
        parent = self._optional_chapter(payload.parent_id, subject.id)
        category = self._resolved_chapter_category(subject.id, payload.category_id, parent)
        name = _required_text(payload.name, "章节名称")
        level = payload.level or ((parent.level + 1) if parent else 1)
        path = _normalized_path(payload.path, name, parent.path if parent else None)
        chapter = self.repository.create_chapter(
            Chapter(
                tenant_id=subject.tenant_id,
                subject_id=subject.id,
                category_id=category.id,
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
        category = self._resolved_chapter_category(subject.id, payload.category_id, parent)
        name = _required_text(payload.name, "章节名称")
        chapter.subject_id = subject.id
        chapter.category_id = category.id
        chapter.parent_id = parent.id if parent else None
        chapter.name = name
        chapter.level = payload.level or ((parent.level + 1) if parent else 1)
        chapter.path = _normalized_path(payload.path, name, parent.path if parent else None)
        chapter.sort_order = payload.sort_order
        chapter.updated_by = operator_id
        self._sync_chapter_tree(chapter)
        self.session.commit()
        return ChapterResponse.model_validate(chapter)

    def delete_chapter(self, chapter_id: int) -> ChapterDeleteResponse:
        chapter = self.repository.get_chapter(chapter_id)
        if chapter is None:
            raise HTTPException(status_code=404, detail="章节不存在")
        chapter_ids = self.repository.descendant_chapter_ids(chapter.id)
        point_ids = self.repository.point_ids_by_chapter_ids(chapter_ids)
        response = ChapterDeleteResponse(
            id=chapter.id,
            name=chapter.name,
            deleted=True,
            removed_chapter_count=len(chapter_ids),
            unbound_point_count=0,
        )
        response.unbound_point_count = self.repository.delete_knowledge_points(point_ids)
        response.removed_chapter_count = self.repository.delete_chapters(chapter_ids)
        self.session.commit()
        return response

    def batch_delete_chapters(self, payload: BatchDeleteRequest) -> ChapterBatchDeleteResponse:
        requested_ids = list(dict.fromkeys(payload.ids))
        all_ids: set[int] = set()
        missing_count = 0
        for chapter_id in requested_ids:
            chapter = self.repository.get_chapter(chapter_id)
            if chapter is None:
                missing_count += 1
                continue
            all_ids.update(self.repository.descendant_chapter_ids(chapter.id))
        point_ids = self.repository.point_ids_by_chapter_ids(list(all_ids))
        unbound_point_count = self.repository.delete_knowledge_points(point_ids)
        removed_chapter_count = self.repository.delete_chapters(list(all_ids))
        self.session.commit()
        return ChapterBatchDeleteResponse(
            requested_count=len(requested_ids),
            removed_chapter_count=removed_chapter_count,
            unbound_point_count=unbound_point_count,
            missing_count=missing_count,
            message=f"已删除 {removed_chapter_count} 个章节，解绑 {unbound_point_count} 个知识点。",
        )

    def import_chapters_from_markdown(
        self,
        payload: ChapterMarkdownImportRequest,
        operator_id: int | None = None,
    ) -> ChapterMarkdownImportResponse:
        subject = self._require_subject(payload.subject_id)
        category = self._require_category(payload.category_id, subject.id, detail="请先选择类目后再导入章节目录")
        drafts = _parse_chapter_markdown(payload.markdown)
        if not drafts:
            raise HTTPException(status_code=422, detail="未从 Markdown 中解析到章节目录")

        existing_chapters = self.repository.list_chapters(subject.id, category.id)
        chapters_by_path_key = {normalized_entity_key(chapter.path or chapter.name): chapter for chapter in existing_chapters}
        sort_by_parent: dict[int | None, int] = {}
        for chapter in existing_chapters:
            parent_key = chapter.parent_id
            sort_by_parent[parent_key] = max(sort_by_parent.get(parent_key, 0), chapter.sort_order)

        stack: dict[int, Chapter] = {}
        numbered_chapters: dict[str, Chapter] = {}
        touched_chapters: list[Chapter] = []
        chapter_created = 0
        chapter_skipped = 0

        for draft in drafts:
            parent = numbered_chapters.get(draft.parent_key or "") if draft.parent_key else _nearest_stack_parent(stack, draft.level)
            if draft.level > 1 and parent is None:
                raise HTTPException(status_code=422, detail=f"节「{draft.name}」缺少对应的章")
            path = _normalized_path(None, draft.name, parent.path if parent else None)
            path_key = normalized_entity_key(path)
            chapter = chapters_by_path_key.get(path_key)
            if chapter is not None:
                chapter_skipped += 1
            else:
                parent_key = parent.id if parent else None
                sort_order = sort_by_parent.get(parent_key, 0) + 1
                sort_by_parent[parent_key] = sort_order
                chapter = self.repository.create_chapter(
                    Chapter(
                        tenant_id=subject.tenant_id,
                        subject_id=subject.id,
                        category_id=category.id,
                        parent_id=parent.id if parent else None,
                        name=draft.name,
                        level=(parent.level + 1) if parent else 1,
                        path=path,
                        sort_order=sort_order,
                        created_by=operator_id,
                        updated_by=operator_id,
                    )
                )
                chapters_by_path_key[path_key] = chapter
                chapter_created += 1

            if chapter is not None:
                touched_chapters.append(chapter)
                stack = {level: item for level, item in stack.items() if level < draft.level}
                stack[draft.level] = chapter
                if draft.key:
                    numbered_chapters[draft.key] = chapter

        self.session.commit()
        return ChapterMarkdownImportResponse(
            subject_id=subject.id,
            chapter_created=chapter_created,
            chapter_skipped=chapter_skipped,
            chapters=[ChapterResponse.model_validate(item) for item in touched_chapters],
            message=f"已导入 {chapter_created} 个章节；跳过 {chapter_skipped} 个已有或重复章节。",
        )

    def list_points(self, subject_id: int | None = None) -> list[KnowledgePointResponse]:
        return [KnowledgePointResponse.model_validate(item) for item in self.repository.list_knowledge_points(subject_id)]

    def create_point(self, payload: KnowledgePointUpsertRequest, operator_id: int | None = None) -> KnowledgePointResponse:
        subject = self._require_subject(payload.subject_id)
        parent = self._optional_detail_parent(payload.parent_id, subject.id)
        category, chapter = self._resolved_point_binding(
            subject_id=subject.id,
            parent=parent,
            category_id=payload.category_id,
            chapter_id=payload.chapter_id,
        )
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
        parent = self._optional_detail_parent(payload.parent_id, subject.id, exclude_id=point_id)
        category, chapter = self._resolved_point_binding(
            subject_id=subject.id,
            parent=parent,
            category_id=payload.category_id,
            chapter_id=payload.chapter_id,
            allow_non_bindable_id=point.chapter_id,
        )
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

    def import_points_from_markdown(
        self,
        payload: KnowledgePointMarkdownImportRequest,
        operator_id: int | None = None,
    ) -> KnowledgePointMarkdownImportResponse:
        if payload.import_mode == "detail":
            return self._import_point_details_from_markdown(payload, operator_id=operator_id)

        subject = self._require_subject(payload.subject_id)
        category = self._require_category(payload.category_id, subject.id, detail="请先选择类目后再导入知识点")
        drafts = _parse_point_markdown(payload.markdown)
        if not drafts:
            raise HTTPException(status_code=422, detail="未从 Markdown 中解析到知识点目录")

        subject_chapters = self.repository.list_chapters(subject.id, category.id)
        if not subject_chapters:
            raise HTTPException(status_code=422, detail=f"类目「{category.name}」下暂无章节，请先导入章节目录")

        chapters_by_id = {chapter.id: chapter for chapter in subject_chapters}
        root_chapters_by_name = {
            normalized_entity_key(chapter.name): chapter
            for chapter in subject_chapters
            if chapter.parent_id is None
        }
        chapter_children = {
            chapter.id: [child for child in subject_chapters if child.parent_id == chapter.id]
            for chapter in subject_chapters
        }
        section_by_parent_and_name = {
            (child.parent_id, normalized_entity_key(child.name)): child
            for child in subject_chapters
            if child.parent_id is not None
        }
        existing_points = self.repository.list_knowledge_points(subject.id)
        points_by_binding = {
            (point.chapter_id, normalized_entity_key(point.name)): point
            for point in existing_points
            if point.chapter_id is not None and point.parent_id is None
        }
        sort_by_chapter: dict[int, int] = {}
        for point in existing_points:
            if point.chapter_id is None or point.parent_id is not None:
                continue
            sort_by_chapter[point.chapter_id] = max(sort_by_chapter.get(point.chapter_id, 0), point.sort_order)

        point_created = 0
        point_skipped = 0
        touched_points: list[KnowledgePoint] = []
        touched_point_ids: set[int] = set()

        for draft in drafts:
            chapter = root_chapters_by_name.get(normalized_entity_key(draft.chapter_name))
            if chapter is None:
                raise HTTPException(status_code=422, detail=f"章节「{draft.chapter_name}」不存在，请先导入对应目录")

            binding_chapter = chapter
            section_name = draft.section_name
            if section_name:
                binding_chapter = section_by_parent_and_name.get((chapter.id, normalized_entity_key(section_name)))
                if binding_chapter is None:
                    raise HTTPException(status_code=422, detail=f"章节「{chapter.name}」下不存在节「{section_name}」")
            elif chapter_children.get(chapter.id):
                raise HTTPException(status_code=422, detail=f"知识点「{draft.name}」缺少所属节，请绑定到章节「{chapter.name}」下的具体节")

            if binding_chapter is None or chapters_by_id.get(binding_chapter.id) is None:
                raise HTTPException(status_code=422, detail=f"知识点「{draft.name}」缺少可绑定的章节")

            point_key = (binding_chapter.id, normalized_entity_key(draft.name))
            point = points_by_binding.get(point_key)
            if point is None:
                next_sort_order = sort_by_chapter.get(binding_chapter.id, 0) + 1
                sort_by_chapter[binding_chapter.id] = next_sort_order
                point = self.repository.create_knowledge_point(
                    KnowledgePoint(
                        tenant_id=subject.tenant_id,
                        subject_id=subject.id,
                        category_id=category.id,
                        chapter_id=binding_chapter.id,
                        parent_id=None,
                        name=draft.name,
                        level=1,
                        path=_normalized_path(None, draft.name, binding_chapter.path),
                        description=None,
                        keywords_json=[],
                        status="active",
                        sort_order=next_sort_order,
                        created_by=operator_id,
                        updated_by=operator_id,
                    )
                )
                points_by_binding[point_key] = point
                point_created += 1
            else:
                point_skipped += 1

            if point.id not in touched_point_ids:
                touched_points.append(point)
                touched_point_ids.add(point.id)

        self.session.commit()
        return KnowledgePointMarkdownImportResponse(
            subject_id=subject.id,
            point_created=point_created,
            point_skipped=point_skipped,
            points=[KnowledgePointResponse.model_validate(item) for item in touched_points],
            message=f"已导入 {point_created} 个知识点；跳过 {point_skipped} 个已有或重复知识点。",
        )

    def _import_point_details_from_markdown(
        self,
        payload: KnowledgePointMarkdownImportRequest,
        operator_id: int | None = None,
    ) -> KnowledgePointMarkdownImportResponse:
        subject = self._require_subject(payload.subject_id)
        category = self._require_category(payload.category_id, subject.id, detail="请先选择类目后再导入知识点详情")
        drafts = _parse_point_detail_markdown(payload.markdown)
        if not drafts:
            raise HTTPException(status_code=422, detail="未从 Markdown 中解析到知识点详情目录")

        subject_chapters = self.repository.list_chapters(subject.id, category.id)
        if not subject_chapters:
            raise HTTPException(status_code=422, detail=f"类目「{category.name}」下暂无章节，请先导入章节目录")

        root_chapters_by_name = {
            normalized_entity_key(chapter.name): chapter
            for chapter in subject_chapters
            if chapter.parent_id is None
        }
        chapter_children = {
            chapter.id: [child for child in subject_chapters if child.parent_id == chapter.id]
            for chapter in subject_chapters
        }
        section_by_parent_and_name = {
            (child.parent_id, normalized_entity_key(child.name)): child
            for child in subject_chapters
            if child.parent_id is not None
        }
        existing_points = self.repository.list_knowledge_points(subject.id)
        root_points_by_binding = {
            (point.chapter_id, normalized_entity_key(point.name)): point
            for point in existing_points
            if point.chapter_id is not None and point.parent_id is None
        }
        detail_points_by_parent = {
            (point.parent_id, normalized_entity_key(point.name)): point
            for point in existing_points
            if point.parent_id is not None
        }
        sort_by_parent: dict[int, int] = {}
        for point in existing_points:
            if point.parent_id is None:
                continue
            sort_by_parent[point.parent_id] = max(sort_by_parent.get(point.parent_id, 0), point.sort_order)

        point_created = 0
        point_skipped = 0
        touched_points: list[KnowledgePoint] = []
        touched_point_ids: set[int] = set()

        for draft in drafts:
            chapter = root_chapters_by_name.get(normalized_entity_key(draft.chapter_name))
            if chapter is None:
                raise HTTPException(status_code=422, detail=f"章节「{draft.chapter_name}」不存在，请先导入对应目录")

            binding_chapter = chapter
            if draft.section_name:
                binding_chapter = section_by_parent_and_name.get((chapter.id, normalized_entity_key(draft.section_name)))
                if binding_chapter is None:
                    raise HTTPException(status_code=422, detail=f"章节「{chapter.name}」下不存在节「{draft.section_name}」")
            elif chapter_children.get(chapter.id):
                raise HTTPException(status_code=422, detail=f"知识点「{draft.point_name}」缺少所属节，请绑定到章节「{chapter.name}」下的具体节")

            if binding_chapter is None:
                raise HTTPException(status_code=422, detail=f"知识点「{draft.point_name}」缺少可绑定的章节")

            parent_point = root_points_by_binding.get((binding_chapter.id, normalized_entity_key(draft.point_name)))
            if parent_point is None:
                raise HTTPException(status_code=422, detail=f"节「{binding_chapter.name}」下不存在知识点「{draft.point_name}」")

            detail_key = (parent_point.id, normalized_entity_key(draft.detail_name))
            point = detail_points_by_parent.get(detail_key)
            if point is None:
                next_sort_order = sort_by_parent.get(parent_point.id, 0) + 1
                sort_by_parent[parent_point.id] = next_sort_order
                point = self.repository.create_knowledge_point(
                    KnowledgePoint(
                        tenant_id=subject.tenant_id,
                        subject_id=subject.id,
                        category_id=parent_point.category_id,
                        chapter_id=parent_point.chapter_id,
                        parent_id=parent_point.id,
                        name=draft.detail_name,
                        level=parent_point.level + 1,
                        path=_normalized_path(None, draft.detail_name, parent_point.path),
                        description=None,
                        keywords_json=[],
                        status="active",
                        sort_order=next_sort_order,
                        created_by=operator_id,
                        updated_by=operator_id,
                    )
                )
                detail_points_by_parent[detail_key] = point
                point_created += 1
            else:
                point_skipped += 1

            if point.id not in touched_point_ids:
                touched_points.append(point)
                touched_point_ids.add(point.id)

        self.session.commit()
        return KnowledgePointMarkdownImportResponse(
            subject_id=subject.id,
            point_created=point_created,
            point_skipped=point_skipped,
            points=[KnowledgePointResponse.model_validate(item) for item in touched_points],
            message=f"已导入 {point_created} 个知识点详情；跳过 {point_skipped} 个已有或重复知识点详情。",
        )

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

    def auto_build_textbook_outline(
        self,
        textbook_id: int,
        payload: TextbookAutoBuildRequest | None = None,
        operator_id: int | None = None,
    ) -> TextbookAutoBuildResponse:
        payload = payload or TextbookAutoBuildRequest()
        textbook = self.repository.get_textbook(textbook_id)
        if textbook is None:
            raise HTTPException(status_code=404, detail="教材不存在")
        if textbook.subject_id is None:
            raise HTTPException(status_code=422, detail="教材尚未绑定学科")

        subject = self._require_subject(textbook.subject_id)
        categories = self.repository.list_categories(subject.id)
        category_id = _category_id_from_tags(textbook.tags_json, categories)
        category = next((item for item in categories if item.id == category_id), None)
        if category is None:
            raise HTTPException(status_code=422, detail="请先为教材选择类目，再生成章节和知识点")
        source, drafts = build_textbook_outline(
            textbook,
            subject,
            category,
            max_chapters=payload.max_chapters,
            points_per_chapter=payload.knowledge_points_per_chapter,
        )
        if not drafts:
            raise HTTPException(status_code=422, detail="未能从教材信息生成章节候选")

        existing_chapters = self.repository.list_chapters(subject.id, category.id)
        existing_points = self.repository.list_knowledge_points(subject.id)
        chapters_by_key: dict[str, Chapter] = {}
        for chapter in existing_chapters:
            chapters_by_key[normalized_entity_key(chapter.name)] = chapter
            chapters_by_key[normalized_entity_key(chapter.path or chapter.name)] = chapter
        points_by_chapter = {
            (point.chapter_id, normalized_entity_key(point.name))
            for point in existing_points
            if point.chapter_id is not None
        }
        point_sort_by_chapter: dict[int, int] = {}
        for point in existing_points:
            if point.chapter_id is None:
                continue
            point_sort_by_chapter[point.chapter_id] = max(point_sort_by_chapter.get(point.chapter_id, 0), point.sort_order)

        chapter_created = 0
        chapter_skipped = 0
        point_created = 0
        point_skipped = 0
        review_task_created = 0
        touched_chapters: list[Chapter] = []
        touched_points: list[KnowledgePoint] = []
        next_chapter_sort = max((chapter.sort_order for chapter in existing_chapters), default=0)

        for draft in drafts:
            chapter_name = _required_text(draft.name, "章节名称")
            chapter_key = normalized_entity_key(chapter_name)
            chapter = chapters_by_key.get(chapter_key)
            if chapter is None:
                next_chapter_sort += 1
                chapter = self.repository.create_chapter(
                    Chapter(
                        tenant_id=subject.tenant_id,
                        subject_id=subject.id,
                        category_id=category.id,
                        parent_id=None,
                        name=chapter_name,
                        level=1,
                        path=chapter_name,
                        sort_order=next_chapter_sort,
                        created_by=operator_id,
                        updated_by=operator_id,
                    )
                )
                chapters_by_key[chapter_key] = chapter
                chapter_created += 1
                review_task_created += self._create_review_task(
                    tenant_id=subject.tenant_id,
                    task_type="chapter_review",
                    target_type="chapter",
                    target_id=chapter.id,
                    operator_id=operator_id,
                    note=f"自动生成自教材《{textbook.source_title}》，请审核章节名称和排序。",
                )
            else:
                chapter_skipped += 1
            touched_chapters.append(chapter)

            for point_name in draft.points[: payload.knowledge_points_per_chapter]:
                point_name = _required_text(point_name, "知识点名称")
                point_key = (chapter.id, normalized_entity_key(point_name))
                if point_key in points_by_chapter:
                    point_skipped += 1
                    continue
                next_point_sort = point_sort_by_chapter.get(chapter.id, 0) + 1
                point_sort_by_chapter[chapter.id] = next_point_sort
                point = self.repository.create_knowledge_point(
                    KnowledgePoint(
                        tenant_id=subject.tenant_id,
                        subject_id=subject.id,
                        category_id=category.id if category else None,
                        chapter_id=chapter.id,
                        parent_id=None,
                        name=point_name,
                        level=1,
                        path=f"{chapter.path}/{point_name}",
                        description=auto_point_description(textbook),
                        keywords_json=auto_keywords(point_name, chapter.name, textbook, subject, category),
                        status="draft",
                        sort_order=next_point_sort,
                        created_by=operator_id,
                        updated_by=operator_id,
                    )
                )
                points_by_chapter.add(point_key)
                touched_points.append(point)
                point_created += 1
                review_task_created += self._create_review_task(
                    tenant_id=subject.tenant_id,
                    task_type="knowledge_point_review",
                    target_type="knowledge_point",
                    target_id=point.id,
                    operator_id=operator_id,
                    note=f"自动生成自教材《{textbook.source_title}》，请审核知识点名称、关键词和章节归属。",
                )

        textbook.parse_status = "outlined" if source == "metadata" else "parsed"
        textbook.updated_by = operator_id
        self.session.commit()
        return TextbookAutoBuildResponse(
            textbook_id=textbook.id,
            subject_id=subject.id,
            source=source,
            chapter_created=chapter_created,
            chapter_skipped=chapter_skipped,
            point_created=point_created,
            point_skipped=point_skipped,
            review_task_created=review_task_created,
            chapters=[ChapterResponse.model_validate(item) for item in touched_chapters],
            points=[KnowledgePointResponse.model_validate(item) for item in touched_points],
            message=f"已生成 {chapter_created} 个章节、{point_created} 个待审核知识点；跳过 {chapter_skipped} 个已有章节、{point_skipped} 个已有知识点。",
        )

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

    def _require_category(self, category_id: int | None, subject_id: int, detail: str = "类目不能为空") -> SubjectCategory:
        if category_id is None:
            raise HTTPException(status_code=422, detail=detail)
        category = self._optional_category(category_id, subject_id)
        if category is None:
            raise HTTPException(status_code=422, detail=detail)
        return category

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

    def _resolved_chapter_category(
        self,
        subject_id: int,
        category_id: int | None,
        parent: Chapter | None,
    ) -> SubjectCategory:
        if parent is not None:
            if parent.category_id is None:
                raise HTTPException(status_code=422, detail="父级章节尚未绑定类目，请先修复父级章节")
            if category_id is not None and category_id != parent.category_id:
                raise HTTPException(status_code=422, detail="子章节必须与父级章节属于同一类目")
            return self._require_category(parent.category_id, subject_id)
        return self._require_category(category_id, subject_id, detail="章节必须绑定到类目下")

    def _optional_bindable_chapter(
        self,
        chapter_id: int | None,
        subject_id: int,
        allow_non_bindable_id: int | None = None,
        category_id: int | None = None,
    ) -> Chapter | None:
        chapter = self._optional_chapter(chapter_id, subject_id)
        if chapter is None:
            return None
        if category_id is not None and chapter.category_id not in {None, category_id}:
            raise HTTPException(status_code=422, detail="章节不属于当前类目")
        if self.repository.chapter_has_children(chapter.id) and chapter.id != allow_non_bindable_id:
            raise HTTPException(status_code=422, detail="知识点请绑定到具体的节，不能直接绑定到章")
        return chapter

    def _resolved_point_binding(
        self,
        *,
        subject_id: int,
        parent: KnowledgePoint | None,
        category_id: int | None,
        chapter_id: int | None,
        allow_non_bindable_id: int | None = None,
    ) -> tuple[SubjectCategory | None, Chapter | None]:
        if parent is not None:
            category = self._optional_category(parent.category_id, subject_id)
            chapter = self._optional_bindable_chapter(
                parent.chapter_id,
                subject_id,
                allow_non_bindable_id=allow_non_bindable_id,
                category_id=category.id if category else None,
            )
            return category, chapter

        requested_category = self._optional_category(category_id, subject_id)
        chapter = self._optional_bindable_chapter(
            chapter_id,
            subject_id,
            allow_non_bindable_id=allow_non_bindable_id,
            category_id=requested_category.id if requested_category else None,
        )
        if chapter is not None:
            if chapter.category_id is None:
                raise HTTPException(status_code=422, detail="当前章节尚未绑定类目，请先修复章节类目")
            category = self._require_category(chapter.category_id, subject_id)
            if requested_category is not None and requested_category.id != category.id:
                raise HTTPException(status_code=422, detail="知识点类目必须与所选章节一致")
            return category, chapter

        return requested_category, None

    def _sync_chapter_tree(self, chapter: Chapter) -> None:
        descendants = [
            item
            for item in self.repository.list_chapters()
            if item.id != chapter.id and item.parent_id is not None
        ]
        descendants_by_parent: dict[int, list[Chapter]] = {}
        for item in descendants:
            descendants_by_parent.setdefault(item.parent_id, []).append(item)

        pending = [chapter]
        while pending:
            current = pending.pop()
            children = descendants_by_parent.get(current.id, [])
            for child in children:
                child.subject_id = current.subject_id
                child.category_id = current.category_id
                child.level = current.level + 1
                child.path = _normalized_path(None, child.name, current.path)
                pending.append(child)

        point_map = self.repository.list_knowledge_points()
        chapter_by_id = {item.id: item for item in self.repository.list_chapters()}
        root_points_by_chapter: dict[int, list[KnowledgePoint]] = {}
        detail_points_by_parent: dict[int, list[KnowledgePoint]] = {}
        for point in point_map:
            if point.parent_id is None and point.chapter_id is not None:
                root_points_by_chapter.setdefault(point.chapter_id, []).append(point)
            elif point.parent_id is not None:
                detail_points_by_parent.setdefault(point.parent_id, []).append(point)

        pending_chapter_ids = [chapter.id]
        while pending_chapter_ids:
            current_id = pending_chapter_ids.pop()
            current_chapter = chapter_by_id.get(current_id)
            if current_chapter is None:
                continue
            for point in root_points_by_chapter.get(current_id, []):
                point.subject_id = current_chapter.subject_id
                point.category_id = current_chapter.category_id
                point.path = _normalized_path(None, point.name, current_chapter.path)
                self._sync_point_detail_tree(point, detail_points_by_parent)
            pending_chapter_ids.extend(child.id for child in descendants_by_parent.get(current_id, []))

    def _sync_point_detail_tree(
        self,
        point: KnowledgePoint,
        detail_points_by_parent: dict[int, list[KnowledgePoint]],
    ) -> None:
        for detail in detail_points_by_parent.get(point.id, []):
            detail.subject_id = point.subject_id
            detail.category_id = point.category_id
            detail.chapter_id = point.chapter_id
            detail.level = point.level + 1
            detail.path = _normalized_path(None, detail.name, point.path)
            self._sync_point_detail_tree(detail, detail_points_by_parent)

    def _optional_detail_parent(
        self,
        point_id: int | None,
        subject_id: int,
        exclude_id: int | None = None,
    ) -> KnowledgePoint | None:
        parent = self._optional_point(point_id, subject_id, exclude_id=exclude_id)
        if parent is not None and parent.parent_id is not None:
            raise HTTPException(status_code=422, detail="知识点详情只能挂在一级知识点下")
        return parent

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

    def _create_review_task(
        self,
        *,
        tenant_id: int,
        task_type: str,
        target_type: str,
        target_id: int,
        operator_id: int | None,
        note: str,
    ) -> int:
        existing_task_id = self.session.scalar(
            select(ReviewTask.id).where(
                ReviewTask.task_type == task_type,
                ReviewTask.target_type == target_type,
                ReviewTask.target_id == str(target_id),
                ReviewTask.status != "completed",
            )
        )
        if existing_task_id is not None:
            return 0
        self.session.add(
            ReviewTask(
                tenant_id=tenant_id,
                task_type=task_type,
                target_type=target_type,
                target_id=str(target_id),
                status="pending",
                assigned_to=operator_id,
                priority="medium",
                review_note=note[:255],
                created_by=operator_id,
                updated_by=operator_id,
            )
        )
        self.session.flush()
        return 1


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


@dataclass(frozen=True)
class _ChapterImportDraft:
    level: int
    name: str
    key: str | None = None
    parent_key: str | None = None


@dataclass(frozen=True)
class _KnowledgePointImportDraft:
    chapter_name: str
    section_name: str | None
    name: str


@dataclass(frozen=True)
class _KnowledgePointDetailImportDraft:
    chapter_name: str
    section_name: str | None
    point_name: str
    detail_name: str


_MARKDOWN_HEADING_PATTERN = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_MARKDOWN_LIST_PATTERN = re.compile(r"^(\s*)[-*+]\s+(.+)$")
_NUMBERED_OUTLINE_PATTERN = re.compile(r"^\s*(\d+(?:[.．]\d+)*)\s+(.+)$")
_TOP_NUMBERED_PATTERN = re.compile(r"^\s*(\d+|[一二三四五六七八九十百千万]+)[.)）、.．](?!\d)\s*(.+)$")
_CHINESE_CHAPTER_PATTERN = re.compile(r"^\s*(第[零〇一二三四五六七八九十百千万\d]+[章篇编单元讲部分].*)$")
_CHINESE_SECTION_PATTERN = re.compile(r"^\s*(第[零〇一二三四五六七八九十百千万\d]+节.*)$")
_POINT_LABEL_PATTERN = re.compile(r"^(?:知识点|考点|要点)\s*[零〇一二三四五六七八九十百千万\d]*[\s　、.．:：-]*(.+)$")
_INLINE_LINK_PATTERN = re.compile(r"!?\[([^\]]+)\]\([^)]+\)")
_LEADING_NUMBER_PATTERN = re.compile(r"^(?:\d+(?:[.．]\d+)*|[一二三四五六七八九十百千万]+)[.)、.．]?\s+")
_TRAILING_TOC_PAGE_PATTERN = re.compile(r"[\s.·•…-]{2,}\d+\s*$")
_MARKDOWN_DECORATION_PATTERN = re.compile(r"[*_~`]+")


def _parse_chapter_markdown(markdown: str) -> list[_ChapterImportDraft]:
    drafts: list[_ChapterImportDraft] = []
    in_code_fence = False
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.lstrip().startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence or not line.strip():
            continue

        heading = _MARKDOWN_HEADING_PATTERN.match(line)
        if heading:
            name = _clean_import_chapter_name(heading.group(2))
            if name:
                drafts.append(_ChapterImportDraft(level=_chapter_import_level(len(heading.group(1))), name=name))
            continue

        outline = _NUMBERED_OUTLINE_PATTERN.match(line)
        if outline:
            number_key = outline.group(1).replace("．", ".")
            name = _clean_import_chapter_name(outline.group(2))
            if name:
                drafts.append(
                    _ChapterImportDraft(
                        level=_chapter_import_level(number_key.count(".") + 1),
                        name=name,
                        key=number_key,
                        parent_key=number_key.split(".", 1)[0] if "." in number_key else None,
                    )
                )
            continue

        item = _MARKDOWN_LIST_PATTERN.match(line.expandtabs(4))
        if item:
            name = _clean_import_chapter_name(item.group(2))
            if name:
                drafts.append(_ChapterImportDraft(level=_chapter_import_level((len(item.group(1)) // 2) + 1), name=name))
            continue

        numbered = _TOP_NUMBERED_PATTERN.match(line)
        if numbered:
            name = _clean_import_chapter_name(numbered.group(2))
            if name:
                number_key = numbered.group(1) if numbered.group(1).isdigit() else None
                drafts.append(_ChapterImportDraft(level=1, name=name, key=number_key))
            continue

        chapter = _CHINESE_CHAPTER_PATTERN.match(line)
        if chapter:
            name = _clean_import_chapter_name(chapter.group(1), strip_number=False)
            if name:
                drafts.append(_ChapterImportDraft(level=1, name=name))
            continue

        section = _CHINESE_SECTION_PATTERN.match(line)
        if section:
            name = _clean_import_chapter_name(section.group(1), strip_number=False)
            if name:
                drafts.append(_ChapterImportDraft(level=2, name=name))

    return drafts


def _clean_import_chapter_name(value: str, strip_number: bool = True) -> str:
    text = value.strip()
    text = _INLINE_LINK_PATTERN.sub(r"\1", text)
    text = _MARKDOWN_DECORATION_PATTERN.sub("", text)
    text = _TRAILING_TOC_PAGE_PATTERN.sub("", text)
    if strip_number:
        text = _LEADING_NUMBER_PATTERN.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" -—_")
    if text in {"目录", "章节目录", "教材目录"} or (text.endswith("目录") and len(text) <= 32):
        return ""
    if not 1 <= len(text) <= 128:
        return ""
    return text


def _parse_point_markdown(markdown: str) -> list[_KnowledgePointImportDraft]:
    drafts: list[_KnowledgePointImportDraft] = []
    current_chapter: str | None = None
    current_section: str | None = None
    in_code_fence = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.lstrip().startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence or not line.strip():
            continue

        chapter_match = _CHINESE_CHAPTER_PATTERN.match(line)
        if chapter_match:
            current_chapter = _clean_import_chapter_name(chapter_match.group(1), strip_number=False) or None
            current_section = None
            continue

        section_match = _CHINESE_SECTION_PATTERN.match(line)
        if section_match:
            current_section = _clean_import_chapter_name(section_match.group(1), strip_number=False) or None
            continue

        heading = _MARKDOWN_HEADING_PATTERN.match(line)
        if heading:
            heading_level = len(heading.group(1))
            text = heading.group(2)
            if _CHINESE_CHAPTER_PATTERN.match(text):
                current_chapter = _clean_import_chapter_name(text, strip_number=False) or None
                current_section = None
                continue
            if _CHINESE_SECTION_PATTERN.match(text):
                current_section = _clean_import_chapter_name(text, strip_number=False) or None
                continue
            if heading_level <= 1:
                current_chapter = _clean_import_chapter_name(text) or None
                current_section = None
                continue
            if heading_level == 2:
                current_section = _clean_import_chapter_name(text) or None
                continue
            _append_point_import_draft(drafts, current_chapter, current_section, _clean_import_point_name(text))
            continue

        outline = _NUMBERED_OUTLINE_PATTERN.match(line)
        if outline:
            raw_level = outline.group(1).replace("．", ".").count(".") + 1
            name = outline.group(2)
            if raw_level <= 1:
                current_chapter = _clean_import_chapter_name(name) or None
                current_section = None
                continue
            if raw_level == 2:
                current_section = _clean_import_chapter_name(name) or None
                continue
            _append_point_import_draft(drafts, current_chapter, current_section, _clean_import_point_name(name))
            continue

        item = _MARKDOWN_LIST_PATTERN.match(line.expandtabs(4))
        if item:
            _append_point_import_draft(drafts, current_chapter, current_section, _clean_import_point_name(item.group(2)))
            continue

        numbered = _TOP_NUMBERED_PATTERN.match(line)
        if numbered:
            name = numbered.group(2)
            if current_section or current_chapter:
                _append_point_import_draft(drafts, current_chapter, current_section, _clean_import_point_name(name))
            else:
                current_chapter = _clean_import_chapter_name(name) or None
                current_section = None

    return drafts


def _parse_point_detail_markdown(markdown: str) -> list[_KnowledgePointDetailImportDraft]:
    drafts: list[_KnowledgePointDetailImportDraft] = []
    current_chapter: str | None = None
    current_section: str | None = None
    current_point: str | None = None
    in_code_fence = False

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if line.lstrip().startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence or not line.strip():
            continue

        chapter_match = _CHINESE_CHAPTER_PATTERN.match(line)
        if chapter_match:
            current_chapter = _clean_import_chapter_name(chapter_match.group(1), strip_number=False) or None
            current_section = None
            current_point = None
            continue

        section_match = _CHINESE_SECTION_PATTERN.match(line)
        if section_match:
            current_section = _clean_import_chapter_name(section_match.group(1), strip_number=False) or None
            current_point = None
            continue

        heading = _MARKDOWN_HEADING_PATTERN.match(line)
        if heading:
            heading_level = len(heading.group(1))
            text = heading.group(2)
            if _CHINESE_CHAPTER_PATTERN.match(text):
                current_chapter = _clean_import_chapter_name(text, strip_number=False) or None
                current_section = None
                current_point = None
                continue
            if _CHINESE_SECTION_PATTERN.match(text):
                current_section = _clean_import_chapter_name(text, strip_number=False) or None
                current_point = None
                continue
            if heading_level <= 1:
                current_chapter = _clean_import_chapter_name(text) or None
                current_section = None
                current_point = None
                continue
            if heading_level == 2:
                current_section = _clean_import_chapter_name(text) or None
                current_point = None
                continue
            if heading_level == 3:
                current_point = _clean_import_point_name(text) or None
                continue
            _append_point_detail_import_draft(
                drafts,
                current_chapter,
                current_section,
                current_point,
                _clean_import_point_name(text),
            )
            continue

        outline = _NUMBERED_OUTLINE_PATTERN.match(line)
        if outline:
            raw_level = outline.group(1).replace("．", ".").count(".") + 1
            name = outline.group(2)
            if raw_level <= 1:
                current_chapter = _clean_import_chapter_name(name) or None
                current_section = None
                current_point = None
                continue
            if raw_level == 2:
                current_section = _clean_import_chapter_name(name) or None
                current_point = None
                continue
            if raw_level == 3:
                current_point = _clean_import_point_name(name) or None
                continue
            _append_point_detail_import_draft(
                drafts,
                current_chapter,
                current_section,
                current_point,
                _clean_import_point_name(name),
            )
            continue

        item = _MARKDOWN_LIST_PATTERN.match(line.expandtabs(4))
        if item:
            _append_point_detail_import_draft(
                drafts,
                current_chapter,
                current_section,
                current_point,
                _clean_import_point_name(item.group(2)),
            )
            continue

        numbered = _TOP_NUMBERED_PATTERN.match(line)
        if numbered:
            name = _clean_import_point_name(numbered.group(2))
            if current_point:
                _append_point_detail_import_draft(drafts, current_chapter, current_section, current_point, name)
            elif current_section or current_chapter:
                current_point = name or None
            else:
                current_chapter = _clean_import_chapter_name(numbered.group(2)) or None
                current_section = None
                current_point = None

    return drafts


def _append_point_import_draft(
    drafts: list[_KnowledgePointImportDraft],
    chapter_name: str | None,
    section_name: str | None,
    point_name: str,
) -> None:
    if not chapter_name or not point_name:
        return
    drafts.append(_KnowledgePointImportDraft(chapter_name=chapter_name, section_name=section_name, name=point_name))


def _append_point_detail_import_draft(
    drafts: list[_KnowledgePointDetailImportDraft],
    chapter_name: str | None,
    section_name: str | None,
    point_name: str | None,
    detail_name: str,
) -> None:
    if not chapter_name or not point_name or not detail_name:
        return
    drafts.append(
        _KnowledgePointDetailImportDraft(
            chapter_name=chapter_name,
            section_name=section_name,
            point_name=point_name,
            detail_name=detail_name,
        )
    )


def _clean_import_point_name(value: str) -> str:
    text = _clean_import_chapter_name(value)
    if not text:
        return ""
    match = _POINT_LABEL_PATTERN.match(text)
    if match:
        text = match.group(1).strip()
    return text if 1 <= len(text) <= 128 else ""


def _chapter_import_level(raw_level: int) -> int:
    return 1 if raw_level <= 1 else 2


def _nearest_stack_parent(stack: dict[int, Chapter], level: int) -> Chapter | None:
    for candidate_level in range(level - 1, 0, -1):
        parent = stack.get(candidate_level)
        if parent is not None:
            return parent
    return None

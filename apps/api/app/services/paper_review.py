from __future__ import annotations

import base64
import hashlib
from datetime import datetime
import mimetypes
from pathlib import Path
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import KnowledgePoint, KnowledgePointAlias, PaperReviewQuestion, PaperReviewQuestionKnowledgePoint
from app.repositories.paper_review import PaperReviewRepository
from app.schemas.paper_review import (
    PaperReviewAIActionResponse,
    PaperReviewAIBatchActionResponse,
    PaperReviewAIBatchFailureResponse,
    PaperReviewBatchReviewResponse,
    PaperReviewAutoTagResponse,
    PaperReviewPaperResponse,
    PaperReviewQuestionKnowledgePointResponse,
    PaperReviewQuestionKnowledgePointUpdateRequest,
    PaperReviewQuestionResponse,
    PaperReviewQuestionUpdateRequest,
    PaperReviewRebuildResponse,
    PaperReviewSummaryResponse,
    PaperReviewWorkspaceResponse,
)
from app.services.paper_ai_cleanup import _normalize_ai_prediction_document
from app.schemas.papers import PaperSectionResponse
from app.services.paper_review_ai import (
    normalize_answer,
    normalize_analysis,
    normalize_options,
    normalize_question_fields,
    normalize_question_text,
    review_question_with_ai,
    standardize_question_with_ai,
)
from app.services.paper_review_tagging_ai import run_auto_tag_questions_with_ollama
from library.ocr_cleaner import clean_parsed_document
from library.parser import ParsedDocument
from library.pdf_ocr_pipeline import CHECKPOINT_NAMESPACE_FILENAME, _get_pdf_ocr_checkpoint_root


def _is_ai_knowledge_point_source(source: str | None) -> bool:
    return (source or "").strip().lower().startswith("ai")


def _paper_section_name_map(sections: list[PaperSectionResponse]) -> dict[str, int]:
    return {
        (section.section_name or "").strip(): section.id
        for section in sections
        if (section.section_name or "").strip()
    }


class PaperReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = PaperReviewRepository(session)

    def _question_response(
        self,
        question: PaperReviewQuestion,
        *,
        image_roots: list[Path] | None = None,
        tag_rows: list[PaperReviewQuestionKnowledgePoint] | None = None,
        point_map: dict[int, KnowledgePoint] | None = None,
        subquestions: list[PaperReviewQuestionResponse] | None = None,
        resolved_section_id: int | None = None,
    ) -> PaperReviewQuestionResponse:
        image_roots = image_roots or []
        tag_rows = tag_rows or []
        point_map = point_map or {}
        subquestions = subquestions or []
        suggested: list[PaperReviewQuestionKnowledgePointResponse] = []
        confirmed: list[PaperReviewQuestionKnowledgePointResponse] = []
        for row in tag_rows:
            point = point_map.get(row.knowledge_point_id)
            if point is None:
                continue
            payload = PaperReviewQuestionKnowledgePointResponse(
                id=row.id,
                question_id=row.question_id,
                knowledge_point_id=point.id,
                name=point.name,
                path=point.path,
                chapter_id=point.chapter_id,
                category_id=point.category_id,
                status=row.status,
                relation_type=row.relation_type,
                source=row.source,
                confidence=float(row.confidence) if row.confidence is not None else None,
                reason=row.reason,
                rank=row.rank,
            )
            if row.status == "confirmed":
                confirmed.append(payload)
            elif row.status == "suggested":
                suggested.append(payload)
        return PaperReviewQuestionResponse.model_validate(
            {
                **question.__dict__,
                "section_id": question.section_id if question.section_id is not None else resolved_section_id,
                "source_raw_text": _inline_review_images(question.source_raw_text, image_roots),
                "group_stem": _inline_optional_review_images(question.group_stem, image_roots),
                "material_text": _inline_optional_review_images(question.material_text, image_roots),
                "stem_text": _inline_review_images(question.stem_text, image_roots),
                "analysis_text": _inline_review_images(question.analysis_text or "", image_roots) or question.analysis_text,
                "options_json": [
                    _inline_review_images(option, image_roots)
                    for option in normalize_options(question.options_json or [], question.question_type)
                ],
                "suggested_knowledge_points": suggested,
                "confirmed_knowledge_points": confirmed,
                "subquestions": subquestions,
            }
        )

    def _question_response_with_existing_tags(self, question: PaperReviewQuestion) -> PaperReviewQuestionResponse:
        paper = self.repository.get_paper(question.paper_id)
        asset = self.repository.get_asset(paper.asset_id if paper else None)
        paper_questions = self.repository.list_questions(question.paper_id)
        section_name_map = _paper_section_name_map(
            [PaperSectionResponse.model_validate(item) for item in self.repository.list_sections(question.paper_id)]
        )
        subtree_ids = {
            item.id
            for item in paper_questions
            if item.id == question.id or item.parent_question_id == question.id
        }
        tag_rows = self.repository.list_question_knowledge_points(sorted(subtree_ids or {question.id}))
        point_ids = {row.knowledge_point_id for row in tag_rows}
        point_map = {
            point.id: point
            for point in self.session.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).all()
        } if point_ids else {}
        response_map = self._build_question_response_map(
            paper_questions,
            image_roots=_paper_markdown_image_roots(asset.id if asset else None),
            tag_rows=tag_rows,
            point_map=point_map,
            section_name_map=section_name_map,
        )
        response = response_map.get(question.id)
        if response is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        return response

    def _build_question_response_map(
        self,
        questions: list[PaperReviewQuestion],
        *,
        image_roots: list[Path],
        tag_rows: list[PaperReviewQuestionKnowledgePoint],
        point_map: dict[int, KnowledgePoint],
        section_name_map: dict[str, int] | None = None,
    ) -> dict[int, PaperReviewQuestionResponse]:
        tags_by_question: dict[int, list[PaperReviewQuestionKnowledgePoint]] = {}
        for row in tag_rows:
            tags_by_question.setdefault(row.question_id, []).append(row)
        children_by_parent = _group_review_questions_by_parent(questions)
        response_map: dict[int, PaperReviewQuestionResponse] = {}
        section_name_map = section_name_map or {}

        def build(question: PaperReviewQuestion) -> PaperReviewQuestionResponse:
            cached = response_map.get(question.id)
            if cached is not None:
                return cached
            payload = self._question_response(
                question,
                image_roots=image_roots,
                tag_rows=tags_by_question.get(question.id, []),
                point_map=point_map,
                subquestions=[build(child) for child in children_by_parent.get(question.id, [])],
                resolved_section_id=section_name_map.get((question.source_section_name or "").strip()),
            )
            response_map[question.id] = payload
            return payload

        for question in questions:
            build(question)
        return response_map

    def get_workspace(self, paper_id: int) -> PaperReviewWorkspaceResponse:
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")

        asset = self.repository.get_asset(paper.asset_id)
        questions = self.repository.list_questions(paper.id)
        root_questions = [question for question in questions if question.parent_question_id is None]

        subject = self.repository.get_subject(paper.subject_id)
        category = self.repository.get_category(paper.category_id)
        sections = [PaperSectionResponse.model_validate(item) for item in self.repository.list_sections(paper.id)]
        section_name_map = _paper_section_name_map(sections)
        summary = _build_summary(root_questions, questions)
        image_roots = _paper_markdown_image_roots(asset.id if asset else None)
        tag_rows = self.repository.list_question_knowledge_points([question.id for question in questions])
        point_ids = sorted({row.knowledge_point_id for row in tag_rows})
        point_map = {
            point.id: point
            for point in self.session.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).all()
        } if point_ids else {}
        response_map = self._build_question_response_map(
            questions,
            image_roots=image_roots,
            tag_rows=tag_rows,
            point_map=point_map,
            section_name_map=section_name_map,
        )
        return PaperReviewWorkspaceResponse(
            paper=PaperReviewPaperResponse(
                id=paper.id,
                paper_name=paper.paper_name,
                subject_name=subject.name if subject else None,
                category=category.name if category else _category_from_asset_tags(asset.tags_json if asset else None),
                status=paper.status,
                review_status=paper.review_status,
                total_question_count=paper.total_question_count,
                question_review_count=len(root_questions),
                leaf_question_count=_count_leaf_review_questions(questions),
                group_question_count=sum(1 for item in root_questions if item.node_role == "group"),
            ),
            sections=sections,
            summary=summary,
            questions=[response_map[item.id] for item in root_questions if item.id in response_map],
        )

    def sync_questions_from_sections(
        self,
        *,
        paper_id: int,
        section_payloads: list[dict[str, Any]],
        operator_id: int | None,
        commit: bool,
    ) -> PaperReviewRebuildResponse:
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")

        prediction_document = _normalize_ai_prediction_document({"sections": section_payloads})
        normalized_sections = prediction_document.get("sections") or []
        if not normalized_sections:
            raise HTTPException(status_code=422, detail="审核工作台只支持 AI questions 数据源")

        existing_questions = self.repository.list_questions(paper.id)
        replaced_count = len(existing_questions)
        existing_by_fingerprint = {
            question.content_fingerprint: question
            for question in existing_questions
            if question.content_fingerprint
        }
        subject_points = (
            self.repository.list_subject_knowledge_points(paper.subject_id, paper.category_id)
            if paper.subject_id is not None
            else []
        )
        aliases_by_point: dict[int, list[KnowledgePointAlias]] = {}
        if subject_points:
            for alias in self.repository.list_knowledge_point_aliases([point.id for point in subject_points]):
                aliases_by_point.setdefault(alias.knowledge_point_id, []).append(alias)

        active_question_ids: list[int] = []
        leaf_question_count = 0
        sort_order = 0

        def sync_tags(question: PaperReviewQuestion) -> None:
            if not subject_points or question.node_role == "group":
                return
            existing_tags = self.repository.list_question_knowledge_points([question.id])
            confirmed_rows = [
                PaperReviewQuestionKnowledgePoint(
                    tenant_id=question.tenant_id,
                    question_id=question.id,
                    knowledge_point_id=row.knowledge_point_id,
                    status="confirmed",
                    relation_type=row.relation_type,
                    source=row.source,
                    confidence=row.confidence,
                    reason=row.reason,
                    rank=row.rank,
                    created_by=row.created_by,
                    updated_by=operator_id,
                )
                for row in existing_tags
                if row.status == "confirmed"
            ]
            suggested_rows = _suggest_knowledge_point_rows(
                question=question,
                points=subject_points,
                aliases_by_point=aliases_by_point,
                excluded_point_ids={row.knowledge_point_id for row in confirmed_rows},
            )
            self.repository.replace_question_knowledge_points(question.id, [*confirmed_rows, *suggested_rows])

        def upsert_question(
            question_payload: dict[str, Any],
            *,
            section_id: int | None,
            source_section_name: str,
            parent_question: PaperReviewQuestion | None,
            inherited_group_stem: str | None,
            inherited_material_text: str | None,
            node_role: str,
            sort_order_value: int,
        ) -> PaperReviewQuestion | None:
            raw_text = str(question_payload.get("source_raw_text") or "").strip()
            question_no = str(question_payload.get("question_no") or "").strip() or str(sort_order_value)
            question_type = str(question_payload.get("question_type") or "mixed").strip() or "mixed"
            group_stem = normalize_question_text(
                str(question_payload.get("group_stem") or question_payload.get("shared_stem") or inherited_group_stem or "")
            ) or None
            material_text = normalize_question_text(
                str(question_payload.get("material_text") or inherited_material_text or "")
            ) or None
            stem_text = normalize_question_text(str(question_payload.get("stem_text") or ""))
            if node_role == "group":
                stem_text = stem_text or group_stem or material_text or question_no
            if not raw_text:
                raw_text = _compose_review_source_raw_text(
                    question_no=question_no,
                    node_role=node_role,
                    group_stem=group_stem,
                    material_text=material_text,
                    stem_text=stem_text,
                    options=question_payload.get("options") or [],
                    answer_text=question_payload.get("answer_text"),
                    analysis_text=question_payload.get("analysis_text"),
                )
            if not raw_text or not stem_text:
                return None
            options = normalize_options(question_payload.get("options") or [], question_type)
            answer_text = str(question_payload.get("answer_text") or "").strip() or None
            analysis_text = normalize_analysis(question_payload.get("analysis_text"))
            quality_issues = [
                str(issue).strip()
                for issue in (question_payload.get("quality_issues") or [])
                if str(issue).strip()
            ]
            subquestion_payloads = [
                child
                for child in (question_payload.get("subquestions") or [])
                if isinstance(child, dict)
            ]
            content_fingerprint = _make_question_fingerprint(
                section_id=section_id,
                question_no=question_no,
                source_raw_text=raw_text,
            )
            question = existing_by_fingerprint.get(content_fingerprint)
            if question is None:
                question = PaperReviewQuestion(
                    tenant_id=paper.tenant_id,
                    paper_id=paper.id,
                    section_id=section_id,
                    parent_question_id=parent_question.id if parent_question else None,
                    question_uid=_make_question_uid(paper.id, section_id, sort_order_value, question_no, stem_text),
                    content_fingerprint=content_fingerprint,
                    sort_order=sort_order_value,
                    question_no=question_no,
                    node_role=node_role,
                    question_type=question_type,
                    source_section_name=source_section_name,
                    source_raw_text=raw_text,
                    group_stem=group_stem,
                    material_text=material_text,
                    stem_text=stem_text,
                    options_json=options,
                    answer_text=answer_text,
                    analysis_text=analysis_text,
                    difficulty_level=3,
                    quality_score=_to_optional_float(question_payload.get("quality_score")),
                    subquestion_count=len(subquestion_payloads) if node_role == "group" else 0,
                    quality_issues_json=quality_issues,
                    parse_status="parsed",
                    review_status="pending",
                    review_note=None,
                    ai_review_status=None,
                    ai_review_note=None,
                    ai_standardization_note=None,
                    reviewed_by=None,
                    reviewed_at=None,
                    created_by=operator_id,
                    updated_by=operator_id,
                )
                self.repository.create_question(question)
                existing_by_fingerprint[content_fingerprint] = question
            else:
                question.section_id = section_id
                question.parent_question_id = parent_question.id if parent_question else None
                question.question_uid = _make_question_uid(paper.id, section_id, sort_order_value, question_no, stem_text)
                question.content_fingerprint = content_fingerprint
                question.sort_order = sort_order_value
                question.question_no = question_no
                question.node_role = node_role
                question.question_type = question_type
                question.source_section_name = source_section_name
                question.source_raw_text = raw_text
                question.group_stem = group_stem
                question.material_text = material_text
                question.stem_text = stem_text
                question.options_json = options
                question.answer_text = answer_text
                question.analysis_text = analysis_text
                question.difficulty_level = 3
                question.quality_score = _to_optional_float(question_payload.get("quality_score"))
                question.subquestion_count = len(subquestion_payloads) if node_role == "group" else 0
                question.quality_issues_json = quality_issues
                question.parse_status = "parsed"
                question.updated_by = operator_id
            if node_role != "group":
                normalize_question_fields(question)
            active_question_ids.append(question.id)
            sync_tags(question)
            return question

        for payload in sorted(normalized_sections, key=lambda item: int(item.get("sort_order") or 0)):
            section_id = _to_optional_int(payload.get("section_id"))
            source_section_name = str(payload.get("title") or "自动切题")
            for question_payload in payload.get("questions") or []:
                if not isinstance(question_payload, dict):
                    continue
                sort_order += 1
                node_role = str(question_payload.get("node_role") or "").strip() or (
                    "group" if isinstance(question_payload.get("subquestions"), list) and (question_payload.get("subquestions") or []) else "standalone"
                )
                group_stem = normalize_question_text(
                    str(question_payload.get("group_stem") or question_payload.get("shared_stem") or "")
                ) or None
                material_text = normalize_question_text(str(question_payload.get("material_text") or "")) or None
                parent_question = upsert_question(
                    question_payload,
                    section_id=section_id,
                    source_section_name=source_section_name,
                    parent_question=None,
                    inherited_group_stem=group_stem,
                    inherited_material_text=material_text,
                    node_role=node_role,
                    sort_order_value=sort_order,
                )
                if parent_question is None:
                    continue
                if parent_question.node_role == "group":
                    child_count = 0
                    for child_payload in question_payload.get("subquestions") or []:
                        if not isinstance(child_payload, dict):
                            continue
                        sort_order += 1
                        child_question = upsert_question(
                            child_payload,
                            section_id=section_id,
                            source_section_name=source_section_name,
                            parent_question=parent_question,
                            inherited_group_stem=parent_question.group_stem,
                            inherited_material_text=parent_question.material_text,
                            node_role="subquestion",
                            sort_order_value=sort_order,
                        )
                        if child_question is None:
                            continue
                        child_count += 1
                        leaf_question_count += 1
                    parent_question.subquestion_count = child_count
                else:
                    leaf_question_count += 1

        active_question_id_set = set(active_question_ids)
        removed_questions = [question for question in existing_questions if question.id not in active_question_id_set]
        self.repository.delete_question_knowledge_points_by_question_ids([question.id for question in removed_questions])
        for question in removed_questions:
            self.session.delete(question)

        paper.total_question_count = leaf_question_count
        paper.review_status = "pending" if leaf_question_count else paper.review_status

        if commit:
            self.session.commit()
        else:
            self.session.flush()

        return PaperReviewRebuildResponse(
            paper_id=paper.id,
            imported_count=leaf_question_count,
            replaced_count=replaced_count,
            section_count=len(normalized_sections),
            message=f"已同步 {leaf_question_count} 道题，覆盖 {replaced_count} 条旧题目记录。",
        )

    def update_question(self, question_id: int, payload: PaperReviewQuestionUpdateRequest) -> PaperReviewQuestionResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")

        paper_questions = self.repository.list_questions(question.paper_id)
        by_id = {item.id: item for item in paper_questions}
        child_questions = [item for item in paper_questions if item.parent_question_id == question.id]

        content_changed, review_changed = _apply_review_question_update(question, payload)
        if payload.group_stem is not None:
            next_group_stem = normalize_question_text(payload.group_stem) or None
            if next_group_stem != question.group_stem:
                question.group_stem = next_group_stem
                content_changed = True
            if question.node_role == "group":
                next_parent_stem = next_group_stem or question.stem_text
                if next_parent_stem and next_parent_stem != question.stem_text:
                    question.stem_text = next_parent_stem
                    content_changed = True
        if payload.material_text is not None:
            next_material_text = normalize_question_text(payload.material_text) or None
            if next_material_text != question.material_text:
                question.material_text = next_material_text
                content_changed = True

        if question.node_role == "group":
            updated_child_ids: set[int] = set()
            for child_payload in payload.subquestions:
                child_question = by_id.get(child_payload.id)
                if child_question is None or child_question.parent_question_id != question.id:
                    raise HTTPException(status_code=422, detail=f"子问 {child_payload.id} 不属于当前题组")
                child_content_changed, child_review_changed = _apply_review_question_update(child_question, child_payload)
                if payload.group_stem is not None and child_question.group_stem != question.group_stem:
                    child_question.group_stem = question.group_stem
                    child_content_changed = True
                if payload.material_text is not None and child_question.material_text != question.material_text:
                    child_question.material_text = question.material_text
                    child_content_changed = True
                if child_content_changed:
                    child_question.parse_status = "manual_updated"
                if child_review_changed:
                    child_question.reviewed_at = datetime.utcnow()
                content_changed = content_changed or child_content_changed
                review_changed = review_changed or child_review_changed
                updated_child_ids.add(child_question.id)
            if payload.group_stem is not None or payload.material_text is not None:
                for child_question in child_questions:
                    if child_question.id in updated_child_ids:
                        continue
                    child_changed = False
                    if payload.group_stem is not None and child_question.group_stem != question.group_stem:
                        child_question.group_stem = question.group_stem
                        child_changed = True
                    if payload.material_text is not None and child_question.material_text != question.material_text:
                        child_question.material_text = question.material_text
                        child_changed = True
                    if child_changed:
                        child_question.parse_status = "manual_updated"
                        content_changed = True

        if content_changed:
            question.parse_status = "manual_updated"
        if review_changed:
            question.reviewed_at = datetime.utcnow()

        root_question = _root_review_question(question, by_id)
        self._maybe_sync_question_bank(root_question)
        self.session.commit()
        self.session.refresh(question)
        return self._question_response_with_existing_tags(question)

    def update_question_knowledge_points(
        self,
        question_id: int,
        payload: PaperReviewQuestionKnowledgePointUpdateRequest,
    ) -> PaperReviewQuestionResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        if question.node_role == "group":
            raise HTTPException(status_code=422, detail="题组父题不支持直接标注考点，请标注子问")
        paper = self.repository.get_paper(question.paper_id)
        if paper is None or paper.subject_id is None:
            raise HTTPException(status_code=422, detail="试卷未绑定学科，无法标注考点")

        scoped_points = {
            point.id: point
            for point in self.repository.list_subject_knowledge_points(paper.subject_id, paper.category_id)
        }
        rows: list[PaperReviewQuestionKnowledgePoint] = []
        seen_point_ids: set[int] = set()
        confirmed_primary_count = 0
        for status, items in (("suggested", payload.suggested), ("confirmed", payload.confirmed)):
            for fallback_rank, item in enumerate(items, start=1):
                point = scoped_points.get(item.knowledge_point_id)
                if point is None:
                    raise HTTPException(status_code=422, detail=f"知识点 {item.knowledge_point_id} 不在当前试卷学科/类目范围内")
                if item.knowledge_point_id in seen_point_ids:
                    raise HTTPException(status_code=422, detail="同一知识点不能重复标注")
                seen_point_ids.add(item.knowledge_point_id)
                if status == "confirmed" and item.relation_type == "primary":
                    confirmed_primary_count += 1
                rows.append(
                    PaperReviewQuestionKnowledgePoint(
                        tenant_id=question.tenant_id,
                        question_id=question.id,
                        knowledge_point_id=point.id,
                        status=status,
                        relation_type=item.relation_type,
                        source=item.source,
                        confidence=item.confidence,
                        reason=(item.reason or "").strip() or None,
                        rank=item.rank or fallback_rank,
                        created_by=question.updated_by,
                        updated_by=question.updated_by,
                    )
                )
        if confirmed_primary_count > 1:
            raise HTTPException(status_code=422, detail="每道题最多只能有一个已确认主考点")

        self.repository.replace_question_knowledge_points(question.id, rows)
        paper_questions = self.repository.list_questions(question.paper_id)
        section_name_map = _paper_section_name_map(
            [PaperSectionResponse.model_validate(item) for item in self.repository.list_sections(question.paper_id)]
        )
        self._maybe_sync_question_bank(_root_review_question(question, {item.id: item for item in paper_questions}))
        self.session.commit()
        self.session.refresh(question)
        image_roots = _paper_markdown_image_roots(self.repository.get_asset(paper.asset_id).id if self.repository.get_asset(paper.asset_id) else None)
        return self._question_response(
            question,
            image_roots=image_roots,
            tag_rows=rows,
            point_map=scoped_points,
            resolved_section_id=section_name_map.get((question.source_section_name or "").strip()),
        )

    def auto_tag_paper_questions(
        self,
        paper_id: int,
        *,
        force_question_id: int | None = None,
        progress_callback: Any | None = None,
    ) -> PaperReviewAutoTagResponse:
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")
        if paper.subject_id is None:
            raise HTTPException(status_code=422, detail="试卷未绑定学科，无法自动标注考点")

        questions = self.repository.list_questions(paper.id)
        if not questions:
            raise HTTPException(status_code=422, detail="当前试卷还没有题目，无法自动标注考点")
        by_id = {question.id: question for question in questions}
        children_by_parent = _group_review_questions_by_parent(questions)

        scoped_points = self.repository.list_subject_knowledge_points(paper.subject_id, paper.category_id)
        if not scoped_points:
            raise HTTPException(status_code=422, detail="当前试卷所属学科/类目下没有知识点，无法自动标注")

        point_payloads = [
            {
                "id": point.id,
                "name": point.name,
                "path": point.path,
            }
            for point in scoped_points
        ]
        tag_rows = self.repository.list_question_knowledge_points([question.id for question in questions])
        tags_by_question: dict[int, list[PaperReviewQuestionKnowledgePoint]] = {}
        for row in tag_rows:
            tags_by_question.setdefault(row.question_id, []).append(row)

        skipped_count = 0
        target_questions: list[PaperReviewQuestion] = []
        if force_question_id is not None:
            forced_question = by_id.get(force_question_id)
            if forced_question is None:
                raise HTTPException(status_code=404, detail="指定题目不存在或不属于当前试卷")
            if forced_question.node_role == "group":
                target_questions = _leaf_review_descendants(forced_question, children_by_parent)
            else:
                target_questions = [forced_question]
        else:
            for question in questions:
                if question.node_role == "group":
                    continue
                if any(_is_ai_knowledge_point_source(row.source) for row in tags_by_question.get(question.id, [])):
                    skipped_count += 1
                    continue
                target_questions.append(question)

        if force_question_id is not None and not target_questions:
            raise HTTPException(status_code=422, detail="当前题组下没有可自动标注的子问")
        if force_question_id is None and not target_questions:
            return PaperReviewAutoTagResponse(
                paper_id=paper.id,
                status="completed",
                progress=100,
                requested_count=0,
                updated_count=0,
                failed_count=0,
                skipped_count=skipped_count,
                message=f"当前试卷题目都已有 AI 标注，已跳过 {skipped_count} 道。",
            )

        question_payloads = [
            {
                "id": question.id,
                "question_type": question.question_type,
                "group_stem": question.group_stem,
                "material_text": question.material_text,
                "stem_text": question.stem_text,
                "answer_text": question.answer_text,
                "analysis_text": question.analysis_text,
            }
            for question in target_questions
        ]
        ai_results = run_auto_tag_questions_with_ollama(
            questions=question_payloads,
            knowledge_points=point_payloads,
            concurrency=5,
        )

        question_map = {question.id: question for question in target_questions}
        point_map = {point.id: point for point in scoped_points}
        updated_count = 0
        failed_count = 0
        for result in ai_results:
            question = question_map.get(result.question_id)
            if question is None:
                continue
            if result.error:
                failed_count += 1
                if progress_callback is not None:
                    progress_callback(updated_count + failed_count, len(target_questions), updated_count, failed_count, skipped_count)
                continue
            existing_tags = self.repository.list_question_knowledge_points([question.id])
            if not result.point_ids:
                failed_count += 1
                if progress_callback is not None:
                    progress_callback(updated_count + failed_count, len(target_questions), updated_count, failed_count, skipped_count)
                continue
            confirmed_rows = [
                PaperReviewQuestionKnowledgePoint(
                    tenant_id=question.tenant_id,
                    question_id=question.id,
                    knowledge_point_id=row.knowledge_point_id,
                    status="confirmed",
                    relation_type=row.relation_type,
                    source=row.source,
                    confidence=row.confidence,
                    reason=row.reason,
                    rank=row.rank,
                    created_by=row.created_by,
                    updated_by=question.updated_by,
                )
                for row in existing_tags
                if row.status == "confirmed"
            ]
            suggested_rows: list[PaperReviewQuestionKnowledgePoint] = []
            excluded_ids = {row.knowledge_point_id for row in confirmed_rows}
            for index, point_id in enumerate(result.point_ids, start=1):
                if point_id in excluded_ids or point_id not in point_map:
                    continue
                suggested_rows.append(
                    PaperReviewQuestionKnowledgePoint(
                        tenant_id=question.tenant_id,
                        question_id=question.id,
                        knowledge_point_id=point_id,
                        status="suggested",
                        relation_type="primary" if index == 1 else "secondary",
                        source="ai",
                        confidence=result.confidence,
                        reason=result.reason,
                        rank=index,
                        created_by=question.updated_by,
                        updated_by=question.updated_by,
                    )
                )
            self.repository.replace_question_knowledge_points(question.id, [*confirmed_rows, *suggested_rows])
            updated_count += 1
            if progress_callback is not None:
                progress_callback(updated_count + failed_count, len(target_questions), updated_count, failed_count, skipped_count)

        self.session.commit()
        return PaperReviewAutoTagResponse(
            paper_id=paper.id,
            status="completed",
            progress=100,
            requested_count=len(target_questions),
            updated_count=updated_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            message=(
                f"已完成 {updated_count} 道题自动考点标注，"
                f"失败 {failed_count} 道，"
                f"跳过 {skipped_count} 道。"
                if force_question_id is None
                else f"已完成当前题自动考点标注，失败 {failed_count} 道。"
            ),
        )

    def standardize_question(self, question_id: int) -> PaperReviewAIActionResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")

        paper = self.repository.get_paper(question.paper_id)
        subject = self.repository.get_subject(paper.subject_id if paper else None)
        category = self.repository.get_category(paper.category_id if paper else None)
        asset = self.repository.get_asset(paper.asset_id) if paper else None
        category_name = category.name if category else _category_from_asset_tags(asset.tags_json if asset else None)
        changed = False
        used_ai = False
        message = "题目无需补全或标准化。"

        if question.node_role == "group":
            paper_questions = self.repository.list_questions(question.paper_id)
            children_by_parent = _group_review_questions_by_parent(paper_questions)
            target_questions = _leaf_review_descendants(question, children_by_parent)
            if not target_questions:
                raise HTTPException(status_code=422, detail="题组下没有可标准化的子问")
            local_changed = _normalize_group_question_fields(question)
            ai_failures: list[str] = []
            for child in target_questions:
                child_local_changed = normalize_question_fields(child)
                result = standardize_question_with_ai(
                    child,
                    subject_name=subject.name if subject else None,
                    category_name=category_name,
                )
                if result.error and not child_local_changed:
                    ai_failures.append(_format_ai_error(result.error))
                    continue
                child_changed = child_local_changed or result.changed
                if child_changed:
                    child.review_status = "needs_revision"
                    child.review_note = _append_note(child.review_note, "题目已重新标准化，请人工复核。")
                    child.parse_status = "manual_updated"
                if result.used_ai and not result.error:
                    child.last_ai_standardized_at = datetime.utcnow()
                    child.ai_standardization_note = "AI 已完成题目补全与标准化。"
                elif child_local_changed:
                    child.ai_standardization_note = "已完成规则级标准化；AI 当前不可用。"
                changed = changed or child_changed
                used_ai = used_ai or result.used_ai
            if local_changed:
                question.parse_status = "manual_updated"
                changed = True
            if changed:
                question.review_note = _append_note(question.review_note, "题组或子问已重新标准化，请人工复核。")
            if used_ai:
                question.last_ai_standardized_at = datetime.utcnow()
                question.ai_standardization_note = f"AI 已完成 {len(target_questions)} 个子问的补全与标准化。"
            elif local_changed:
                question.ai_standardization_note = "已完成题组规则级标准化；AI 当前不可用。"
            if ai_failures and not changed:
                raise HTTPException(status_code=503, detail=ai_failures[0])
            if ai_failures and changed:
                message = f"已完成题组标准化，部分子问 AI 未执行：{ai_failures[0]}"
            elif changed:
                message = "题组及其子问已完成补全与标准化。"
        else:
            local_changed = normalize_question_fields(question)
            result = standardize_question_with_ai(
                question,
                subject_name=subject.name if subject else None,
                category_name=category_name,
            )
            if result.error and not local_changed:
                raise HTTPException(status_code=503, detail=_format_ai_error(result.error))
            changed = local_changed or result.changed
            used_ai = result.used_ai
            if changed:
                question.review_status = "needs_revision"
                question.review_note = _append_note(question.review_note, "题目已重新标准化，请人工复核。")
            if result.used_ai and not result.error:
                question.last_ai_standardized_at = datetime.utcnow()
                question.ai_standardization_note = "AI 已完成题目补全与标准化。"
            elif local_changed:
                question.ai_standardization_note = "已完成规则级标准化；AI 当前不可用。"
            if result.error and local_changed:
                message = f"已完成基础标准化，AI 未执行：{_format_ai_error(result.error)}"
            elif changed:
                message = "题目已完成补全与标准化。"

        self._maybe_sync_question_bank(_root_review_question(question, {item.id: item for item in self.repository.list_questions(question.paper_id)}))
        self.session.commit()
        self.session.refresh(question)
        return PaperReviewAIActionResponse(
            message=message,
            changed=changed,
            used_ai=used_ai,
            question=self._question_response_with_existing_tags(question),
        )

    def review_question(self, question_id: int) -> PaperReviewAIActionResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")

        paper = self.repository.get_paper(question.paper_id)
        subject = self.repository.get_subject(paper.subject_id if paper else None)
        used_ai = False
        if question.node_role == "group":
            paper_questions = self.repository.list_questions(question.paper_id)
            children_by_parent = _group_review_questions_by_parent(paper_questions)
            target_questions = _leaf_review_descendants(question, children_by_parent)
            if not target_questions:
                raise HTTPException(status_code=422, detail="题组下没有可审核的子问")
            failures: list[str] = []
            success_count = 0
            for child in target_questions:
                result = review_question_with_ai(child, subject_name=subject.name if subject else None)
                if result.error or result.review_status is None:
                    failures.append(_format_ai_error(result.error or "ai_review_failed"))
                    continue
                child.ai_review_status = result.review_status
                child.ai_review_note = result.review_note
                child.last_ai_reviewed_at = datetime.utcnow()
                success_count += 1
                used_ai = used_ai or result.used_ai
            if success_count <= 0 and failures:
                raise HTTPException(status_code=503, detail=failures[0])
            question.last_ai_reviewed_at = datetime.utcnow()
            question.ai_review_note = (
                f"AI 已完成 {success_count} 个子问答案与解析审核。"
                if not failures
                else f"AI 已完成 {success_count} 个子问审核，部分失败：{failures[0]}"
            )
        else:
            result = review_question_with_ai(question, subject_name=subject.name if subject else None)
            if result.error or result.review_status is None:
                raise HTTPException(status_code=503, detail=_format_ai_error(result.error or "ai_review_failed"))
            question.ai_review_status = result.review_status
            question.ai_review_note = result.review_note
            question.last_ai_reviewed_at = datetime.utcnow()
            used_ai = result.used_ai
        self.session.commit()
        self.session.refresh(question)
        return PaperReviewAIActionResponse(
            message="AI 已完成答案与解析审核。" if question.node_role != "group" else "AI 已完成题组子问答案与解析审核。",
            changed=False,
            used_ai=used_ai,
            question=self._question_response_with_existing_tags(question),
        )

    def batch_standardize_questions(self, question_ids: list[int]) -> PaperReviewAIBatchActionResponse:
        return self._run_ai_batch(question_ids, action="standardize")

    def batch_review_questions(self, question_ids: list[int]) -> PaperReviewAIBatchActionResponse:
        return self._run_ai_batch(question_ids, action="review")

    def batch_update_review(
        self,
        question_ids: list[int],
        review_status: str,
        review_note: str | None = None,
    ) -> PaperReviewBatchReviewResponse:
        normalized_ids = _unique_question_ids(question_ids)
        if not normalized_ids:
            raise HTTPException(status_code=422, detail="请至少选择一道题")

        normalized_note = normalize_question_text(review_note or "") or None
        questions: list[PaperReviewQuestionResponse] = []
        failures: list[PaperReviewAIBatchFailureResponse] = []
        handled_root_ids: set[int] = set()

        for question_id in normalized_ids:
            question = self.repository.get_question(question_id)
            if question is None:
                failures.append(
                    PaperReviewAIBatchFailureResponse(question_id=question_id, message="题目不存在")
                )
                continue

            paper_questions = self.repository.list_questions(question.paper_id)
            by_id = {item.id: item for item in paper_questions}
            target_question = _root_review_question(question, by_id)
            if target_question.id in handled_root_ids:
                continue
            handled_root_ids.add(target_question.id)
            payload = PaperReviewQuestionUpdateRequest(
                review_status=review_status,
                review_note=normalized_note,
                subquestions=[
                    {
                        "id": child.id,
                        "review_status": review_status,
                        "review_note": normalized_note,
                    }
                    for child in paper_questions
                    if child.parent_question_id == target_question.id
                ],
            )
            try:
                result = self.update_question(target_question.id, payload)
            except HTTPException as exc:
                failures.append(
                    PaperReviewAIBatchFailureResponse(
                        question_id=question_id,
                        message=_batch_review_failure_message(target_question, by_id, _http_exception_message(exc)),
                    )
                )
                self.session.rollback()
                continue
            except Exception as exc:
                failures.append(
                    PaperReviewAIBatchFailureResponse(
                        question_id=question_id,
                        message=_batch_review_failure_message(target_question, by_id, str(exc) or "批量人工审核失败。"),
                    )
                )
                self.session.rollback()
                continue
            questions.append(result)

        requested_count = len(normalized_ids)
        success_count = len(questions)
        failed_count = len(failures)
        message = f"批量人工审核已完成：共 {requested_count} 道，成功 {success_count} 道"
        if failed_count:
            message += f"，失败 {failed_count} 道"
        message += "。"
        if failures:
            failure_details = "；".join(item.message for item in failures[:3])
            if len(failures) > 3:
                failure_details += "；其余失败请逐题查看。"
            message += f" 失败明细：{failure_details}"

        return PaperReviewBatchReviewResponse(
            message=message,
            requested_count=requested_count,
            success_count=success_count,
            failed_count=failed_count,
            questions=questions,
            failures=failures,
        )

    def _run_ai_batch(self, question_ids: list[int], *, action: str) -> PaperReviewAIBatchActionResponse:
        normalized_ids = _unique_question_ids(question_ids)
        if not normalized_ids:
            raise HTTPException(status_code=422, detail="请至少选择一道题")

        questions: list[PaperReviewQuestionResponse] = []
        failures: list[PaperReviewAIBatchFailureResponse] = []
        changed_count = 0
        used_ai_count = 0

        for question_id in normalized_ids:
            try:
                result = (
                    self.standardize_question(question_id)
                    if action == "standardize"
                    else self.review_question(question_id)
                )
            except HTTPException as exc:
                failures.append(
                    PaperReviewAIBatchFailureResponse(
                        question_id=question_id,
                        message=_http_exception_message(exc),
                    )
                )
                continue
            except Exception as exc:
                failures.append(
                    PaperReviewAIBatchFailureResponse(
                        question_id=question_id,
                        message=str(exc) or "AI 服务执行失败。",
                    )
                )
                continue

            questions.append(result.question)
            if result.changed:
                changed_count += 1
            if result.used_ai:
                used_ai_count += 1

        requested_count = len(normalized_ids)
        success_count = len(questions)
        failed_count = len(failures)
        action_label = "AI 补全与标准化" if action == "standardize" else "AI 答案审核"
        message = _build_ai_batch_message(
            action_label=action_label,
            requested_count=requested_count,
            success_count=success_count,
            failed_count=failed_count,
            changed_count=changed_count,
            failures=failures,
        )
        return PaperReviewAIBatchActionResponse(
            message=message,
            requested_count=requested_count,
            success_count=success_count,
            failed_count=failed_count,
            changed_count=changed_count,
            used_ai_count=used_ai_count,
            questions=questions,
            failures=failures,
        )

    def _maybe_sync_question_bank(self, root_question: PaperReviewQuestion) -> None:
        if root_question.node_role == "group":
            if root_question.review_status != "approved":
                return
            paper_questions = self.repository.list_questions(root_question.paper_id)
            children_by_parent = _group_review_questions_by_parent(paper_questions)
            leaf_questions = _leaf_review_descendants(root_question, children_by_parent)
            if not leaf_questions:
                return
            if any((question.review_status or "").strip() != "approved" for question in leaf_questions):
                return
            if not (root_question.group_stem or root_question.material_text):
                return
        elif (root_question.review_status or "").strip() != "approved":
            return

        from app.services.question_bank import QuestionBankService

        try:
            QuestionBankService(self.session).sync_from_review_question(root_question.id, commit=False)
        except HTTPException as exc:
            if exc.status_code in {409, 422}:
                return
            raise


def _build_summary(root_questions: list[PaperReviewQuestion], all_questions: list[PaperReviewQuestion]) -> PaperReviewSummaryResponse:
    summary = PaperReviewSummaryResponse(
        total_questions=len(root_questions),
        leaf_question_count=_count_leaf_review_questions(all_questions),
        group_question_count=sum(1 for question in root_questions if question.node_role == "group"),
    )
    for question in root_questions:
        review_status = (question.review_status or "pending").strip()
        if review_status == "approved":
            summary.approved_count += 1
        elif review_status == "needs_revision":
            summary.needs_revision_count += 1
        elif review_status == "rejected":
            summary.rejected_count += 1
        else:
            summary.pending_count += 1

        if (question.ai_review_status or "") in {"needs_revision", "rejected"}:
            summary.ai_flagged_count += 1
        if question.last_ai_reviewed_at is not None:
            summary.ai_reviewed_count += 1
    for question in all_questions:
        if question.node_role == "group":
            continue
        if not (question.answer_text or "").strip() or not (question.analysis_text or "").strip():
            summary.missing_solution_count += 1
    return summary


def _group_review_questions_by_parent(questions: list[PaperReviewQuestion]) -> dict[int, list[PaperReviewQuestion]]:
    children_by_parent: dict[int, list[PaperReviewQuestion]] = {}
    for question in questions:
        if question.parent_question_id is None:
            continue
        children_by_parent.setdefault(question.parent_question_id, []).append(question)
    for items in children_by_parent.values():
        items.sort(key=lambda item: (item.sort_order, item.id))
    return children_by_parent


def _leaf_review_descendants(
    question: PaperReviewQuestion,
    children_by_parent: dict[int, list[PaperReviewQuestion]],
) -> list[PaperReviewQuestion]:
    children = children_by_parent.get(question.id, [])
    if not children:
        return [question] if question.node_role != "group" else []
    leaves: list[PaperReviewQuestion] = []
    for child in children:
        leaves.extend(_leaf_review_descendants(child, children_by_parent))
    return leaves


def _count_leaf_review_questions(questions: list[PaperReviewQuestion]) -> int:
    return sum(1 for question in questions if question.node_role != "group")


def _apply_review_question_update(question: PaperReviewQuestion, payload: Any) -> tuple[bool, bool]:
    content_changed = False
    review_changed = False
    question_type_changed = False

    if getattr(payload, "question_type", None) is not None:
        next_question_type = str(payload.question_type).strip()
        if next_question_type and next_question_type != question.question_type:
            question.question_type = next_question_type
            content_changed = True
            question_type_changed = True

    if getattr(payload, "stem_text", None) is not None:
        next_stem = normalize_question_text(payload.stem_text)
        if next_stem and next_stem != question.stem_text:
            question.stem_text = next_stem
            content_changed = True

    if getattr(payload, "options_json", None) is not None:
        next_options = normalize_options(payload.options_json, question.question_type)
        if next_options != (question.options_json or []):
            question.options_json = next_options
            content_changed = True
    elif question_type_changed:
        next_options = normalize_options(question.options_json or [], question.question_type)
        if next_options != (question.options_json or []):
            question.options_json = next_options
            content_changed = True

    if getattr(payload, "answer_text", None) is not None:
        next_answer = normalize_answer(payload.answer_text, question.question_type)
        if next_answer != question.answer_text:
            question.answer_text = next_answer
            content_changed = True

    if getattr(payload, "analysis_text", None) is not None:
        next_analysis = normalize_analysis(payload.analysis_text)
        if next_analysis != question.analysis_text:
            question.analysis_text = next_analysis
            content_changed = True

    if getattr(payload, "review_status", None) is not None and payload.review_status != question.review_status:
        question.review_status = payload.review_status
        review_changed = True

    if getattr(payload, "review_note", None) is not None:
        next_note = normalize_question_text(payload.review_note) or None
        if next_note != question.review_note:
            question.review_note = next_note
            review_changed = True

    return content_changed, review_changed


def _normalize_group_question_fields(question: PaperReviewQuestion) -> bool:
    changed = False
    group_stem = normalize_question_text(question.group_stem or "") or None
    material_text = normalize_question_text(question.material_text or "") or None
    if group_stem != question.group_stem:
        question.group_stem = group_stem
        changed = True
    if material_text != question.material_text:
        question.material_text = material_text
        changed = True
    next_stem = group_stem or question.stem_text
    if next_stem and next_stem != question.stem_text:
        question.stem_text = next_stem
        changed = True
    return changed


def _root_review_question(question: PaperReviewQuestion, by_id: dict[int, PaperReviewQuestion]) -> PaperReviewQuestion:
    current = question
    seen: set[int] = set()
    while current.parent_question_id is not None and current.parent_question_id in by_id and current.parent_question_id not in seen:
        seen.add(current.parent_question_id)
        current = by_id[current.parent_question_id]
    return current


def _compose_review_source_raw_text(
    *,
    question_no: str,
    node_role: str,
    group_stem: str | None,
    material_text: str | None,
    stem_text: str,
    options: list[str] | Any,
    answer_text: Any,
    analysis_text: Any,
) -> str:
    parts: list[str] = []
    if node_role == "group" and group_stem:
        parts.append(group_stem)
    if node_role == "group" and material_text:
        parts.append(material_text)
    if stem_text:
        parts.append(f"{question_no}. {stem_text}" if node_role != "group" else stem_text)
    option_lines = [str(option).strip() for option in (options or []) if str(option).strip()]
    if option_lines:
        parts.extend(option_lines)
    if str(answer_text or "").strip():
        parts.append(f"答案：{str(answer_text).strip()}")
    normalized_analysis = normalize_analysis(analysis_text)
    if normalized_analysis:
        parts.append(f"解析：{normalized_analysis}")
    return "\n".join(part for part in parts if part).strip()


def _make_question_uid(
    paper_id: int,
    section_id: int | None,
    sort_order: int,
    question_no: str,
    stem_text: str,
) -> str:
    uid_seed = f"{paper_id}:{section_id or 0}:{sort_order}:{question_no}:{stem_text[:96]}"
    digest = hashlib.sha1(uid_seed.encode("utf-8")).hexdigest()[:24]
    return f"PRQ{paper_id}-{digest}"


def _make_question_fingerprint(
    *,
    section_id: int | None,
    question_no: str,
    source_raw_text: str,
) -> str:
    normalized = "|".join(
        [
            str(section_id or 0),
            (question_no or "").strip(),
            _normalize_match_text(source_raw_text)[:2000],
        ]
    )
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _category_from_asset_tags(tags: list[str] | None) -> str | None:
    for tag in tags or []:
        if isinstance(tag, str) and tag.startswith("category:"):
            value = tag.removeprefix("category:").strip()
            return value or None
    return None


def _append_note(existing: str | None, note: str) -> str:
    if not existing:
        return note
    if note in existing:
        return existing
    return f"{existing}；{note}"


def _to_optional_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _to_optional_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _format_ai_error(error: str) -> str:
    if error == "reviewer_llm_unavailable":
        return "当前未配置可用的 reviewer LLM。"
    if error == "question_ai_standardizer_unavailable":
        return "当前未配置可用的题目补全与标准化模型。"
    if error == "question_auto_tagger_unavailable":
        return "当前未配置可用的题目自动考点标注模型。"
    if error == "invalid_review_status":
        return "AI 返回了无效的审核状态。"
    return error or "AI 服务执行失败。"


def _http_exception_message(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return "请求执行失败。"


def _batch_review_failure_message(
    question: PaperReviewQuestion,
    by_id: dict[int, PaperReviewQuestion],
    message: str,
) -> str:
    prefix = _batch_review_question_label(question)
    normalized_message = (message or "").strip() or "请求执行失败。"
    if question.node_role != "group":
        return f"{prefix}：{normalized_message}"

    if normalized_message == "题组下仍有子问未人工审核通过":
        child_questions = [
            item
            for item in by_id.values()
            if item.parent_question_id == question.id and (item.review_status or "").strip() != "approved"
        ]
        if child_questions:
            child_labels = "、".join(_batch_review_question_label(item, include_role=False) for item in child_questions[:3])
            suffix = " 等" if len(child_questions) > 3 else ""
            return f"{prefix}：{normalized_message}（未通过子问：{child_labels}{suffix}）"

    return f"{prefix}：{normalized_message}"


def _batch_review_question_label(question: PaperReviewQuestion, *, include_role: bool = True) -> str:
    question_no = str(question.question_no or "").strip() or f"ID {question.id}"
    if not include_role:
        return question_no
    if question.node_role == "group":
        return f"题组 {question_no}"
    if question.node_role == "subquestion":
        return f"子问 {question_no}"
    return f"题目 {question_no}"


def _build_ai_batch_message(
    *,
    action_label: str,
    requested_count: int,
    success_count: int,
    failed_count: int,
    changed_count: int,
    failures: list[PaperReviewAIBatchFailureResponse],
) -> str:
    parts = [f"{action_label}已完成：共 {requested_count} 道，成功 {success_count} 道"]
    if action_label == "AI 补全与标准化":
        parts.append(f"有更新 {changed_count} 道")
    if failed_count:
        parts.append(f"失败 {failed_count} 道")
    message = "，".join(parts) + "。"
    if failures:
        message += f" 首个失败：{failures[0].message}"
    return message


def _unique_question_ids(question_ids: list[int]) -> list[int]:
    seen: set[int] = set()
    normalized: list[int] = []
    for question_id in question_ids:
        try:
            normalized_id = int(question_id)
        except (TypeError, ValueError):
            continue
        if normalized_id <= 0 or normalized_id in seen:
            continue
        seen.add(normalized_id)
        normalized.append(normalized_id)
    return normalized


def _paper_markdown_image_roots(asset_id: int | None) -> list[Path]:
    if not asset_id:
        return []
    checkpoint_root = _get_pdf_ocr_checkpoint_root() / "layout"
    if not checkpoint_root.exists():
        return []
    namespace = f"paper_asset_{asset_id}"
    roots: list[Path] = []
    for namespace_path in checkpoint_root.rglob(CHECKPOINT_NAMESPACE_FILENAME):
        try:
            if namespace_path.read_text(encoding="utf-8").strip() != namespace:
                continue
        except OSError:
            continue
        checkpoint_dir = namespace_path.parent
        for assets_dir in sorted(checkpoint_dir.glob("page_*_assets")):
            if assets_dir.is_dir():
                roots.append(assets_dir)
    return roots


def _inline_review_images(text: str, image_roots: list[Path]) -> str:
    if not text or not image_roots:
        return text

    def replace_html(match):
        before = match.group(1)
        image_path = str(match.group(2) or "").replace("\\", "/")
        after = match.group(3)
        data_url = _review_image_to_data_url(image_path, image_roots)
        if not data_url:
            return match.group(0)
        return f'<img{before}src="{data_url}"{after}>'

    def replace_markdown(match):
        alt = match.group(1)
        image_path = str(match.group(2) or "").replace("\\", "/")
        data_url = _review_image_to_data_url(image_path, image_roots)
        if not data_url:
            return match.group(0)
        return f"![{alt}]({data_url})"

    updated = re.sub(r'<img([^>]*?)src=["\'](imgs/[^"\']+)["\']([^>]*?)>', replace_html, text, flags=re.IGNORECASE)
    updated = re.sub(r"!\[([^\]]*)\]\((imgs/[^)\s]+)\)", replace_markdown, updated)
    return updated


def _inline_optional_review_images(text: str | None, image_roots: list[Path]) -> str | None:
    if not text:
        return text
    return _inline_review_images(text, image_roots)


def _review_image_to_data_url(relative_path: str, image_roots: list[Path]) -> str:
    normalized = relative_path.replace("\\", "/").lstrip("/")
    for root in image_roots:
        candidate = root / normalized
        if not candidate.exists() and normalized.startswith("imgs/"):
            candidate = root / normalized.removeprefix("imgs/")
        if not candidate.exists():
            continue
        raw = candidate.read_bytes()
        mime = mimetypes.guess_type(candidate.name)[0] or "image/jpeg"
        encoded = base64.b64encode(raw).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    return ""


def _normalize_match_text(value: str) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n").lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _score_knowledge_point_match(
    corpus: str,
    point: KnowledgePoint,
    aliases: list[KnowledgePointAlias],
) -> tuple[int, str]:
    best_score = 0
    best_reason = ""
    names = [(point.name or "").strip(), *[(alias.alias_name or "").strip() for alias in aliases]]
    for candidate in [name for name in dict.fromkeys(names) if name]:
        normalized = _normalize_match_text(candidate)
        if len(normalized) < 2:
            continue
        if normalized in corpus:
            score = 80 if candidate == point.name else 65
            if score > best_score:
                best_score = score
                best_reason = f"命中知识点名称“{candidate}”"
    for keyword in point.keywords_json or []:
        normalized_keyword = _normalize_match_text(str(keyword))
        if len(normalized_keyword) < 2:
            continue
        if normalized_keyword in corpus:
            score = 55
            if score > best_score:
                best_score = score
                best_reason = f"命中关键词“{keyword}”"
    if point.chapter_id and point.path:
        path_leaf = _normalize_match_text(point.path.split("/")[-1])
        if len(path_leaf) >= 2 and path_leaf in corpus and 35 > best_score:
            best_score = 35
            best_reason = f"命中路径节点“{point.path.split('/')[-1]}”"
    return best_score, best_reason


def _suggest_knowledge_point_rows(
    *,
    question: PaperReviewQuestion,
    points: list[KnowledgePoint],
    aliases_by_point: dict[int, list[KnowledgePointAlias]],
    excluded_point_ids: set[int],
) -> list[PaperReviewQuestionKnowledgePoint]:
    corpus = _normalize_match_text(
        "\n".join(
            [
                question.source_section_name,
                question.stem_text,
                question.answer_text or "",
                question.analysis_text or "",
            ]
        )
    )
    scored: list[tuple[int, KnowledgePoint, str]] = []
    for point in points:
        if point.id in excluded_point_ids:
            continue
        score, reason = _score_knowledge_point_match(corpus, point, aliases_by_point.get(point.id, []))
        if score <= 0:
            continue
        scored.append((score, point, reason))
    scored.sort(key=lambda item: (-item[0], item[1].sort_order, item[1].id))
    rows: list[PaperReviewQuestionKnowledgePoint] = []
    for index, (score, point, reason) in enumerate(scored[:5], start=1):
        rows.append(
            PaperReviewQuestionKnowledgePoint(
                tenant_id=question.tenant_id,
                question_id=question.id,
                knowledge_point_id=point.id,
                status="suggested",
                relation_type="primary" if index == 1 else "secondary",
                source="rule",
                confidence=min(round(score / 100, 2), 1.0),
                reason=reason,
                rank=index,
                created_by=question.updated_by,
                updated_by=question.updated_by,
            )
        )
    return rows

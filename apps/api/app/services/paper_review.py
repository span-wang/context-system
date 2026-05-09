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
from app.schemas.papers import PaperSectionResponse
from app.services.paper_parser_rules.engine import RuleBlock, RuleSection, parse_question_block, parse_sections_from_text
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
    ) -> PaperReviewQuestionResponse:
        image_roots = image_roots or []
        tag_rows = tag_rows or []
        point_map = point_map or {}
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
                "source_raw_text": _inline_review_images(question.source_raw_text, image_roots),
                "stem_text": _inline_review_images(question.stem_text, image_roots),
                "analysis_text": _inline_review_images(question.analysis_text or "", image_roots) or question.analysis_text,
                "options_json": [_inline_review_images(option, image_roots) for option in (question.options_json or [])],
                "suggested_knowledge_points": suggested,
                "confirmed_knowledge_points": confirmed,
            }
        )

    def _question_response_with_existing_tags(self, question: PaperReviewQuestion) -> PaperReviewQuestionResponse:
        paper = self.repository.get_paper(question.paper_id)
        asset = self.repository.get_asset(paper.asset_id if paper else None)
        tag_rows = self.repository.list_question_knowledge_points([question.id])
        point_ids = {row.knowledge_point_id for row in tag_rows}
        point_map = {
            point.id: point
            for point in self.session.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).all()
        } if point_ids else {}
        return self._question_response(
            question,
            image_roots=_paper_markdown_image_roots(asset.id if asset else None),
            tag_rows=tag_rows,
            point_map=point_map,
        )

    def get_workspace(self, paper_id: int, *, auto_rebuild: bool = True) -> PaperReviewWorkspaceResponse:
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")

        asset = self.repository.get_asset(paper.asset_id)
        questions = self.repository.list_questions(paper.id)
        if auto_rebuild and not questions and asset and (asset.parsed_text or "").strip():
            self.rebuild_questions(paper.id, commit=True)
            questions = self.repository.list_questions(paper.id)

        subject = self.repository.get_subject(paper.subject_id)
        category = self.repository.get_category(paper.category_id)
        sections = [PaperSectionResponse.model_validate(item) for item in self.repository.list_sections(paper.id)]
        summary = _build_summary(questions)
        image_roots = _paper_markdown_image_roots(asset.id if asset else None)
        tag_rows = self.repository.list_question_knowledge_points([question.id for question in questions])
        point_ids = sorted({row.knowledge_point_id for row in tag_rows})
        point_map = {
            point.id: point
            for point in self.session.query(KnowledgePoint).filter(KnowledgePoint.id.in_(point_ids)).all()
        } if point_ids else {}
        tags_by_question: dict[int, list[PaperReviewQuestionKnowledgePoint]] = {}
        for row in tag_rows:
            tags_by_question.setdefault(row.question_id, []).append(row)
        return PaperReviewWorkspaceResponse(
            paper=PaperReviewPaperResponse(
                id=paper.id,
                paper_name=paper.paper_name,
                subject_name=subject.name if subject else None,
                category=category.name if category else _category_from_asset_tags(asset.tags_json if asset else None),
                status=paper.status,
                review_status=paper.review_status,
                total_question_count=paper.total_question_count,
                question_review_count=len(questions),
            ),
            sections=sections,
            summary=summary,
            questions=[
                self._question_response(
                    item,
                    image_roots=image_roots,
                    tag_rows=tags_by_question.get(item.id, []),
                    point_map=point_map,
                )
                for item in questions
            ],
        )

    def rebuild_questions(self, paper_id: int, *, commit: bool = True) -> PaperReviewRebuildResponse:
        paper = self.repository.get_paper(paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="试卷不存在")
        asset = self.repository.get_asset(paper.asset_id)
        if asset is None or not (asset.parsed_text or "").strip():
            raise HTTPException(status_code=422, detail="试卷还没有可用的解析文本，无法重建题目")

        paper_sections = self.repository.list_sections(paper.id)
        cleaned_text = clean_parsed_document(
            ParsedDocument(
                text=asset.parsed_text,
                markdown=asset.parsed_text,
                provider="legacy_cache",
                used_ocr=True,
                warnings=[],
            ),
            force=True,
        ).text
        rule_sections = parse_sections_from_text(cleaned_text)
        section_payloads = _build_section_payloads(rule_sections, paper_sections)
        return self.sync_questions_from_sections(
            paper_id=paper.id,
            section_payloads=section_payloads,
            operator_id=paper.updated_by,
            commit=commit,
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
        sort_order = 0
        for payload in sorted(section_payloads, key=lambda item: int(item.get("sort_order") or 0)):
            rule_section = RuleSection(
                title=str(payload.get("title") or "自动切题"),
                section_type=str(payload.get("section_type") or "mixed"),
                sort_order=int(payload.get("sort_order") or 0),
                blocks=[],
            )
            section_id = _to_optional_int(payload.get("section_id"))
            source_section_name = str(payload.get("title") or "自动切题")
            for raw_block in payload.get("blocks") or []:
                raw_text = str((raw_block or {}).get("raw_text") or "").strip()
                if not raw_text:
                    continue
                sort_order += 1
                parsed = _parse_review_block(
                    raw_text=raw_text,
                    question_no_override=str((raw_block or {}).get("question_no_override") or "").strip() or None,
                    stem_prefix=str((raw_block or {}).get("stem_prefix") or "").strip() or None,
                    section=rule_section,
                    sort_order=sort_order,
                )
                content_fingerprint = _make_question_fingerprint(
                    section_id=section_id,
                    question_no=parsed.question_no,
                    source_raw_text=raw_text,
                )
                question = existing_by_fingerprint.get(content_fingerprint)
                if question is None:
                    question = PaperReviewQuestion(
                        tenant_id=paper.tenant_id,
                        paper_id=paper.id,
                        section_id=section_id,
                        question_uid=_make_question_uid(paper.id, section_id, sort_order, parsed.question_no, parsed.stem_text),
                        content_fingerprint=content_fingerprint,
                        sort_order=sort_order,
                        question_no=parsed.question_no,
                        question_type=parsed.question_type,
                        source_section_name=source_section_name,
                        source_raw_text=raw_text,
                        stem_text=parsed.stem_text,
                        options_json=parsed.options,
                        answer_text=parsed.answer_text,
                        analysis_text=parsed.analysis_text,
                        difficulty_level=parsed.difficulty_level,
                        quality_score=parsed.quality_score,
                        subquestion_count=parsed.subquestion_count,
                        quality_issues_json=parsed.quality_issues,
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
                else:
                    question.section_id = section_id
                    question.question_uid = _make_question_uid(paper.id, section_id, sort_order, parsed.question_no, parsed.stem_text)
                    question.content_fingerprint = content_fingerprint
                    question.sort_order = sort_order
                    question.question_no = parsed.question_no
                    question.question_type = parsed.question_type
                    question.source_section_name = source_section_name
                    question.source_raw_text = raw_text
                    question.stem_text = parsed.stem_text
                    question.options_json = parsed.options
                    question.answer_text = parsed.answer_text
                    question.analysis_text = parsed.analysis_text
                    question.difficulty_level = parsed.difficulty_level
                    question.quality_score = parsed.quality_score
                    question.subquestion_count = parsed.subquestion_count
                    question.quality_issues_json = parsed.quality_issues
                    question.parse_status = "parsed"
                    question.updated_by = operator_id
                normalize_question_fields(question)
                active_question_ids.append(question.id)

                if subject_points:
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

        active_question_id_set = set(active_question_ids)
        removed_questions = [question for question in existing_questions if question.id not in active_question_id_set]
        self.repository.delete_question_knowledge_points_by_question_ids([question.id for question in removed_questions])
        for question in removed_questions:
            self.session.delete(question)

        paper.total_question_count = len(active_question_ids)
        paper.review_status = "pending" if active_question_ids else paper.review_status

        if commit:
            self.session.commit()
        else:
            self.session.flush()

        return PaperReviewRebuildResponse(
            paper_id=paper.id,
            imported_count=len(active_question_ids),
            replaced_count=replaced_count,
            section_count=len(section_payloads),
            message=f"已同步 {len(active_question_ids)} 道题，覆盖 {replaced_count} 条旧题目记录。",
        )

    def update_question(self, question_id: int, payload: PaperReviewQuestionUpdateRequest) -> PaperReviewQuestionResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")

        content_changed = False
        review_changed = False

        if payload.question_type is not None:
            next_question_type = payload.question_type.strip()
            if next_question_type and next_question_type != question.question_type:
                question.question_type = next_question_type
                content_changed = True

        if payload.stem_text is not None:
            next_stem = normalize_question_text(payload.stem_text)
            if next_stem and next_stem != question.stem_text:
                question.stem_text = next_stem
                content_changed = True

        if payload.options_json is not None:
            next_options = normalize_options(payload.options_json)
            if next_options != (question.options_json or []):
                question.options_json = next_options
                content_changed = True

        if payload.answer_text is not None:
            next_answer = normalize_answer(payload.answer_text, question.question_type)
            if next_answer != question.answer_text:
                question.answer_text = next_answer
                content_changed = True

        if payload.analysis_text is not None:
            next_analysis = normalize_analysis(payload.analysis_text)
            if next_analysis != question.analysis_text:
                question.analysis_text = next_analysis
                content_changed = True

        if payload.review_status is not None and payload.review_status != question.review_status:
            question.review_status = payload.review_status
            review_changed = True

        if payload.review_note is not None:
            next_note = normalize_question_text(payload.review_note) or None
            if next_note != question.review_note:
                question.review_note = next_note
                review_changed = True

        if content_changed:
            question.parse_status = "manual_updated"
        if review_changed:
            question.reviewed_at = datetime.utcnow()

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
        self.session.commit()
        self.session.refresh(question)
        image_roots = _paper_markdown_image_roots(self.repository.get_asset(paper.asset_id).id if self.repository.get_asset(paper.asset_id) else None)
        return self._question_response(
            question,
            image_roots=image_roots,
            tag_rows=rows,
            point_map=scoped_points,
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
        for question in questions:
            if force_question_id is not None:
                if question.id == force_question_id:
                    target_questions.append(question)
                continue
            if tags_by_question.get(question.id):
                skipped_count += 1
                continue
            target_questions.append(question)

        if force_question_id is not None and not target_questions:
            raise HTTPException(status_code=404, detail="指定题目不存在或不属于当前试卷")
        if force_question_id is None and not target_questions:
            return PaperReviewAutoTagResponse(
                paper_id=paper.id,
                status="completed",
                progress=100,
                requested_count=0,
                updated_count=0,
                failed_count=0,
                skipped_count=skipped_count,
                message=f"当前试卷题目都已有考点标注，已跳过 {skipped_count} 道。",
            )

        question_payloads = [
            {
                "id": question.id,
                "question_type": question.question_type,
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
        local_changed = normalize_question_fields(question)
        result = standardize_question_with_ai(question, subject_name=subject.name if subject else None)

        if result.error and not local_changed:
            raise HTTPException(status_code=503, detail=_format_ai_error(result.error))

        changed = local_changed or result.changed
        if changed:
            question.review_status = "needs_revision"
            question.review_note = _append_note(question.review_note, "题目已重新标准化，请人工复核。")
        if result.used_ai and not result.error:
            question.last_ai_standardized_at = datetime.utcnow()
            question.ai_standardization_note = "AI 已完成题目补全与标准化。"
        elif local_changed:
            question.ai_standardization_note = "已完成规则级标准化；AI 当前不可用。"

        self.session.commit()
        self.session.refresh(question)
        if result.error and local_changed:
            message = f"已完成基础标准化，AI 未执行：{_format_ai_error(result.error)}"
        elif changed:
            message = "题目已完成补全与标准化。"
        else:
            message = "题目无需补全或标准化。"
        return PaperReviewAIActionResponse(
            message=message,
            changed=changed,
            used_ai=result.used_ai,
            question=self._question_response_with_existing_tags(question),
        )

    def review_question(self, question_id: int) -> PaperReviewAIActionResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="题目不存在")

        paper = self.repository.get_paper(question.paper_id)
        subject = self.repository.get_subject(paper.subject_id if paper else None)
        result = review_question_with_ai(question, subject_name=subject.name if subject else None)
        if result.error or result.review_status is None:
            raise HTTPException(status_code=503, detail=_format_ai_error(result.error or "ai_review_failed"))

        question.ai_review_status = result.review_status
        question.ai_review_note = result.review_note
        question.last_ai_reviewed_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(question)
        return PaperReviewAIActionResponse(
            message="AI 已完成答案与解析审核。",
            changed=False,
            used_ai=result.used_ai,
            question=self._question_response_with_existing_tags(question),
        )


def _build_section_payloads(rule_sections: list[RuleSection], paper_sections: list[Any]) -> list[dict[str, Any]]:
    sections_by_sort = {section.sort_order: section for section in paper_sections}
    payloads: list[dict[str, Any]] = []
    for rule_section in rule_sections:
        section = sections_by_sort.get(rule_section.sort_order)
        payloads.append(
            {
                "section_id": section.id if section else None,
                "title": rule_section.title,
                "section_type": rule_section.section_type,
                "sort_order": rule_section.sort_order,
                "blocks": [
                    {
                        "raw_text": block.raw_text,
                        "question_no_override": block.question_no_override,
                        "stem_prefix": block.stem_prefix,
                    }
                    for block in rule_section.blocks
                    if block.raw_text.strip()
                ],
            }
        )
    return payloads


def _build_summary(questions: list[PaperReviewQuestion]) -> PaperReviewSummaryResponse:
    summary = PaperReviewSummaryResponse(total_questions=len(questions))
    for question in questions:
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
        if not (question.answer_text or "").strip() or not (question.analysis_text or "").strip():
            summary.missing_solution_count += 1
    return summary


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


def _parse_review_block(
    *,
    raw_text: str,
    question_no_override: str | None,
    stem_prefix: str | None,
    section: RuleSection,
    sort_order: int,
):
    try:
        return parse_question_block(
            RuleBlock(
                raw_text=raw_text,
                question_no_override=question_no_override,
                stem_prefix=stem_prefix,
            ),
            section,
        )
    except Exception:
        fallback_stem = "\n\n".join(part for part in [stem_prefix, raw_text] if part).strip()
        return type(
            "FallbackRuleQuestion",
            (),
            {
                "question_no": question_no_override or str(sort_order),
                "question_type": section.section_type or "mixed",
                "stem_text": fallback_stem[:6000] or f"题目 {sort_order}",
                "options": [],
                "answer_text": None,
                "analysis_text": None,
                "difficulty_level": 3,
                "quality_score": 0.35,
                "subquestion_count": 0,
                "source_section_name": section.title,
                "quality_issues": ["题块二次结构化失败，需要人工整理"],
            },
        )()


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


def _format_ai_error(error: str) -> str:
    if error == "reviewer_llm_unavailable":
        return "当前未配置可用的 reviewer LLM。"
    if error == "invalid_review_status":
        return "AI 返回了无效的审核状态。"
    return error or "AI 服务执行失败。"


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

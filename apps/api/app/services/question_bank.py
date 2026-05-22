from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import math
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import KnowledgePoint, PaperReviewQuestion, QuestionBankItem, QuestionBankSourceLink
from app.services.paper_review_ai import normalize_options, normalize_question_text
from app.repositories.question_bank import QuestionBankRepository
from app.schemas.question_bank import (
    QuestionBankAnalysisChapterItemResponse,
    QuestionBankAnalysisPointItemResponse,
    QuestionBankAnalysisPredictionItemResponse,
    QuestionBankAnalysisReportResponse,
    QuestionBankAnalysisSummaryResponse,
    QuestionBankDeleteResponse,
    QuestionBankAnalysisYearOverviewResponse,
    QuestionBankExportPaperOptionResponse,
    QuestionBankItemResponse,
    QuestionBankItemUpdateRequest,
    QuestionBankKnowledgeAnalysisResponse,
    QuestionBankKnowledgePointResponse,
    QuestionBankListResponse,
    QuestionBankPaperExportRequest,
    QuestionBankSourceResponse,
    QuestionBankSyncResponse,
)


class QuestionBankService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = QuestionBankRepository(session)

    def list_questions(
        self,
        *,
        subject_id: int | None = None,
        category_id: int | None = None,
        status: str | None = None,
        question_type: str | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QuestionBankListResponse:
        safe_limit = max(1, min(limit, 200))
        safe_offset = max(0, offset)
        rows, total = self.repository.list_questions(
            subject_id=subject_id,
            category_id=category_id,
            status=status,
            question_type=question_type,
            keyword=keyword.strip() if keyword else None,
            limit=safe_limit,
            offset=safe_offset,
        )
        root_questions = [item for item, _subject, _category, _paper in rows]
        children = self.repository.list_child_questions([item.id for item in root_questions])
        response_map = self._build_question_response_map(
            [*root_questions, *children],
            subject_name_by_id={item.id: subject.name if subject else None for item, subject, _category, _paper in rows},
            category_name_by_id={item.id: category.name if category else None for item, _subject, category, _paper in rows},
            first_source_paper_by_id={item.id: paper.paper_name if paper else None for item, _subject, _category, paper in rows},
        )
        return QuestionBankListResponse(
            total=total,
            items=[response_map[item.id] for item in root_questions if item.id in response_map],
            status_counts=self.repository.count_by_status(),
        )

    def get_question(self, question_id: int) -> QuestionBankItemResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="正式题不存在")
        children = self.repository.list_child_questions([question.id])
        response_map = self._build_question_response_map([question, *children])
        return response_map.get(question.id) or self._question_response(question)

    def list_export_papers(
        self,
        *,
        subject_id: int | None = None,
        category_id: int | None = None,
        status: str | None = None,
        question_type: str | None = None,
        keyword: str | None = None,
    ) -> list[QuestionBankExportPaperOptionResponse]:
        rows = self.repository.list_export_papers(
            subject_id=subject_id,
            category_id=category_id,
            status=status,
            question_type=question_type,
            keyword=keyword.strip() if keyword else None,
        )
        return [
            QuestionBankExportPaperOptionResponse(
                paper_id=paper.id,
                paper_name=paper.paper_name,
                subject_name=subject.name if subject else None,
                category_name=category.name if category else None,
                question_count=question_count,
            )
            for paper, subject, category, question_count in rows
        ]

    def export_questions_by_paper(self, payload: QuestionBankPaperExportRequest) -> tuple[str, str]:
        rows = self.repository.list_export_rows(
            paper_id=payload.paper_id,
            subject_id=payload.subject_id,
            category_id=payload.category_id,
            status=payload.status,
            question_type=payload.question_type,
            keyword=payload.keyword.strip() if payload.keyword else None,
        )
        if not rows:
            raise HTTPException(status_code=422, detail="所选试卷下没有匹配当前筛选条件的正式题")

        paper = rows[0][3]
        root_questions = [bank_question for _source_link, bank_question, _review_question, _paper in rows]
        child_questions = self.repository.list_child_questions([question.id for question in root_questions])
        child_by_parent: dict[int, list[QuestionBankItem]] = defaultdict(list)
        for child in child_questions:
            if child.parent_question_id is None:
                continue
            child_by_parent.setdefault(child.parent_question_id, []).append(child)
        child_review_links: dict[int, tuple[QuestionBankSourceLink, PaperReviewQuestion] | None] = {}
        for child in child_questions:
            source_rows = self.repository.list_sources(child.id)
            child_review_links[child.id] = (source_rows[0][0], source_rows[0][1]) if source_rows and source_rows[0][1] is not None else None
        records = [
            _build_export_record(
                source_link,
                bank_question,
                review_question,
                child_questions=child_by_parent.get(bank_question.id, []),
                child_review_links=child_review_links,
            )
            for source_link, bank_question, review_question, _ in rows
        ]
        content = _render_question_bank_markdown(
            paper_name=paper.paper_name,
            records=records,
            solution_mode=payload.solution_mode,
        )
        return content, _build_export_filename(paper.paper_name, payload.solution_mode)

    def update_question(self, question_id: int, payload: QuestionBankItemUpdateRequest) -> QuestionBankItemResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="正式题不存在")
        if payload.status is not None:
            question.status = payload.status
        self.session.commit()
        self.session.refresh(question)
        return self._question_response(question)

    def delete_question(self, question_id: int) -> QuestionBankDeleteResponse:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="正式题不存在")

        question_uid = question.question_uid
        child_ids = [item.id for item in self.repository.list_child_questions([question.id])]
        removed_source_link_count = self.repository.delete_source_links_by_bank_question_ids([question.id, *child_ids])
        self.repository.delete_question(question)
        self.session.commit()

        return QuestionBankDeleteResponse(
            id=question_id,
            question_uid=question_uid,
            deleted=True,
            removed_source_link_count=removed_source_link_count,
            message="正式题已删除，原始审核题保留。",
        )

    def list_sources(self, question_id: int) -> list[QuestionBankSourceResponse]:
        question = self.repository.get_question(question_id)
        if question is None:
            raise HTTPException(status_code=404, detail="正式题不存在")
        child_ids = [item.id for item in self.repository.list_child_questions([question.id])]
        return [
            QuestionBankSourceResponse(
                id=link.id,
                source_type=link.source_type,
                source_question_id=link.source_question_id,
                paper_id=link.paper_id,
                paper_name=paper.paper_name if paper else None,
                section_id=link.section_id,
                question_no=link.question_no,
                status=link.status,
                created_at=link.created_at,
            )
            for link, _review_question, paper in self.repository.list_sources_by_bank_question_ids([question.id, *child_ids])
        ]

    def sync_from_review_question(self, question_id: int, *, commit: bool = True) -> QuestionBankSyncResponse:
        review_question = self.repository.get_review_question(question_id)
        if review_question is None:
            raise HTTPException(status_code=404, detail="题目不存在")
        review_questions = self.repository.list_review_questions(review_question.paper_id)
        review_by_id = {item.id: item for item in review_questions}
        root_review_question = _root_review_question(review_question, review_by_id)
        paper = self.repository.get_paper(root_review_question.paper_id)
        if root_review_question.node_role == "group":
            if (root_review_question.review_status or "").strip() != "approved":
                raise HTTPException(status_code=409, detail="只有人工审核通过的题组才能进入正式题库")
            child_review_questions = [item for item in review_questions if item.parent_question_id == root_review_question.id]
            _validate_review_group_ready(root_review_question, child_review_questions)
            bank_question, source_link, created, linked = self._sync_group_question(
                root_review_question=root_review_question,
                child_review_questions=child_review_questions,
                paper=paper,
            )
        else:
            if (review_question.review_status or "").strip() != "approved":
                raise HTTPException(status_code=409, detail="只有人工审核通过的题目才能进入正式题库")
            _validate_review_question_ready(review_question)
            touched_bank_ids: set[int] = set()
            bank_question, source_link, created, linked = self._upsert_bank_question(
                review_question,
                paper=paper,
                parent_bank_question=None,
                touched_bank_ids=touched_bank_ids,
            )
            self._refresh_bank_source_counts(touched_bank_ids)

        if commit:
            self.session.commit()
        else:
            self.session.flush()

        return QuestionBankSyncResponse(
            bank_question_id=bank_question.id,
            source_link_id=source_link.id,
            created=created,
            linked=linked,
            status=bank_question.status,
            message="题目已同步至正式题库。",
        )

    def _sync_group_question(
        self,
        *,
        root_review_question: PaperReviewQuestion,
        child_review_questions: list[PaperReviewQuestion],
        paper: object | None,
    ) -> tuple[QuestionBankItem, QuestionBankSourceLink, bool, bool]:
        touched_bank_ids: set[int] = set()
        bank_question, source_link, created, linked = self._upsert_bank_question(
            root_review_question,
            paper=paper,
            parent_bank_question=None,
            child_review_questions=child_review_questions,
            touched_bank_ids=touched_bank_ids,
        )
        for child_question in child_review_questions:
            self._upsert_bank_question(
                child_question,
                paper=paper,
                parent_bank_question=bank_question,
                touched_bank_ids=touched_bank_ids,
            )
        self._refresh_bank_source_counts(touched_bank_ids)
        return bank_question, source_link, created, linked

    def _upsert_bank_question(
        self,
        review_question: PaperReviewQuestion,
        *,
        paper: object | None,
        parent_bank_question: QuestionBankItem | None,
        child_review_questions: list[PaperReviewQuestion] | None = None,
        touched_bank_ids: set[int] | None = None,
    ) -> tuple[QuestionBankItem, QuestionBankSourceLink, bool, bool]:
        touched_bank_ids = touched_bank_ids if touched_bank_ids is not None else set()
        fingerprint = _make_bank_fingerprint(review_question, child_questions=child_review_questions)
        bank_question = self.repository.get_by_fingerprint(fingerprint)
        if bank_question is None:
            legacy_fingerprint = _make_bank_fingerprint(
                review_question,
                child_questions=child_review_questions,
                normalize_option_labels=False,
            )
            if legacy_fingerprint != fingerprint:
                bank_question = self.repository.get_by_fingerprint(legacy_fingerprint)
        created = False
        if bank_question is None:
            bank_question = QuestionBankItem(
                tenant_id=review_question.tenant_id,
                subject_id=paper.subject_id if paper else None,
                category_id=paper.category_id if paper else None,
                parent_question_id=parent_bank_question.id if parent_bank_question else None,
                question_uid=_make_bank_uid(fingerprint),
                content_fingerprint=fingerprint,
                node_role=review_question.node_role or "standalone",
                question_type=review_question.question_type,
                group_stem=review_question.group_stem,
                material_text=review_question.material_text,
                stem_text=review_question.stem_text,
                options_json=normalize_options(review_question.options_json, review_question.question_type),
                answer_text=review_question.answer_text,
                analysis_text=review_question.analysis_text,
                difficulty_level=review_question.difficulty_level,
                quality_score=review_question.quality_score,
                status="active",
                source_count=0,
                first_source_question_id=review_question.id,
                created_by=review_question.reviewed_by or review_question.updated_by,
                updated_by=review_question.reviewed_by or review_question.updated_by,
            )
            self.repository.create_question(bank_question)
            created = True
        else:
            bank_question.subject_id = bank_question.subject_id or (paper.subject_id if paper else None)
            bank_question.category_id = bank_question.category_id or (paper.category_id if paper else None)
            bank_question.parent_question_id = parent_bank_question.id if parent_bank_question else None
            bank_question.node_role = review_question.node_role or "standalone"
            bank_question.question_type = review_question.question_type
            bank_question.group_stem = review_question.group_stem
            bank_question.material_text = review_question.material_text
            bank_question.stem_text = review_question.stem_text
            bank_question.options_json = normalize_options(review_question.options_json, review_question.question_type)
            bank_question.answer_text = review_question.answer_text
            bank_question.analysis_text = review_question.analysis_text
            bank_question.difficulty_level = review_question.difficulty_level
            bank_question.quality_score = review_question.quality_score
            bank_question.first_source_question_id = review_question.id
            bank_question.updated_by = review_question.reviewed_by or review_question.updated_by

        source_link = self.repository.get_source_link("paper_review_question", review_question.id)
        previous_bank_question_id = source_link.bank_question_id if source_link is not None else None
        linked = False
        if source_link is None:
            source_link = QuestionBankSourceLink(
                tenant_id=review_question.tenant_id,
                bank_question_id=bank_question.id,
                source_type="paper_review_question",
                source_question_id=review_question.id,
                paper_id=review_question.paper_id,
                section_id=review_question.section_id,
                question_no=review_question.question_no,
                source_fingerprint=review_question.content_fingerprint,
                status="active",
                created_by=review_question.reviewed_by or review_question.updated_by,
                updated_by=review_question.reviewed_by or review_question.updated_by,
            )
            self.repository.create_source_link(source_link)
            linked = True
        else:
            source_link.bank_question_id = bank_question.id
            source_link.paper_id = review_question.paper_id
            source_link.section_id = review_question.section_id
            source_link.question_no = review_question.question_no
            source_link.source_fingerprint = review_question.content_fingerprint
            source_link.status = "active"
            source_link.updated_by = review_question.reviewed_by or review_question.updated_by

        touched_bank_ids.add(bank_question.id)
        if previous_bank_question_id is not None and previous_bank_question_id != bank_question.id:
            touched_bank_ids.add(previous_bank_question_id)
        self.session.flush()
        return bank_question, source_link, created, linked

    def _refresh_bank_source_counts(self, bank_question_ids: set[int]) -> None:
        for bank_question_id in sorted(bank_question_ids):
            bank_question = self.repository.get_question(bank_question_id)
            if bank_question is None:
                continue
            bank_question.source_count = self.repository.count_sources(bank_question.id)

    def get_knowledge_analysis(
        self,
        *,
        subject_id: int | None = None,
        category_id: int | None = None,
        start_year: int | None = None,
        end_year: int | None = None,
    ) -> QuestionBankKnowledgeAnalysisResponse:
        subject = self.repository.get_subject(subject_id) if subject_id is not None else None
        category = self.repository.get_category(category_id) if category_id is not None else None
        rows = self.repository.list_knowledge_analysis_rows(
            subject_id=subject_id,
            category_id=category_id,
            start_year=start_year,
            end_year=end_year,
        )

        year_candidates = sorted(
            {
                int(paper.exam_year)
                for _bank_question, _source_link, _review_question, paper, _knowledge_point in rows
                if paper.exam_year is not None
            }
        )
        years = _expanded_years(year_candidates, start_year=start_year, end_year=end_year)
        prediction_year = (years[-1] + 1) if years else ((end_year or start_year or 0) + 1 if (end_year or start_year) else None)

        paper_ids = {paper.id for _bank_question, _source_link, _review_question, paper, _knowledge_point in rows}
        bank_question_ids = {bank_question.id for bank_question, _source_link, _review_question, _paper, _knowledge_point in rows}
        source_question_ids = {review_question.id for _bank_question, _source_link, review_question, _paper, _knowledge_point in rows}
        tagged_source_question_ids = {
            review_question.id
            for _bank_question, _source_link, review_question, _paper, knowledge_point in rows
            if knowledge_point is not None
        }

        yearly_overview = _build_yearly_overview(rows, years)
        point_distribution = _build_point_distribution(rows, years)
        chapter_distribution = _build_chapter_distribution(rows, years)

        point_frequency_total = sum(item.total_frequency for item in point_distribution)
        top_point_total = sum(item.total_frequency for item in point_distribution[:5])
        summary = QuestionBankAnalysisSummaryResponse(
            paper_count=len(paper_ids),
            bank_question_count=len(bank_question_ids),
            source_question_count=len(source_question_ids),
            tagged_source_question_count=len(tagged_source_question_ids),
            point_count=len(point_distribution),
            chapter_count=len(chapter_distribution),
            year_count=len(years),
            primary_coverage_rate=_safe_ratio(len(tagged_source_question_ids), len(source_question_ids)),
            top_point_concentration_rate=_safe_ratio(top_point_total, point_frequency_total),
        )

        top_predicted_points = [
            _to_prediction_item(item)
            for item in point_distribution[:5]
        ]
        top_predicted_chapters = [
            _to_prediction_item(item)
            for item in chapter_distribution[:5]
        ]
        report = _build_analysis_report(
            summary=summary,
            years=years,
            prediction_year=prediction_year,
            point_distribution=point_distribution,
            chapter_distribution=chapter_distribution,
        )

        return QuestionBankKnowledgeAnalysisResponse(
            data_scope="正式题库 + 正式试卷（真题）",
            subject_id=subject.id if subject else subject_id,
            subject_name=subject.name if subject else None,
            category_id=category.id if category else category_id,
            category_name=category.name if category else None,
            start_year=start_year,
            end_year=end_year,
            years=years,
            prediction_year=prediction_year,
            summary=summary,
            yearly_overview=yearly_overview,
            point_distribution=point_distribution,
            chapter_distribution=chapter_distribution,
            top_predicted_points=top_predicted_points,
            top_predicted_chapters=top_predicted_chapters,
            report=report,
        )

    def _question_response(
        self,
        question: QuestionBankItem,
        *,
        subject_name: str | None = None,
        category_name: str | None = None,
        first_source_paper_name: str | None = None,
        subquestions: list[QuestionBankItemResponse] | None = None,
        knowledge_points: list[QuestionBankKnowledgePointResponse] | None = None,
    ) -> QuestionBankItemResponse:
        subquestions = subquestions or []
        if subject_name is None and question.subject_id is not None:
            subject = self.repository.get_subject(question.subject_id)
            subject_name = subject.name if subject else None
        if category_name is None and question.category_id is not None:
            category = self.repository.get_category(question.category_id)
            category_name = category.name if category else None
        if subject_name is None or category_name is None or first_source_paper_name is None:
            sources = self.repository.list_sources(question.id)
            first_paper = sources[0][2] if sources else None
            first_source_paper_name = first_source_paper_name or (first_paper.paper_name if first_paper else None)
        else:
            sources = []
        knowledge_points = knowledge_points or self._knowledge_points_for_question(question, subquestions=subquestions)
        question_no = None
        if sources:
            question_no = sources[0][0].question_no
        elif question.first_source_question_id is not None:
            review_question = self.repository.get_review_question(question.first_source_question_id)
            question_no = review_question.question_no if review_question else None
        return QuestionBankItemResponse.model_validate(
            {
                **question.__dict__,
                "subject_name": subject_name,
                "category_name": category_name,
                "first_source_paper_name": first_source_paper_name,
                "question_no": question_no,
                "options_json": normalize_options(question.options_json or [], question.question_type),
                "subquestion_count": len(subquestions) if question.node_role == "group" else 0,
                "knowledge_points": knowledge_points,
                "subquestions": subquestions,
            }
        )

    def _build_question_response_map(
        self,
        questions: list[QuestionBankItem],
        *,
        subject_name_by_id: dict[int, str | None] | None = None,
        category_name_by_id: dict[int, str | None] | None = None,
        first_source_paper_by_id: dict[int, str | None] | None = None,
    ) -> dict[int, QuestionBankItemResponse]:
        subject_name_by_id = subject_name_by_id or {}
        category_name_by_id = category_name_by_id or {}
        first_source_paper_by_id = first_source_paper_by_id or {}
        children_by_parent: dict[int, list[QuestionBankItem]] = defaultdict(list)
        question_no_by_bank_id: dict[int, str] = {}
        for question in questions:
            question_no = _question_bank_question_no(self, question)
            if question_no:
                question_no_by_bank_id[question.id] = question_no
        for question in questions:
            if question.parent_question_id is None:
                continue
            children_by_parent[question.parent_question_id].append(question)
        for items in children_by_parent.values():
            items.sort(key=lambda item: _question_bank_child_sort_key(item, question_no_by_bank_id.get(item.id)))
        response_map: dict[int, QuestionBankItemResponse] = {}

        def build(question: QuestionBankItem) -> QuestionBankItemResponse:
            cached = response_map.get(question.id)
            if cached is not None:
                return cached
            subquestions = [build(child) for child in children_by_parent.get(question.id, [])]
            payload = self._question_response(
                question,
                subject_name=subject_name_by_id.get(question.id),
                category_name=category_name_by_id.get(question.id),
                first_source_paper_name=first_source_paper_by_id.get(question.id),
                subquestions=subquestions,
            )
            response_map[question.id] = payload
            return payload

        for question in questions:
            build(question)
        return response_map

    def _knowledge_points_for_question(
        self,
        question: QuestionBankItem,
        *,
        subquestions: list[QuestionBankItemResponse] | None = None,
    ) -> list[QuestionBankKnowledgePointResponse]:
        if question.node_role == "group" and subquestions:
            seen: set[int] = set()
            rows: list[QuestionBankKnowledgePointResponse] = []
            for child in subquestions:
                for point in child.knowledge_points:
                    if point.id in seen:
                        continue
                    seen.add(point.id)
                    rows.append(point)
            return rows
        if question.first_source_question_id is None:
            return []
        rows = self.repository.list_review_question_tags(question.first_source_question_id)
        seen: set[int] = set()
        payload: list[QuestionBankKnowledgePointResponse] = []
        for tag, point in rows:
            if tag.status not in {"confirmed", "suggested"} or point.id in seen:
                continue
            seen.add(point.id)
            payload.append(
                QuestionBankKnowledgePointResponse(
                    id=point.id,
                    name=point.name,
                    path=point.path,
                    relation_type=tag.relation_type,
                    status=tag.status,
                )
            )
        return payload


def _validate_review_question_ready(question: PaperReviewQuestion) -> None:
    missing = []
    if question.node_role == "group":
        if not (question.group_stem or "").strip() and not (question.material_text or "").strip():
            missing.append("共用材料")
        if missing:
            raise HTTPException(status_code=422, detail=f"题组缺少{ '、'.join(missing) }，暂不能进入正式题库")
        return
    if not (question.stem_text or "").strip():
        missing.append("题干")
    if not (question.answer_text or "").strip():
        missing.append("答案")
    if not (question.analysis_text or "").strip():
        missing.append("解析")
    if missing:
        raise HTTPException(status_code=422, detail=f"题目缺少{ '、'.join(missing) }，暂不能进入正式题库")


def _validate_review_group_ready(
    root_question: PaperReviewQuestion,
    child_questions: list[PaperReviewQuestion],
) -> None:
    _validate_review_question_ready(root_question)
    if not child_questions:
        raise HTTPException(status_code=422, detail="题组下没有可入库的子问")
    for child in child_questions:
        if (child.review_status or "").strip() != "approved":
            raise HTTPException(status_code=409, detail="题组下仍有子问未人工审核通过")
        _validate_review_question_ready(child)


def _make_bank_uid(fingerprint: str) -> str:
    return f"QB{fingerprint[:24]}"


def _make_bank_fingerprint(
    question: PaperReviewQuestion,
    *,
    child_questions: list[PaperReviewQuestion] | None = None,
    normalize_option_labels: bool = True,
) -> str:
    parts = [
        _normalize_match_text(question.node_role or "standalone"),
        _normalize_match_text(question.question_type),
        _normalize_match_text(question.group_stem or ""),
        _normalize_match_text(question.material_text or ""),
        _normalize_match_text(question.stem_text),
        _normalize_options(question.options_json or [], normalize_option_labels=normalize_option_labels),
        _normalize_match_text(question.answer_text or ""),
    ]
    if child_questions:
        child_signatures = [
            "|".join(
                [
                    _normalize_match_text(child.question_no),
                    _normalize_match_text(child.question_type),
                    _normalize_match_text(child.stem_text),
                    _normalize_options(child.options_json or [], normalize_option_labels=normalize_option_labels),
                    _normalize_match_text(child.answer_text or ""),
                ]
            )
            for child in sorted(
                child_questions,
                key=lambda item: _review_child_sort_key(item),
            )
        ]
        parts.extend(child_signatures)
    normalized = "|".join(parts)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _normalize_options(options: list[str], *, normalize_option_labels: bool = True) -> str:
    values = normalize_options(options) if normalize_option_labels else options
    return "||".join(_normalize_match_text(option) for option in values)


def _question_bank_question_no(service: QuestionBankService, item: QuestionBankItem) -> str:
    if item.first_source_question_id is None:
        return ""
    review_question = service.repository.get_review_question(item.first_source_question_id)
    return str(review_question.question_no if review_question else "" or "").strip()


def _question_bank_child_sort_key(item: QuestionBankItem, question_no: str | None = None) -> tuple[int, str, int]:
    question_no = str(question_no or "").strip()
    numeric_parts = [int(part) for part in re.findall(r"\d+", question_no)]
    numeric_rank = numeric_parts[0] if numeric_parts else 10**9
    return (numeric_rank, question_no or str(item.id), int(item.id))


def _review_child_sort_key(item: PaperReviewQuestion) -> tuple[int, str, int]:
    question_no = str(item.question_no or "").strip()
    numeric_parts = [int(part) for part in re.findall(r"\d+", question_no)]
    numeric_rank = numeric_parts[0] if numeric_parts else 10**9
    return (numeric_rank, question_no or str(item.id), int(item.id))


def _normalize_match_text(value: str) -> str:
    text = (value or "").replace("\r\n", "\n").replace("\r", "\n").lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@dataclass(slots=True)
class _QuestionBankExportSubquestionRecord:
    question_no: str
    question_type: str
    stem_text: str
    options: list[str]
    answer_text: str | None
    analysis_text: str | None


@dataclass(slots=True)
class _QuestionBankExportRecord:
    question_no: str
    question_type: str
    section_name: str
    shared_stem: str
    material_text: str
    stem_text: str
    options: list[str]
    answer_text: str | None
    analysis_text: str | None
    subquestions: list[_QuestionBankExportSubquestionRecord]


_QUESTION_TYPE_SECTION_LABELS = {
    "single_choice": "单选题",
    "multiple_choice": "多选题",
    "judge": "判断题",
    "fill_blank": "填空题",
    "short_answer": "简答题",
    "calculation": "计算题",
    "case_analysis": "案例分析题",
    "material_analysis": "材料题",
    "composite": "综合题",
    "mixed": "练习题",
}
_OPTION_LABEL_PATTERN = re.compile(r"^\s*[A-Ha-h]\s*[\.\、．\)]\s*")


def _build_export_record(
    source_link: QuestionBankSourceLink,
    bank_question: QuestionBankItem,
    review_question: PaperReviewQuestion,
    *,
    child_questions: list[QuestionBankItem],
    child_review_links: dict[int, tuple[QuestionBankSourceLink, PaperReviewQuestion] | None],
) -> _QuestionBankExportRecord:
    if bank_question.node_role == "group" or child_questions:
        subquestions: list[_QuestionBankExportSubquestionRecord] = []
        for child_question in sorted(
            child_questions,
            key=lambda item: _question_bank_child_sort_key(
                item,
                child_review_links.get(item.id)[1].question_no
                if child_review_links.get(item.id) and child_review_links.get(item.id)[1]
                else None,
            ),
        ):
            review_payload = child_review_links.get(child_question.id)
            child_source_link = review_payload[0] if review_payload else None
            child_review_question = review_payload[1] if review_payload else None
            subquestions.append(
                _QuestionBankExportSubquestionRecord(
                    question_no=(child_source_link.question_no if child_source_link else None) or (child_review_question.question_no if child_review_question else None) or child_question.question_uid,
                    question_type=child_question.question_type or (child_review_question.question_type if child_review_question else "mixed"),
                    stem_text=normalize_question_text(child_question.stem_text or (child_review_question.stem_text if child_review_question else "") or ""),
                    options=_normalize_export_options(child_question.options_json or (child_review_question.options_json if child_review_question else []) or []),
                    answer_text=(child_question.answer_text or (child_review_question.answer_text if child_review_question else "") or "").strip() or None,
                    analysis_text=(child_question.analysis_text or (child_review_question.analysis_text if child_review_question else "") or "").strip() or None,
                )
            )
        return _QuestionBankExportRecord(
            question_no=(source_link.question_no or review_question.question_no or "").strip() or str(review_question.id),
            question_type=bank_question.question_type or review_question.question_type or "material_analysis",
            section_name=(review_question.source_section_name or "未分区").strip() or "未分区",
            shared_stem=normalize_question_text(bank_question.group_stem or review_question.group_stem or bank_question.stem_text or ""),
            material_text=normalize_question_text(bank_question.material_text or review_question.material_text or ""),
            stem_text="",
            options=[],
            answer_text=None,
            analysis_text=None,
            subquestions=subquestions,
        )
    full_stem = normalize_question_text(bank_question.stem_text or review_question.stem_text or "")
    source_only_stem = _extract_source_only_stem(review_question)
    shared_stem, stem_text = _split_shared_stem(full_stem, source_only_stem)
    return _QuestionBankExportRecord(
        question_no=(source_link.question_no or review_question.question_no or "").strip() or str(review_question.id),
        question_type=bank_question.question_type or review_question.question_type or "mixed",
        section_name=(review_question.source_section_name or "未分区").strip() or "未分区",
        shared_stem=shared_stem,
        material_text="",
        stem_text=stem_text or full_stem,
        options=_normalize_export_options(bank_question.options_json or review_question.options_json or []),
        answer_text=(bank_question.answer_text or review_question.answer_text or "").strip() or None,
        analysis_text=(bank_question.analysis_text or review_question.analysis_text or "").strip() or None,
        subquestions=[],
    )


def _extract_source_only_stem(review_question: PaperReviewQuestion) -> str:
    raw_text = (review_question.source_raw_text or "").strip()
    if not raw_text:
        return normalize_question_text(review_question.stem_text or "")
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return normalize_question_text(review_question.stem_text or "")
    body: list[str] = []
    for line in lines:
        normalized = normalize_question_text(line)
        if not normalized:
            continue
        if normalized.startswith(("答案：", "参考答案：", "正确答案：", "解析：", "答案解析：", "【解析】")):
            break
        if _OPTION_LABEL_PATTERN.match(normalized):
            break
        body.append(normalized)
    if not body:
        return normalize_question_text(review_question.stem_text or "")
    return normalize_question_text("\n".join(body))


def _split_shared_stem(full_stem: str, source_only_stem: str) -> tuple[str, str]:
    normalized_full_stem = normalize_question_text(full_stem)
    normalized_source_only_stem = normalize_question_text(source_only_stem)
    if not normalized_full_stem:
        return "", ""
    if not normalized_source_only_stem or normalized_full_stem == normalized_source_only_stem:
        return "", normalized_full_stem
    if normalized_full_stem.endswith(normalized_source_only_stem):
        shared_stem = normalized_full_stem[: -len(normalized_source_only_stem)].strip()
        if shared_stem:
            return shared_stem, normalized_source_only_stem
    return "", normalized_full_stem


def _normalize_export_options(options: list[str]) -> list[str]:
    normalized = normalize_options(options)
    rendered: list[str] = []
    for index, option in enumerate(normalized):
        label = chr(65 + index)
        rendered.append(f"{label}. {option}")
    return rendered


def _render_question_bank_markdown(
    *,
    paper_name: str,
    records: list[_QuestionBankExportRecord],
    solution_mode: str,
) -> str:
    lines = [f"# {paper_name}", ""]
    current_section = ""
    current_shared_stem = ""
    for record in records:
        section_heading = _question_section_heading(record)
        if section_heading != current_section:
            if lines[-1] != "":
                lines.append("")
            lines.extend([f"## {section_heading}", ""])
            current_section = section_heading
            current_shared_stem = ""
        if record.subquestions:
            lines.extend(_render_group_block(record, include_solution=solution_mode == "inline"))
            current_shared_stem = ""
            continue
        if record.shared_stem:
            if record.shared_stem != current_shared_stem:
                lines.extend(["### 共用材料", "", record.shared_stem, ""])
                current_shared_stem = record.shared_stem
        else:
            current_shared_stem = ""
        lines.extend(_render_question_block(record, include_solution=solution_mode == "inline"))

    if solution_mode == "appendix":
        lines.extend(["", "## 答案与解析", ""])
        for record in records:
            lines.extend(_render_solution_block(record))
    return "\n".join(lines).strip() + "\n"


def _render_question_block(record: _QuestionBankExportRecord, *, include_solution: bool) -> list[str]:
    lines = [f"{_question_heading(record)} {_question_body_text(record.stem_text)}".strip(), ""]
    if record.options:
        lines.extend(record.options)
        lines.append("")
    if include_solution:
        lines.extend(_render_solution_lines(record))
    return lines


def _render_group_block(record: _QuestionBankExportRecord, *, include_solution: bool) -> list[str]:
    lines: list[str] = []
    if record.shared_stem:
        lines.extend(["### 共用材料", "", record.shared_stem, ""])
    if record.material_text:
        lines.extend(["材料：", "", record.material_text, ""])
    for child in record.subquestions:
        lines.extend(_render_subquestion_block(child, include_solution=include_solution))
    return lines


def _render_subquestion_block(record: _QuestionBankExportSubquestionRecord, *, include_solution: bool) -> list[str]:
    lines = [f"{_subquestion_heading(record)} {_question_body_text(record.stem_text)}".strip(), ""]
    if record.options:
        lines.extend(record.options)
        lines.append("")
    if include_solution:
        lines.extend(_render_subquestion_solution_lines(record))
    return lines


def _render_solution_block(record: _QuestionBankExportRecord) -> list[str]:
    if record.subquestions:
        lines: list[str] = []
        for child in record.subquestions:
            lines.extend(_render_subquestion_solution_item(child))
        return lines
    return _render_solution_item(record)


def _render_solution_lines(record: _QuestionBankExportRecord) -> list[str]:
    return _render_answer_block(None, record.answer_text, record.analysis_text)


def _render_subquestion_solution_lines(record: _QuestionBankExportSubquestionRecord) -> list[str]:
    return _render_answer_block(None, record.answer_text, record.analysis_text)


def _render_solution_item(record: _QuestionBankExportRecord) -> list[str]:
    return _render_answer_block(_question_heading(record), record.answer_text, record.analysis_text)


def _render_subquestion_solution_item(record: _QuestionBankExportSubquestionRecord) -> list[str]:
    return _render_answer_block(_subquestion_heading(record), record.answer_text, record.analysis_text)


def _render_answer_block(title: str | None, answer_text: str | None, analysis_text: str | None) -> list[str]:
    return [
        f":::answer-block {title}".rstrip() if title else ":::answer-block",
        f"答案：{answer_text or '暂无'}",
        "",
        f"解析：{analysis_text or '暂无'}",
        ":::",
        "",
    ]


def _question_section_heading(record: _QuestionBankExportRecord) -> str:
    if record.section_name.strip():
        normalized = record.section_name.strip()
        if normalized in {
            "单选题",
            "单项选择题",
            "多选题",
            "多项选择题",
            "不定项选择题",
            "判断题",
            "填空题",
            "简答题",
            "问答题",
            "计算题",
            "计算分析题",
            "综合题",
            "案例分析题",
            "材料题",
            "选择题",
            "客观题",
            "主观题",
            "真题",
            "练习题",
            "模拟题",
        }:
            return normalized
    return _QUESTION_TYPE_SECTION_LABELS.get(record.question_type, "练习题")


def _question_body_text(text: str) -> str:
    return (text or "").strip()
def _question_heading(record: _QuestionBankExportRecord) -> str:
    return f"第{record.question_no}题"


def _subquestion_heading(record: _QuestionBankExportSubquestionRecord) -> str:
    return f"第{record.question_no}题"


def _root_review_question(
    question: PaperReviewQuestion,
    by_id: dict[int, PaperReviewQuestion],
) -> PaperReviewQuestion:
    current = question
    seen: set[int] = set()
    while current.parent_question_id is not None and current.parent_question_id in by_id and current.parent_question_id not in seen:
        seen.add(current.parent_question_id)
        current = by_id[current.parent_question_id]
    return current


def _build_export_filename(paper_name: str, solution_mode: str) -> str:
    safe_name = re.sub(r"[\\\\/:*?\"<>|]+", "_", (paper_name or "question-bank-paper").strip()).strip(" .")
    if not safe_name:
        safe_name = "question-bank-paper"
    suffix = "inline" if solution_mode == "inline" else "appendix"
    return f"{safe_name}-{suffix}.md"


@dataclass(slots=True)
class _DistributionAccumulator:
    key: str
    name: str
    path: str | None
    chapter_name: str | None = None
    knowledge_point_id: int | None = None
    total_frequency: int = 0
    paper_ids: set[int] | None = None
    year_counts: dict[int, int] | None = None

    def __post_init__(self) -> None:
        if self.paper_ids is None:
            self.paper_ids = set()
        if self.year_counts is None:
            self.year_counts = {}


def _expanded_years(years: list[int], *, start_year: int | None, end_year: int | None) -> list[int]:
    if years:
        min_year = start_year if start_year is not None else years[0]
        max_year = end_year if end_year is not None else years[-1]
        if min_year > max_year:
            min_year, max_year = max_year, min_year
        return list(range(min_year, max_year + 1))
    if start_year is not None and end_year is not None:
        min_year = min(start_year, end_year)
        max_year = max(start_year, end_year)
        return list(range(min_year, max_year + 1))
    return []


def _build_yearly_overview(
    rows: list[tuple[QuestionBankItem, QuestionBankSourceLink, PaperReviewQuestion, object, KnowledgePoint | None]],
    years: list[int],
) -> list[QuestionBankAnalysisYearOverviewResponse]:
    paper_ids_by_year: dict[int, set[int]] = defaultdict(set)
    question_ids_by_year: dict[int, set[int]] = defaultdict(set)
    tagged_question_ids_by_year: dict[int, set[int]] = defaultdict(set)
    for _bank_question, _source_link, review_question, paper, knowledge_point in rows:
        if paper.exam_year is None:
            continue
        year = int(paper.exam_year)
        paper_ids_by_year[year].add(int(paper.id))
        question_ids_by_year[year].add(int(review_question.id))
        if knowledge_point is not None:
            tagged_question_ids_by_year[year].add(int(review_question.id))
    return [
        QuestionBankAnalysisYearOverviewResponse(
            year=year,
            paper_count=len(paper_ids_by_year.get(year, set())),
            source_question_count=len(question_ids_by_year.get(year, set())),
            tagged_source_question_count=len(tagged_question_ids_by_year.get(year, set())),
        )
        for year in years
    ]


def _build_point_distribution(
    rows: list[tuple[QuestionBankItem, QuestionBankSourceLink, PaperReviewQuestion, object, KnowledgePoint | None]],
    years: list[int],
) -> list[QuestionBankAnalysisPointItemResponse]:
    accumulators: dict[str, _DistributionAccumulator] = {}
    total_frequency = 0
    for _bank_question, _source_link, review_question, paper, knowledge_point in rows:
        if knowledge_point is None:
            continue
        key = f"kp:{knowledge_point.id}"
        if key not in accumulators:
            accumulators[key] = _DistributionAccumulator(
                key=key,
                name=knowledge_point.name,
                path=knowledge_point.path,
                chapter_name=_chapter_name_for_point(knowledge_point),
                knowledge_point_id=int(knowledge_point.id),
            )
        bucket = accumulators[key]
        bucket.total_frequency += 1
        bucket.paper_ids.add(int(paper.id))
        if paper.exam_year is not None:
            year = int(paper.exam_year)
            bucket.year_counts[year] = int(bucket.year_counts.get(year, 0)) + 1
        total_frequency += 1
    result = [
        _to_point_distribution_item(accumulator, years, total_frequency)
        for accumulator in accumulators.values()
    ]
    return sorted(
        result,
        key=lambda item: (
            -item.prediction_frequency,
            -item.total_frequency,
            -item.paper_count,
            item.name,
        ),
    )


def _build_chapter_distribution(
    rows: list[tuple[QuestionBankItem, QuestionBankSourceLink, PaperReviewQuestion, object, KnowledgePoint | None]],
    years: list[int],
) -> list[QuestionBankAnalysisChapterItemResponse]:
    accumulators: dict[str, _DistributionAccumulator] = {}
    total_frequency = 0
    for _bank_question, _source_link, review_question, paper, knowledge_point in rows:
        if knowledge_point is None:
            continue
        chapter_key, chapter_name, chapter_path = _chapter_bucket_for_point(knowledge_point)
        if chapter_key not in accumulators:
            accumulators[chapter_key] = _DistributionAccumulator(
                key=chapter_key,
                name=chapter_name,
                path=chapter_path,
            )
        bucket = accumulators[chapter_key]
        bucket.total_frequency += 1
        bucket.paper_ids.add(int(paper.id))
        if paper.exam_year is not None:
            year = int(paper.exam_year)
            bucket.year_counts[year] = int(bucket.year_counts.get(year, 0)) + 1
        total_frequency += 1
    result = [
        _to_chapter_distribution_item(accumulator, years, total_frequency)
        for accumulator in accumulators.values()
    ]
    return sorted(
        result,
        key=lambda item: (
            -item.prediction_frequency,
            -item.total_frequency,
            -item.paper_count,
            item.name,
        ),
    )


def _to_point_distribution_item(
    accumulator: _DistributionAccumulator,
    years: list[int],
    total_frequency: int,
) -> QuestionBankAnalysisPointItemResponse:
    yearly_frequency = [int(accumulator.year_counts.get(year, 0)) for year in years]
    metrics = _series_metrics(yearly_frequency)
    return QuestionBankAnalysisPointItemResponse(
        key=accumulator.key,
        name=accumulator.name,
        path=accumulator.path,
        total_frequency=accumulator.total_frequency,
        paper_count=len(accumulator.paper_ids),
        yearly_frequency=yearly_frequency,
        share=_safe_ratio(accumulator.total_frequency, total_frequency),
        last_frequency=metrics["last_frequency"],
        recent_average=metrics["recent_average"],
        slope=metrics["slope"],
        trend_label=metrics["trend_label"],
        prediction_frequency=metrics["prediction_frequency"],
        confidence=metrics["confidence"],
        appearance_year_count=metrics["appearance_year_count"],
        knowledge_point_id=accumulator.knowledge_point_id,
        chapter_name=accumulator.chapter_name,
    )


def _to_chapter_distribution_item(
    accumulator: _DistributionAccumulator,
    years: list[int],
    total_frequency: int,
) -> QuestionBankAnalysisChapterItemResponse:
    yearly_frequency = [int(accumulator.year_counts.get(year, 0)) for year in years]
    metrics = _series_metrics(yearly_frequency)
    return QuestionBankAnalysisChapterItemResponse(
        chapter_key=accumulator.key,
        key=accumulator.key,
        name=accumulator.name,
        path=accumulator.path,
        total_frequency=accumulator.total_frequency,
        paper_count=len(accumulator.paper_ids),
        yearly_frequency=yearly_frequency,
        share=_safe_ratio(accumulator.total_frequency, total_frequency),
        last_frequency=metrics["last_frequency"],
        recent_average=metrics["recent_average"],
        slope=metrics["slope"],
        trend_label=metrics["trend_label"],
        prediction_frequency=metrics["prediction_frequency"],
        confidence=metrics["confidence"],
        appearance_year_count=metrics["appearance_year_count"],
    )


def _series_metrics(values: list[int]) -> dict[str, float | int | str]:
    if not values:
        return {
            "last_frequency": 0,
            "recent_average": 0.0,
            "slope": 0.0,
            "trend_label": "stable",
            "prediction_frequency": 0,
            "confidence": 0.0,
            "appearance_year_count": 0,
        }
    last_frequency = int(values[-1])
    recent_window = values[-3:] if len(values) >= 3 else values
    recent_average = sum(recent_window) / len(recent_window)
    if len(values) == 1:
        slope = 0.0
    else:
        slope = (values[-1] - values[0]) / (len(values) - 1)
    appearance_year_count = sum(1 for value in values if value > 0)
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values) if values else 0
    std_dev = math.sqrt(variance)
    stability = 1 / (1 + std_dev)
    confidence = max(
        0.15,
        min(
            0.95,
            0.35 + (appearance_year_count / max(len(values), 1)) * 0.35 + stability * 0.25,
        ),
    )
    raw_prediction = last_frequency * 0.5 + recent_average * 0.3 + max(0.0, slope) * 0.2
    if appearance_year_count <= 1 and last_frequency <= 1:
        raw_prediction *= 0.7
    prediction_frequency = max(0, int(round(raw_prediction)))
    if slope >= 0.5:
        trend_label = "rising"
    elif slope <= -0.5:
        trend_label = "falling"
    elif last_frequency > 0 and recent_average > 0:
        trend_label = "stable"
    else:
        trend_label = "sporadic"
    return {
        "last_frequency": last_frequency,
        "recent_average": round(recent_average, 2),
        "slope": round(slope, 2),
        "trend_label": trend_label,
        "prediction_frequency": prediction_frequency,
        "confidence": round(confidence, 2),
        "appearance_year_count": appearance_year_count,
    }


def _chapter_name_for_point(point: KnowledgePoint) -> str | None:
    if point.path:
        parts = [part.strip() for part in point.path.split("/") if part.strip()]
        if len(parts) >= 2:
            return parts[-2]
        if parts:
            return parts[0]
    return None


def _chapter_bucket_for_point(point: KnowledgePoint) -> tuple[str, str, str | None]:
    if point.path:
        parts = [part.strip() for part in point.path.split("/") if part.strip()]
        if len(parts) >= 2:
            name = "/".join(parts[:2])
            return f"chapter:{name}", name, name
        if parts:
            return f"chapter:{parts[0]}", parts[0], parts[0]
    if point.chapter_id is not None:
        fallback = f"章节 {point.chapter_id}"
        return f"chapter:{point.chapter_id}", fallback, fallback
    return "chapter:unbound", "未绑定章节", None


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0
    return round(numerator / denominator, 4)


def _to_prediction_item(
    item: QuestionBankAnalysisPointItemResponse | QuestionBankAnalysisChapterItemResponse,
) -> QuestionBankAnalysisPredictionItemResponse:
    evidence = (
        f"近年均值 {item.recent_average:.2f}，最近一年 {item.last_frequency}，"
        f"趋势斜率 {item.slope:.2f}，历史出现 {item.appearance_year_count} 年。"
    )
    return QuestionBankAnalysisPredictionItemResponse(
        key=item.key,
        name=item.name,
        prediction_frequency=item.prediction_frequency,
        confidence=item.confidence,
        trend_label=item.trend_label,
        evidence=evidence,
    )


def _build_analysis_report(
    *,
    summary: QuestionBankAnalysisSummaryResponse,
    years: list[int],
    prediction_year: int | None,
    point_distribution: list[QuestionBankAnalysisPointItemResponse],
    chapter_distribution: list[QuestionBankAnalysisChapterItemResponse],
) -> QuestionBankAnalysisReportResponse:
    year_label = f"{years[0]}-{years[-1]} 年" if years else "当前样本"
    top_points = "、".join(item.name for item in point_distribution[:3]) or "暂无稳定主考点"
    top_chapters = "、".join(item.name for item in chapter_distribution[:3]) or "暂无稳定章节"
    rising_points = [item.name for item in point_distribution if item.trend_label == "rising"][:3]
    stable_chapters = [item.name for item in chapter_distribution if item.trend_label == "stable"][:3]
    predicted_points = "、".join(item.name for item in point_distribution[:5]) or "暂无可预测考点"
    predicted_chapters = "、".join(item.name for item in chapter_distribution[:5]) or "暂无可预测章节"

    overview = (
        f"本次分析基于 {summary.paper_count} 份真题试卷、{summary.source_question_count} 道正式题来源题，"
        f"统计区间为 {year_label}。其中有 {summary.tagged_source_question_count} 道题具备主考点标注，"
        f"主考点覆盖率为 {summary.primary_coverage_rate:.0%}。"
    )
    point_insight = (
        f"主考点分布呈现一定集中度，Top 5 主考点合计占比 {summary.top_point_concentration_rate:.0%}。"
        f"当前样本中最活跃的主考点主要为 {top_points}。"
        + (f"其中 {('、'.join(rising_points))} 近年呈升温趋势。" if rising_points else "整体以稳定重复考察为主。")
    )
    chapter_insight = (
        f"章节维度上，考察重心主要落在 {top_chapters}。"
        + (f"{('、'.join(stable_chapters))} 连续多年保持出题。 " if stable_chapters else "")
        + "章节热度判断基于主考点所属章节汇总，适合观察命题覆盖面与高频集中区。"
    )
    forecast = (
        f"{prediction_year or '下一年'} 年建议优先关注主考点 {predicted_points}，"
        f"以及章节 {predicted_chapters}。预测结果依据近一年频次、近三年均值与趋势斜率加权生成，"
        "用于提示关注重点，不代表必考结论。"
    )
    disclaimer = (
        "分析结果仅使用正式题库中已上架且能回溯到真题试卷的题目；"
        "若部分正式题缺少主考点标注、年份样本不足或个别年份试卷未入库，都会影响频次与预测稳定性。"
    )
    return QuestionBankAnalysisReportResponse(
        overview=overview,
        point_insight=point_insight,
        chapter_insight=chapter_insight,
        forecast=forecast,
        disclaimer=disclaimer,
    )

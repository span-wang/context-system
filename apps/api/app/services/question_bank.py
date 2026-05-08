from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import KnowledgePoint, MockExam, MockExamQuestion, PracticeSet, PracticeSetQuestion, QuestionBankItem, QuestionSourceLink
from app.repositories.knowledge import KnowledgeRepository
from app.repositories.question_bank import QuestionBankRepository
from app.schemas.question_bank import (
    GenerateMockExamRequest,
    GeneratePracticeSetRequest,
    MockExamResponse,
    PracticeSetDetailResponse,
    PracticeSetQuestionResponse,
    PracticeSetResponse,
    QuestionSourceSummaryResponse,
    QuestionBankItemResponse,
    StandardizeQuestionsRequest,
    StandardizeQuestionsResponse,
)
from app.services.question_enrichment import (
    apply_ai_tags,
    complete_missing_solution_with_ai,
    normalize_question_fields,
)
from app.services.tagging import apply_rule_tags


class QuestionBankService:
    def __init__(self, session: Session) -> None:
        self.repository = QuestionBankRepository(session)
        self.knowledge_repository = KnowledgeRepository(session)

    def list_questions(self) -> list[QuestionBankItemResponse]:
        items = self.repository.list_bank_questions()
        if not items:
            return []

        bank_ids = [item.id for item in items]
        source_links = self.repository.list_source_links_by_bank_question_ids(bank_ids)
        raw_questions = self.repository.list_raw_questions_by_ids([link.exam_question_id for link in source_links])
        papers = self.repository.list_papers_by_ids([link.paper_id for link in source_links])

        question_by_id = {item.id: item for item in raw_questions}
        paper_by_id = {item.id: item for item in papers}
        sources_by_bank_id: dict[int, list[QuestionSourceSummaryResponse]] = {item.id: [] for item in items}

        for link in source_links:
            question = question_by_id.get(link.exam_question_id)
            paper = paper_by_id.get(link.paper_id)
            if question is None or paper is None:
                continue
            source_label = _build_source_label(paper.paper_name, question.question_no)
            sources_by_bank_id.setdefault(link.bank_question_id, []).append(
                QuestionSourceSummaryResponse.model_validate(
                    {
                        "id": link.id,
                        "exam_question_id": link.exam_question_id,
                        "paper_id": link.paper_id,
                        "paper_name": paper.paper_name,
                        "question_no": question.question_no,
                        "source_label": source_label,
                        "source_year": link.source_year,
                        "source_region": link.source_region,
                    }
                )
            )

        rows: list[QuestionBankItemResponse] = []
        for item in items:
            sources = sources_by_bank_id.get(item.id, [])
            rows.append(
                QuestionBankItemResponse.model_validate(
                    {
                        **item.__dict__,
                        "source_labels": [source.source_label for source in sources],
                        "sources": sources,
                    }
                )
            )
        return rows

    def list_practice_sets(self) -> list[PracticeSetResponse]:
        return [PracticeSetResponse.model_validate(item) for item in self.repository.list_practice_sets()]

    def get_practice_set_detail(self, practice_set_id: int) -> PracticeSetDetailResponse:
        item = self.repository.get_practice_set(practice_set_id)
        if item is None:
            raise HTTPException(status_code=404, detail="练习题包不存在")
        questions = self.repository.list_practice_set_questions(practice_set_id)
        question_rows = self._build_practice_question_rows(questions)
        return PracticeSetDetailResponse.model_validate(
            {
                **item.__dict__,
                "questions": question_rows,
            }
        )

    def list_mock_exams(self) -> list[MockExamResponse]:
        return [MockExamResponse.model_validate(item) for item in self.repository.list_mock_exams()]

    def standardize_questions(self, payload: StandardizeQuestionsRequest) -> StandardizeQuestionsResponse:
        raw_questions = self.repository.list_raw_questions(payload.paper_id)
        created = 0
        linked = 0
        unlinked = 0
        skipped = 0
        normalized = 0
        ai_completed = 0
        tagged = 0
        ai_tagged = 0
        subject_names: dict[int, str | None] = {}
        knowledge_points_by_subject: dict[int, list[KnowledgePoint]] = {}
        for question in raw_questions:
            if normalize_question_fields(question):
                normalized += 1

            if payload.use_ai:
                subject_name = subject_names.get(question.subject_id)
                if question.subject_id not in subject_names:
                    subject = self.repository.get_subject(question.subject_id)
                    subject_name = subject.name if subject else None
                    subject_names[question.subject_id] = subject_name
                result = complete_missing_solution_with_ai(question, subject_name=subject_name)
                if result.changed:
                    ai_completed += 1

            points = knowledge_points_by_subject.get(question.subject_id)
            if points is None:
                points = self.knowledge_repository.list_knowledge_points(question.subject_id)
                knowledge_points_by_subject[question.subject_id] = points
            rule_created = apply_rule_tags(self.repository.session, question, points, question.tenant_id, question.updated_by)
            tagged += len(rule_created)
            if payload.use_ai and not rule_created and not self.repository.has_knowledge_links(question.id):
                ai_created = apply_ai_tags(
                    self.repository.session,
                    question,
                    points,
                    question.tenant_id,
                    question.updated_by,
                )
                ai_tagged += len(ai_created)

            sync_result = self.sync_question_to_bank(question, publish=payload.publish)
            created += sync_result["created"]
            linked += sync_result["linked"]
            unlinked += sync_result["unlinked"]
            skipped += sync_result["skipped"]
        self.repository.session.commit()
        return StandardizeQuestionsResponse(
            created=created,
            linked=linked,
            unlinked=unlinked,
            skipped=skipped,
            normalized=normalized,
            ai_completed=ai_completed,
            tagged=tagged,
            ai_tagged=ai_tagged,
        )

    def generate_practice_set(self, payload: GeneratePracticeSetRequest) -> PracticeSetResponse:
        questions = self._select_bank_questions(payload.subject_id, payload.question_limit)
        if not questions:
            raise HTTPException(status_code=422, detail="暂无可组包的标准题")
        subject_id = payload.subject_id or questions[0].subject_id
        item = self.repository.create_practice_set(
            PracticeSet(
                tenant_id=questions[0].tenant_id,
                subject_id=subject_id,
                set_type=payload.set_type,
                title=payload.title or "自动生成练习题包",
                description="由当前标准题自动生成，可继续人工调整题目与顺序。",
                source_report_id=None,
                difficulty_policy="source_count_desc",
                question_count=len(questions),
                status="published",
                created_by=questions[0].created_by,
                updated_by=questions[0].updated_by,
            )
        )
        self.repository.create_practice_set_questions(
            [
                PracticeSetQuestion(
                    tenant_id=item.tenant_id,
                    practice_set_id=item.id,
                    bank_question_id=question.id,
                    sort_order=index,
                    score=question.difficulty_level or 1,
                    created_by=item.created_by,
                    updated_by=item.updated_by,
                )
                for index, question in enumerate(questions, start=1)
            ]
        )
        self.repository.session.commit()
        return PracticeSetResponse.model_validate(item)

    def generate_mock_exam(self, payload: GenerateMockExamRequest) -> MockExamResponse:
        questions = self._select_bank_questions(payload.subject_id, payload.question_limit)
        if not questions:
            raise HTTPException(status_code=422, detail="暂无可组卷的标准题")
        subject_id = payload.subject_id or questions[0].subject_id
        total_score = sum(question.difficulty_level or 1 for question in questions)
        item = self.repository.create_mock_exam(
            MockExam(
                tenant_id=questions[0].tenant_id,
                subject_id=subject_id,
                title=payload.title or "自动生成模考试卷",
                exam_mode="timed",
                duration_minutes=payload.duration_minutes,
                total_score=total_score,
                status="published",
                created_by=questions[0].created_by,
                updated_by=questions[0].updated_by,
            )
        )
        self.repository.create_mock_exam_questions(
            [
                MockExamQuestion(
                    tenant_id=item.tenant_id,
                    mock_exam_id=item.id,
                    bank_question_id=question.id,
                    sort_order=index,
                    score=question.difficulty_level or 1,
                    created_by=item.created_by,
                    updated_by=item.updated_by,
                )
                for index, question in enumerate(questions, start=1)
            ]
        )
        self.repository.session.commit()
        return MockExamResponse.model_validate(item)

    def _select_bank_questions(self, subject_id: int | None, limit: int) -> list[QuestionBankItem]:
        rows = self.repository.list_bank_questions()
        if subject_id is not None:
            rows = [item for item in rows if item.subject_id == subject_id]
        rows.sort(key=lambda item: (item.source_count, item.quality_score or 0), reverse=True)
        return rows[: max(1, min(limit, 100))]

    def _build_practice_question_rows(self, questions: list[PracticeSetQuestion]) -> list[PracticeSetQuestionResponse]:
        if not questions:
            return []
        bank_question_ids = [row.bank_question_id for row in questions]
        bank_questions = {item.id: item for item in self.repository.list_bank_questions_by_ids(bank_question_ids)}
        knowledge_map = self.repository.list_knowledge_points_by_bank_question_ids(list(bank_questions))
        rows: list[PracticeSetQuestionResponse] = []
        for row in questions:
            bank_question = bank_questions.get(row.bank_question_id)
            if bank_question is None:
                continue
            rows.append(
                PracticeSetQuestionResponse.model_validate(
                    {
                        "id": row.id,
                        "bank_question_id": row.bank_question_id,
                        "sort_order": row.sort_order,
                        "score": row.score,
                        "question_type": bank_question.question_type,
                        "stem_text": bank_question.canonical_stem,
                        "options_json": bank_question.canonical_options_json,
                        "answer_text": bank_question.canonical_answer,
                        "analysis_text": bank_question.canonical_analysis,
                        "difficulty_level": bank_question.difficulty_level,
                        "quality_score": bank_question.quality_score,
                        "source_count": bank_question.source_count,
                        "knowledge_point_names": [point.name for point in knowledge_map.get(bank_question.id, [])],
                    }
                )
            )
        rows.sort(key=lambda item: item.sort_order)
        return rows

    def sync_question_to_bank(self, question, publish: bool = True) -> dict[str, int]:
        source_link = self.repository.get_source_link(question.id)
        bank_item = self.repository.get_bank_question(source_link.bank_question_id) if source_link else None
        source_link_needs_repair = source_link is not None and bank_item is None
        stem = question.stem_text.strip()

        if question.review_status != "approved" or not stem:
            if source_link is None:
                return {"created": 0, "linked": 0, "unlinked": 0, "skipped": 1}
            bank_item = bank_item or self.repository.get_bank_question(source_link.bank_question_id)
            self.repository.delete_source_link(source_link)
            if bank_item is not None:
                bank_item.source_count = max(0, bank_item.source_count - 1)
                if bank_item.source_count == 0:
                    bank_item.status = "draft"
            return {"created": 0, "linked": 0, "unlinked": 1, "skipped": 0}

        created = 0
        linked = 0
        skipped = 0
        if bank_item is not None:
            _sync_bank_item_fields(bank_item, question, publish=publish)
        else:
            bank_item = self.repository.find_bank_question_by_stem(question.subject_id, stem)
        if bank_item is None:
            bank_item = self.repository.create_bank_question(
                QuestionBankItem(
                    tenant_id=question.tenant_id,
                    subject_id=question.subject_id,
                    canonical_stem=stem,
                    canonical_options_json=question.options_json,
                    canonical_answer=question.answer_text,
                    canonical_analysis=question.analysis_text,
                    question_type=question.question_type,
                    difficulty_level=question.difficulty_level,
                    quality_score=question.quality_score,
                    source_count=0,
                    status="published" if publish else "draft",
                    created_by=question.created_by,
                    updated_by=question.updated_by,
                )
            )
            created += 1
        else:
            _sync_bank_item_fields(bank_item, question, publish=publish)

        if source_link is not None:
            if source_link_needs_repair:
                source_link.bank_question_id = bank_item.id
                bank_item.source_count += 1
                linked += 1
            else:
                skipped += 1
            return {"created": created, "linked": linked, "unlinked": 0, "skipped": skipped}

        paper = self.repository.get_paper(question.paper_id)
        self.repository.create_source_link(
            QuestionSourceLink(
                tenant_id=question.tenant_id,
                bank_question_id=bank_item.id,
                exam_question_id=question.id,
                paper_id=question.paper_id,
                source_year=paper.exam_year if paper else None,
                source_region=paper.exam_region if paper else None,
                created_by=question.created_by,
                updated_by=question.updated_by,
            )
        )
        bank_item.source_count += 1
        linked += 1
        return {"created": created, "linked": linked, "unlinked": 0, "skipped": skipped}


def _sync_bank_item_fields(bank_item: QuestionBankItem, question, publish: bool) -> None:
    bank_item.canonical_stem = question.stem_text.strip()
    bank_item.canonical_options_json = question.options_json
    bank_item.canonical_answer = question.answer_text
    bank_item.canonical_analysis = question.analysis_text
    bank_item.question_type = question.question_type
    bank_item.difficulty_level = question.difficulty_level
    bank_item.quality_score = question.quality_score
    bank_item.status = "published" if publish else bank_item.status


def _build_source_label(paper_name: str, question_no: str) -> str:
    normalized_no = str(question_no or "").strip() or "-"
    return f"{paper_name} · 第{normalized_no}题"

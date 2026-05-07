from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import MockExam, MockExamQuestion, PracticeSet, PracticeSetQuestion, QuestionBankItem, QuestionSourceLink
from app.repositories.question_bank import QuestionBankRepository
from app.schemas.question_bank import (
    GenerateMockExamRequest,
    GeneratePracticeSetRequest,
    MockExamResponse,
    PracticeSetResponse,
    QuestionBankItemResponse,
    StandardizeQuestionsRequest,
    StandardizeQuestionsResponse,
)


class QuestionBankService:
    def __init__(self, session: Session) -> None:
        self.repository = QuestionBankRepository(session)

    def list_questions(self) -> list[QuestionBankItemResponse]:
        return [QuestionBankItemResponse.model_validate(item) for item in self.repository.list_bank_questions()]

    def list_practice_sets(self) -> list[PracticeSetResponse]:
        return [PracticeSetResponse.model_validate(item) for item in self.repository.list_practice_sets()]

    def list_mock_exams(self) -> list[MockExamResponse]:
        return [MockExamResponse.model_validate(item) for item in self.repository.list_mock_exams()]

    def standardize_questions(self, payload: StandardizeQuestionsRequest) -> StandardizeQuestionsResponse:
        raw_questions = self.repository.list_raw_questions(payload.paper_id)
        created = 0
        linked = 0
        skipped = 0
        for question in raw_questions:
            stem = question.stem_text.strip()
            if not stem:
                skipped += 1
                continue
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
                        status="published" if payload.publish else "draft",
                        created_by=question.created_by,
                        updated_by=question.updated_by,
                    )
                )
                created += 1

            if self.repository.has_source_link(question.id):
                skipped += 1
                continue
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
        self.repository.session.commit()
        return StandardizeQuestionsResponse(created=created, linked=linked, skipped=skipped)

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

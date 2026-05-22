from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import random
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import MasterySnapshot, PracticeAnswer, PracticeSession, PracticeSessionItem, QuestionBankItem, WrongBookItem
from app.repositories.learning import LearningRepository
from app.schemas.auth import CurrentUserResponse
from app.schemas.learning import (
    DailyPlanResponse,
    DailyPlanTaskResponse,
    MasterySnapshotResponse,
    PracticeQuestionKnowledgePointResponse,
    PracticeQuestionSnapshotResponse,
    PracticeAnswerReflectionRequest,
    PracticeAnswerSubmitRequest,
    PracticeSessionCreateRequest,
    PracticeDerivedSessionRequest,
    PracticeSessionDetailResponse,
    PracticeSessionItemResponse,
    PracticeResultItemResponse,
    PracticeResultResponse,
    PracticeSessionSummaryResponse,
    PracticeWrongReasonCountResponse,
    ReviewDueItemResponse,
    WrongBookItemResponse,
)


DEFAULT_TENANT_ID = 1
WRONG_REASON_LABELS: dict[str, str] = {
    "concept_unclear": "概念没吃透",
    "memory_unstable": "记忆不稳定",
    "misread_question": "审题偏了",
    "calculation_error": "计算出错",
    "careless": "粗心失误",
    "method_unfamiliar": "解题方法不熟",
}


class LearningService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = LearningRepository(session)

    def list_sessions(self, current_user: CurrentUserResponse, *, limit: int = 20) -> list[PracticeSessionSummaryResponse]:
        rows = self.repository.list_sessions(current_user.id, max(1, min(limit, 50)))
        return [self._build_session_summary(row) for row in rows]

    def list_wrong_book(self, current_user: CurrentUserResponse, *, limit: int = 50) -> list[WrongBookItemResponse]:
        rows = self.repository.list_wrong_book_items(current_user.id, max(1, min(limit, 100)))
        return [self._build_wrong_book_item(row) for row in rows]

    def list_mastery(
        self,
        current_user: CurrentUserResponse,
        *,
        subject_id: int | None = None,
        limit: int = 20,
    ) -> list[MasterySnapshotResponse]:
        rows = self.repository.list_mastery_rows(
            current_user.id,
            subject_id=subject_id,
            limit=max(1, min(limit, 50)),
        )
        return [self._build_mastery_snapshot(snapshot, knowledge_point) for snapshot, knowledge_point in rows]

    def list_review_today(
        self,
        current_user: CurrentUserResponse,
        *,
        limit: int = 20,
    ) -> list[ReviewDueItemResponse]:
        rows = self.repository.list_wrong_book_items(current_user.id, max(1, min(limit * 4, 200)), mastered=False)
        due_items = [item for item in rows if _review_due_at(item) <= datetime.utcnow()]
        due_items.sort(key=lambda item: (_review_due_at(item), -item.wrong_count, item.id))
        return [self._build_review_due_item(item) for item in due_items[:limit]]

    def get_daily_plan(self, current_user: CurrentUserResponse) -> DailyPlanResponse:
        review_today = self.list_review_today(current_user, limit=20)
        weak_points = self.list_mastery(current_user, limit=3)
        tasks: list[DailyPlanTaskResponse] = []

        if review_today:
            tasks.append(
                DailyPlanTaskResponse(
                    task_id="review_today",
                    task_type="review_today",
                    title=f"先完成今日待复习 {len(review_today)} 题",
                    description="优先把已经错过且今天到期的题回顾一轮，先稳住遗忘速度。",
                    priority="high",
                    question_count=min(len(review_today), 20),
                    action_type="review_today_start",
                    derived_session_payload=PracticeDerivedSessionRequest(
                        answer_mode="memorize",
                        question_count=min(len(review_today), 20),
                    ),
                )
            )

        if weak_points:
            weakest = weak_points[0]
            tasks.append(
                DailyPlanTaskResponse(
                    task_id=f"weak_point_{weakest.knowledge_point_id}",
                    task_type="weak_point_practice",
                    title=f"围绕「{weakest.name}」再练 10 题",
                    description=f"当前掌握度 {weakest.mastery_score}%，建议优先做一轮章节或同类题巩固。",
                    priority="high" if weakest.mastery_score < 60 else "medium",
                    question_count=10,
                    action_type="create_session" if weakest.chapter_id is not None else None,
                    session_create_payload=PracticeSessionCreateRequest(
                        session_type="chapter",
                        answer_mode="memorize",
                        subject_id=None,
                        category_id=None,
                        chapter_id=weakest.chapter_id,
                        paper_id=None,
                        question_type=None,
                        question_count=10,
                    ) if weakest.chapter_id is not None else None,
                    derived_session_payload=None,
                )
            )

        recent_sessions = self.repository.list_sessions(current_user.id, 5)
        latest_submitted = next((item for item in recent_sessions if item.status == "submitted"), None)
        if latest_submitted is not None and (float(latest_submitted.accuracy_rate or 0) < 75):
            tasks.append(
                DailyPlanTaskResponse(
                    task_id=f"stabilize_{latest_submitted.id}",
                    task_type="stabilize_accuracy",
                    title="再做一组乱序巩固题",
                    description="最近一套题正确率偏低，建议补一组短题保持手感，再回头攻薄弱点。",
                    priority="medium",
                    question_count=10,
                    action_type="create_session",
                    session_create_payload=PracticeSessionCreateRequest(
                        session_type="random",
                        answer_mode="memorize",
                        subject_id=latest_submitted.subject_id if hasattr(latest_submitted, "subject_id") else None,
                        category_id=latest_submitted.category_id if hasattr(latest_submitted, "category_id") else None,
                        chapter_id=None,
                        paper_id=None,
                        question_type=None,
                        question_count=10,
                    ),
                    derived_session_payload=None,
                )
            )

        if not tasks:
            tasks.append(
                DailyPlanTaskResponse(
                    task_id="keep_momentum",
                    task_type="keep_momentum",
                    title="今天做一组 10 题乱序练习",
                    description="当前没有明显积压复习任务，保持手感即可。",
                    priority="low",
                    question_count=10,
                    action_type="create_session",
                    session_create_payload=PracticeSessionCreateRequest(
                        session_type="random",
                        answer_mode="memorize",
                        subject_id=None,
                        category_id=None,
                        chapter_id=None,
                        paper_id=None,
                        question_type=None,
                        question_count=10,
                    ),
                    derived_session_payload=None,
                )
            )

        headline = "今天先复习，再巩固，再补弱点" if review_today or weak_points else "今天保持节奏，做一组轻量练习"
        summary_parts = []
        if review_today:
            summary_parts.append(f"待复习 {len(review_today)} 题")
        if weak_points:
            summary_parts.append(f"薄弱点 {weak_points[0].name}")
        if not summary_parts:
            summary_parts.append("当前复习压力不大，适合保持手感")
        return DailyPlanResponse(
            headline=headline,
            summary="，".join(summary_parts) + "。",
            review_today_count=len(review_today),
            weak_points=weak_points,
            tasks=tasks,
        )

    def create_session(
        self,
        payload: PracticeSessionCreateRequest,
        current_user: CurrentUserResponse,
    ) -> PracticeSessionDetailResponse:
        self._validate_create_payload(payload)
        candidates = self.repository.list_candidate_questions(
            session_type=payload.session_type,
            user_id=current_user.id,
            subject_id=payload.subject_id,
            category_id=payload.category_id,
            chapter_id=payload.chapter_id,
            paper_id=payload.paper_id,
            question_type=payload.question_type,
        )
        if payload.session_type in {"random", "chapter"}:
            random.shuffle(candidates)
        if not candidates:
            raise HTTPException(status_code=422, detail="当前筛选条件下暂无可练习题目")

        selected_questions = candidates[: payload.question_count]
        snapshots_by_bank_id = self._build_question_snapshots(selected_questions)
        session_id = self._create_session_from_snapshot_records(
            current_user=current_user,
            session_type=payload.session_type,
            answer_mode=payload.answer_mode,
            title=self._build_session_title(payload),
            subject_id=payload.subject_id,
            category_id=payload.category_id,
            chapter_id=payload.chapter_id,
            paper_id=payload.paper_id,
            filters_json=payload.model_dump(exclude_none=True),
            records=[
                {
                    "bank_question_id": question.id,
                    "snapshot": snapshots_by_bank_id[question.id],
                }
                for question in selected_questions
            ],
        )
        return self.get_session_detail(session_id, current_user)

    def get_session_detail(self, session_id: int, current_user: CurrentUserResponse) -> PracticeSessionDetailResponse:
        practice_session = self._require_session(session_id, current_user.id)
        items = self.repository.list_session_items(practice_session.id)
        answers = self.repository.list_answers(practice_session.id)
        answer_by_item_id = {item.session_item_id: item for item in answers}
        can_show_solutions = practice_session.answer_mode == "memorize" or practice_session.status == "submitted"
        item_responses: list[PracticeSessionItemResponse] = []
        answered_count = 0

        for item in items:
            answer = answer_by_item_id.get(item.id)
            is_answered = answer is not None and _has_user_answer(answer.learner_answer)
            if is_answered:
                answered_count += 1
            show_result = practice_session.status == "submitted" or (practice_session.answer_mode == "memorize" and is_answered)
            item_responses.append(
                PracticeSessionItemResponse(
                    id=item.id,
                    sort_order=item.sort_order,
                    score=item.score,
                    question=self._build_question_snapshot_response(item.question_snapshot_json, show_result),
                    user_answer=answer.learner_answer if answer else None,
                    is_answered=is_answered,
                    is_correct=answer.is_correct if answer and show_result else None,
                    marked=answer.marked if answer else False,
                    spent_seconds=answer.spent_seconds if answer else None,
                    show_result=show_result,
                )
            )

        correct_count = sum(1 for answer in answers if answer.is_correct is True)
        incomplete_count = max(practice_session.total_count - answered_count, 0)
        retry_wrong_count = sum(1 for answer in answers if answer.is_correct is False)
        similar_practice_available = False
        similar_knowledge_point_ids = _top_session_knowledge_point_ids(
            [item for item in items if answer_by_item_id.get(item.id) and answer_by_item_id[item.id].is_correct is False]
            or items,
        )
        if similar_knowledge_point_ids:
            similar_candidates = self.repository.list_questions_by_knowledge_points(
                similar_knowledge_point_ids,
                exclude_bank_question_ids=[item.bank_question_id for item in items if item.bank_question_id is not None],
                subject_id=practice_session.subject_id,
                limit=1,
            )
            similar_practice_available = bool(similar_candidates)
        session_knowledge_point_ids = _session_knowledge_point_ids(items)
        weak_points = []
        if session_knowledge_point_ids:
            mastery_rows = self.repository.list_mastery_rows(
                current_user.id,
                subject_id=practice_session.subject_id,
                knowledge_point_ids=session_knowledge_point_ids,
                limit=5,
            )
            weak_points = [self._build_mastery_snapshot(snapshot, knowledge_point) for snapshot, knowledge_point in mastery_rows]
        today_review_count = len(self.list_review_today(current_user, limit=100))

        return PracticeSessionDetailResponse(
            id=practice_session.id,
            title=practice_session.title,
            session_type=practice_session.session_type,
            answer_mode=practice_session.answer_mode,
            status=practice_session.status,
            total_count=practice_session.total_count,
            answered_count=answered_count,
            correct_count=correct_count,
            accuracy_rate=_accuracy_rate(correct_count, practice_session.total_count),
            created_at=practice_session.created_at,
            started_at=practice_session.started_at,
            submitted_at=practice_session.submitted_at,
            subject_id=practice_session.subject_id,
            category_id=practice_session.category_id,
            chapter_id=practice_session.chapter_id,
            paper_id=practice_session.paper_id,
            duration_seconds=practice_session.duration_seconds,
            can_show_solutions=can_show_solutions,
            can_submit=practice_session.status != "submitted" and incomplete_count == 0 and practice_session.total_count > 0,
            incomplete_count=incomplete_count,
            today_review_count=today_review_count,
            retry_wrong_count=retry_wrong_count,
            similar_practice_available=similar_practice_available,
            weak_points=weak_points,
            items=item_responses,
        )

    def create_review_today_session(
        self,
        payload: PracticeDerivedSessionRequest,
        current_user: CurrentUserResponse,
    ) -> PracticeSessionDetailResponse:
        wrong_book_items = self.repository.list_wrong_book_items(current_user.id, 200, mastered=False)
        due_items = [item for item in wrong_book_items if _review_due_at(item) <= datetime.utcnow()]
        due_items.sort(key=lambda item: (_review_due_at(item), -item.wrong_count, item.id))
        if not due_items:
            raise HTTPException(status_code=422, detail="今天没有待复习的错题")

        session_id = self._create_session_from_snapshot_records(
            current_user=current_user,
            session_type="wrong_book",
            answer_mode=payload.answer_mode,
            title="今日待复习",
            subject_id=None,
            category_id=None,
            chapter_id=None,
            paper_id=None,
            filters_json={"source": "review_today", "question_count": payload.question_count},
            records=[
                {
                    "bank_question_id": item.bank_question_id,
                    "snapshot": item.question_snapshot_json,
                }
                for item in due_items[: payload.question_count]
            ],
        )
        return self.get_session_detail(session_id, current_user)

    def create_retry_wrong_session(
        self,
        session_id: int,
        payload: PracticeDerivedSessionRequest,
        current_user: CurrentUserResponse,
    ) -> PracticeSessionDetailResponse:
        practice_session = self._require_session(session_id, current_user.id)
        session_items = self.repository.list_session_items(practice_session.id)
        answers = self.repository.list_answers(practice_session.id)
        answer_by_item_id = {item.session_item_id: item for item in answers}
        wrong_items = [item for item in session_items if answer_by_item_id.get(item.id) and answer_by_item_id[item.id].is_correct is False]
        if not wrong_items:
            raise HTTPException(status_code=422, detail="本次练习没有可重做的错题")

        new_session_id = self._create_session_from_snapshot_records(
            current_user=current_user,
            session_type="wrong_book",
            answer_mode=payload.answer_mode,
            title=f"{practice_session.title} · 错题重练",
            subject_id=practice_session.subject_id,
            category_id=practice_session.category_id,
            chapter_id=practice_session.chapter_id,
            paper_id=practice_session.paper_id,
            filters_json={"source_session_id": practice_session.id, "source": "retry_wrong"},
            records=[
                {
                    "bank_question_id": item.bank_question_id,
                    "snapshot": item.question_snapshot_json,
                }
                for item in wrong_items[: payload.question_count]
            ],
        )
        return self.get_session_detail(new_session_id, current_user)

    def create_similar_practice_session(
        self,
        session_id: int,
        payload: PracticeDerivedSessionRequest,
        current_user: CurrentUserResponse,
    ) -> PracticeSessionDetailResponse:
        practice_session = self._require_session(session_id, current_user.id)
        session_items = self.repository.list_session_items(practice_session.id)
        answers = self.repository.list_answers(practice_session.id)
        answer_by_item_id = {item.session_item_id: item for item in answers}
        wrong_items = [item for item in session_items if answer_by_item_id.get(item.id) and answer_by_item_id[item.id].is_correct is False]
        source_items = wrong_items or session_items
        knowledge_point_ids = _top_session_knowledge_point_ids(source_items)
        if not knowledge_point_ids:
            raise HTTPException(status_code=422, detail="当前练习缺少可关联的知识点，暂时不能生成同类题")

        exclude_bank_question_ids = [item.bank_question_id for item in session_items if item.bank_question_id is not None]
        candidates = self.repository.list_questions_by_knowledge_points(
            knowledge_point_ids,
            exclude_bank_question_ids=exclude_bank_question_ids,
            subject_id=practice_session.subject_id,
            limit=payload.question_count,
        )
        if not candidates:
            raise HTTPException(status_code=422, detail="当前知识点下暂无更多同类题可练")

        random.shuffle(candidates)
        selected_questions = candidates[: payload.question_count]
        snapshots_by_bank_id = self._build_question_snapshots(selected_questions)
        new_session_id = self._create_session_from_snapshot_records(
            current_user=current_user,
            session_type="random",
            answer_mode=payload.answer_mode,
            title=f"{practice_session.title} · 同类题再练",
            subject_id=practice_session.subject_id,
            category_id=practice_session.category_id,
            chapter_id=None,
            paper_id=None,
            filters_json={
                "source_session_id": practice_session.id,
                "source": "similar_practice",
                "knowledge_point_ids": knowledge_point_ids,
            },
            records=[
                {
                    "bank_question_id": question.id,
                    "snapshot": snapshots_by_bank_id[question.id],
                }
                for question in selected_questions
            ],
        )
        return self.get_session_detail(new_session_id, current_user)

    def save_answer_reflection(
        self,
        session_id: int,
        payload: PracticeAnswerReflectionRequest,
        current_user: CurrentUserResponse,
    ) -> PracticeResultResponse:
        practice_session = self._require_session(session_id, current_user.id)
        if practice_session.status != "submitted":
            raise HTTPException(status_code=409, detail="只有交卷后才能记录错因")

        session_item = self.repository.get_session_item(payload.item_id)
        if session_item is None or session_item.session_id != practice_session.id:
            raise HTTPException(status_code=404, detail="练习题目不存在")

        answer = self.repository.get_answer_by_item(session_item.id)
        if answer is None or not _has_user_answer(answer.learner_answer):
            raise HTTPException(status_code=422, detail="当前题目还没有有效作答记录")
        if answer.is_correct is not False:
            raise HTTPException(status_code=422, detail="当前只支持给错题记录错因")

        answer.wrong_reason_tags_json = _normalize_wrong_reason_tags(payload.wrong_reason_tags)
        answer.reflection_note = _normalize_reflection_note(payload.reflection_note)
        answer.updated_by = current_user.id
        self.session.commit()
        return self.get_session_result(session_id, current_user)

    def get_session_result(self, session_id: int, current_user: CurrentUserResponse) -> PracticeResultResponse:
        detail = self.get_session_detail(session_id, current_user)
        if detail.status != "submitted":
            raise HTTPException(status_code=409, detail="当前练习尚未交卷，暂时没有完整结果页")

        practice_session = self._require_session(session_id, current_user.id)
        session_items = self.repository.list_session_items(practice_session.id)
        answers = self.repository.list_answers(practice_session.id)
        answer_by_item_id = {item.session_item_id: item for item in answers}
        wrong_reason_counts: dict[str, int] = defaultdict(int)
        result_items: list[PracticeResultItemResponse] = []

        for item in session_items:
            answer = answer_by_item_id.get(item.id)
            wrong_reason_tags = _normalize_wrong_reason_tags(answer.wrong_reason_tags_json if answer else [])
            for tag in wrong_reason_tags:
                wrong_reason_counts[tag] += 1
            result_items.append(
                PracticeResultItemResponse(
                    id=item.id,
                    sort_order=item.sort_order,
                    score=item.score,
                    question=self._build_question_snapshot_response(item.question_snapshot_json, True),
                    user_answer=answer.learner_answer if answer else None,
                    is_correct=answer.is_correct if answer else None,
                    marked=answer.marked if answer else False,
                    spent_seconds=answer.spent_seconds if answer else None,
                    wrong_reason_tags=wrong_reason_tags,
                    reflection_note=answer.reflection_note if answer else None,
                )
            )

        wrong_reason_count_rows = [
            PracticeWrongReasonCountResponse(
                reason_code=reason_code,
                reason_label=WRONG_REASON_LABELS.get(reason_code, reason_code),
                count=count,
            )
            for reason_code, count in sorted(wrong_reason_counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        knowledge_point_ids = _top_session_knowledge_point_ids(
            [item for item in session_items if answer_by_item_id.get(item.id) and answer_by_item_id[item.id].is_correct is False]
            or session_items,
        )
        similar_candidates = self.repository.list_questions_by_knowledge_points(
            knowledge_point_ids,
            exclude_bank_question_ids=[item.bank_question_id for item in session_items if item.bank_question_id is not None],
            subject_id=practice_session.subject_id,
            limit=1,
        ) if knowledge_point_ids else []

        return PracticeResultResponse(
            id=detail.id,
            title=detail.title,
            session_type=detail.session_type,
            answer_mode=detail.answer_mode,
            total_count=detail.total_count,
            correct_count=detail.correct_count,
            wrong_count=max(detail.total_count - detail.correct_count, 0),
            accuracy_rate=detail.accuracy_rate,
            duration_seconds=detail.duration_seconds,
            submitted_at=detail.submitted_at,
            today_review_count=detail.today_review_count,
            retry_wrong_count=detail.retry_wrong_count,
            similar_practice_available=bool(similar_candidates),
            weak_points=detail.weak_points,
            wrong_reason_counts=wrong_reason_count_rows,
            review_suggestions=_build_review_suggestions(detail, wrong_reason_count_rows),
            items=result_items,
        )

    def save_answer(
        self,
        session_id: int,
        payload: PracticeAnswerSubmitRequest,
        current_user: CurrentUserResponse,
    ) -> PracticeSessionDetailResponse:
        practice_session = self._require_session(session_id, current_user.id)
        if practice_session.status == "submitted":
            raise HTTPException(status_code=409, detail="当前练习已交卷，不能继续作答")

        session_item = self.repository.get_session_item(payload.item_id)
        if session_item is None or session_item.session_id != practice_session.id:
            raise HTTPException(status_code=404, detail="练习题目不存在")

        answer_text = _normalize_submitted_answer(payload.answer)
        if not answer_text and not payload.marked:
            raise HTTPException(status_code=422, detail="请先作答或标记后再保存")

        snapshot = session_item.question_snapshot_json or {}
        answer = self.repository.get_answer_by_item(session_item.id)
        evaluated = _evaluate_answer(answer_text, snapshot.get("answer_text"), str(snapshot.get("question_type") or ""))
        now = datetime.utcnow()

        if answer is None:
            self.repository.create_answer(
                PracticeAnswer(
                    tenant_id=DEFAULT_TENANT_ID,
                    session_id=practice_session.id,
                    session_item_id=session_item.id,
                    bank_question_id=session_item.bank_question_id,
                    learner_answer=answer_text,
                    is_correct=evaluated,
                    marked=payload.marked,
                    spent_seconds=payload.spent_seconds,
                    answered_at=now if answer_text else None,
                    created_by=current_user.id,
                    updated_by=current_user.id,
                )
            )
        else:
            answer.learner_answer = answer_text
            answer.is_correct = evaluated
            answer.marked = payload.marked
            answer.spent_seconds = payload.spent_seconds
            answer.answered_at = now if answer_text else None
            answer.updated_by = current_user.id

        practice_session.answered_count = self.repository.count_answered_items(practice_session.id)
        practice_session.correct_count = self.repository.count_correct_items(practice_session.id)
        practice_session.accuracy_rate = _accuracy_rate(practice_session.correct_count, practice_session.total_count)
        practice_session.updated_by = current_user.id
        self.session.commit()
        return self.get_session_detail(practice_session.id, current_user)

    def submit_session(self, session_id: int, current_user: CurrentUserResponse) -> PracticeSessionDetailResponse:
        practice_session = self._require_session(session_id, current_user.id)
        if practice_session.status == "submitted":
            return self.get_session_detail(practice_session.id, current_user)

        session_items = self.repository.list_session_items(practice_session.id)
        answers = self.repository.list_answers(practice_session.id)
        answer_by_item_id = {item.session_item_id: item for item in answers}
        unanswered_items = [
            item.id
            for item in session_items
            if item.id not in answer_by_item_id or not _has_user_answer(answer_by_item_id[item.id].learner_answer)
        ]
        if unanswered_items:
            raise HTTPException(status_code=422, detail="必须全部做完后才能统一交卷查看答案")

        now = datetime.utcnow()
        practice_session.status = "submitted"
        practice_session.answered_count = len(session_items)
        practice_session.correct_count = sum(1 for answer in answers if answer.is_correct is True)
        practice_session.accuracy_rate = _accuracy_rate(practice_session.correct_count, practice_session.total_count)
        practice_session.submitted_at = now
        practice_session.duration_seconds = _duration_seconds(practice_session.started_at, now)
        practice_session.updated_by = current_user.id
        self._sync_wrong_book(practice_session, session_items, answers, current_user.id)
        self._sync_mastery(practice_session, session_items, answers, current_user.id)
        self.session.commit()
        return self.get_session_detail(practice_session.id, current_user)

    def _validate_create_payload(self, payload: PracticeSessionCreateRequest) -> None:
        if payload.session_type == "chapter" and payload.chapter_id is None:
            raise HTTPException(status_code=422, detail="章节刷题必须选择章节")
        if payload.session_type == "paper" and payload.paper_id is None:
            raise HTTPException(status_code=422, detail="套卷刷题必须选择试卷")

    def _require_session(self, session_id: int, user_id: int) -> PracticeSession:
        practice_session = self.repository.get_session(session_id)
        if practice_session is None:
            raise HTTPException(status_code=404, detail="练习会话不存在")
        if practice_session.user_id != user_id:
            raise HTTPException(status_code=403, detail="当前账号无权查看该练习")
        return practice_session

    def _build_question_snapshots(self, questions: list[QuestionBankItem]) -> dict[int, dict[str, object]]:
        bank_question_ids = [question.id for question in questions]
        source_rows = self.repository.list_question_sources(bank_question_ids)
        first_source_by_bank_id: dict[int, tuple[str | None, str | None]] = {}
        for source_link, _review_question, paper in source_rows:
            first_source_by_bank_id.setdefault(
                source_link.bank_question_id,
                (paper.paper_name if paper else None, source_link.question_no),
            )

        review_question_ids = [question.first_source_question_id for question in questions if question.first_source_question_id is not None]
        tag_rows = self.repository.list_review_question_tags(review_question_ids)
        knowledge_points_by_review_id: dict[int, list[dict[str, object]]] = defaultdict(list)
        for tag, knowledge_point in tag_rows:
            knowledge_points_by_review_id[tag.question_id].append(
                {
                    "id": knowledge_point.id,
                    "name": knowledge_point.name,
                    "path": knowledge_point.path,
                    "relation_type": tag.relation_type,
                    "status": tag.status,
                }
            )

        snapshot_by_bank_id: dict[int, dict[str, object]] = {}
        for question in questions:
            source_paper_name, source_question_no = first_source_by_bank_id.get(question.id, (None, None))
            snapshot_by_bank_id[question.id] = {
                "bank_question_id": question.id,
                "question_uid": question.question_uid,
                "node_role": question.node_role,
                "question_type": question.question_type,
                "group_stem": question.group_stem,
                "material_text": question.material_text,
                "stem_text": question.stem_text,
                "options_json": list(question.options_json or []),
                "difficulty_level": question.difficulty_level,
                "source_paper_name": source_paper_name,
                "source_question_no": source_question_no,
                "knowledge_points": knowledge_points_by_review_id.get(question.first_source_question_id or -1, []),
                "answer_text": question.answer_text,
                "analysis_text": question.analysis_text,
            }
        return snapshot_by_bank_id

    def _build_question_snapshot_response(
        self,
        snapshot: dict[str, object],
        show_solution: bool,
    ) -> PracticeQuestionSnapshotResponse:
        knowledge_points = [
            PracticeQuestionKnowledgePointResponse.model_validate(item)
            for item in list(snapshot.get("knowledge_points") or [])
        ]
        payload = {
            "bank_question_id": snapshot.get("bank_question_id"),
            "question_uid": snapshot.get("question_uid"),
            "node_role": snapshot.get("node_role"),
            "question_type": snapshot.get("question_type"),
            "group_stem": snapshot.get("group_stem"),
            "material_text": snapshot.get("material_text"),
            "stem_text": snapshot.get("stem_text"),
            "options_json": list(snapshot.get("options_json") or []),
            "difficulty_level": snapshot.get("difficulty_level"),
            "source_paper_name": snapshot.get("source_paper_name"),
            "source_question_no": snapshot.get("source_question_no"),
            "knowledge_points": knowledge_points,
            "answer_text": snapshot.get("answer_text") if show_solution else None,
            "analysis_text": snapshot.get("analysis_text") if show_solution else None,
        }
        return PracticeQuestionSnapshotResponse.model_validate(payload)

    def _build_session_summary(self, session_item: PracticeSession) -> PracticeSessionSummaryResponse:
        return PracticeSessionSummaryResponse(
            id=session_item.id,
            title=session_item.title,
            session_type=session_item.session_type,
            answer_mode=session_item.answer_mode,
            status=session_item.status,
            total_count=session_item.total_count,
            answered_count=session_item.answered_count,
            correct_count=session_item.correct_count,
            accuracy_rate=float(session_item.accuracy_rate) if session_item.accuracy_rate is not None else None,
            created_at=session_item.created_at,
            started_at=session_item.started_at,
            submitted_at=session_item.submitted_at,
        )

    def _build_wrong_book_item(self, item: WrongBookItem) -> WrongBookItemResponse:
        snapshot = item.question_snapshot_json or {}
        knowledge_points = [
            PracticeQuestionKnowledgePointResponse.model_validate(point)
            for point in list(snapshot.get("knowledge_points") or [])
        ]
        return WrongBookItemResponse(
            id=item.id,
            bank_question_id=item.bank_question_id,
            question_type=str(snapshot.get("question_type") or ""),
            stem_text=str(snapshot.get("stem_text") or ""),
            source_paper_name=snapshot.get("source_paper_name"),
            knowledge_points=knowledge_points,
            wrong_count=item.wrong_count,
            correct_streak=item.correct_streak,
            mastered=item.mastered,
            last_wrong_at=item.last_wrong_at,
            last_practiced_at=item.last_practiced_at,
            due_at=_review_due_at(item),
            due_reason=_review_due_reason(item),
        )

    def _build_mastery_snapshot(
        self,
        snapshot: MasterySnapshot,
        knowledge_point,
    ) -> MasterySnapshotResponse:
        return MasterySnapshotResponse(
            knowledge_point_id=knowledge_point.id,
            name=knowledge_point.name,
            path=knowledge_point.path,
            chapter_id=knowledge_point.chapter_id,
            mastery_score=float(snapshot.mastery_score),
            answered_count=snapshot.answered_count,
            correct_count=snapshot.correct_count,
            snapshot_date=snapshot.snapshot_date,
            last_practiced_at=snapshot.last_practiced_at,
        )

    def _build_review_due_item(self, item: WrongBookItem) -> ReviewDueItemResponse:
        snapshot = item.question_snapshot_json or {}
        knowledge_points = [
            PracticeQuestionKnowledgePointResponse.model_validate(point)
            for point in list(snapshot.get("knowledge_points") or [])
        ]
        return ReviewDueItemResponse(
            id=item.id,
            bank_question_id=item.bank_question_id,
            question_type=str(snapshot.get("question_type") or ""),
            stem_text=str(snapshot.get("stem_text") or ""),
            source_paper_name=snapshot.get("source_paper_name"),
            knowledge_points=knowledge_points,
            wrong_count=item.wrong_count,
            correct_streak=item.correct_streak,
            due_at=_review_due_at(item),
            due_reason=_review_due_reason(item),
        )

    def _build_session_title(self, payload: PracticeSessionCreateRequest) -> str:
        if payload.session_type == "paper":
            paper = self.repository.get_paper(payload.paper_id)
            return f"{paper.paper_name if paper else '套卷'}练习"
        if payload.session_type == "wrong_book":
            return "错题重练"
        if payload.session_type == "chapter":
            chapter = self.repository.get_chapter(payload.chapter_id)
            return f"{chapter.name if chapter else '章节'}练习"
        category = self.repository.get_category(payload.category_id)
        subject = self.repository.get_subject(payload.subject_id)
        if category is not None:
            return f"{category.name}乱序练习"
        if subject is not None:
            return f"{subject.name}乱序练习"
        return "随机练习"

    def _create_session_from_snapshot_records(
        self,
        *,
        current_user: CurrentUserResponse,
        session_type: str,
        answer_mode: str,
        title: str,
        subject_id: int | None,
        category_id: int | None,
        chapter_id: int | None,
        paper_id: int | None,
        filters_json: dict[str, object],
        records: list[dict[str, object]],
    ) -> int:
        if not records:
            raise HTTPException(status_code=422, detail="当前没有可生成练习的题目")
        now = datetime.utcnow()
        practice_session = PracticeSession(
            tenant_id=DEFAULT_TENANT_ID,
            user_id=current_user.id,
            session_type=session_type,
            answer_mode=answer_mode,
            subject_id=subject_id,
            category_id=category_id,
            chapter_id=chapter_id,
            paper_id=paper_id,
            title=title,
            filters_json=filters_json,
            status="in_progress",
            total_count=len(records),
            answered_count=0,
            correct_count=0,
            accuracy_rate=None,
            started_at=now,
            submitted_at=None,
            duration_seconds=None,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        self.repository.create_session(practice_session)
        self.repository.create_session_items(
            [
                PracticeSessionItem(
                    tenant_id=DEFAULT_TENANT_ID,
                    session_id=practice_session.id,
                    bank_question_id=record.get("bank_question_id"),
                    sort_order=index,
                    score=1,
                    question_snapshot_json=dict(record.get("snapshot") or {}),
                    created_by=current_user.id,
                    updated_by=current_user.id,
                )
                for index, record in enumerate(records, start=1)
            ]
        )
        self.session.commit()
        return practice_session.id

    def _sync_wrong_book(
        self,
        practice_session: PracticeSession,
        session_items: list[PracticeSessionItem],
        answers: list[PracticeAnswer],
        user_id: int,
    ) -> None:
        answer_by_item_id = {item.session_item_id: item for item in answers}
        now = practice_session.submitted_at or datetime.utcnow()
        for session_item in session_items:
            answer = answer_by_item_id.get(session_item.id)
            if answer is None or not _has_user_answer(answer.learner_answer):
                continue

            wrong_book_item = self.repository.get_wrong_book_item(user_id, session_item.bank_question_id)
            if answer.is_correct is True:
                if wrong_book_item is None:
                    continue
                wrong_book_item.correct_streak += 1
                wrong_book_item.mastered = wrong_book_item.correct_streak >= 2
                wrong_book_item.last_practiced_at = now
                wrong_book_item.source_session_id = practice_session.id
                wrong_book_item.question_snapshot_json = session_item.question_snapshot_json
                wrong_book_item.updated_by = user_id
                continue

            if wrong_book_item is None:
                self.repository.create_wrong_book_item(
                    WrongBookItem(
                        tenant_id=DEFAULT_TENANT_ID,
                        user_id=user_id,
                        bank_question_id=session_item.bank_question_id,
                        source_session_id=practice_session.id,
                        question_snapshot_json=session_item.question_snapshot_json,
                        wrong_count=1,
                        correct_streak=0,
                        mastered=False,
                        last_wrong_at=now,
                        last_practiced_at=now,
                        created_by=user_id,
                        updated_by=user_id,
                    )
                )
                continue

            wrong_book_item.question_snapshot_json = session_item.question_snapshot_json
            wrong_book_item.source_session_id = practice_session.id
            wrong_book_item.wrong_count += 1
            wrong_book_item.correct_streak = 0
            wrong_book_item.mastered = False
            wrong_book_item.last_wrong_at = now
            wrong_book_item.last_practiced_at = now
            wrong_book_item.updated_by = user_id

    def _sync_mastery(
        self,
        practice_session: PracticeSession,
        session_items: list[PracticeSessionItem],
        answers: list[PracticeAnswer],
        user_id: int,
    ) -> None:
        if practice_session.subject_id is None:
            return
        answer_by_item_id = {item.session_item_id: item for item in answers}
        today = date.today()
        now = practice_session.submitted_at or datetime.utcnow()
        for session_item in session_items:
            answer = answer_by_item_id.get(session_item.id)
            if answer is None or not _has_user_answer(answer.learner_answer):
                continue
            knowledge_point_ids = _snapshot_knowledge_point_ids(session_item.question_snapshot_json or {})
            for knowledge_point_id in knowledge_point_ids:
                snapshot = self.repository.get_mastery_snapshot(user_id, knowledge_point_id)
                if snapshot is None:
                    snapshot = self.repository.create_mastery_snapshot(
                        MasterySnapshot(
                            tenant_id=DEFAULT_TENANT_ID,
                            user_id=user_id,
                            subject_id=practice_session.subject_id,
                            knowledge_point_id=knowledge_point_id,
                            mastery_score=0,
                            answered_count=0,
                            correct_count=0,
                            snapshot_date=today,
                            last_practiced_at=now,
                            created_by=user_id,
                            updated_by=user_id,
                        )
                    )
                snapshot.answered_count += 1
                if answer.is_correct is True:
                    snapshot.correct_count += 1
                snapshot.mastery_score = _accuracy_rate(snapshot.correct_count, snapshot.answered_count) or 0
                snapshot.snapshot_date = today
                snapshot.last_practiced_at = now
                snapshot.updated_by = user_id


def _normalize_submitted_answer(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_reflection_note(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_wrong_reason_tags(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        normalized = str(value).strip()
        if normalized in WRONG_REASON_LABELS and normalized not in result:
            result.append(normalized)
    return result[:4]


def _has_user_answer(value: str | None) -> bool:
    return bool(value and value.strip())


def _evaluate_answer(user_answer: str | None, standard_answer: object, question_type: str) -> bool | None:
    expected = _normalize_answer_text(standard_answer)
    actual = _normalize_answer_text(user_answer)
    if not actual:
        return None
    if not expected:
        return None
    if question_type == "multiple_choice":
        return _extract_choice_tokens(actual) == _extract_choice_tokens(expected)
    return actual == expected


def _normalize_answer_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("　", " ")
    text = re.sub(r"\s+", "", text)
    return text.upper()


def _extract_choice_tokens(value: str) -> tuple[str, ...]:
    tokens = re.findall(r"[A-Z]", value.upper())
    if tokens:
        return tuple(sorted(set(tokens)))
    return (value,)


def _accuracy_rate(correct_count: int, total_count: int) -> float | None:
    if total_count <= 0:
        return None
    return round(correct_count * 100 / total_count, 2)


def _duration_seconds(started_at: datetime | None, finished_at: datetime) -> int | None:
    if started_at is None:
        return None
    return max(int((finished_at - started_at).total_seconds()), 0)


def _snapshot_knowledge_point_ids(snapshot: dict[str, object]) -> list[int]:
    result: list[int] = []
    for item in list(snapshot.get("knowledge_points") or []):
        if not isinstance(item, dict):
            continue
        knowledge_point_id = item.get("id")
        if isinstance(knowledge_point_id, int) and knowledge_point_id not in result:
            result.append(knowledge_point_id)
    return result


def _session_knowledge_point_ids(items: list[PracticeSessionItem]) -> list[int]:
    result: list[int] = []
    for item in items:
        for knowledge_point_id in _snapshot_knowledge_point_ids(item.question_snapshot_json or {}):
            if knowledge_point_id not in result:
                result.append(knowledge_point_id)
    return result


def _top_session_knowledge_point_ids(items: list[PracticeSessionItem], *, limit: int = 3) -> list[int]:
    counts: dict[int, int] = defaultdict(int)
    for item in items:
        for knowledge_point_id in _snapshot_knowledge_point_ids(item.question_snapshot_json or {}):
            counts[knowledge_point_id] += 1
    sorted_ids = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [knowledge_point_id for knowledge_point_id, _count in sorted_ids[:limit]]


def _review_due_at(item: WrongBookItem) -> datetime:
    base_at = item.last_practiced_at or item.last_wrong_at or item.updated_at or item.created_at
    delay_days = 0 if item.correct_streak <= 0 else 1 if item.correct_streak == 1 else 3
    return base_at + timedelta(days=delay_days)


def _review_due_reason(item: WrongBookItem) -> str:
    if item.correct_streak <= 0:
        return "新错题，建议当天回顾一轮"
    if item.correct_streak == 1:
        return "已改对 1 次，建议次日再巩固"
    return "建议按间隔复习继续巩固"


def _build_review_suggestions(
    detail: PracticeSessionDetailResponse,
    wrong_reason_counts: list[PracticeWrongReasonCountResponse],
) -> list[str]:
    suggestions: list[str] = []
    accuracy = float(detail.accuracy_rate or 0)
    if accuracy < 60:
        suggestions.append("先不要急着刷新题，优先把这次错题和同类题再练一轮，把正确率先拉回到 70% 以上。")
    elif accuracy < 80:
        suggestions.append("本次正确率处在可提升区间，建议先完成错题重练，再补一组 10 题同类题巩固。")
    else:
        suggestions.append("整体表现不错，建议把注意力放在薄弱知识点和今日待复习题，保持稳定输出。")

    top_reason = wrong_reason_counts[0] if wrong_reason_counts else None
    if top_reason is not None:
        if top_reason.reason_code == "misread_question":
            suggestions.append("错题主要集中在审题偏差，下一轮做题时先画关键词，再下手作答。")
        elif top_reason.reason_code == "concept_unclear":
            suggestions.append("概念型错误偏多，建议先回看对应知识点定义和典型例题，再继续刷题。")
        elif top_reason.reason_code == "memory_unstable":
            suggestions.append("记忆型错误偏多，建议把易混点单独整理成短卡片，配合背记模式反复强化。")
        elif top_reason.reason_code == "calculation_error":
            suggestions.append("计算型错误偏多，建议下一轮控制节奏，分步写关键过程，减少中间跳步。")
        elif top_reason.reason_code == "method_unfamiliar":
            suggestions.append("方法型错误偏多，说明会做但路径不熟，建议用同类题再练把套路走顺。")
        elif top_reason.reason_code == "careless":
            suggestions.append("粗心失误偏多，建议下一轮降低速度，优先减少非知识性失分。")

    if detail.today_review_count > 0:
        suggestions.append(f"当前还有 {detail.today_review_count} 题待复习，建议今天把回顾任务清掉，避免错题继续积压。")
    if detail.weak_points:
        suggestions.append(f"本次最该补的知识点是「{detail.weak_points[0].name}」，后续练习优先围绕它展开。")
    return suggestions[:4]

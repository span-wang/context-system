from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Chapter,
    ExamPaper,
    KnowledgePoint,
    PaperReviewQuestion,
    PaperReviewQuestionKnowledgePoint,
    QuestionBankItem,
    QuestionBankSourceLink,
    Subject,
    SubjectCategory,
    Tenant,
    User,
)
from app.models.base import Base
from app.schemas.auth import CurrentUserResponse
from app.schemas.learning import (
    PracticeAnswerReflectionRequest,
    PracticeAnswerSubmitRequest,
    PracticeDerivedSessionRequest,
    PracticeSessionCreateRequest,
)
from app.services.learning import LearningService


def test_create_chapter_session_uses_question_bank_tags() -> None:
    session = _build_session()
    try:
        current_user, context = _seed_learning_context(session)
        service = LearningService(session)

        detail = service.create_session(
            PracticeSessionCreateRequest(
                session_type="chapter",
                answer_mode="memorize",
                subject_id=context["subject"].id,
                category_id=context["category"].id,
                chapter_id=context["target_chapter"].id,
                question_count=10,
            ),
            current_user,
        )

        assert detail.total_count == 2
        assert len(detail.items) == 2
        assert {item.question.bank_question_id for item in detail.items} == {
            context["target_question"].id,
            context["similar_question"].id,
        }
        assert all(item.question.knowledge_points[0].id == context["target_point"].id for item in detail.items)
    finally:
        session.close()


def test_exam_session_reveals_answer_only_after_submit_and_updates_wrong_book() -> None:
    session = _build_session()
    try:
        current_user, context = _seed_learning_context(session)
        service = LearningService(session)

        detail = service.create_session(
            PracticeSessionCreateRequest(
                session_type="paper",
                answer_mode="exam",
                subject_id=context["subject"].id,
                category_id=context["category"].id,
                paper_id=context["paper"].id,
                question_count=1,
            ),
            current_user,
        )
        item = detail.items[0]

        after_answer = service.save_answer(
            detail.id,
            PracticeAnswerSubmitRequest(item_id=item.id, answer="B"),
            current_user,
        )

        assert after_answer.items[0].question.answer_text is None
        assert after_answer.items[0].is_correct is None
        assert after_answer.can_submit is True

        submitted = service.submit_session(detail.id, current_user)

        assert submitted.status == "submitted"
        assert submitted.items[0].question.answer_text == "A"
        assert submitted.items[0].is_correct is False

        wrong_book = service.list_wrong_book(current_user)
        assert len(wrong_book) == 1
        assert wrong_book[0].bank_question_id == context["target_question"].id
        assert wrong_book[0].wrong_count == 1
        assert wrong_book[0].due_at is not None

        mastery = service.list_mastery(current_user, subject_id=context["subject"].id)
        assert len(mastery) == 1
        assert mastery[0].knowledge_point_id == context["target_point"].id
        assert mastery[0].mastery_score == 0

        review_today = service.list_review_today(current_user)
        assert len(review_today) == 1
        assert review_today[0].bank_question_id == context["target_question"].id
    finally:
        session.close()


def test_similar_practice_uses_same_knowledge_point_and_excludes_original_question() -> None:
    session = _build_session()
    try:
        current_user, context = _seed_learning_context(session)
        service = LearningService(session)

        detail = service.create_session(
            PracticeSessionCreateRequest(
                session_type="paper",
                answer_mode="exam",
                subject_id=context["subject"].id,
                category_id=context["category"].id,
                paper_id=context["paper"].id,
                question_count=1,
            ),
            current_user,
        )
        item = detail.items[0]
        service.save_answer(
            detail.id,
            PracticeAnswerSubmitRequest(item_id=item.id, answer="B"),
            current_user,
        )
        service.submit_session(detail.id, current_user)

        similar = service.create_similar_practice_session(
            detail.id,
            PracticeDerivedSessionRequest(question_count=5, answer_mode="memorize"),
            current_user,
        )

        assert similar.total_count == 1
        assert similar.items[0].question.bank_question_id == context["similar_question"].id
        assert similar.items[0].question.knowledge_points[0].id == context["target_point"].id
    finally:
        session.close()


def test_result_report_and_daily_plan_include_reflection_and_review_tasks() -> None:
    session = _build_session()
    try:
        current_user, context = _seed_learning_context(session)
        service = LearningService(session)

        detail = service.create_session(
            PracticeSessionCreateRequest(
                session_type="paper",
                answer_mode="exam",
                subject_id=context["subject"].id,
                category_id=context["category"].id,
                paper_id=context["paper"].id,
                question_count=1,
            ),
            current_user,
        )
        item = detail.items[0]
        service.save_answer(
            detail.id,
            PracticeAnswerSubmitRequest(item_id=item.id, answer="B"),
            current_user,
        )
        service.submit_session(detail.id, current_user)

        result = service.save_answer_reflection(
            detail.id,
            PracticeAnswerReflectionRequest(
                item_id=item.id,
                wrong_reason_tags=["concept_unclear", "misread_question"],
                reflection_note="题干关键词没抓住，概念也没记牢。",
            ),
            current_user,
        )

        assert result.wrong_count == 1
        assert result.items[0].wrong_reason_tags == ["concept_unclear", "misread_question"]
        assert result.items[0].reflection_note == "题干关键词没抓住，概念也没记牢。"
        assert result.wrong_reason_counts[0].reason_code == "concept_unclear"
        assert result.review_suggestions

        daily_plan = service.get_daily_plan(current_user)
        assert daily_plan.review_today_count == 1
        assert daily_plan.tasks
        assert daily_plan.tasks[0].task_type == "review_today"
        assert daily_plan.weak_points
    finally:
        session.close()


def _build_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    return session_factory()


def _seed_learning_context(session: Session) -> tuple[CurrentUserResponse, dict[str, object]]:
    tenant = Tenant(code="tenant-learning", name="Tenant Learning", status="active", plan_type="professional")
    session.add(tenant)
    session.flush()

    user = User(
        tenant_id=tenant.id,
        username="learner",
        password_hash="hashed",
        display_name="学习用户",
        mobile=None,
        email=None,
        user_type="student",
        status="active",
        last_login_at=None,
        created_by=None,
        updated_by=None,
    )
    session.add(user)
    session.flush()

    subject = Subject(tenant_id=tenant.id, code="acct", name="会计", status="active", created_by=None, updated_by=None)
    session.add(subject)
    session.flush()

    category = SubjectCategory(
        tenant_id=tenant.id,
        subject_id=subject.id,
        name="会计实务",
        sort_order=1,
        created_by=None,
        updated_by=None,
    )
    session.add(category)
    session.flush()

    target_chapter = Chapter(
        tenant_id=tenant.id,
        subject_id=subject.id,
        category_id=category.id,
        parent_id=None,
        name="收入",
        level=1,
        path="收入",
        sort_order=1,
        created_by=None,
        updated_by=None,
    )
    other_chapter = Chapter(
        tenant_id=tenant.id,
        subject_id=subject.id,
        category_id=category.id,
        parent_id=None,
        name="成本",
        level=1,
        path="成本",
        sort_order=2,
        created_by=None,
        updated_by=None,
    )
    session.add_all([target_chapter, other_chapter])
    session.flush()

    target_point = KnowledgePoint(
        tenant_id=tenant.id,
        subject_id=subject.id,
        category_id=category.id,
        chapter_id=target_chapter.id,
        parent_id=None,
        name="收入确认",
        level=1,
        path="收入/收入确认",
        description=None,
        keywords_json=["收入"],
        status="active",
        sort_order=1,
        created_by=None,
        updated_by=None,
    )
    other_point = KnowledgePoint(
        tenant_id=tenant.id,
        subject_id=subject.id,
        category_id=category.id,
        chapter_id=other_chapter.id,
        parent_id=None,
        name="成本归集",
        level=1,
        path="成本/成本归集",
        description=None,
        keywords_json=["成本"],
        status="active",
        sort_order=2,
        created_by=None,
        updated_by=None,
    )
    session.add_all([target_point, other_point])
    session.flush()

    paper = ExamPaper(
        tenant_id=tenant.id,
        subject_id=subject.id,
        category_id=category.id,
        asset_id=None,
        paper_name="2026 模拟卷",
        paper_code=None,
        exam_year=2026,
        exam_month=5,
        exam_region=None,
        exam_type=None,
        paper_type="模拟题",
        source_channel=None,
        status="published",
        total_question_count=2,
        total_score=None,
        parsed_version=1,
        review_status="approved",
        created_by=None,
        updated_by=None,
    )
    session.add(paper)
    session.flush()

    target_review = PaperReviewQuestion(
        tenant_id=tenant.id,
        paper_id=paper.id,
        section_id=None,
        parent_question_id=None,
        question_uid="RQ-1",
        content_fingerprint="review-fp-1",
        sort_order=1,
        question_no="1",
        node_role="standalone",
        question_type="single_choice",
        source_section_name="单选题",
        source_raw_text="题1",
        group_stem=None,
        material_text=None,
        stem_text="收入确认应当在何时确认？",
        options_json=["A. 控制权转移时", "B. 合同签订时"],
        answer_text="A",
        analysis_text="控制权转移时确认收入。",
        difficulty_level=2,
        quality_score=0.95,
        subquestion_count=0,
        quality_issues_json=[],
        parse_status="manual_updated",
        review_status="approved",
        review_note=None,
        ai_review_status=None,
        ai_review_note=None,
        ai_standardization_note=None,
        last_ai_standardized_at=None,
        last_ai_reviewed_at=None,
        reviewed_by=None,
        reviewed_at=None,
        created_by=None,
        updated_by=None,
    )
    other_review = PaperReviewQuestion(
        tenant_id=tenant.id,
        paper_id=paper.id,
        section_id=None,
        parent_question_id=None,
        question_uid="RQ-2",
        content_fingerprint="review-fp-2",
        sort_order=2,
        question_no="2",
        node_role="standalone",
        question_type="single_choice",
        source_section_name="单选题",
        source_raw_text="题2",
        group_stem=None,
        material_text=None,
        stem_text="成本应当如何归集？",
        options_json=["A. 按收入", "B. 按对象"],
        answer_text="B",
        analysis_text="按成本对象归集。",
        difficulty_level=2,
        quality_score=0.9,
        subquestion_count=0,
        quality_issues_json=[],
        parse_status="manual_updated",
        review_status="approved",
        review_note=None,
        ai_review_status=None,
        ai_review_note=None,
        ai_standardization_note=None,
        last_ai_standardized_at=None,
        last_ai_reviewed_at=None,
        reviewed_by=None,
        reviewed_at=None,
        created_by=None,
        updated_by=None,
    )
    similar_review = PaperReviewQuestion(
        tenant_id=tenant.id,
        paper_id=paper.id,
        section_id=None,
        parent_question_id=None,
        question_uid="RQ-3",
        content_fingerprint="review-fp-3",
        sort_order=3,
        question_no="3",
        node_role="standalone",
        question_type="single_choice",
        source_section_name="单选题",
        source_raw_text="题3",
        group_stem=None,
        material_text=None,
        stem_text="收入确认五步法中先识别什么？",
        options_json=["A. 合同", "B. 存货"],
        answer_text="A",
        analysis_text="先识别合同。",
        difficulty_level=2,
        quality_score=0.92,
        subquestion_count=0,
        quality_issues_json=[],
        parse_status="manual_updated",
        review_status="approved",
        review_note=None,
        ai_review_status=None,
        ai_review_note=None,
        ai_standardization_note=None,
        last_ai_standardized_at=None,
        last_ai_reviewed_at=None,
        reviewed_by=None,
        reviewed_at=None,
        created_by=None,
        updated_by=None,
    )
    session.add_all([target_review, other_review, similar_review])
    session.flush()

    session.add_all(
        [
            PaperReviewQuestionKnowledgePoint(
                tenant_id=tenant.id,
                question_id=target_review.id,
                knowledge_point_id=target_point.id,
                status="confirmed",
                relation_type="primary",
                source="manual",
                confidence=0.99,
                reason=None,
                rank=1,
                created_by=None,
                updated_by=None,
            ),
            PaperReviewQuestionKnowledgePoint(
                tenant_id=tenant.id,
                question_id=other_review.id,
                knowledge_point_id=other_point.id,
                status="confirmed",
                relation_type="primary",
                source="manual",
                confidence=0.99,
                reason=None,
                rank=1,
                created_by=None,
                updated_by=None,
            ),
            PaperReviewQuestionKnowledgePoint(
                tenant_id=tenant.id,
                question_id=similar_review.id,
                knowledge_point_id=target_point.id,
                status="confirmed",
                relation_type="primary",
                source="manual",
                confidence=0.99,
                reason=None,
                rank=1,
                created_by=None,
                updated_by=None,
            ),
        ]
    )
    session.flush()

    target_question = QuestionBankItem(
        tenant_id=tenant.id,
        subject_id=subject.id,
        category_id=category.id,
        parent_question_id=None,
        question_uid="QB-1",
        content_fingerprint="bank-fp-1",
        node_role="standalone",
        question_type="single_choice",
        group_stem=None,
        material_text=None,
        stem_text=target_review.stem_text,
        options_json=target_review.options_json,
        answer_text=target_review.answer_text,
        analysis_text=target_review.analysis_text,
        difficulty_level=2,
        quality_score=0.95,
        status="active",
        source_count=1,
        first_source_question_id=target_review.id,
        created_by=None,
        updated_by=None,
    )
    other_question = QuestionBankItem(
        tenant_id=tenant.id,
        subject_id=subject.id,
        category_id=category.id,
        parent_question_id=None,
        question_uid="QB-2",
        content_fingerprint="bank-fp-2",
        node_role="standalone",
        question_type="single_choice",
        group_stem=None,
        material_text=None,
        stem_text=other_review.stem_text,
        options_json=other_review.options_json,
        answer_text=other_review.answer_text,
        analysis_text=other_review.analysis_text,
        difficulty_level=2,
        quality_score=0.9,
        status="active",
        source_count=1,
        first_source_question_id=other_review.id,
        created_by=None,
        updated_by=None,
    )
    similar_question = QuestionBankItem(
        tenant_id=tenant.id,
        subject_id=subject.id,
        category_id=category.id,
        parent_question_id=None,
        question_uid="QB-3",
        content_fingerprint="bank-fp-3",
        node_role="standalone",
        question_type="single_choice",
        group_stem=None,
        material_text=None,
        stem_text=similar_review.stem_text,
        options_json=similar_review.options_json,
        answer_text=similar_review.answer_text,
        analysis_text=similar_review.analysis_text,
        difficulty_level=2,
        quality_score=0.92,
        status="active",
        source_count=1,
        first_source_question_id=similar_review.id,
        created_by=None,
        updated_by=None,
    )
    session.add_all([target_question, other_question, similar_question])
    session.flush()

    session.add_all(
        [
            QuestionBankSourceLink(
                tenant_id=tenant.id,
                bank_question_id=target_question.id,
                source_type="paper_review_question",
                source_question_id=target_review.id,
                paper_id=paper.id,
                section_id=None,
                question_no="1",
                source_fingerprint=target_review.content_fingerprint,
                status="active",
                created_by=None,
                updated_by=None,
            ),
            QuestionBankSourceLink(
                tenant_id=tenant.id,
                bank_question_id=other_question.id,
                source_type="paper_review_question",
                source_question_id=other_review.id,
                paper_id=paper.id,
                section_id=None,
                question_no="2",
                source_fingerprint=other_review.content_fingerprint,
                status="active",
                created_by=None,
                updated_by=None,
            ),
            QuestionBankSourceLink(
                tenant_id=tenant.id,
                bank_question_id=similar_question.id,
                source_type="paper_review_question",
                source_question_id=similar_review.id,
                paper_id=paper.id,
                section_id=None,
                question_no="3",
                source_fingerprint=similar_review.content_fingerprint,
                status="active",
                created_by=None,
                updated_by=None,
            ),
        ]
    )
    session.commit()

    current_user = CurrentUserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        mobile=user.mobile,
        user_type=user.user_type,
        status=user.status,
        last_login_at=user.last_login_at,
        roles=[],
    )
    return current_user, {
        "subject": subject,
        "category": category,
        "paper": paper,
        "target_chapter": target_chapter,
        "target_point": target_point,
        "target_question": target_question,
        "similar_question": similar_question,
    }

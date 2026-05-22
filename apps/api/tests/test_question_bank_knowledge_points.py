from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import Chapter, ExamPaper, KnowledgePoint, PaperReviewQuestion, PaperReviewQuestionKnowledgePoint, Subject, SubjectCategory, Tenant
from app.models.base import Base
from app.schemas.paper_review import PaperReviewQuestionKnowledgePointUpdateRequest, PaperReviewQuestionKnowledgePointUpsertItem
from app.services.paper_review import PaperReviewService
from app.services.question_bank import QuestionBankService


def test_question_bank_keeps_knowledge_points_aligned_with_latest_synced_review_question() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = session_factory()
    try:
        tenant = Tenant(code="tenant-1", name="Tenant 1", status="active", plan_type="professional")
        session.add(tenant)
        session.flush()

        subject = Subject(tenant_id=tenant.id, code="math", name="数学", status="active")
        session.add(subject)
        session.flush()

        category = SubjectCategory(tenant_id=tenant.id, subject_id=subject.id, name="高考", sort_order=1)
        session.add(category)
        session.flush()

        chapter = Chapter(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            parent_id=None,
            name="函数",
            level=1,
            path="数学/函数",
            sort_order=1,
        )
        session.add(chapter)
        session.flush()

        point = KnowledgePoint(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            chapter_id=chapter.id,
            parent_id=None,
            name="二次函数",
            level=1,
            path="数学/函数/二次函数",
            description=None,
            keywords_json=None,
            status="active",
            sort_order=1,
        )
        session.add(point)
        session.flush()

        paper = ExamPaper(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            asset_id=None,
            paper_name="2025 真题",
            paper_code=None,
            exam_year=2025,
            exam_month=6,
            exam_region=None,
            exam_type=None,
            paper_type="真题",
            source_channel=None,
            status="published",
            total_question_count=2,
            total_score=None,
            parsed_version=1,
            review_status="approved",
        )
        session.add(paper)
        session.flush()

        first_review_question = PaperReviewQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_id=None,
            question_uid="RQ-1",
            content_fingerprint="fingerprint-1",
            sort_order=1,
            question_no="1",
            question_type="single_choice",
            source_section_name="选择题",
            source_raw_text="题目",
            stem_text="已知二次函数图像，求最值。",
            options_json=["A", "B", "C", "D"],
            answer_text="A",
            analysis_text="解析 1",
            difficulty_level=3,
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
        second_review_question = PaperReviewQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_id=None,
            question_uid="RQ-2",
            content_fingerprint="fingerprint-2",
            sort_order=2,
            question_no="2",
            question_type="single_choice",
            source_section_name="选择题",
            source_raw_text="题目",
            stem_text="已知二次函数图像，求最值。",
            options_json=["A", "B", "C", "D"],
            answer_text="A",
            analysis_text="解析 2",
            difficulty_level=3,
            quality_score=0.97,
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
        session.add_all([first_review_question, second_review_question])
        session.flush()

        session.add(
            PaperReviewQuestionKnowledgePoint(
                tenant_id=tenant.id,
                question_id=second_review_question.id,
                knowledge_point_id=point.id,
                status="confirmed",
                relation_type="primary",
                source="manual",
                confidence=1.0,
                reason=None,
                rank=1,
                created_by=None,
                updated_by=None,
            )
        )
        session.flush()

        service = QuestionBankService(session)
        first_sync = service.sync_from_review_question(first_review_question.id)
        second_sync = service.sync_from_review_question(second_review_question.id)
        payload = service.get_question(second_sync.bank_question_id)

        assert [item.id for item in payload.knowledge_points] == [point.id]
        assert payload.knowledge_points[0].name == "二次函数"
        assert payload.knowledge_points[0].relation_type == "primary"
        assert payload.first_source_question_id == second_review_question.id
        assert first_sync.bank_question_id == second_sync.bank_question_id
    finally:
        session.close()
        engine.dispose()


def test_approved_review_question_resyncs_bank_when_knowledge_points_change() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = session_factory()
    try:
        tenant = Tenant(code="tenant-2", name="Tenant 2", status="active", plan_type="professional")
        session.add(tenant)
        session.flush()

        subject = Subject(tenant_id=tenant.id, code="math", name="数学", status="active")
        session.add(subject)
        session.flush()

        category = SubjectCategory(tenant_id=tenant.id, subject_id=subject.id, name="高考", sort_order=1)
        session.add(category)
        session.flush()

        chapter = Chapter(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            parent_id=None,
            name="函数",
            level=1,
            path="数学/函数",
            sort_order=1,
        )
        session.add(chapter)
        session.flush()

        point = KnowledgePoint(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            chapter_id=chapter.id,
            parent_id=None,
            name="函数单调性",
            level=1,
            path="数学/函数/函数单调性",
            description=None,
            keywords_json=None,
            status="active",
            sort_order=1,
        )
        session.add(point)
        session.flush()

        paper = ExamPaper(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            asset_id=None,
            paper_name="2026 真题",
            paper_code=None,
            exam_year=2026,
            exam_month=6,
            exam_region=None,
            exam_type=None,
            paper_type="真题",
            source_channel=None,
            status="published",
            total_question_count=1,
            total_score=None,
            parsed_version=1,
            review_status="approved",
        )
        session.add(paper)
        session.flush()

        review_question = PaperReviewQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_id=None,
            question_uid="RQ-3",
            content_fingerprint="fingerprint-3",
            sort_order=1,
            question_no="1",
            question_type="single_choice",
            source_section_name="选择题",
            source_raw_text="题目",
            stem_text="已知函数在区间上单调，判断参数范围。",
            options_json=["A", "B", "C", "D"],
            answer_text="B",
            analysis_text="解析 3",
            difficulty_level=3,
            quality_score=0.93,
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
        session.add(review_question)
        session.commit()

        bank_payload = QuestionBankService(session).sync_from_review_question(review_question.id)
        before = QuestionBankService(session).get_question(bank_payload.bank_question_id)
        assert before.knowledge_points == []

        PaperReviewService(session).update_question_knowledge_points(
            review_question.id,
            PaperReviewQuestionKnowledgePointUpdateRequest(
                suggested=[
                    PaperReviewQuestionKnowledgePointUpsertItem(
                        knowledge_point_id=point.id,
                        relation_type="primary",
                        source="ai",
                        confidence=0.86,
                        reason="AI 候选",
                        rank=1,
                    )
                ],
                confirmed=[],
            ),
        )

        after_suggested = QuestionBankService(session).get_question(bank_payload.bank_question_id)
        assert [item.id for item in after_suggested.knowledge_points] == [point.id]
        assert after_suggested.knowledge_points[0].status == "suggested"
        suggested_analysis = QuestionBankService(session).get_knowledge_analysis(
            subject_id=subject.id,
            category_id=category.id,
        )
        assert suggested_analysis.summary.tagged_source_question_count == 1
        assert [item.knowledge_point_id for item in suggested_analysis.point_distribution] == [point.id]

        PaperReviewService(session).update_question_knowledge_points(
            review_question.id,
            PaperReviewQuestionKnowledgePointUpdateRequest(
                suggested=[],
                confirmed=[
                    PaperReviewQuestionKnowledgePointUpsertItem(
                        knowledge_point_id=point.id,
                        relation_type="primary",
                        source="manual",
                        confidence=1.0,
                        reason="人工确认",
                        rank=1,
                    )
                ],
            ),
        )

        after = QuestionBankService(session).get_question(bank_payload.bank_question_id)
        assert [item.id for item in after.knowledge_points] == [point.id]
        assert after.knowledge_points[0].status == "confirmed"
        assert after.first_source_question_id == review_question.id
    finally:
        session.close()
        engine.dispose()

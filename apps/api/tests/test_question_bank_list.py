from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models import ExamPaper, PaperReviewQuestion, QuestionBankItem, QuestionBankSourceLink, Subject, SubjectCategory, Tenant
from app.models.base import Base
from app.services.question_bank import QuestionBankService


def test_list_questions_handles_bank_children_without_sort_order() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = session_factory()
    try:
        tenant = Tenant(code="tenant-qb-list", name="Tenant QB List", status="active", plan_type="professional")
        session.add(tenant)
        session.flush()

        subject = Subject(tenant_id=tenant.id, code="acct", name="会计", status="active")
        session.add(subject)
        session.flush()

        category = SubjectCategory(tenant_id=tenant.id, subject_id=subject.id, name="实务", sort_order=1)
        session.add(category)
        session.flush()

        paper = ExamPaper(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            asset_id=None,
            paper_name="2025 真题",
            paper_code=None,
            exam_year=2025,
            exam_month=5,
            exam_region=None,
            exam_type=None,
            paper_type="真题",
            source_channel=None,
            status="published",
            total_question_count=3,
            total_score=None,
            parsed_version=1,
            review_status="approved",
        )
        session.add(paper)
        session.flush()

        root_review = PaperReviewQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_id=None,
            parent_question_id=None,
            question_uid="RQ-GROUP",
            content_fingerprint="rq-group-fp",
            sort_order=1,
            question_no="（一）",
            node_role="group",
            question_type="mixed",
            source_section_name="综合题",
            source_raw_text="题组",
            group_stem="题组导语",
            material_text="材料",
            stem_text="题组导语",
            options_json=None,
            answer_text=None,
            analysis_text=None,
            difficulty_level=3,
            quality_score=0.95,
            subquestion_count=2,
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
        child_review_2 = PaperReviewQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_id=None,
            parent_question_id=None,
            question_uid="RQ-CHILD-2",
            content_fingerprint="rq-child-fp-2",
            sort_order=3,
            question_no="2",
            node_role="subquestion",
            question_type="single_choice",
            source_section_name="综合题",
            source_raw_text="小问2",
            group_stem="题组导语",
            material_text="材料",
            stem_text="小问2",
            options_json=["A", "B"],
            answer_text="A",
            analysis_text="解析2",
            difficulty_level=3,
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
        child_review_1 = PaperReviewQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_id=None,
            parent_question_id=None,
            question_uid="RQ-CHILD-1",
            content_fingerprint="rq-child-fp-1",
            sort_order=2,
            question_no="1",
            node_role="subquestion",
            question_type="single_choice",
            source_section_name="综合题",
            source_raw_text="小问1",
            group_stem="题组导语",
            material_text="材料",
            stem_text="小问1",
            options_json=["A", "B"],
            answer_text="B",
            analysis_text="解析1",
            difficulty_level=3,
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
        session.add_all([root_review, child_review_2, child_review_1])
        session.flush()

        root_bank = QuestionBankItem(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            parent_question_id=None,
            question_uid="QB-GROUP",
            content_fingerprint="qb-group-fp",
            node_role="group",
            question_type="mixed",
            group_stem="题组导语",
            material_text="材料",
            stem_text="题组导语",
            options_json=None,
            answer_text=None,
            analysis_text=None,
            difficulty_level=3,
            quality_score=0.95,
            status="active",
            source_count=1,
            first_source_question_id=root_review.id,
            created_by=None,
            updated_by=None,
        )
        session.add(root_bank)
        session.flush()

        child_bank_2 = QuestionBankItem(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            parent_question_id=root_bank.id,
            question_uid="QB-CHILD-2",
            content_fingerprint="qb-child-fp-2",
            node_role="subquestion",
            question_type="single_choice",
            group_stem="题组导语",
            material_text="材料",
            stem_text="小问2",
            options_json=["A", "B"],
            answer_text="A",
            analysis_text="解析2",
            difficulty_level=3,
            quality_score=0.9,
            status="active",
            source_count=1,
            first_source_question_id=child_review_2.id,
            created_by=None,
            updated_by=None,
        )
        child_bank_1 = QuestionBankItem(
            tenant_id=tenant.id,
            subject_id=subject.id,
            category_id=category.id,
            parent_question_id=root_bank.id,
            question_uid="QB-CHILD-1",
            content_fingerprint="qb-child-fp-1",
            node_role="subquestion",
            question_type="single_choice",
            group_stem="题组导语",
            material_text="材料",
            stem_text="小问1",
            options_json=["A", "B"],
            answer_text="B",
            analysis_text="解析1",
            difficulty_level=3,
            quality_score=0.9,
            status="active",
            source_count=1,
            first_source_question_id=child_review_1.id,
            created_by=None,
            updated_by=None,
        )
        session.add_all([child_bank_2, child_bank_1])
        session.flush()

        session.add_all(
            [
                QuestionBankSourceLink(
                    tenant_id=tenant.id,
                    bank_question_id=root_bank.id,
                    source_type="paper_review_question",
                    source_question_id=root_review.id,
                    paper_id=paper.id,
                    section_id=None,
                    question_no=root_review.question_no,
                    source_fingerprint=root_review.content_fingerprint,
                    status="active",
                    created_by=None,
                    updated_by=None,
                ),
                QuestionBankSourceLink(
                    tenant_id=tenant.id,
                    bank_question_id=child_bank_2.id,
                    source_type="paper_review_question",
                    source_question_id=child_review_2.id,
                    paper_id=paper.id,
                    section_id=None,
                    question_no=child_review_2.question_no,
                    source_fingerprint=child_review_2.content_fingerprint,
                    status="active",
                    created_by=None,
                    updated_by=None,
                ),
                QuestionBankSourceLink(
                    tenant_id=tenant.id,
                    bank_question_id=child_bank_1.id,
                    source_type="paper_review_question",
                    source_question_id=child_review_1.id,
                    paper_id=paper.id,
                    section_id=None,
                    question_no=child_review_1.question_no,
                    source_fingerprint=child_review_1.content_fingerprint,
                    status="active",
                    created_by=None,
                    updated_by=None,
                ),
            ]
        )
        session.commit()

        result = QuestionBankService(session).list_questions(limit=10, offset=0)

        assert result.total == 1
        assert len(result.items) == 1
        assert [item.question_no for item in result.items[0].subquestions] == ["1", "2"]
    finally:
        session.close()
        engine.dispose()

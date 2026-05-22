from __future__ import annotations

import sys
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.db.base import Base  # noqa: E402
from app.models import (  # noqa: E402
    ExamPaper,
    PaperReviewQuestion,
    QuestionBankItem,
    QuestionBankSourceLink,
    Subject,
    Tenant,
    User,
)
from app.services.question_bank import QuestionBankService  # noqa: E402


class QuestionBankDeleteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.session: Session = self.SessionLocal()

        self.tenant = Tenant(code="default", name="Default")
        self.session.add(self.tenant)
        self.session.flush()

        self.subject = Subject(
            tenant_id=self.tenant.id,
            code="subject",
            name="Subject",
            created_by=None,
            updated_by=None,
        )
        self.session.add(self.subject)

        self.user = User(
            tenant_id=self.tenant.id,
            username="admin",
            password_hash="hash",
            display_name="Admin",
            created_by=None,
            updated_by=None,
        )
        self.session.add(self.user)
        self.session.flush()

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_delete_question_removes_bank_item_and_source_links_but_keeps_review_question(self) -> None:
        paper = ExamPaper(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            paper_name="2026 真题",
            paper_type="真题",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(paper)
        self.session.flush()

        review_question = PaperReviewQuestion(
            tenant_id=self.tenant.id,
            paper_id=paper.id,
            section_id=None,
            question_uid="PRQ-test-1",
            content_fingerprint="review-fp-1",
            sort_order=1,
            question_no="1",
            question_type="single_choice",
            source_section_name="单选题",
            source_raw_text="1. 原始题干\nA. 选项1\nB. 选项2\n答案：A\n解析：解析",
            stem_text="1. 原始题干",
            options_json=["选项1", "选项2"],
            answer_text="A",
            analysis_text="解析",
            difficulty_level=2,
            quality_score=0.95,
            subquestion_count=0,
            quality_issues_json=[],
            parse_status="parsed",
            review_status="approved",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(review_question)
        self.session.flush()

        bank_question = QuestionBankItem(
            tenant_id=self.tenant.id,
            subject_id=self.subject.id,
            category_id=None,
            question_uid="QB-test-1",
            content_fingerprint="bank-fp-1",
            question_type="single_choice",
            stem_text="标准题干",
            options_json=["A. 选项1", "B. 选项2"],
            answer_text="A",
            analysis_text="解析",
            difficulty_level=2,
            quality_score=0.95,
            status="active",
            source_count=1,
            first_source_question_id=review_question.id,
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(bank_question)
        self.session.flush()

        source_link = QuestionBankSourceLink(
            tenant_id=self.tenant.id,
            bank_question_id=bank_question.id,
            source_type="paper_review_question",
            source_question_id=review_question.id,
            paper_id=paper.id,
            section_id=None,
            question_no="1",
            source_fingerprint="review-fp-1",
            status="active",
            created_by=self.user.id,
            updated_by=self.user.id,
        )
        self.session.add(source_link)
        self.session.commit()
        source_link_id = source_link.id

        result = QuestionBankService(self.session).delete_question(bank_question.id)

        self.assertTrue(result.deleted)
        self.assertEqual(result.id, bank_question.id)
        self.assertEqual(result.question_uid, "QB-test-1")
        self.assertEqual(result.removed_source_link_count, 1)

        verify_session = self.SessionLocal()
        try:
            self.assertIsNone(verify_session.get(QuestionBankItem, bank_question.id))
            self.assertIsNone(verify_session.get(QuestionBankSourceLink, source_link_id))

            persisted_review_question = verify_session.get(PaperReviewQuestion, review_question.id)
            self.assertIsNotNone(persisted_review_question)
            assert persisted_review_question is not None
            self.assertEqual(persisted_review_question.review_status, "approved")
        finally:
            verify_session.close()


if __name__ == "__main__":
    unittest.main()

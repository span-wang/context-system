from __future__ import annotations

from sqlalchemy import func, select

from app.models import (
    AnalysisJob,
    AnalysisReport,
    Asset,
    Chapter,
    ExamPaper,
    ExamQuestion,
    Favorite,
    KnowledgePoint,
    KnowledgePointAlias,
    KnowledgePointRelation,
    MasterySnapshot,
    MockExam,
    MockExamQuestion,
    PaperSection,
    PracticeAnswer,
    PracticeSession,
    PracticeSet,
    PracticeSetQuestion,
    QuestionBankItem,
    QuestionKnowledgeLink,
    QuestionSourceLink,
    ReviewTask,
    Subject,
    SubjectCategory,
    Tenant,
    User,
    WrongBookItem,
)
from app.repositories.base import Repository


class KnowledgeRepository(Repository):
    def list_subjects(self) -> list[Subject]:
        return list(self.session.scalars(select(Subject).order_by(Subject.id.asc())))

    def get_default_tenant(self, code: str) -> Tenant | None:
        return self.session.scalar(select(Tenant).where(Tenant.code == code))

    def get_default_user(self, tenant_id: int) -> User | None:
        stmt = select(User).where(User.tenant_id == tenant_id).order_by(User.id.asc())
        return self.session.scalar(stmt)

    def get_subject(self, subject_id: int) -> Subject | None:
        return self.session.get(Subject, subject_id)

    def create_subject(self, subject: Subject) -> Subject:
        self.session.add(subject)
        self.session.flush()
        return subject

    def list_categories(self, subject_id: int | None = None) -> list[SubjectCategory]:
        stmt = select(SubjectCategory)
        if subject_id is not None:
            stmt = stmt.where(SubjectCategory.subject_id == subject_id)
        stmt = stmt.order_by(SubjectCategory.sort_order.asc(), SubjectCategory.id.asc())
        return list(self.session.scalars(stmt))

    def get_category(self, category_id: int) -> SubjectCategory | None:
        return self.session.get(SubjectCategory, category_id)

    def create_category(self, category: SubjectCategory) -> SubjectCategory:
        self.session.add(category)
        self.session.flush()
        return category

    def list_chapters(self, subject_id: int | None = None, category_id: int | None = None) -> list[Chapter]:
        stmt = select(Chapter)
        if subject_id is not None:
            stmt = stmt.where(Chapter.subject_id == subject_id)
        if category_id is not None:
            stmt = stmt.where(Chapter.category_id == category_id)
        stmt = stmt.order_by(Chapter.sort_order.asc(), Chapter.id.asc())
        return list(self.session.scalars(stmt))

    def get_chapter(self, chapter_id: int) -> Chapter | None:
        return self.session.get(Chapter, chapter_id)

    def chapter_has_children(self, chapter_id: int) -> bool:
        return (
            self.session.scalar(select(Chapter.id).where(Chapter.parent_id == chapter_id).limit(1))
            is not None
        )

    def create_chapter(self, chapter: Chapter) -> Chapter:
        self.session.add(chapter)
        self.session.flush()
        return chapter

    def list_knowledge_points(self, subject_id: int | None = None) -> list[KnowledgePoint]:
        stmt = select(KnowledgePoint)
        if subject_id is not None:
            stmt = stmt.where(KnowledgePoint.subject_id == subject_id)
        stmt = stmt.order_by(KnowledgePoint.sort_order.asc(), KnowledgePoint.id.asc())
        return list(self.session.scalars(stmt))

    def get_knowledge_point(self, point_id: int) -> KnowledgePoint | None:
        return self.session.get(KnowledgePoint, point_id)

    def create_knowledge_point(self, point: KnowledgePoint) -> KnowledgePoint:
        self.session.add(point)
        self.session.flush()
        return point

    def list_textbooks(self, subject_id: int | None = None) -> list[Asset]:
        stmt = select(Asset).where(Asset.source_type == "textbook")
        if subject_id is not None:
            stmt = stmt.where(Asset.subject_id == subject_id)
        stmt = stmt.order_by(Asset.created_at.desc(), Asset.id.desc())
        return list(self.session.scalars(stmt))

    def get_textbook(self, textbook_id: int) -> Asset | None:
        asset = self.session.get(Asset, textbook_id)
        if asset is None or asset.source_type != "textbook":
            return None
        return asset

    def update_textbook(self, textbook: Asset, data: dict[str, object]) -> Asset:
        for key, value in data.items():
            setattr(textbook, key, value)
        self.session.flush()
        return textbook

    def subject_dependency_counts(self, subject_id: int) -> dict[str, int]:
        models = {
            "类目": SubjectCategory,
            "章节": Chapter,
            "知识点": KnowledgePoint,
            "素材/教材": Asset,
            "试卷": ExamPaper,
            "原始题": ExamQuestion,
            "题库题": QuestionBankItem,
            "分析报告": AnalysisReport,
            "分析任务": AnalysisJob,
            "练习集": PracticeSet,
            "模考": MockExam,
            "练习记录": PracticeSession,
            "掌握度记录": MasterySnapshot,
        }
        counts: dict[str, int] = {}
        for label, model in models.items():
            count = int(self.session.scalar(select(func.count()).select_from(model).where(model.subject_id == subject_id)) or 0)
            if count:
                counts[label] = count
        return counts

    def delete_subject(self, subject_id: int) -> None:
        self.session.query(Subject).filter(Subject.id == subject_id).delete(synchronize_session=False)

    def descendant_chapter_ids(self, chapter_id: int) -> list[int]:
        all_chapters = self.session.execute(select(Chapter.id, Chapter.parent_id)).all()
        children_by_parent: dict[int | None, list[int]] = {}
        for child_id, parent_id in all_chapters:
            children_by_parent.setdefault(parent_id, []).append(child_id)

        result: list[int] = []
        pending = [chapter_id]
        while pending:
            current = pending.pop()
            result.append(current)
            pending.extend(children_by_parent.get(current, []))
        return result

    def unbind_points_from_chapters(self, chapter_ids: list[int]) -> int:
        if not chapter_ids:
            return 0
        return int(
            self.session.query(KnowledgePoint)
            .filter(KnowledgePoint.chapter_id.in_(chapter_ids))
            .update({KnowledgePoint.chapter_id: None}, synchronize_session=False)
        )

    def delete_chapters(self, chapter_ids: list[int]) -> int:
        if not chapter_ids:
            return 0
        return int(
            self.session.query(Chapter)
            .filter(Chapter.id.in_(chapter_ids))
            .delete(synchronize_session=False)
        )

    def delete_knowledge_points(self, point_ids: list[int]) -> int:
        if not point_ids:
            return 0
        self.session.query(QuestionKnowledgeLink).filter(
            QuestionKnowledgeLink.knowledge_point_id.in_(point_ids)
        ).delete(synchronize_session=False)
        self.session.query(MasterySnapshot).filter(
            MasterySnapshot.knowledge_point_id.in_(point_ids)
        ).delete(synchronize_session=False)
        self.session.query(KnowledgePointAlias).filter(
            KnowledgePointAlias.knowledge_point_id.in_(point_ids)
        ).delete(synchronize_session=False)
        self.session.query(KnowledgePointRelation).filter(
            KnowledgePointRelation.from_kp_id.in_(point_ids) | KnowledgePointRelation.to_kp_id.in_(point_ids)
        ).delete(synchronize_session=False)
        return int(
            self.session.query(KnowledgePoint)
            .filter(KnowledgePoint.id.in_(point_ids))
            .delete(synchronize_session=False)
        )

    def point_ids_by_chapter_ids(self, chapter_ids: list[int]) -> list[int]:
        if not chapter_ids:
            return []
        return [
            int(point_id)
            for point_id in self.session.scalars(
                select(KnowledgePoint.id).where(KnowledgePoint.chapter_id.in_(chapter_ids))
            )
        ]

    def delete_subject_tree(self, subject_id: int) -> dict[str, int]:
        chapter_ids = [int(chapter_id) for chapter_id in self.session.scalars(select(Chapter.id).where(Chapter.subject_id == subject_id))]
        point_ids = [int(point_id) for point_id in self.session.scalars(select(KnowledgePoint.id).where(KnowledgePoint.subject_id == subject_id))]
        paper_ids = [int(paper_id) for paper_id in self.session.scalars(select(ExamPaper.id).where(ExamPaper.subject_id == subject_id))]
        question_ids = [int(question_id) for question_id in self.session.scalars(select(ExamQuestion.id).where(ExamQuestion.subject_id == subject_id))]
        bank_question_ids = [int(item_id) for item_id in self.session.scalars(select(QuestionBankItem.id).where(QuestionBankItem.subject_id == subject_id))]
        practice_set_ids = [int(item_id) for item_id in self.session.scalars(select(PracticeSet.id).where(PracticeSet.subject_id == subject_id))]
        mock_exam_ids = [int(item_id) for item_id in self.session.scalars(select(MockExam.id).where(MockExam.subject_id == subject_id))]
        practice_session_ids = [int(item_id) for item_id in self.session.scalars(select(PracticeSession.id).where(PracticeSession.subject_id == subject_id))]

        if practice_session_ids:
            self.session.query(PracticeAnswer).filter(PracticeAnswer.session_id.in_(practice_session_ids)).delete(synchronize_session=False)
            self.session.query(WrongBookItem).filter(WrongBookItem.source_session_id.in_(practice_session_ids)).delete(synchronize_session=False)
        if bank_question_ids:
            self.session.query(Favorite).filter(Favorite.bank_question_id.in_(bank_question_ids)).delete(synchronize_session=False)
            self.session.query(WrongBookItem).filter(WrongBookItem.bank_question_id.in_(bank_question_ids)).delete(synchronize_session=False)
            self.session.query(PracticeAnswer).filter(PracticeAnswer.bank_question_id.in_(bank_question_ids)).delete(synchronize_session=False)
            self.session.query(PracticeSetQuestion).filter(PracticeSetQuestion.bank_question_id.in_(bank_question_ids)).delete(synchronize_session=False)
            self.session.query(MockExamQuestion).filter(MockExamQuestion.bank_question_id.in_(bank_question_ids)).delete(synchronize_session=False)
            self.session.query(QuestionSourceLink).filter(QuestionSourceLink.bank_question_id.in_(bank_question_ids)).delete(synchronize_session=False)
            self.session.query(QuestionBankItem).filter(QuestionBankItem.id.in_(bank_question_ids)).delete(synchronize_session=False)
        if question_ids:
            string_question_ids = [str(question_id) for question_id in question_ids]
            self.session.query(QuestionKnowledgeLink).filter(QuestionKnowledgeLink.question_id.in_(question_ids)).delete(synchronize_session=False)
            self.session.query(QuestionSourceLink).filter(QuestionSourceLink.exam_question_id.in_(question_ids)).delete(synchronize_session=False)
            self.session.query(ReviewTask).filter(
                ReviewTask.target_type.in_(("exam_question", "question")),
                ReviewTask.target_id.in_(string_question_ids),
            ).delete(synchronize_session=False)
            self.session.query(ExamQuestion).filter(ExamQuestion.id.in_(question_ids)).delete(synchronize_session=False)
        if paper_ids:
            string_paper_ids = [str(paper_id) for paper_id in paper_ids]
            self.session.query(PaperSection).filter(PaperSection.paper_id.in_(paper_ids)).delete(synchronize_session=False)
            self.session.query(ReviewTask).filter(
                ReviewTask.target_type.in_(("paper", "exam_paper")),
                ReviewTask.target_id.in_(string_paper_ids),
            ).delete(synchronize_session=False)
            self.session.query(ExamPaper).filter(ExamPaper.id.in_(paper_ids)).delete(synchronize_session=False)
        if practice_session_ids:
            self.session.query(PracticeSession).filter(PracticeSession.id.in_(practice_session_ids)).delete(synchronize_session=False)
        if practice_set_ids:
            self.session.query(PracticeSetQuestion).filter(PracticeSetQuestion.practice_set_id.in_(practice_set_ids)).delete(synchronize_session=False)
            self.session.query(PracticeSet).filter(PracticeSet.id.in_(practice_set_ids)).delete(synchronize_session=False)
        if mock_exam_ids:
            self.session.query(MockExamQuestion).filter(MockExamQuestion.mock_exam_id.in_(mock_exam_ids)).delete(synchronize_session=False)
            self.session.query(MockExam).filter(MockExam.id.in_(mock_exam_ids)).delete(synchronize_session=False)
        self.session.query(AnalysisJob).filter(AnalysisJob.subject_id == subject_id).delete(synchronize_session=False)
        self.session.query(AnalysisReport).filter(AnalysisReport.subject_id == subject_id).delete(synchronize_session=False)
        self.session.query(Asset).filter(Asset.subject_id == subject_id).delete(synchronize_session=False)
        self.session.query(MasterySnapshot).filter(MasterySnapshot.subject_id == subject_id).delete(synchronize_session=False)
        removed_points = self.delete_knowledge_points(point_ids)
        removed_chapters = self.delete_chapters(chapter_ids)
        self.session.query(SubjectCategory).filter(SubjectCategory.subject_id == subject_id).delete(synchronize_session=False)
        self.session.query(Subject).filter(Subject.id == subject_id).delete(synchronize_session=False)
        return {
            "removed_chapter_count": removed_chapters,
            "removed_point_count": removed_points,
            "removed_paper_count": len(paper_ids),
            "removed_question_count": len(question_ids),
            "removed_bank_question_count": len(bank_question_ids),
        }

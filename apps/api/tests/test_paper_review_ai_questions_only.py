from __future__ import annotations

import sys
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[2]
API_ROOT = ROOT / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.models import ExamPaper, PaperReviewQuestion, PaperSection, Tenant
from app.models.base import Base
from app.models.question_bank import QuestionBankItem, QuestionBankSourceLink
from app.services.paper_review import PaperReviewService
from app.services.paper_review_ai import normalize_analysis
from app.services.paper_review_standardize_jobs import start_paper_review_ai_standardize_jobs
from app.services.papers import _to_parsed_question_payload


def test_normalize_analysis_flattens_structured_payload() -> None:
    assert normalize_analysis(
        {
            "考察知识点": "固定资产处置的会计处理。",
            "步骤": ["先确认处置价款。", "再结转账面价值。"],
        }
    ) == (
        "考察知识点：固定资产处置的会计处理。\n\n"
        "步骤：\n"
        "1. 先确认处置价款。\n"
        "2. 再结转账面价值。"
    )


def test_to_parsed_question_payload_flattens_structured_analysis() -> None:
    payload = _to_parsed_question_payload(
        {
            "question_no": "1",
            "node_role": "standalone",
            "question_type": "single_choice",
            "stem_text": "测试题干",
            "options": ["A. 选项一", "B. 选项二"],
            "answer_text": "A",
            "analysis_text": {
                "考察知识点": "收入确认。",
                "步骤": ["先识别履约义务。", "再判断控制权转移。"],
            },
            "difficulty_level": 3,
            "quality_score": 0.9,
            "subquestion_count": 0,
            "quality_issues": [],
            "source_raw_text": "1. 测试题干\nA. 选项一\nB. 选项二\n答案：A",
        }
    )

    assert payload is not None
    assert payload.analysis_text == (
        "考察知识点：收入确认。\n\n"
        "步骤：\n"
        "1. 先识别履约义务。\n"
        "2. 再判断控制权转移。"
    )


def test_sync_questions_from_sections_uses_ai_questions_only() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = session_factory()
    try:
        tenant = Tenant(code="tenant-review-ai", name="Tenant Review AI", status="active", plan_type="professional")
        session.add(tenant)
        session.flush()

        paper = ExamPaper(
            tenant_id=tenant.id,
            subject_id=None,
            category_id=None,
            asset_id=None,
            paper_name="AI 切题试卷",
            paper_code=None,
            exam_year=2026,
            exam_month=5,
            exam_region=None,
            exam_type=None,
            paper_type="模拟题",
            source_channel=None,
            status="published",
            total_question_count=0,
            total_score=None,
            parsed_version=1,
            review_status="pending",
        )
        session.add(paper)
        session.flush()

        section = PaperSection(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_name="单项选择题",
            question_type="single_choice",
            start_no=1,
            end_no=1,
            score=None,
            sort_order=1,
            created_by=None,
            updated_by=None,
        )
        session.add(section)
        session.flush()

        service = PaperReviewService(session)
        result = service.sync_questions_from_sections(
            paper_id=paper.id,
            section_payloads=[
                {
                    "section_id": section.id,
                    "title": "单项选择题",
                    "section_type": "single_choice",
                    "sort_order": 1,
                    "questions": [
                        {
                            "order": 1,
                            "question_no": "1",
                            "question_type": "single_choice",
                            "stem_text": "AI 结构化题干",
                            "options": ["A. 选项一", "B. 选项二"],
                            "answer_text": "B",
                            "analysis_text": "AI 结构化解析",
                            "subquestion_count": 0,
                            "quality_score": 0.92,
                            "quality_issues": [],
                            "source_raw_text": "1. AI 结构化题干\nA. 选项一\nB. 选项二\n答案：B\n解析：AI 结构化解析",
                        }
                    ],
                }
            ],
            operator_id=None,
            commit=False,
        )

        assert result.imported_count == 1
        question = service.repository.list_questions(paper.id)[0]
        assert question.section_id == section.id
        assert question.stem_text == "AI 结构化题干"
        assert question.answer_text == "B"
        assert question.analysis_text == "AI 结构化解析"
        assert question.options_json == ["选项一", "选项二"]
    finally:
        session.close()
        engine.dispose()


def test_sync_questions_from_sections_flattens_structured_analysis_payload() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = session_factory()
    try:
        tenant = Tenant(code="tenant-review-analysis", name="Tenant Review Analysis", status="active", plan_type="professional")
        session.add(tenant)
        session.flush()

        paper = ExamPaper(
            tenant_id=tenant.id,
            subject_id=None,
            category_id=None,
            asset_id=None,
            paper_name="结构化解析试卷",
            paper_code=None,
            exam_year=2026,
            exam_month=5,
            exam_region=None,
            exam_type=None,
            paper_type="模拟题",
            source_channel=None,
            status="published",
            total_question_count=0,
            total_score=None,
            parsed_version=1,
            review_status="pending",
        )
        session.add(paper)
        session.flush()

        section = PaperSection(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_name="单项选择题",
            question_type="single_choice",
            start_no=1,
            end_no=1,
            score=None,
            sort_order=1,
            created_by=None,
            updated_by=None,
        )
        session.add(section)
        session.flush()

        service = PaperReviewService(session)
        result = service.sync_questions_from_sections(
            paper_id=paper.id,
            section_payloads=[
                {
                    "section_id": section.id,
                    "title": "单项选择题",
                    "section_type": "single_choice",
                    "sort_order": 1,
                    "questions": [
                        {
                            "order": 1,
                            "question_no": "1",
                            "question_type": "single_choice",
                            "stem_text": "AI 结构化题干",
                            "options": ["A. 选项一", "B. 选项二"],
                            "answer_text": "B",
                            "analysis_text": {
                                "考察知识点": "收入确认。",
                                "步骤": ["先识别履约义务。", "再判断控制权转移。"],
                            },
                            "subquestion_count": 0,
                            "quality_score": 0.92,
                            "quality_issues": [],
                        }
                    ],
                }
            ],
            operator_id=None,
            commit=False,
        )

        assert result.imported_count == 1
        question = service.repository.list_questions(paper.id)[0]
        assert question.analysis_text == (
            "考察知识点:收入确认。\n\n"
            "步骤:\n"
            "1. 先识别履约义务。\n"
            "2. 再判断控制权转移。"
        )
        assert "{'考察知识点'" not in (question.source_raw_text or "")
        assert "步骤:\n1. 先识别履约义务。" in (question.source_raw_text or "")
    finally:
        session.close()
        engine.dispose()


def test_start_paper_review_ai_standardize_jobs_batches_by_root_question(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = session_factory()
    try:
        tenant = Tenant(code="tenant-review-standardize", name="Tenant Review Standardize", status="active", plan_type="professional")
        session.add(tenant)
        session.flush()

        paper = ExamPaper(
            tenant_id=tenant.id,
            subject_id=None,
            category_id=None,
            asset_id=None,
            paper_name="异步解题试卷",
            paper_code=None,
            exam_year=2026,
            exam_month=5,
            exam_region=None,
            exam_type=None,
            paper_type="模拟题",
            source_channel=None,
            status="published",
            total_question_count=0,
            total_score=None,
            parsed_version=1,
            review_status="pending",
        )
        session.add(paper)
        session.flush()

        section = PaperSection(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_name="综合题",
            question_type="mixed",
            start_no=1,
            end_no=13,
            score=None,
            sort_order=1,
            created_by=None,
            updated_by=None,
        )
        session.add(section)
        session.flush()

        standalone_questions = [
            {
                "order": index,
                "question_no": str(index),
                "question_type": "single_choice",
                "stem_text": f"第 {index} 题题干",
                "options": ["A. 选项一", "B. 选项二"],
                "answer_text": "",
                "analysis_text": "",
                "subquestion_count": 0,
                "quality_score": 0.9,
                "quality_issues": [],
            }
            for index in range(1, 11)
        ]
        group_question = {
            "order": 11,
            "question_no": "11-12",
            "node_role": "group",
            "question_type": "material_analysis",
            "group_stem": "阅读下面材料，回答问题。",
            "material_text": "这是共用材料。",
            "stem_text": "阅读下面材料，回答问题。",
            "options": [],
            "answer_text": "",
            "analysis_text": "",
            "subquestion_count": 2,
            "quality_score": 0.88,
            "quality_issues": [],
            "subquestions": [
                {
                    "order": 12,
                    "question_no": "11",
                    "node_role": "subquestion",
                    "question_type": "short_answer",
                    "stem_text": "概括材料中心思想。",
                    "options": [],
                    "answer_text": "",
                    "analysis_text": "",
                    "subquestion_count": 0,
                    "quality_score": 0.86,
                    "quality_issues": [],
                },
                {
                    "order": 13,
                    "question_no": "12",
                    "node_role": "subquestion",
                    "question_type": "short_answer",
                    "stem_text": "分析作者观点。",
                    "options": [],
                    "answer_text": "",
                    "analysis_text": "",
                    "subquestion_count": 0,
                    "quality_score": 0.86,
                    "quality_issues": [],
                },
            ],
        }
        solved_question = {
            "order": 14,
            "question_no": "13",
            "question_type": "single_choice",
            "stem_text": "这道题原文已带答案与解析。",
            "options": ["A. 选项一", "B. 选项二"],
            "answer_text": "A",
            "analysis_text": "原文已有解析。",
            "subquestion_count": 0,
            "quality_score": 0.93,
            "quality_issues": [],
        }

        PaperReviewService(session).sync_questions_from_sections(
            paper_id=paper.id,
            section_payloads=[
                {
                    "section_id": section.id,
                    "title": "综合题",
                    "section_type": "mixed",
                    "sort_order": 1,
                    "questions": [*standalone_questions, group_question, solved_question],
                }
            ],
            operator_id=None,
            commit=True,
        )

        monkeypatch.setattr("app.services.paper_review_standardize_jobs.threading.Thread.start", lambda self: None)
        jobs = start_paper_review_ai_standardize_jobs(session, paper_id=paper.id, only_missing_solutions=True)

        assert len(jobs) == 2
        scopes = [job.scope_config_json or {} for job in jobs]
        assert [int(scope.get("requested_count") or 0) for scope in scopes] == [10, 1]

        root_questions = [question for question in PaperReviewService(session).repository.list_questions(paper.id) if question.parent_question_id is None]
        group_root = next(question for question in root_questions if question.node_role == "group")
        solved_root = next(question for question in root_questions if question.question_no == "13")
        batched_ids = [question_id for scope in scopes for question_id in (scope.get("question_ids") or [])]

        assert len(batched_ids) == 11
        assert group_root.id in batched_ids
        assert solved_root.id not in batched_ids
    finally:
        session.close()
        engine.dispose()


def test_sync_questions_from_sections_rejects_rule_blocks_payload() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = session_factory()
    try:
        tenant = Tenant(code="tenant-review-invalid", name="Tenant Review Invalid", status="active", plan_type="professional")
        session.add(tenant)
        session.flush()

        paper = ExamPaper(
            tenant_id=tenant.id,
            subject_id=None,
            category_id=None,
            asset_id=None,
            paper_name="无效块格式试卷",
            paper_code=None,
            exam_year=2026,
            exam_month=5,
            exam_region=None,
            exam_type=None,
            paper_type="模拟题",
            source_channel=None,
            status="published",
            total_question_count=0,
            total_score=None,
            parsed_version=1,
            review_status="pending",
        )
        session.add(paper)
        session.flush()

        service = PaperReviewService(session)
        try:
            service.sync_questions_from_sections(
                paper_id=paper.id,
                section_payloads=[
                    {
                        "title": "单项选择题",
                        "section_type": "single_choice",
                        "sort_order": 1,
                        "blocks": [
                            {
                                "raw_text": "1. 规则题干\nA. 选项一\nB. 选项二\n答案：A",
                            }
                        ],
                    }
                ],
                operator_id=None,
                commit=False,
            )
            assert False, "expected HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 422
            assert "只支持 AI questions" in str(exc.detail)
    finally:
        session.close()
        engine.dispose()


def test_get_workspace_backfills_section_id_from_section_name_for_legacy_questions() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = session_factory()
    try:
        tenant = Tenant(code="tenant-review-legacy", name="Tenant Review Legacy", status="active", plan_type="professional")
        session.add(tenant)
        session.flush()

        paper = ExamPaper(
            tenant_id=tenant.id,
            subject_id=None,
            category_id=None,
            asset_id=None,
            paper_name="历史试卷",
            paper_code=None,
            exam_year=2026,
            exam_month=5,
            exam_region=None,
            exam_type=None,
            paper_type="模拟题",
            source_channel=None,
            status="published",
            total_question_count=1,
            total_score=None,
            parsed_version=1,
            review_status="pending",
        )
        session.add(paper)
        session.flush()

        section = PaperSection(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_name="单项选择题",
            question_type="single_choice",
            start_no=1,
            end_no=1,
            score=None,
            sort_order=1,
            created_by=None,
            updated_by=None,
        )
        session.add(section)
        session.flush()

        session.execute(
            PaperReviewQuestion.__table__.insert().values(
                tenant_id=tenant.id,
                paper_id=paper.id,
                section_id=None,
                parent_question_id=None,
                question_uid="LEGACY-RQ-1",
                content_fingerprint="legacy-fingerprint-1",
                sort_order=1,
                question_no="1",
                node_role="standalone",
                question_type="single_choice",
                source_section_name="单项选择题",
                source_raw_text="1. 历史题干",
                group_stem=None,
                material_text=None,
                stem_text="历史题干",
                options_json=["A. 选项一", "B. 选项二"],
                answer_text="A",
                analysis_text="历史解析",
                difficulty_level=3,
                quality_score=0.9,
                subquestion_count=0,
                quality_issues_json=[],
                parse_status="parsed",
                review_status="pending",
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
        )
        session.commit()

        workspace = PaperReviewService(session).get_workspace(paper.id)

        assert workspace.sections[0].id == section.id
        assert workspace.questions[0].section_id == section.id
        assert workspace.questions[0].source_section_name == "单项选择题"
        assert workspace.questions[0].options_json == ["选项一", "选项二"]
    finally:
        session.close()
        engine.dispose()


def test_batch_update_review_syncs_group_and_subquestions() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = session_factory()
    try:
        tenant = Tenant(code="tenant-review-batch", name="Tenant Review Batch", status="active", plan_type="professional")
        session.add(tenant)
        session.flush()

        paper = ExamPaper(
            tenant_id=tenant.id,
            subject_id=None,
            category_id=None,
            asset_id=None,
            paper_name="批量审核试卷",
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
            review_status="pending",
        )
        session.add(paper)
        session.flush()

        root = PaperReviewQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_id=None,
            parent_question_id=None,
            question_uid="GROUP-1",
            content_fingerprint="group-fp-1",
            sort_order=1,
            question_no="1",
            node_role="group",
            question_type="material_analysis",
            source_section_name="综合题",
            source_raw_text="题组原文",
            group_stem="阅读材料",
            material_text="材料内容",
            stem_text="阅读材料",
            options_json=None,
            answer_text=None,
            analysis_text=None,
            difficulty_level=3,
            quality_score=0.8,
            subquestion_count=2,
            quality_issues_json=[],
            parse_status="parsed",
            review_status="pending",
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
        session.add(root)
        session.flush()

        child1 = PaperReviewQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_id=None,
            parent_question_id=root.id,
            question_uid="GROUP-1-1",
            content_fingerprint="group-fp-1-1",
            sort_order=2,
            question_no="1-1",
            node_role="subquestion",
            question_type="short_answer",
            source_section_name="综合题",
            source_raw_text="小问一",
            group_stem="阅读材料",
            material_text="材料内容",
            stem_text="问题一",
            options_json=None,
            answer_text="答案一",
            analysis_text="解析一",
            difficulty_level=3,
            quality_score=0.8,
            subquestion_count=0,
            quality_issues_json=[],
            parse_status="parsed",
            review_status="pending",
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
        child2 = PaperReviewQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_id=None,
            parent_question_id=root.id,
            question_uid="GROUP-1-2",
            content_fingerprint="group-fp-1-2",
            sort_order=3,
            question_no="1-2",
            node_role="subquestion",
            question_type="short_answer",
            source_section_name="综合题",
            source_raw_text="小问二",
            group_stem="阅读材料",
            material_text="材料内容",
            stem_text="问题二",
            options_json=None,
            answer_text="答案二",
            analysis_text="解析二",
            difficulty_level=3,
            quality_score=0.8,
            subquestion_count=0,
            quality_issues_json=[],
            parse_status="parsed",
            review_status="pending",
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
        session.add_all([child1, child2])
        session.commit()

        result = PaperReviewService(session).batch_update_review([root.id], "approved", "批量确认通过")

        assert result.requested_count == 1
        assert result.success_count == 1
        assert result.failed_count == 0
        assert result.questions[0].review_status == "approved"
        assert result.questions[0].review_note == "批量确认通过"
        assert len(result.questions[0].subquestions) == 2
        assert all(item.review_status == "approved" for item in result.questions[0].subquestions)
        assert all(item.review_note == "批量确认通过" for item in result.questions[0].subquestions)
    finally:
        session.close()
        engine.dispose()


def test_batch_update_review_reports_specific_group_sync_failure_reason() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)
    session = session_factory()
    try:
        tenant = Tenant(code="tenant-review-batch-failure", name="Tenant Review Batch Failure", status="active", plan_type="professional")
        session.add(tenant)
        session.flush()

        paper = ExamPaper(
            tenant_id=tenant.id,
            subject_id=None,
            category_id=None,
            asset_id=None,
            paper_name="批量审核失败试卷",
            paper_code=None,
            exam_year=2026,
            exam_month=5,
            exam_region=None,
            exam_type=None,
            paper_type="真题",
            source_channel=None,
            status="published",
            total_question_count=1,
            total_score=None,
            parsed_version=1,
            review_status="pending",
        )
        session.add(paper)
        session.flush()

        root = PaperReviewQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_id=None,
            parent_question_id=None,
            question_uid="GROUP-FAIL-1",
            content_fingerprint="group-fail-fp-1",
            sort_order=1,
            question_no="（一）",
            node_role="group",
            question_type="material_analysis",
            source_section_name="综合题",
            source_raw_text="题组原文",
            group_stem="阅读材料",
            material_text="材料内容",
            stem_text="阅读材料",
            options_json=None,
            answer_text=None,
            analysis_text=None,
            difficulty_level=3,
            quality_score=0.8,
            subquestion_count=1,
            quality_issues_json=[],
            parse_status="parsed",
            review_status="pending",
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
        session.add(root)
        session.flush()

        child = PaperReviewQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            section_id=None,
            parent_question_id=root.id,
            question_uid="GROUP-FAIL-1-1",
            content_fingerprint="group-fail-fp-1-1",
            sort_order=2,
            question_no="5",
            node_role="subquestion",
            question_type="short_answer",
            source_section_name="综合题",
            source_raw_text="小问一",
            group_stem="阅读材料",
            material_text="材料内容",
            stem_text="问题一",
            options_json=None,
            answer_text="答案一",
            analysis_text="解析一",
            difficulty_level=3,
            quality_score=0.8,
            subquestion_count=0,
            quality_issues_json=[],
            parse_status="parsed",
            review_status="pending",
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
        session.add(child)
        session.flush()

        bank_root = QuestionBankItem(
            tenant_id=tenant.id,
            subject_id=None,
            category_id=None,
            parent_question_id=None,
            question_uid="QB-GROUP-FAIL-1",
            content_fingerprint="group-fail-fp-1",
            node_role="group",
            question_type="material_analysis",
            group_stem="阅读材料",
            material_text="材料内容",
            stem_text="阅读材料",
            options_json=None,
            answer_text=None,
            analysis_text=None,
            difficulty_level=3,
            quality_score=0.8,
            status="active",
            source_count=1,
            first_source_question_id=root.id,
            created_by=None,
            updated_by=None,
        )
        session.add(bank_root)
        session.flush()

        session.add(
            QuestionBankSourceLink(
                tenant_id=tenant.id,
                bank_question_id=bank_root.id,
                source_type="paper_review_question",
                source_question_id=root.id,
                paper_id=paper.id,
                section_id=None,
                question_no=root.question_no,
                source_fingerprint=root.content_fingerprint,
                status="active",
                created_by=None,
                updated_by=None,
            )
        )
        session.commit()

        result = PaperReviewService(session).batch_update_review([root.id], "approved", "批量确认通过")

        assert result.requested_count == 1
        assert result.success_count == 0
        assert result.failed_count == 1
        assert result.failures[0].message == "题组 （一）：题组下仍有子问未人工审核通过（未通过子问：5）"
        assert "失败明细：题组 （一）：题组下仍有子问未人工审核通过（未通过子问：5）" in result.message
    finally:
        session.close()
        engine.dispose()

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text

from app.core.config import PROJECT_ROOT, get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.models.legacy import LEGACY_TABLE_NAMES
from app.models import (
    AnalysisJob,
    AnalysisReport,
    Asset,
    Chapter,
    ExamPaper,
    ExamQuestion,
    Favorite,
    KnowledgePoint,
    LearnerProfile,
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
    Role,
    Subject,
    SubjectCategory,
    Tenant,
    User,
    UserRole,
    WrongBookItem,
)


def _get_alembic_config() -> Config:
    config_path = PROJECT_ROOT / "apps" / "api" / "alembic.ini"
    script_location = PROJECT_ROOT / "apps" / "api" / "alembic"
    alembic_config = Config(str(config_path))
    alembic_config.set_main_option("script_location", str(script_location))
    return alembic_config


def get_current_revision() -> str | None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "alembic_version" not in existing_tables:
        return None
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar()


def get_head_revision() -> str | None:
    alembic_config = _get_alembic_config()
    script = ScriptDirectory.from_config(alembic_config)
    return script.get_current_head()


def get_migration_status() -> dict[str, object]:
    settings = get_settings()
    alembic_config = _get_alembic_config()
    script = ScriptDirectory.from_config(alembic_config)
    head_revision = script.get_current_head()
    managed_tables = set(Base.metadata.tables.keys())
    platform_tables = managed_tables - LEGACY_TABLE_NAMES
    database_ping_ok = False
    existing_tables: set[str] = set()
    current_revision: str | None = None
    status = "unknown"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_ping_ok = True
    except Exception:
        database_ping_ok = False

    if database_ping_ok:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        current_revision = get_current_revision()

        if current_revision and head_revision and current_revision == head_revision:
            status = "up_to_date"
        elif current_revision and head_revision:
            status = "outdated"
        elif not current_revision and managed_tables.issubset(existing_tables):
            status = "stamp_needed"
        elif not current_revision and platform_tables.intersection(existing_tables):
            status = "partial_schema"
        elif not platform_tables.intersection(existing_tables):
            status = "empty_schema"
    else:
        status = "connection_failed"

    return {
        "database_url": settings.db.url,
        "database_type": "mysql" if settings.db.resolved_url.startswith("mysql") else "sqlite" if settings.db.resolved_url.startswith("sqlite") else "other",
        "migration_target": settings.db.migration_target,
        "auto_migrate": settings.db.auto_migrate,
        "seed_on_startup": settings.db.seed_on_startup,
        "current_revision": current_revision,
        "head_revision": head_revision,
        "status": status,
        "migration_ready": status in {"up_to_date", "stamp_needed", "empty_schema", "outdated"},
        "database_ping_ok": database_ping_ok,
        "managed_table_count": len(managed_tables),
    }


def run_database_migrations(target_revision: str | None = None) -> None:
    settings = get_settings()
    alembic_config = _get_alembic_config()
    versions_dir = Path(alembic_config.get_main_option("script_location")) / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    managed_tables = set(Base.metadata.tables.keys())
    platform_tables = managed_tables - LEGACY_TABLE_NAMES
    current_revision = get_current_revision()
    revision_target = target_revision or settings.db.migration_target

    if not current_revision and managed_tables.issubset(existing_tables):
        command.stamp(alembic_config, revision_target)
        return
    if not current_revision and (managed_tables - {"background_tasks"}).issubset(existing_tables):
        command.stamp(alembic_config, "9a0b1c2d3e4f")
        command.upgrade(alembic_config, revision_target)
        return
    partial_tables = platform_tables.intersection(existing_tables)
    if not current_revision and partial_tables:
        preview = ", ".join(sorted(partial_tables)[:8])
        raise RuntimeError(
            "Detected a partially initialized professional-platform schema without a usable Alembic revision. "
            f"Existing managed tables: {preview}. Please back up the database and either "
            "recreate the schema from Alembic or stamp the correct revision after reconciliation."
        )
    command.upgrade(alembic_config, revision_target)


def initialize_database(run_migrations: bool | None = None, seed_data: bool | None = None) -> None:
    settings = get_settings()
    should_run_migrations = settings.db.auto_migrate if run_migrations is None else run_migrations
    should_seed_data = settings.db.seed_on_startup if seed_data is None else seed_data
    if should_run_migrations:
        run_database_migrations(settings.db.migration_target)
    with SessionLocal() as session:
        if should_seed_data and session.scalar(select(Tenant.id).limit(1)) is None:
            seed_demo_data(session)


def seed_demo_data(session) -> None:
    settings = get_settings()
    tenant = Tenant(
        code=settings.app.default_tenant_code,
        name=settings.app.default_tenant_name,
        status="active",
        plan_type="professional",
    )
    session.add(tenant)
    session.flush()

    roles: list[Role] = []
    for code, name in (
        ("super_admin", "超级管理员"),
        ("admin", "教研管理员"),
        ("teacher", "教研老师"),
        ("reviewer", "审核员"),
        ("operator", "运营"),
        ("viewer", "查看者"),
        ("student", "学员"),
    ):
        role = Role(tenant_id=tenant.id, role_code=code, role_name=name, is_system=True)
        roles.append(role)
        session.add(role)
    session.flush()

    admin = User(
        tenant_id=tenant.id,
        username="admin",
        password_hash=hash_password("admin123456"),
        display_name="平台管理员",
        mobile="13800000000",
        email="admin@example.com",
        user_type="admin",
        status="active",
        last_login_at=datetime.utcnow(),
    )
    learner_user = User(
        tenant_id=tenant.id,
        username="learner_demo",
        password_hash=hash_password("learner123456"),
        display_name="演示学员",
        mobile="13900000000",
        email="learner@example.com",
        user_type="student",
        status="active",
    )
    session.add_all([admin, learner_user])
    session.flush()

    session.add_all(
        [
            UserRole(tenant_id=tenant.id, user_id=admin.id, role_id=roles[0].id),
            UserRole(tenant_id=tenant.id, user_id=learner_user.id, role_id=roles[-1].id),
        ]
    )

    configured_subjects = settings.subjects or [
        {"code": "cpa", "name": "注册会计师", "categories": ["会计", "审计", "税法"]},
        {"code": "postgraduate", "name": "考研", "categories": ["政治", "英语", "数学"]},
    ]

    subjects: list[Subject] = []
    for item in configured_subjects[:4]:
        subject = Subject(
            tenant_id=tenant.id,
            code=item.code if hasattr(item, "code") else item["code"],
            name=item.name if hasattr(item, "name") else item["name"],
            status="active",
            created_by=admin.id,
            updated_by=admin.id,
        )
        session.add(subject)
        subjects.append(subject)
    session.flush()

    primary_subject = subjects[0]
    primary_categories = ["会计准则", "收入确认", "合并报表"]
    primary_category_models: list[SubjectCategory] = []
    for order, category_name in enumerate(primary_categories, start=1):
        subject_category = SubjectCategory(
            tenant_id=tenant.id,
            subject_id=primary_subject.id,
            name=category_name,
            sort_order=order,
            created_by=admin.id,
            updated_by=admin.id,
        )
        primary_category_models.append(subject_category)
        session.add(subject_category)
    session.flush()

    chapter_foundation = Chapter(
        tenant_id=tenant.id,
        subject_id=primary_subject.id,
        category_id=primary_category_models[0].id if primary_category_models else None,
        parent_id=None,
        name="会计基础",
        level=1,
        path="会计基础",
        sort_order=1,
        created_by=admin.id,
        updated_by=admin.id,
    )
    chapter_income = Chapter(
        tenant_id=tenant.id,
        subject_id=primary_subject.id,
        category_id=primary_category_models[1].id if len(primary_category_models) > 1 else (primary_category_models[0].id if primary_category_models else None),
        parent_id=None,
        name="收入与合同",
        level=1,
        path="收入与合同",
        sort_order=2,
        created_by=admin.id,
        updated_by=admin.id,
    )
    session.add_all([chapter_foundation, chapter_income])
    session.flush()

    kp_revenue = KnowledgePoint(
        tenant_id=tenant.id,
        subject_id=primary_subject.id,
        category_id=chapter_income.category_id,
        chapter_id=chapter_income.id,
        parent_id=None,
        name="收入确认五步法",
        level=1,
        path="收入与合同/收入确认五步法",
        description="识别合同、履约义务、交易价格、分摊交易价格、确认收入。",
        keywords_json=["合同", "履约义务", "交易价格"],
        status="active",
        sort_order=1,
        created_by=admin.id,
        updated_by=admin.id,
    )
    kp_control = KnowledgePoint(
        tenant_id=tenant.id,
        subject_id=primary_subject.id,
        category_id=chapter_income.category_id,
        chapter_id=chapter_income.id,
        parent_id=None,
        name="控制权转移判断",
        level=1,
        path="收入与合同/控制权转移判断",
        description="判断某一时点或某一时段确认收入。",
        keywords_json=["控制权", "时点确认", "时段确认"],
        status="active",
        sort_order=2,
        created_by=admin.id,
        updated_by=admin.id,
    )
    kp_inventory = KnowledgePoint(
        tenant_id=tenant.id,
        subject_id=primary_subject.id,
        category_id=chapter_foundation.category_id,
        chapter_id=chapter_foundation.id,
        parent_id=None,
        name="存货初始计量",
        level=1,
        path="会计基础/存货初始计量",
        description="区分采购成本、加工成本和其他成本。",
        keywords_json=["存货", "成本", "计量"],
        status="active",
        sort_order=3,
        created_by=admin.id,
        updated_by=admin.id,
    )
    session.add_all([kp_revenue, kp_control, kp_inventory])
    session.flush()

    asset = Asset(
        tenant_id=tenant.id,
        subject_id=primary_subject.id,
        asset_type="pdf",
        source_type="exam",
        source_title="2025 注册会计师会计真题卷",
        filename="cpa-2025-paper.pdf",
        mime_type="application/pdf",
        storage_path="data/library/202605/cpa-2025-paper.pdf",
        sha256="seed-paper-sha256",
        file_size=348216,
        parse_status="parsed",
        ocr_status="completed",
        parsed_text="演示试卷已完成 OCR、切题与结构化抽取。",
        token_count=12800,
        year=2025,
        region="全国",
        tags_json=["注册会计师", "真题", "会计"],
        created_by=admin.id,
        updated_by=admin.id,
    )
    session.add(asset)
    session.flush()

    paper = ExamPaper(
        tenant_id=tenant.id,
        subject_id=primary_subject.id,
        category_id=primary_category_models[0].id if primary_category_models else None,
        asset_id=asset.id,
        paper_name="2025 注册会计师《会计》真题",
        paper_code="CPA-ACC-2025",
        exam_year=2025,
        exam_month=8,
        exam_region="全国",
        exam_type="资格考试",
        paper_type="真题",
        source_channel="导入演示数据",
        status="reviewed",
        total_question_count=4,
        total_score=10,
        parsed_version=1,
        review_status="approved",
        created_by=admin.id,
        updated_by=admin.id,
    )
    session.add(paper)
    session.flush()

    section_choice = PaperSection(
        tenant_id=tenant.id,
        paper_id=paper.id,
        section_name="单项选择题",
        question_type="single_choice",
        start_no=1,
        end_no=2,
        score=4,
        sort_order=1,
        created_by=admin.id,
        updated_by=admin.id,
    )
    section_case = PaperSection(
        tenant_id=tenant.id,
        paper_id=paper.id,
        section_name="案例分析题",
        question_type="case_analysis",
        start_no=3,
        end_no=4,
        score=6,
        sort_order=2,
        created_by=admin.id,
        updated_by=admin.id,
    )
    session.add_all([section_choice, section_case])
    session.flush()

    questions = [
        ExamQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            subject_id=primary_subject.id,
            section_id=section_choice.id,
            question_no="1",
            question_uid="CPA2025-1",
            question_type="single_choice",
            stem_text="企业识别履约义务时，以下哪项最符合收入准则要求？",
            options_json=["按合同逐条拆分", "按可明确区分的承诺拆分", "按收款节点拆分", "按交付批次拆分"],
            answer_text="B",
            analysis_text="履约义务应当基于可单独区分的承诺识别。",
            source_page_from=2,
            source_page_to=2,
            score=2,
            difficulty_level=2,
            quality_score=0.93,
            is_duplicate=False,
            duplicate_group_id=None,
            parse_status="parsed",
            review_status="approved",
            reviewed_by=admin.id,
            reviewed_at=datetime.utcnow(),
            created_by=admin.id,
            updated_by=admin.id,
        ),
        ExamQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            subject_id=primary_subject.id,
            section_id=section_choice.id,
            question_no="2",
            question_uid="CPA2025-2",
            question_type="single_choice",
            stem_text="关于控制权转移时点的判断，下列说法正确的是哪一项？",
            options_json=["只看收款时间", "只看发票时间", "结合法定所有权与实物占有等指标", "只看风险报酬"],
            answer_text="C",
            analysis_text="控制权转移判断需要综合多项证据，而非单一指标。",
            source_page_from=2,
            source_page_to=2,
            score=2,
            difficulty_level=3,
            quality_score=0.9,
            is_duplicate=False,
            duplicate_group_id=None,
            parse_status="parsed",
            review_status="approved",
            reviewed_by=admin.id,
            reviewed_at=datetime.utcnow(),
            created_by=admin.id,
            updated_by=admin.id,
        ),
        ExamQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            subject_id=primary_subject.id,
            section_id=section_case.id,
            question_no="3",
            question_uid="CPA2025-3",
            question_type="case_analysis",
            stem_text="甲公司销售设备并提供安装服务，请判断收入确认时点并说明依据。",
            options_json=[],
            answer_text="应分别判断设备与安装服务的履约义务，并依据控制权转移时点确认收入。",
            analysis_text="本题同时考查履约义务拆分与控制权转移判断。",
            source_page_from=4,
            source_page_to=5,
            score=3,
            difficulty_level=4,
            quality_score=0.95,
            is_duplicate=False,
            duplicate_group_id=None,
            parse_status="parsed",
            review_status="approved",
            reviewed_by=admin.id,
            reviewed_at=datetime.utcnow(),
            created_by=admin.id,
            updated_by=admin.id,
        ),
        ExamQuestion(
            tenant_id=tenant.id,
            paper_id=paper.id,
            subject_id=primary_subject.id,
            section_id=section_case.id,
            question_no="4",
            question_uid="CPA2025-4",
            question_type="case_analysis",
            stem_text="分析委托加工材料形成存货时的初始计量口径。",
            options_json=[],
            answer_text="应计入采购成本、加工成本及达到当前场所和状态所发生的其他成本。",
            analysis_text="本题聚焦存货初始计量的成本构成。",
            source_page_from=6,
            source_page_to=6,
            score=3,
            difficulty_level=3,
            quality_score=0.88,
            is_duplicate=False,
            duplicate_group_id=None,
            parse_status="parsed",
            review_status="approved",
            reviewed_by=admin.id,
            reviewed_at=datetime.utcnow(),
            created_by=admin.id,
            updated_by=admin.id,
        ),
    ]
    session.add_all(questions)
    session.flush()

    bank_items = [
        QuestionBankItem(
            tenant_id=tenant.id,
            subject_id=primary_subject.id,
            canonical_stem=question.stem_text,
            canonical_options_json=question.options_json,
            canonical_answer=question.answer_text,
            canonical_analysis=question.analysis_text,
            question_type=question.question_type,
            difficulty_level=question.difficulty_level,
            quality_score=question.quality_score,
            source_count=1,
            status="published",
            created_by=admin.id,
            updated_by=admin.id,
        )
        for question in questions
    ]
    session.add_all(bank_items)
    session.flush()

    for question, item in zip(questions, bank_items, strict=True):
        session.add(
            QuestionSourceLink(
                tenant_id=tenant.id,
                bank_question_id=item.id,
                exam_question_id=question.id,
                paper_id=paper.id,
                source_year=paper.exam_year,
                source_region=paper.exam_region,
                created_by=admin.id,
                updated_by=admin.id,
            )
        )

    knowledge_mapping = [
        (questions[0], kp_revenue, True),
        (questions[1], kp_control, True),
        (questions[2], kp_revenue, True),
        (questions[2], kp_control, False),
        (questions[3], kp_inventory, True),
    ]
    for question, point, is_primary in knowledge_mapping:
        session.add(
            QuestionKnowledgeLink(
                tenant_id=tenant.id,
                question_id=question.id,
                question_layer="raw",
                knowledge_point_id=point.id,
                link_type="manual_reviewed",
                confidence_score=0.92 if is_primary else 0.74,
                evidence_text=question.stem_text[:64],
                tag_source="seed",
                is_primary=is_primary,
                review_status="approved",
                reviewed_by=admin.id,
                reviewed_at=datetime.utcnow(),
                created_by=admin.id,
                updated_by=admin.id,
            )
        )

    report = AnalysisReport(
        tenant_id=tenant.id,
        subject_id=primary_subject.id,
        report_type="hot_knowledge",
        report_name="2025 会计高频考点报告",
        scope_config_json={"paper_ids": [paper.id]},
        filters_json={"exam_year": 2025},
        snapshot_date=date.today(),
        version_no=1,
        status="ready",
        report_json={
            "summary": "当前高频考点集中在收入确认与控制权转移。",
            "top_points": ["收入确认五步法", "控制权转移判断"],
        },
        created_by=admin.id,
        updated_by=admin.id,
    )
    job = AnalysisJob(
        tenant_id=tenant.id,
        job_type="generate_report",
        subject_id=primary_subject.id,
        scope_type="paper",
        scope_config_json={"paper_ids": [paper.id]},
        status="completed",
        progress=100,
        result_summary_json={"report_name": report.report_name},
        error_message=None,
        created_by=admin.id,
        started_at=datetime.utcnow() - timedelta(minutes=8),
        finished_at=datetime.utcnow() - timedelta(minutes=2),
        updated_by=admin.id,
    )
    session.add_all([report, job])
    session.flush()

    practice_set = PracticeSet(
        tenant_id=tenant.id,
        subject_id=primary_subject.id,
        set_type="high_frequency",
        title="收入确认冲刺题包",
        description="围绕收入确认五步法与控制权转移判断的组合训练。",
        source_report_id=report.id,
        difficulty_policy="recent_hot_first",
        question_count=3,
        status="published",
        created_by=admin.id,
        updated_by=admin.id,
    )
    mock_exam = MockExam(
        tenant_id=tenant.id,
        subject_id=primary_subject.id,
        title="会计冲刺模考 A 卷",
        exam_mode="timed",
        duration_minutes=45,
        total_score=10,
        status="published",
        created_by=admin.id,
        updated_by=admin.id,
    )
    session.add_all([practice_set, mock_exam])
    session.flush()

    for order, item in enumerate(bank_items[:3], start=1):
        session.add(
            PracticeSetQuestion(
                tenant_id=tenant.id,
                practice_set_id=practice_set.id,
                bank_question_id=item.id,
                sort_order=order,
                score=2 if order < 3 else 3,
                created_by=admin.id,
                updated_by=admin.id,
            )
        )
    for order, item in enumerate(bank_items, start=1):
        session.add(
            MockExamQuestion(
                tenant_id=tenant.id,
                mock_exam_id=mock_exam.id,
                bank_question_id=item.id,
                sort_order=order,
                score=2 if order < 3 else 3,
                created_by=admin.id,
                updated_by=admin.id,
            )
        )

    learner = LearnerProfile(
        tenant_id=tenant.id,
        user_id=learner_user.id,
        target_exam="注册会计师",
        target_year=2026,
        level="冲刺",
        preferred_subjects_json=[primary_subject.name],
        created_by=learner_user.id,
        updated_by=learner_user.id,
    )
    session.add(learner)
    session.flush()

    session_record = PracticeSession(
        tenant_id=tenant.id,
        learner_id=learner.id,
        session_type="practice_set",
        subject_id=primary_subject.id,
        practice_set_id=practice_set.id,
        mock_exam_id=None,
        status="submitted",
        started_at=datetime.utcnow() - timedelta(days=1),
        submitted_at=datetime.utcnow() - timedelta(days=1, minutes=-35),
        score=5,
        accuracy_rate=0.67,
        duration_seconds=1980,
        created_by=learner_user.id,
        updated_by=learner_user.id,
    )
    session.add(session_record)
    session.flush()

    session.add_all(
        [
            PracticeAnswer(
                tenant_id=tenant.id,
                session_id=session_record.id,
                bank_question_id=bank_items[0].id,
                learner_answer="B",
                is_correct=True,
                score=2,
                spent_seconds=260,
                knowledge_snapshot_json={"primary": kp_revenue.name},
                created_by=learner_user.id,
                updated_by=learner_user.id,
            ),
            PracticeAnswer(
                tenant_id=tenant.id,
                session_id=session_record.id,
                bank_question_id=bank_items[1].id,
                learner_answer="A",
                is_correct=False,
                score=0,
                spent_seconds=310,
                knowledge_snapshot_json={"primary": kp_control.name},
                created_by=learner_user.id,
                updated_by=learner_user.id,
            ),
        ]
    )

    session.add(
        WrongBookItem(
            tenant_id=tenant.id,
            learner_id=learner.id,
            bank_question_id=bank_items[1].id,
            source_session_id=session_record.id,
            wrong_count=2,
            last_wrong_at=datetime.utcnow() - timedelta(days=1),
            mastered=False,
            created_by=learner_user.id,
            updated_by=learner_user.id,
        )
    )
    session.add(
        Favorite(
            tenant_id=tenant.id,
            learner_id=learner.id,
            bank_question_id=bank_items[2].id,
            created_by=learner_user.id,
            updated_by=learner_user.id,
        )
    )
    session.add_all(
        [
            MasterySnapshot(
                tenant_id=tenant.id,
                learner_id=learner.id,
                subject_id=primary_subject.id,
                knowledge_point_id=kp_revenue.id,
                mastery_score=0.81,
                answered_count=12,
                correct_count=10,
                snapshot_date=date.today(),
                created_by=learner_user.id,
                updated_by=learner_user.id,
            ),
            MasterySnapshot(
                tenant_id=tenant.id,
                learner_id=learner.id,
                subject_id=primary_subject.id,
                knowledge_point_id=kp_control.id,
                mastery_score=0.58,
                answered_count=9,
                correct_count=5,
                snapshot_date=date.today(),
                created_by=learner_user.id,
                updated_by=learner_user.id,
            ),
        ]
    )

    session.add(
        ReviewTask(
            tenant_id=tenant.id,
            task_type="question_review",
            target_type="exam_question",
            target_id=str(questions[2].id),
            status="pending",
            assigned_to=admin.id,
            priority="high",
            review_note="补充次考点解释与证据片段。",
            created_by=admin.id,
            updated_by=admin.id,
        )
    )

    session.commit()

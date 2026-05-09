from __future__ import annotations

from datetime import datetime
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
    Asset,
    Chapter,
    ExamPaper,
    KnowledgePoint,
    PaperSection,
    ReviewTask,
    Role,
    Subject,
    SubjectCategory,
    Tenant,
    User,
    UserRole,
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
    session.add(admin)
    session.flush()

    session.add_all(
        [
            UserRole(tenant_id=tenant.id, user_id=admin.id, role_id=roles[0].id),
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

    job = AnalysisJob(
        tenant_id=tenant.id,
        job_type="paper_parse",
        subject_id=primary_subject.id,
        scope_type="paper",
        scope_config_json={
            "paper_id": paper.id,
            "stage": "completed",
            "detail": {
                "paper_id": paper.id,
                "question_count": paper.total_question_count,
                "section_count": 2,
                "tagged_count": 0,
                "provider": "seed_data",
                "warnings": [],
            },
        },
        status="completed",
        progress=100,
        result_summary_json={
            "paper_id": paper.id,
            "asset_id": asset.id,
            "parse_status": "parsed",
            "paper_status": "reviewed",
            "question_count": paper.total_question_count,
            "section_count": 2,
            "tagged_count": 0,
            "provider": "seed_data",
            "parse_mode": "rules",
            "output_format": "markdown",
            "warnings": [],
            "parse_options": {},
        },
        error_message=None,
        created_by=admin.id,
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        updated_by=admin.id,
    )
    session.add(job)

    session.commit()

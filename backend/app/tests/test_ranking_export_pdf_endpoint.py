"""Integration tests for the export-excel `format=pdf` branch."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_scholarship_manager
from app.main import app
from app.models.application import Application, ApplicationStatus
from app.models.audit_log import AuditAction, AuditLog
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import AdminScholarship, User, UserRole, UserType


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(
        nycu_id="admin901",
        name="Admin",
        email="admin901@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def scholarship(db: AsyncSession) -> ScholarshipType:
    s = ScholarshipType(
        code="phd_pdf_test",
        name="Test PDF PhD",
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status="active",
    )
    db.add(s)
    await db.flush()
    return s


@pytest_asyncio.fixture
async def configuration(db: AsyncSession, scholarship: ScholarshipType, admin_user: User) -> ScholarshipConfiguration:
    cfg = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=114,
        semester=None,  # yearly
        config_name="Test PhD 114",
        config_code="test-pdf-114",
        amount=40000,
        is_active=True,
    )
    db.add(cfg)
    db.add(AdminScholarship(admin_id=admin_user.id, scholarship_id=scholarship.id))
    await db.flush()
    return cfg


@pytest_asyncio.fixture
async def ranking_with_item(
    db: AsyncSession,
    admin_user: User,
    scholarship: ScholarshipType,
    configuration: ScholarshipConfiguration,
) -> CollegeRanking:
    student = User(
        nycu_id="310460098",
        name="李大華",
        email="s98@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    await db.flush()

    r = CollegeRanking(
        scholarship_type_id=scholarship.id,
        sub_type_code="nstc",
        academic_year=114,
        ranking_name="Test",
        created_by=admin_user.id,
        is_finalized=False,
    )
    db.add(r)
    await db.flush()

    app_row = Application(
        app_id="APP-114-0-09998",
        user_id=student.id,
        scholarship_type_id=scholarship.id,
        academic_year=114,
        semester=None,
        status=ApplicationStatus.submitted,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        student_data={"std_stdcode": "310460098", "std_cname": "李大華", "std_pid": "A223456789"},
        sub_type_preferences=["nstc"],
        scholarship_subtype_list=["nstc"],
        submitted_form_data={"fields": {}},
    )
    db.add(app_row)
    await db.flush()

    item = CollegeRankingItem(
        ranking_id=r.id,
        application_id=app_row.id,
        rank_position=1,
        status="ranked",
        college_rejected=False,
        is_allocated=False,
    )
    db.add(item)
    await db.flush()
    return r


@pytest.mark.asyncio
class TestExportPdfFormat:
    async def test_format_pdf_returns_pdf(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        ranking_with_item: CollegeRanking,
    ):
        app.dependency_overrides[require_scholarship_manager] = lambda: admin_user
        try:
            resp = await client.get(
                f"/api/v1/college-review/rankings/{ranking_with_item.id}/export-excel",
                params={"format": "pdf"},
            )
        finally:
            app.dependency_overrides.pop(require_scholarship_manager, None)

        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"].startswith("application/pdf")
        # quote() never encodes ".", so the filename* ends with a literal .pdf
        assert resp.headers["content-disposition"].endswith(".pdf")
        assert resp.content[:5] == b"%PDF-"

        # PII audit recorded, tagged with the pdf format.
        result = await db.execute(
            select(AuditLog).where(
                AuditLog.action == AuditAction.pii_access.value,
                AuditLog.resource_type == "college_ranking",
                AuditLog.resource_id == str(ranking_with_item.id),
            )
        )
        audit = result.scalars().first()
        assert audit is not None, "pdf export must record a pii_access audit"
        assert audit.meta_data["export_format"] == "pdf"

    async def test_format_pdf_with_template_is_rejected(
        self,
        client: AsyncClient,
        admin_user: User,
        ranking_with_item: CollegeRanking,
    ):
        app.dependency_overrides[require_scholarship_manager] = lambda: admin_user
        try:
            resp = await client.get(
                f"/api/v1/college-review/rankings/{ranking_with_item.id}/export-excel",
                params={"format": "pdf", "template": "true"},
            )
        finally:
            app.dependency_overrides.pop(require_scholarship_manager, None)

        assert resp.status_code == 400, resp.text

    async def test_invalid_format_is_422(
        self,
        client: AsyncClient,
        admin_user: User,
        ranking_with_item: CollegeRanking,
    ):
        app.dependency_overrides[require_scholarship_manager] = lambda: admin_user
        try:
            resp = await client.get(
                f"/api/v1/college-review/rankings/{ranking_with_item.id}/export-excel",
                params={"format": "docx"},
            )
        finally:
            app.dependency_overrides.pop(require_scholarship_manager, None)

        assert resp.status_code == 422, resp.text

    async def test_default_format_is_xlsx(
        self,
        client: AsyncClient,
        admin_user: User,
        ranking_with_item: CollegeRanking,
    ):
        app.dependency_overrides[require_scholarship_manager] = lambda: admin_user
        try:
            resp = await client.get(f"/api/v1/college-review/rankings/{ranking_with_item.id}/export-excel")
        finally:
            app.dependency_overrides.pop(require_scholarship_manager, None)

        assert resp.status_code == 200, resp.text
        assert "spreadsheetml" in resp.headers["content-type"]
        assert resp.content[:2] == b"PK"  # xlsx is a zip

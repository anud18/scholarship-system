"""Tests for the admin toggle + college view of distribution results."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin, require_college
from app.main import app
from app.models.scholarship import ScholarshipConfiguration, ScholarshipStatus, ScholarshipType
from app.models.user import AdminScholarship, User, UserRole, UserType

CONFIG_BASE = "/api/v1/scholarship-configurations/configurations"


@pytest_asyncio.fixture
async def sch_type(db: AsyncSession) -> ScholarshipType:
    st = ScholarshipType(
        code="cvd_phd",
        name="CVD PhD Scholarship",
        description="college-view-distribution test",
        status=ScholarshipStatus.active.value,
    )
    db.add(st)
    await db.commit()
    await db.refresh(st)
    return st


@pytest_asyncio.fixture
async def config(db: AsyncSession, sch_type) -> ScholarshipConfiguration:
    cfg = ScholarshipConfiguration(
        scholarship_type_id=sch_type.id,
        config_name="CVD 114-1",
        config_code="CVD-114-1",
        academic_year=114,
        semester="first",
        amount=40000,
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@pytest_asyncio.fixture
async def admin_client(db: AsyncSession, client: AsyncClient, sch_type) -> AsyncClient:
    admin = User(
        nycu_id="cvd_admin",
        email="cvd_admin@university.edu",
        name="CVD Admin",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    db.add(AdminScholarship(admin_id=admin.id, scholarship_id=sch_type.id))
    await db.commit()

    async def override_admin():
        return admin

    app.dependency_overrides[require_admin] = override_admin
    try:
        yield client
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_admin_can_toggle_college_view_distribution(admin_client, config, db):
    resp = await admin_client.patch(f"{CONFIG_BASE}/{config.id}/college-view-distribution", json={"allow": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["allow_college_view_distribution"] is True

    await db.refresh(config)
    assert config.allow_college_view_distribution is True

"""Pin: revoke + suspend POST endpoints return the ApiResponse envelope,
require admin auth, reject empty reason (422), surface conflict as 409,
surface non-allocated as 400."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import Mock

from app.models.user import User, UserRole, UserType


# ---------------------------------------------------------------------------
# Helpers: build mock users for dependency injection
# ---------------------------------------------------------------------------

def _make_mock_admin() -> Mock:
    u = Mock(spec=User)
    u.id = 1
    u.role = UserRole.admin
    u.email = "admin@nycu.edu.tw"
    return u


def _make_mock_student() -> Mock:
    u = Mock(spec=User)
    u.id = 99
    u.role = UserRole.student
    u.email = "student@nycu.edu.tw"
    return u


# ---------------------------------------------------------------------------
# Fixtures: auth clients
# `client` is provided by conftest.py (wraps async DB session via get_db).
# We add fixtures that override get_current_admin_user / get_current_user.
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def client_admin(db, client: AsyncClient):
    """client with admin auth override and DB override for app.core.deps.get_db
    (the endpoint imports get_db from app.core.deps, while conftest overrides
    app.db.deps.get_db — we need to patch both so the service hits the same
    in-memory test DB that contains the fixture data)."""
    from app.core.deps import get_current_admin_user
    from app.core.deps import get_db as core_get_db
    from app.main import app

    mock_admin = _make_mock_admin()

    async def override_admin():
        return mock_admin

    async def override_core_db():
        yield db

    app.dependency_overrides[get_current_admin_user] = override_admin
    app.dependency_overrides[core_get_db] = override_core_db
    yield client
    del app.dependency_overrides[get_current_admin_user]
    del app.dependency_overrides[core_get_db]


@pytest_asyncio.fixture
async def client_student(db, client: AsyncClient):
    """client that simulates a student (no admin access) — 403 expected."""
    from fastapi import HTTPException, status
    from app.core.deps import get_current_admin_user
    from app.core.deps import get_db as core_get_db
    from app.main import app

    async def override_not_admin():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    async def override_core_db():
        yield db

    app.dependency_overrides[get_current_admin_user] = override_not_admin
    app.dependency_overrides[core_get_db] = override_core_db
    yield client
    del app.dependency_overrides[get_current_admin_user]
    del app.dependency_overrides[core_get_db]


# ---------------------------------------------------------------------------
# Fixtures: DB objects (same pattern as test_revoke_suspend_service.py,
# duplicated here so this file is self-contained — DRY can come later)
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def admin_db_user(db):
    """Real DB-backed admin user."""
    u = User(
        nycu_id="admin_ep_test",
        email="admin_ep@nycu.edu.tw",
        name="Admin EP",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    # Patch the mock admin id to match the DB user so FK references work
    return u


@pytest_asyncio.fixture
async def allocated_application(db, admin_db_user):
    """Application in post-finalize 'allocated' state."""
    from app.models.application import Application, ApplicationStatus
    from app.models.scholarship import SubTypeSelectionMode
    from app.models.enums import ReviewStage

    app = Application(
        user_id=admin_db_user.id,
        app_id="APP-EP-REVOKE-001",
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.student_draft,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
        quota_allocation_status="allocated",
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest_asyncio.fixture
async def unallocated_application(db, admin_db_user):
    """Application without quota_allocation_status='allocated'."""
    from app.models.application import Application, ApplicationStatus
    from app.models.scholarship import SubTypeSelectionMode
    from app.models.enums import ReviewStage

    app = Application(
        user_id=admin_db_user.id,
        app_id="APP-EP-REVOKE-002",
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.student_draft,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
        quota_allocation_status=None,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


# ---------------------------------------------------------------------------
# Tests (6 as required by Task 6)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_revoke_endpoint_success(client_admin: AsyncClient, allocated_application):
    resp = await client_admin.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/revoke",
        json={"reason": "violated"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["quota_allocation_status"] == "revoked"
    assert "ranking_item_id" in body["data"]


@pytest.mark.asyncio
async def test_suspend_endpoint_success(client_admin: AsyncClient, allocated_application):
    resp = await client_admin.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/suspend",
        json={"reason": "leave"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["quota_allocation_status"] == "suspended"


@pytest.mark.asyncio
async def test_revoke_empty_reason_returns_422(client_admin: AsyncClient, allocated_application):
    resp = await client_admin.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/revoke",
        json={"reason": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_revoke_twice_returns_409(client_admin: AsyncClient, allocated_application):
    await client_admin.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/revoke",
        json={"reason": "first"},
    )
    resp = await client_admin.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/revoke",
        json={"reason": "second"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_revoke_non_allocated_returns_400(client_admin: AsyncClient, unallocated_application):
    resp = await client_admin.post(
        f"/api/v1/manual-distribution/applications/{unallocated_application.id}/revoke",
        json={"reason": "x"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_revoke_requires_admin(client_student: AsyncClient, allocated_application):
    resp = await client_student.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/revoke",
        json={"reason": "x"},
    )
    assert resp.status_code in (401, 403)

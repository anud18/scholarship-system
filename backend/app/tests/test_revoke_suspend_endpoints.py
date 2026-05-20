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


# ---------------------------------------------------------------------------
# Task 7: Roster revoked-suspended listing + locked-item DELETE
#
# payment_rosters.py uses get_current_user (not get_current_admin_user) and
# get_sync_db.  We build sync DB fixtures + roster client fixtures that
# override both deps and wire them to the same sync test engine so the
# service can see the inserted data.
# ---------------------------------------------------------------------------

import pytest
from app.tests.conftest import TestingSessionLocalSync, test_engine_sync
from app.db.base_class import Base as _Base


@pytest.fixture
def sync_db_for_roster():
    """Sync session backed by a fresh in-memory SQLite DB — roster tests."""
    _Base.metadata.create_all(bind=test_engine_sync)
    with TestingSessionLocalSync() as session:
        yield session
    _Base.metadata.drop_all(bind=test_engine_sync)


@pytest.fixture
def locked_roster_two_items(sync_db_for_roster):
    """LOCKED roster with one revoked + one suspended item (sync fixture)."""
    from datetime import datetime, timezone
    from app.models.application import Application, ApplicationStatus
    from app.models.enums import ReviewStage
    from app.models.payment_roster import (
        PaymentRoster,
        PaymentRosterItem,
        RosterCycle,
        RosterStatus,
        RosterTriggerType,
    )
    from app.models.scholarship import SubTypeSelectionMode
    from app.models.user import User, UserRole, UserType

    s = sync_db_for_roster

    admin_u = User(
        nycu_id="admin_lk_ep",
        email="admin_lk_ep@nycu.edu.tw",
        name="Admin LK EP",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    student_u = User(
        nycu_id="student_lk_ep",
        email="student_lk_ep@nycu.edu.tw",
        name="Student LK EP",
        role=UserRole.student,
        user_type=UserType.student,
    )
    s.add_all([admin_u, student_u])
    s.flush()

    a1 = Application(
        user_id=admin_u.id,
        app_id="APP-LK-EP-001",
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.cancelled,
        review_stage=ReviewStage.student_draft,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        quota_allocation_status="revoked",
        revoke_reason="bad",
        revoked_by=admin_u.id,
        revoked_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    a2 = Application(
        user_id=student_u.id,
        app_id="APP-LK-EP-002",
        scholarship_type_id=1,
        academic_year=114,
        semester="second",
        status=ApplicationStatus.cancelled,
        review_stage=ReviewStage.student_draft,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        quota_allocation_status="suspended",
        suspend_reason="leave",
        suspended_by=admin_u.id,
        suspended_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    s.add_all([a1, a2])
    s.flush()

    r = PaymentRoster(
        roster_code="ROSTER-LK-EP-01",
        scholarship_configuration_id=1,
        period_label="2025-12",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.LOCKED,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin_u.id,
        qualified_count=2,
        disqualified_count=0,
        total_applications=2,
        total_amount=80000,
    )
    s.add(r)
    s.flush()

    i1 = PaymentRosterItem(
        roster_id=r.id,
        application_id=a1.id,
        student_id_number="EP1",
        student_name="Alice",
        scholarship_name="NSTC",
        scholarship_amount=40000,
        is_included=True,
    )
    i2 = PaymentRosterItem(
        roster_id=r.id,
        application_id=a2.id,
        student_id_number="EP2",
        student_name="Bob",
        scholarship_name="NSTC",
        scholarship_amount=40000,
        is_included=True,
    )
    s.add_all([i1, i2])
    s.commit()
    s.refresh(r)
    r.items = [i1, i2]
    return r


@pytest.fixture
def draft_roster_with_item(sync_db_for_roster):
    """DRAFT roster with one item — DELETE should return 400."""
    from app.models.application import Application, ApplicationStatus
    from app.models.enums import ReviewStage
    from app.models.payment_roster import (
        PaymentRoster,
        PaymentRosterItem,
        RosterCycle,
        RosterStatus,
        RosterTriggerType,
    )
    from app.models.scholarship import SubTypeSelectionMode
    from app.models.user import User, UserRole, UserType

    s = sync_db_for_roster

    u = User(
        nycu_id="admin_dr_ep",
        email="admin_dr_ep@nycu.edu.tw",
        name="Admin DR EP",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    s.add(u)
    s.flush()

    a = Application(
        user_id=u.id,
        app_id="APP-DR-EP-001",
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.student_draft,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        quota_allocation_status="allocated",
    )
    s.add(a)
    s.flush()

    r = PaymentRoster(
        roster_code="ROSTER-DR-EP-01",
        scholarship_configuration_id=1,
        period_label="2026-01",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.DRAFT,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=u.id,
    )
    s.add(r)
    s.flush()

    item = PaymentRosterItem(
        roster_id=r.id,
        application_id=a.id,
        student_id_number="EP3",
        student_name="Carol",
        scholarship_name="NSTC",
        scholarship_amount=40000,
        is_included=True,
    )
    s.add(item)
    s.commit()
    s.refresh(r)
    r.items = [item]
    return r


@pytest_asyncio.fixture
async def roster_client_admin(client: AsyncClient, sync_db_for_roster):
    """AsyncClient with admin get_current_user + get_sync_db overrides.
    The sync_db_for_roster session is the same DB the fixture data lives in,
    so the endpoint can see the inserted rows."""
    from app.core.deps import get_current_user as _gcu
    from app.db.deps import get_sync_db
    from app.main import app

    mock_admin = _make_mock_admin()

    def override_gcu():
        return mock_admin

    def override_sync_db():
        yield sync_db_for_roster

    app.dependency_overrides[_gcu] = override_gcu
    app.dependency_overrides[get_sync_db] = override_sync_db
    yield client
    del app.dependency_overrides[_gcu]
    del app.dependency_overrides[get_sync_db]


@pytest_asyncio.fixture
async def roster_client_student(client: AsyncClient, sync_db_for_roster):
    """AsyncClient with student get_current_user override — 403 expected.
    Also overrides get_sync_db so the test roster data is visible to the
    endpoint before the role check fires."""
    from app.core.deps import get_current_user as _gcu
    from app.db.deps import get_sync_db
    from app.main import app

    mock_student = _make_mock_student()

    def override_gcu():
        return mock_student

    def override_sync_db():
        yield sync_db_for_roster

    app.dependency_overrides[_gcu] = override_gcu
    app.dependency_overrides[get_sync_db] = override_sync_db
    yield client
    del app.dependency_overrides[_gcu]
    del app.dependency_overrides[get_sync_db]


# Task 7 tests

@pytest.mark.asyncio
async def test_get_revoked_suspended_returns_split_lists(
    roster_client_admin, locked_roster_two_items
):
    resp = await roster_client_admin.get(
        f"/api/v1/payment-rosters/{locked_roster_two_items.id}/revoked-suspended"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["revoked"]) == 1
    assert len(data["suspended"]) == 1


@pytest.mark.asyncio
async def test_delete_locked_item_returns_200_and_sets_stale(
    roster_client_admin, locked_roster_two_items
):
    import json as _json
    item_id = locked_roster_two_items.items[0].id
    resp = await roster_client_admin.request(
        "DELETE",
        f"/api/v1/payment-rosters/{locked_roster_two_items.id}/items/{item_id}",
        content=_json.dumps({"reason": "cleanup"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["excel_stale"] is True


@pytest.mark.asyncio
async def test_delete_item_on_non_locked_returns_400(
    roster_client_admin, draft_roster_with_item
):
    import json as _json
    item_id = draft_roster_with_item.items[0].id
    resp = await roster_client_admin.request(
        "DELETE",
        f"/api/v1/payment-rosters/{draft_roster_with_item.id}/items/{item_id}",
        content=_json.dumps({"reason": "x"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_item_requires_admin(
    roster_client_student, locked_roster_two_items
):
    import json as _json
    item_id = locked_roster_two_items.items[0].id
    resp = await roster_client_student.request(
        "DELETE",
        f"/api/v1/payment-rosters/{locked_roster_two_items.id}/items/{item_id}",
        content=_json.dumps({"reason": "x"}),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code in (401, 403)

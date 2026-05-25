"""API-contract smoke tests for payment-roster endpoints (issue #124 §7).

Pin the *contract* surface of `backend/app/api/v1/endpoints/payment_rosters.py`,
not the full functional behaviour:

  - auth gates: student role hits 401/403 on every admin endpoint
  - ApiResponse envelope: every 2xx response carries {success, message, data}
  - input validation: missing body / unknown id returns 4xx (not 5xx)
  - locked-roster guards: DELETE roster and exclude-item on a LOCKED roster
    return 4xx, never silently mutate

Endpoints covered (Priority 1 first):
  POST   /api/v1/payment-rosters/generate
  POST   /api/v1/payment-rosters/{id}/lock
  POST   /api/v1/payment-rosters/{id}/unlock
  POST   /api/v1/payment-rosters/{id}/items/{item_id}/exclude
  DELETE /api/v1/payment-rosters/{id}
  GET    /api/v1/payment-rosters
  GET    /api/v1/payment-rosters/{id}
  GET    /api/v1/payment-rosters/{id}/audit-logs

Notes on session wiring (the hardest part):
  - All payment-roster endpoints depend on `get_current_user` (admin-ness is
    enforced *inside* the handler via `check_user_roles` / `_require_admin`).
    Auth-gate tests therefore override `get_current_user` to return a student
    Mock and assert 401/403, rather than overriding an admin gate that
    doesn't exist on these routes.
  - The `generate`, `revoked-suspended`, and locked-item `DELETE` handlers
    use the *sync* `get_sync_db`; `lock`, `unlock`, `exclude`, `delete`,
    `list`, `get`, and `audit-logs` use the *async* `get_db`. We override
    both so a single client fixture works regardless of which path the
    handler takes.
  - Mock(spec=User) shadows `has_role` with a Mock that is truthy by
    default — that would silently bypass `check_user_roles`. We patch
    `has_role.side_effect` to do the real comparison so the student mock
    actually fails the admin check.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.db.base_class import Base as _Base
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
)
from app.models.user import User, UserRole, UserType
from app.tests.conftest import TestingSessionLocalSync, test_engine_sync

# ---------------------------------------------------------------------------
# Mock user helpers
# ---------------------------------------------------------------------------


def _make_mock_admin() -> Mock:
    """Mock admin with real `has_role` semantics so `check_user_roles` works."""
    u = Mock(spec=User)
    u.id = 1
    u.role = UserRole.admin
    u.name = "Admin EP"
    u.email = "admin_pr@nycu.edu.tw"
    u.has_role.side_effect = lambda role: u.role == role
    u.is_admin.side_effect = lambda: u.role == UserRole.admin
    u.is_super_admin.side_effect = lambda: u.role == UserRole.super_admin
    return u


def _make_mock_student() -> Mock:
    """Mock student. `has_role` must return False for admin/super_admin so
    `check_user_roles([admin, super_admin], ...)` raises 403."""
    u = Mock(spec=User)
    u.id = 99
    u.role = UserRole.student
    u.name = "Student EP"
    u.email = "student_pr@nycu.edu.tw"
    u.has_role.side_effect = lambda role: u.role == role
    u.is_admin.side_effect = lambda: False
    u.is_super_admin.side_effect = lambda: False
    return u


# ---------------------------------------------------------------------------
# Sync DB fixture (payment_rosters' generate/revoked-suspended/locked-item
# DELETE paths run on `get_sync_db`; the lock/unlock/delete/exclude paths
# run on the async `get_db` provided by conftest's `client` fixture). We
# override both deps to point to the same engine so test data is visible
# regardless of which path the handler picks.
# ---------------------------------------------------------------------------


@pytest.fixture
def sync_db_for_rosters():
    """Fresh sync session over the shared in-memory test engine."""
    _Base.metadata.create_all(bind=test_engine_sync)
    with TestingSessionLocalSync() as session:
        yield session
    _Base.metadata.drop_all(bind=test_engine_sync)


@pytest_asyncio.fixture
async def client_admin(client: AsyncClient, sync_db_for_rosters):
    """AsyncClient wired with an admin `get_current_user` override + sync DB
    override. The conftest `client` already overrides `app.db.deps.get_db`
    (async) to the test session, so async endpoints stay wired too."""
    from app.core.deps import get_current_user
    from app.db.deps import get_sync_db
    from app.main import app

    admin = _make_mock_admin()

    def override_user():
        return admin

    def override_sync_db():
        yield sync_db_for_rosters

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_sync_db] = override_sync_db
    yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_sync_db, None)


@pytest_asyncio.fixture
async def client_student(client: AsyncClient, sync_db_for_rosters):
    """Same wiring as `client_admin` but with a student `get_current_user`
    so every admin-only handler returns 401/403 before doing any DB work."""
    from app.core.deps import get_current_user
    from app.db.deps import get_sync_db
    from app.main import app

    student = _make_mock_student()

    def override_user():
        return student

    def override_sync_db():
        yield sync_db_for_rosters

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_sync_db] = override_sync_db
    yield client
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_sync_db, None)


# ---------------------------------------------------------------------------
# Roster fixtures (built via the async `db` session from conftest, which is
# the SAME session the `client` fixture wires into `get_db`. Sync-only
# endpoints — `generate`, `revoked-suspended`, locked-item `DELETE` — would
# need a separate sync session, but the smoke tests we keep here all target
# async endpoints, so the async session is enough.)
# ---------------------------------------------------------------------------


async def _seed_admin_user(db, suffix: str) -> User:
    u = User(
        nycu_id=f"admin_pr_{suffix}",
        email=f"admin_pr_{suffix}@nycu.edu.tw",
        name=f"Admin PR {suffix}",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _build_roster(
    db,
    *,
    code: str,
    status: RosterStatus,
    created_by: int,
    with_item: bool = False,
    period: str = "2026-01",
) -> PaymentRoster:
    r = PaymentRoster(
        roster_code=code,
        scholarship_configuration_id=1,
        period_label=period,
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=status,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=created_by,
        qualified_count=1 if with_item else 0,
        disqualified_count=0,
        total_applications=1 if with_item else 0,
        total_amount=Decimal("40000") if with_item else Decimal("0"),
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc) if status != RosterStatus.DRAFT else None,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    if with_item:
        item = PaymentRosterItem(
            roster_id=r.id,
            application_id=1,  # No application row required for these contract checks
            student_id_number="PR001",
            student_name="Item Owner",
            scholarship_name="Test Scholarship",
            scholarship_amount=Decimal("40000"),
            is_included=True,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
        r._test_item_id = item.id  # stash for tests
    return r


@pytest_asyncio.fixture
async def draft_roster(db) -> PaymentRoster:
    """DRAFT roster — DELETE/lock/unlock can mutate it."""
    u = await _seed_admin_user(db, "draft")
    r = await _build_roster(
        db,
        code="ROSTER-PR-DRAFT",
        status=RosterStatus.DRAFT,
        created_by=u.id,
    )
    return r


@pytest_asyncio.fixture
async def completed_roster(db) -> PaymentRoster:
    """COMPLETED roster — can be locked."""
    u = await _seed_admin_user(db, "comp")
    r = await _build_roster(
        db,
        code="ROSTER-PR-COMP",
        status=RosterStatus.COMPLETED,
        created_by=u.id,
        period="2026-02",
    )
    return r


@pytest_asyncio.fixture
async def locked_roster_with_item(db) -> PaymentRoster:
    """LOCKED roster + one included item.

    DELETE on this roster must 4xx (locked-guard).
    POST /items/{id}/exclude must 4xx (locked-guard).
    """
    u = await _seed_admin_user(db, "lk")
    r = await _build_roster(
        db,
        code="ROSTER-PR-LK",
        status=RosterStatus.LOCKED,
        created_by=u.id,
        with_item=True,
        period="2026-03",
    )
    return r


@pytest_asyncio.fixture
async def draft_roster_with_item(db) -> PaymentRoster:
    """COMPLETED roster + item — exclude-item happy path returns 200.
    (COMPLETED rather than DRAFT so the locked-guard isn't triggered.)"""
    u = await _seed_admin_user(db, "dri")
    r = await _build_roster(
        db,
        code="ROSTER-PR-DRI",
        status=RosterStatus.COMPLETED,
        created_by=u.id,
        with_item=True,
        period="2026-04",
    )
    return r


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_api_response_envelope(body: dict) -> None:
    """Every 2xx must have these three keys (CLAUDE.md §5 ApiResponse)."""
    assert "success" in body, f"missing 'success' key: {body!r}"
    assert "message" in body, f"missing 'message' key: {body!r}"
    assert "data" in body, f"missing 'data' key: {body!r}"


# ===========================================================================
# POST /generate — auth gate + body validation
# ===========================================================================


@pytest.mark.asyncio
async def test_generate_requires_admin(client_student: AsyncClient):
    """Student role must be rejected before any Redis/lock work happens."""
    resp = await client_student.post(
        "/api/v1/payment-rosters/generate",
        json={
            "scholarship_configuration_id": 1,
            "period_label": "2026-01",
            "roster_cycle": "monthly",
            "academic_year": 114,
        },
    )
    assert resp.status_code in (401, 403), resp.text


@pytest.mark.asyncio
async def test_generate_empty_body_returns_422(client_admin: AsyncClient):
    """Pydantic schema rejects empty body before the handler runs."""
    resp = await client_admin.post("/api/v1/payment-rosters/generate", json={})
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_generate_missing_required_field_returns_422(client_admin: AsyncClient):
    """Missing `academic_year` is a Pydantic 422, not a 500."""
    resp = await client_admin.post(
        "/api/v1/payment-rosters/generate",
        json={
            "scholarship_configuration_id": 1,
            "period_label": "2026-01",
            "roster_cycle": "monthly",
            # academic_year intentionally omitted
        },
    )
    assert resp.status_code == 422, resp.text


# ===========================================================================
# POST /{id}/lock
# ===========================================================================


@pytest.mark.asyncio
async def test_lock_requires_admin(client_student: AsyncClient):
    resp = await client_student.post("/api/v1/payment-rosters/999/lock")
    assert resp.status_code in (401, 403), resp.text


@pytest.mark.asyncio
async def test_lock_missing_roster_returns_404(client_admin: AsyncClient):
    resp = await client_admin.post("/api/v1/payment-rosters/99999/lock")
    assert resp.status_code in (400, 404), resp.text


@pytest.mark.asyncio
async def test_lock_completed_roster_returns_envelope(client_admin: AsyncClient, completed_roster: PaymentRoster):
    resp = await client_admin.post(f"/api/v1/payment-rosters/{completed_roster.id}/lock")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _assert_api_response_envelope(body)
    assert body["success"] is True
    assert body["data"]["roster_code"] == completed_roster.roster_code


@pytest.mark.asyncio
async def test_lock_already_locked_returns_4xx(client_admin: AsyncClient, locked_roster_with_item: PaymentRoster):
    """Locking an already-LOCKED roster surfaces as 4xx, not silent no-op."""
    resp = await client_admin.post(f"/api/v1/payment-rosters/{locked_roster_with_item.id}/lock")
    assert resp.status_code in (400, 409), resp.text


# ===========================================================================
# POST /{id}/unlock
# ===========================================================================


@pytest.mark.asyncio
async def test_unlock_requires_admin(client_student: AsyncClient):
    resp = await client_student.post("/api/v1/payment-rosters/999/unlock")
    assert resp.status_code in (401, 403), resp.text


@pytest.mark.asyncio
async def test_unlock_missing_roster_returns_404(client_admin: AsyncClient):
    resp = await client_admin.post("/api/v1/payment-rosters/99999/unlock")
    assert resp.status_code in (400, 404), resp.text


@pytest.mark.asyncio
async def test_unlock_non_locked_returns_4xx(client_admin: AsyncClient, completed_roster: PaymentRoster):
    """Unlocking a non-LOCKED roster is a 4xx, not a no-op."""
    resp = await client_admin.post(f"/api/v1/payment-rosters/{completed_roster.id}/unlock")
    assert resp.status_code in (400, 409), resp.text


@pytest.mark.asyncio
async def test_unlock_locked_roster_returns_envelope(client_admin: AsyncClient, locked_roster_with_item: PaymentRoster):
    resp = await client_admin.post(f"/api/v1/payment-rosters/{locked_roster_with_item.id}/unlock")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _assert_api_response_envelope(body)
    assert body["success"] is True


# ===========================================================================
# POST /{id}/items/{item_id}/exclude
# ===========================================================================


@pytest.mark.asyncio
async def test_exclude_requires_admin(client_student: AsyncClient):
    resp = await client_student.post(
        "/api/v1/payment-rosters/999/items/999/exclude",
        json={"reason_category": "returned"},
    )
    assert resp.status_code in (401, 403), resp.text


@pytest.mark.asyncio
async def test_exclude_missing_body_returns_422(client_admin: AsyncClient, draft_roster_with_item: PaymentRoster):
    """reason_category is required; empty body fails Pydantic validation."""
    item_id = draft_roster_with_item._test_item_id
    resp = await client_admin.post(
        f"/api/v1/payment-rosters/{draft_roster_with_item.id}/items/{item_id}/exclude",
        json={},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_exclude_bad_reason_category_returns_400(
    client_admin: AsyncClient, draft_roster_with_item: PaymentRoster
):
    """Endpoint validates reason_category ∈ {returned, declined, other}."""
    item_id = draft_roster_with_item._test_item_id
    resp = await client_admin.post(
        f"/api/v1/payment-rosters/{draft_roster_with_item.id}/items/{item_id}/exclude",
        json={"reason_category": "bogus_category"},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_exclude_other_without_note_returns_400(client_admin: AsyncClient, draft_roster_with_item: PaymentRoster):
    """reason_category='other' requires reason_note."""
    item_id = draft_roster_with_item._test_item_id
    resp = await client_admin.post(
        f"/api/v1/payment-rosters/{draft_roster_with_item.id}/items/{item_id}/exclude",
        json={"reason_category": "other"},
    )
    assert resp.status_code == 400, resp.text


@pytest.mark.asyncio
async def test_exclude_on_locked_roster_returns_4xx(client_admin: AsyncClient, locked_roster_with_item: PaymentRoster):
    """Locked-guard: exclude-item on a LOCKED roster must 4xx."""
    item_id = locked_roster_with_item._test_item_id
    resp = await client_admin.post(
        f"/api/v1/payment-rosters/{locked_roster_with_item.id}/items/{item_id}/exclude",
        json={"reason_category": "returned"},
    )
    assert resp.status_code in (400, 409), resp.text


@pytest.mark.asyncio
async def test_exclude_unknown_item_returns_404(client_admin: AsyncClient, draft_roster_with_item: PaymentRoster):
    resp = await client_admin.post(
        f"/api/v1/payment-rosters/{draft_roster_with_item.id}/items/999999/exclude",
        json={"reason_category": "returned"},
    )
    assert resp.status_code in (400, 404), resp.text


@pytest.mark.asyncio
async def test_exclude_happy_path_returns_envelope(client_admin: AsyncClient, draft_roster_with_item: PaymentRoster):
    item_id = draft_roster_with_item._test_item_id
    resp = await client_admin.post(
        f"/api/v1/payment-rosters/{draft_roster_with_item.id}/items/{item_id}/exclude",
        json={"reason_category": "returned", "reason_note": "退回"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _assert_api_response_envelope(body)
    assert body["success"] is True
    assert body["data"]["is_included"] is False
    assert body["data"]["exclusion_reason"]


# ===========================================================================
# DELETE /{id}
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_requires_admin(client_student: AsyncClient):
    resp = await client_student.delete("/api/v1/payment-rosters/999")
    assert resp.status_code in (401, 403), resp.text


@pytest.mark.asyncio
async def test_delete_missing_roster_returns_404(client_admin: AsyncClient):
    resp = await client_admin.delete("/api/v1/payment-rosters/99999")
    assert resp.status_code in (400, 404), resp.text


@pytest.mark.asyncio
async def test_delete_locked_roster_returns_4xx(client_admin: AsyncClient, locked_roster_with_item: PaymentRoster):
    """Locked-guard: a LOCKED roster cannot be deleted."""
    resp = await client_admin.delete(f"/api/v1/payment-rosters/{locked_roster_with_item.id}")
    assert resp.status_code in (400, 409), resp.text


@pytest.mark.asyncio
async def test_delete_draft_roster_returns_envelope(client_admin: AsyncClient, draft_roster: PaymentRoster):
    resp = await client_admin.delete(f"/api/v1/payment-rosters/{draft_roster.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _assert_api_response_envelope(body)
    assert body["success"] is True
    assert body["data"] is None


# ===========================================================================
# GET endpoints — ApiResponse envelope sanity (Priority 2)
# ===========================================================================


@pytest.mark.asyncio
async def test_list_rosters_returns_envelope(client_admin: AsyncClient):
    """Empty list still wraps in {success, message, data}."""
    resp = await client_admin.get("/api/v1/payment-rosters")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _assert_api_response_envelope(body)
    assert body["success"] is True
    # data carries the PaginatedResponse shape
    assert "items" in body["data"]
    assert "total" in body["data"]


@pytest.mark.asyncio
async def test_get_roster_returns_envelope(client_admin: AsyncClient, draft_roster: PaymentRoster):
    resp = await client_admin.get(f"/api/v1/payment-rosters/{draft_roster.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _assert_api_response_envelope(body)
    assert body["data"]["roster_code"] == draft_roster.roster_code


@pytest.mark.asyncio
async def test_get_roster_missing_returns_404(client_admin: AsyncClient):
    resp = await client_admin.get("/api/v1/payment-rosters/99999")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_get_audit_logs_returns_envelope(client_admin: AsyncClient, draft_roster: PaymentRoster):
    resp = await client_admin.get(f"/api/v1/payment-rosters/{draft_roster.id}/audit-logs")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    _assert_api_response_envelope(body)
    assert "items" in body["data"]
    assert "total" in body["data"]


@pytest.mark.asyncio
async def test_get_audit_logs_missing_roster_returns_404(client_admin: AsyncClient):
    resp = await client_admin.get("/api/v1/payment-rosters/99999/audit-logs")
    assert resp.status_code == 404, resp.text

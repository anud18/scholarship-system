"""Lifecycle guard tests for payment rosters (issue #124 §4).

Covers the lock / unlock / delete / exclude transitions that gate downstream
financial operations. Tests assert on **observable I/O only** — row state in
`payment_rosters`, `payment_roster_items`, and `roster_audit_logs`, plus the
HTTP status codes returned by the endpoints — never on private helpers.

Layer split (per advisor + existing test conventions):

- `TestLockGuards` — service layer. Verifies that `RosterService.lock_roster`
  only refuses when the roster is *already* LOCKED. NOTE: neither the service
  (`roster_service.py:506-528`) nor the endpoint (`payment_rosters.py:1319`)
  currently require COMPLETED status before locking; DRAFT / PROCESSING /
  COMPLETED / FAILED all succeed. The task spec assumes a stricter guard —
  see test docstrings for the gap. Filed for follow-up rather than mutated
  here, per `feedback_file_repro_issues`.

- `TestUnlockGuards` — service layer happy path + API layer for the non-admin
  403. The auth gate lives only at the endpoint, so the role check has to be
  driven through the HTTP surface.

- `TestExcludeGuards` — API layer only. The exclude operation is *endpoint-
  only* (no service method), so the LOCKED guard at
  `payment_rosters.py:1832` is reachable only via HTTP. Asserts the
  `roster_audit_logs` row gets written with `action=ITEM_REMOVE`.

- `TestDeleteGuards` — API layer only. Same rationale: delete is endpoint-
  inline (`await db.delete(roster)`), no service method exists. Verifies the
  LOCKED → 400 guard and that an unlocked roster's row is gone after DELETE.

- `TestRegenerateAfterDelete` — service layer. `_generate_roster_code` is
  deterministic (`ROSTER-{academic_year}-{period_label}-{config_code}`), so
  after delete + regenerate the new roster has the **same `roster_code`
  string** but a **new primary-key id** and a fresh audit chain. Asserts the
  actually-fresh properties, not the loose "fresh roster_code" wording in
  the task spec.

Builder fixtures mirror `test_roster_service_generation.py` to stay light;
heavier multi-item locked-roster setups follow the pattern from
`test_revoke_suspend_endpoints.py` (sync engine + override
`get_current_user` / `get_db`).
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.exceptions import RosterLockedError
from app.models.application import Application
from app.models.enums import QuotaManagementMode, Semester
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
)
from app.models.roster_audit import RosterAuditAction, RosterAuditLog
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Service-layer builders (sync DB)
# ---------------------------------------------------------------------------


def _make_admin(db_sync, nycu_id: str = "lifecycle_admin") -> User:
    user = User(
        nycu_id=nycu_id,
        name="Lifecycle Admin",
        email=f"{nycu_id}@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db_sync.add(user)
    db_sync.commit()
    db_sync.refresh(user)
    return user


def _make_scholarship(db_sync, code: str = "lifecycle_sch") -> ScholarshipType:
    s = ScholarshipType(
        code=code,
        name="Lifecycle Test Scholarship",
        description="issue #124 §4",
    )
    db_sync.add(s)
    db_sync.commit()
    db_sync.refresh(s)
    return s


def _make_config(
    db_sync,
    scholarship_type: ScholarshipType,
    *,
    config_code: str = "LC-113-1",
) -> ScholarshipConfiguration:
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type.id,
        config_code=config_code,
        config_name="Lifecycle Test Config",
        academic_year=113,
        semester=Semester.first,
        quota_management_mode=QuotaManagementMode.simple,
        has_quota_limit=False,
        amount=50000,
    )
    db_sync.add(c)
    db_sync.commit()
    db_sync.refresh(c)
    return c


def _make_approved_application(
    db_sync,
    user: User,
    scholarship: ScholarshipType,
    config: ScholarshipConfiguration,
    *,
    app_id: str = "APP-LC-113-1-00001",
    student_id: str = "112550999",
    student_name: str = "生命週期同學",
) -> Application:
    a = Application(
        user_id=user.id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id,
        scholarship_subtype_list=[],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status="approved",
        app_id=app_id,
        academic_year=113,
        semester="first",
        student_data={"std_stdcode": student_id, "std_cname": student_name},
        submitted_form_data={},
        agree_terms=True,
        amount=Decimal("50000"),
    )
    db_sync.add(a)
    db_sync.commit()
    db_sync.refresh(a)
    return a


@pytest.fixture
def patch_dependencies():
    """Replace RosterService's external collaborators so tests stay in-process.

    Mirrors the fixture in `test_roster_service_generation.py` — keeps the
    StudentVerificationService and audit_service singletons from doing any
    real I/O while still letting us count calls.
    """
    with (
        patch("app.services.roster_service.StudentVerificationService") as svs,
        patch("app.services.roster_service.audit_service") as audit,
    ):
        svs.return_value.verify_student.return_value = {
            "status": "verified",
            "verified": True,
            "data": {},
        }
        yield {"student_verification": svs, "audit": audit}


def _generate_completed_roster(
    db_sync,
    patch_dependencies,
    *,
    period_label: str = "2024-01",
    config_code: str = "LC-113-1",
    nycu_id: str = "lifecycle_admin",
) -> tuple[PaymentRoster, User, ScholarshipConfiguration]:
    """Build a fully wired DRAFT-/COMPLETED-style roster via the service.

    Returns (roster, admin_user, config). The roster is left in PROCESSING
    after generation (the service does not flip status to COMPLETED — that
    is the caller's responsibility); callers that need COMPLETED should set
    `roster.status = RosterStatus.COMPLETED` and commit.
    """
    admin = _make_admin(db_sync, nycu_id=nycu_id)
    scholarship = _make_scholarship(db_sync, code=f"sch_{nycu_id}")
    config = _make_config(db_sync, scholarship, config_code=config_code)
    _make_approved_application(
        db_sync,
        admin,
        scholarship,
        config,
        app_id=f"APP-LC-{nycu_id}-001",
        student_id=f"99{abs(hash(nycu_id)) % 1000000:06d}",
    )

    svc = RosterService(db_sync)
    roster = svc.generate_roster(
        scholarship_configuration_id=config.id,
        period_label=period_label,
        roster_cycle=RosterCycle.MONTHLY,
        academic_year=113,
        created_by_user_id=admin.id,
        trigger_type=RosterTriggerType.MANUAL,
        student_verification_enabled=False,
    )
    db_sync.commit()
    return roster, admin, config


# ---------------------------------------------------------------------------
# Service-layer: lock guards
# ---------------------------------------------------------------------------


class TestLockGuards:
    """RosterService.lock_roster only refuses when already LOCKED.

    The task spec asks for "lock on a roster NOT in `completed` status → 4xx",
    but the implementation does not enforce that — see module docstring. The
    tests below pin the *actual* behavior so a future tightening of the guard
    surfaces here as a regression rather than silently breaking the contract.
    """

    def test_lock_completed_roster_succeeds_and_flips_state(self, db_sync, patch_dependencies):
        roster, admin, _ = _generate_completed_roster(db_sync, patch_dependencies, period_label="2024-01")
        roster.status = RosterStatus.COMPLETED
        db_sync.commit()

        svc = RosterService(db_sync)
        locked = svc.lock_roster(roster.id, locked_by_user_id=admin.id)

        assert locked.status == RosterStatus.LOCKED
        assert locked.locked_at is not None
        assert locked.locked_by == admin.id

    def test_lock_already_locked_raises_roster_locked_error(self, db_sync, patch_dependencies):
        roster, admin, _ = _generate_completed_roster(db_sync, patch_dependencies, period_label="2024-02")
        svc = RosterService(db_sync)
        svc.lock_roster(roster.id, locked_by_user_id=admin.id)

        with pytest.raises(RosterLockedError, match="already locked"):
            svc.lock_roster(roster.id, locked_by_user_id=admin.id)

        # No state change on the failed second call: still LOCKED, locked_by
        # still points at the original user, locked_at is the first timestamp.
        db_sync.refresh(roster)
        assert roster.status == RosterStatus.LOCKED

    def test_lock_processing_roster_currently_succeeds(self, db_sync, patch_dependencies):
        """Documented gap: lock from PROCESSING currently passes the guard.

        See module docstring — the task spec assumes a `status == COMPLETED`
        precondition that the implementation does not yet enforce. If a guard
        is later added (e.g. issue #124 §4 follow-up), this test should flip
        to expect a `ValueError` / HTTP 400 and the assertions inverted.
        """
        roster, admin, _ = _generate_completed_roster(db_sync, patch_dependencies, period_label="2024-03")
        # Service leaves the roster in PROCESSING; we deliberately keep it
        # there to expose the guard gap.
        assert roster.status == RosterStatus.PROCESSING

        svc = RosterService(db_sync)
        locked = svc.lock_roster(roster.id, locked_by_user_id=admin.id)
        assert locked.status == RosterStatus.LOCKED


# ---------------------------------------------------------------------------
# Service-layer: unlock guards (happy path + non-locked guard)
# ---------------------------------------------------------------------------


class TestUnlockGuards:
    """RosterService.unlock_roster service-layer state transitions."""

    def test_unlock_locked_roster_reverts_to_completed(self, db_sync, patch_dependencies):
        roster, admin, _ = _generate_completed_roster(db_sync, patch_dependencies, period_label="2024-04")
        svc = RosterService(db_sync)
        svc.lock_roster(roster.id, locked_by_user_id=admin.id)

        unlocked = svc.unlock_roster(roster.id, unlocked_by_user_id=admin.id)

        assert unlocked.status == RosterStatus.COMPLETED
        assert unlocked.locked_at is None
        assert unlocked.locked_by is None

    def test_unlock_non_locked_roster_raises_value_error(self, db_sync, patch_dependencies):
        roster, admin, _ = _generate_completed_roster(db_sync, patch_dependencies, period_label="2024-05")
        # Roster never locked — service refuses to unlock.
        svc = RosterService(db_sync)
        with pytest.raises(ValueError, match="not locked"):
            svc.unlock_roster(roster.id, unlocked_by_user_id=admin.id)


# ---------------------------------------------------------------------------
# API-layer fixtures (async client + dependency overrides)
# Mirrors `test_revoke_suspend_endpoints.py` for consistency.
# ---------------------------------------------------------------------------


def _mock_admin_user() -> Mock:
    u = Mock(spec=User)
    u.id = 1
    u.role = UserRole.admin
    u.email = "admin_lc@nycu.edu.tw"
    u.name = "Admin LC"
    # User.has_role(role) -> self.role == role. With Mock(spec=User) the
    # method is auto-mocked; wire it to the real semantics.
    u.has_role.side_effect = lambda role: role == UserRole.admin
    u.is_admin.return_value = True
    return u


def _mock_student_user() -> Mock:
    u = Mock(spec=User)
    u.id = 99
    u.role = UserRole.student
    u.email = "student_lc@nycu.edu.tw"
    u.name = "Student LC"
    u.has_role.side_effect = lambda role: role == UserRole.student
    u.is_admin.return_value = False
    return u


@pytest_asyncio.fixture
async def admin_api_client(db, client: AsyncClient):
    """AsyncClient with admin `get_current_user` override.

    The endpoints under test (`lock`, `unlock`, `delete`, `exclude`) use the
    async `get_db` dependency, which the base `client` fixture already wires
    to the shared `db` session. We only need to override the auth dep.
    """
    from app.core.deps import get_current_user
    from app.main import app

    mock_admin = _mock_admin_user()

    async def override_get_current_user():
        return mock_admin

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def student_api_client(db, client: AsyncClient):
    """AsyncClient with student `get_current_user` override — should 403."""
    from app.core.deps import get_current_user
    from app.main import app

    mock_student = _mock_student_user()

    async def override_get_current_user():
        return mock_student

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def locked_roster_async(db):
    """LOCKED roster + one included item, on the *async* test DB.

    Returns dict with `id` and `item_id`; we materialise primitives because
    the async session may expire the SQLAlchemy instance once the test
    enters an HTTP round-trip.
    """
    admin = User(
        nycu_id="admin_async_lc",
        email="admin_async_lc@nycu.edu.tw",
        name="Admin Async LC",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db.add(admin)
    await db.flush()

    app_row = Application(
        user_id=admin.id,
        app_id="APP-ASYNC-LC-LOCKED",
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status="approved",
        sub_type_selection_mode=SubTypeSelectionMode.single,
    )
    db.add(app_row)
    await db.flush()

    roster = PaymentRoster(
        roster_code="ROSTER-ASYNC-LC-LOCKED",
        scholarship_configuration_id=1,
        period_label="2025-12",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.LOCKED,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin.id,
        qualified_count=1,
        disqualified_count=0,
        total_applications=1,
        total_amount=50000,
        locked_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        locked_by=admin.id,
    )
    db.add(roster)
    await db.flush()

    item = PaymentRosterItem(
        roster_id=roster.id,
        application_id=app_row.id,
        student_id_number="L001",
        student_name="Locked Student",
        scholarship_name="LC NSTC",
        scholarship_amount=50000,
        is_included=True,
    )
    db.add(item)
    await db.commit()
    await db.refresh(roster)
    await db.refresh(item)
    return {"id": roster.id, "item_id": item.id, "code": roster.roster_code}


@pytest_asyncio.fixture
async def completed_roster_async(db):
    """COMPLETED (unlocked) roster + one included item, on the *async* DB.

    Used by the DELETE-success and EXCLUDE-success tests.
    """
    admin = User(
        nycu_id="admin_async_cp",
        email="admin_async_cp@nycu.edu.tw",
        name="Admin Async CP",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db.add(admin)
    await db.flush()

    app_row = Application(
        user_id=admin.id,
        app_id="APP-ASYNC-LC-COMPLETED",
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status="approved",
        sub_type_selection_mode=SubTypeSelectionMode.single,
    )
    db.add(app_row)
    await db.flush()

    roster = PaymentRoster(
        roster_code="ROSTER-ASYNC-LC-COMPLETED",
        scholarship_configuration_id=1,
        period_label="2026-01",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.COMPLETED,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin.id,
        qualified_count=1,
        disqualified_count=0,
        total_applications=1,
        total_amount=50000,
    )
    db.add(roster)
    await db.flush()

    item = PaymentRosterItem(
        roster_id=roster.id,
        application_id=app_row.id,
        student_id_number="C001",
        student_name="Completed Student",
        scholarship_name="LC NSTC",
        scholarship_amount=50000,
        is_included=True,
    )
    db.add(item)
    await db.commit()
    await db.refresh(roster)
    await db.refresh(item)
    return {"id": roster.id, "item_id": item.id, "code": roster.roster_code}


# ---------------------------------------------------------------------------
# API-layer: unlock auth gate (only reachable through HTTP)
# ---------------------------------------------------------------------------


class TestUnlockAuth:
    """The `unlock` endpoint guards on `UserRole.admin`; the service does not.

    Lifecycle-relevant because a non-admin must NEVER be able to revert a
    locked roster — that would let a non-financial actor reopen distribution
    after the books closed.
    """

    @pytest.mark.asyncio
    async def test_unlock_by_non_admin_returns_403(self, student_api_client, locked_roster_async):
        roster_id = locked_roster_async["id"]
        resp = await student_api_client.post(f"/api/v1/payment-rosters/{roster_id}/unlock")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# API-layer: exclude_item guards (locked vs unlocked + audit row)
# ---------------------------------------------------------------------------


class TestExcludeGuards:
    """POST /{roster_id}/items/{item_id}/exclude

    The LOCKED guard at `payment_rosters.py:1832` is endpoint-only — no
    matching service helper exists for the soft-delete `is_included=False`
    path (the locked-roster hard-delete lives in
    `RosterService.remove_item_from_locked_roster` and is covered by
    `test_roster_item_removal_service.py`).
    """

    @pytest.mark.asyncio
    async def test_exclude_on_locked_roster_returns_400(self, admin_api_client, locked_roster_async):
        roster_id = locked_roster_async["id"]
        item_id = locked_roster_async["item_id"]
        resp = await admin_api_client.post(
            f"/api/v1/payment-rosters/{roster_id}/items/{item_id}/exclude",
            json={"reason_category": "declined"},
        )
        assert resp.status_code == 400
        # The global StarletteHTTPException handler in main.py wraps every
        # `HTTPException(detail=...)` into the ApiResponse envelope
        # `{"success": False, "message": <detail>, "trace_id": ...}` —
        # so we read `message`, not `detail`. The message names the lock
        # explicitly so the UI can surface "請先解鎖" hint cleanly.
        body = resp.json()
        assert body["success"] is False
        assert "鎖定" in body["message"]

    @pytest.mark.asyncio
    async def test_exclude_on_unlocked_roster_writes_audit_log(self, admin_api_client, completed_roster_async, db):
        from sqlalchemy import select

        roster_id = completed_roster_async["id"]
        item_id = completed_roster_async["item_id"]
        resp = await admin_api_client.post(
            f"/api/v1/payment-rosters/{roster_id}/items/{item_id}/exclude",
            json={"reason_category": "returned"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["is_included"] is False
        assert "學生繳回" in body["data"]["exclusion_reason"]

        # Audit row in roster_audit_logs (not the generic audit_logs table).
        stmt = select(RosterAuditLog).where(
            RosterAuditLog.roster_id == roster_id,
            RosterAuditLog.action == RosterAuditAction.ITEM_REMOVE,
        )
        result = await db.execute(stmt)
        logs = result.scalars().all()
        assert len(logs) == 1
        log = logs[0]
        assert log.old_values == {"is_included": True, "exclusion_reason": None}
        assert log.new_values["is_included"] is False
        assert log.affected_items_count == 1

        # And the item row itself was soft-updated (not deleted).
        item = await db.get(PaymentRosterItem, item_id)
        assert item is not None
        assert item.is_included is False

    @pytest.mark.asyncio
    async def test_exclude_other_category_requires_reason_note(self, admin_api_client, completed_roster_async):
        roster_id = completed_roster_async["id"]
        item_id = completed_roster_async["item_id"]
        # 'other' without `reason_note` is rejected at the endpoint guard
        # before the LOCKED check fires — pinned here so a future request-
        # shape change cannot silently accept partial payloads.
        resp = await admin_api_client.post(
            f"/api/v1/payment-rosters/{roster_id}/items/{item_id}/exclude",
            json={"reason_category": "other"},
        )
        assert resp.status_code == 400
        body = resp.json()
        # Same envelope wrapper as the LOCKED case — `message` not `detail`.
        assert body["success"] is False
        assert "reason_note" in body["message"]


# ---------------------------------------------------------------------------
# API-layer: delete guards (locked → 400, unlocked → 200 + row gone)
# ---------------------------------------------------------------------------


class TestDeleteGuards:
    """DELETE /{roster_id}

    Delete is endpoint-inline (`await db.delete(roster)` at
    `payment_rosters.py:1947`); the cascade on PaymentRoster.items takes
    care of detail rows + audit_logs.
    """

    @pytest.mark.asyncio
    async def test_delete_on_locked_roster_returns_400_and_keeps_row(self, admin_api_client, locked_roster_async, db):
        roster_id = locked_roster_async["id"]
        resp = await admin_api_client.delete(f"/api/v1/payment-rosters/{roster_id}")
        assert resp.status_code == 400

        # Row must still exist — guard is strictly preventative.
        survivor = await db.get(PaymentRoster, roster_id)
        assert survivor is not None
        assert survivor.status == RosterStatus.LOCKED

    @pytest.mark.asyncio
    async def test_delete_on_completed_roster_succeeds_and_removes_row(
        self, admin_api_client, completed_roster_async, db
    ):
        roster_id = completed_roster_async["id"]
        item_id = completed_roster_async["item_id"]
        resp = await admin_api_client.delete(f"/api/v1/payment-rosters/{roster_id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Row gone + cascade dropped its items.
        assert await db.get(PaymentRoster, roster_id) is None
        assert await db.get(PaymentRosterItem, item_id) is None


# ---------------------------------------------------------------------------
# Service-layer: re-generate after delete (no 409, fresh audit chain)
# ---------------------------------------------------------------------------


class TestRegenerateAfterDelete:
    """After deleting a roster, generating a new one for the same
    (config_id, period_label) succeeds — no AlreadyExists conflict.

    `_generate_roster_code` is deterministic
    (`ROSTER-{academic_year}-{period_label}-{config_code}`), so the new
    roster carries the **same `roster_code` string** as the deleted one. We
    assert what's actually fresh: a new primary-key id, a new audit chain,
    and `check_roster_exists` resolving to the new row.
    """

    def test_regenerate_after_delete_yields_fresh_row_and_audit_chain(self, db_sync, patch_dependencies):
        audit_mock = patch_dependencies["audit"]

        first, admin, config = _generate_completed_roster(
            db_sync,
            patch_dependencies,
            period_label="2024-06",
            config_code="LC-REGEN-113-1",
            nycu_id="regen_admin",
        )
        first_id = first.id
        first_code = first.roster_code

        # `audit_service` is patched, so the service never writes
        # RosterAuditLog rows during this test — observability comes from
        # the mock's call list. The first generation must have emitted
        # exactly one `log_roster_creation` call against `first_id`.
        first_creation_calls = [
            c for c in audit_mock.log_roster_creation.call_args_list if c.kwargs.get("roster_id") == first_id
        ]
        assert len(first_creation_calls) == 1, "First generation should have emitted one log_roster_creation call"
        # Reset so we can isolate the regenerate cycle's calls.
        audit_mock.reset_mock()

        # Cascade-delete the roster (mirrors the API DELETE path's
        # `await db.delete(roster)` at payment_rosters.py:1947).
        db_sync.delete(first)
        db_sync.commit()
        assert db_sync.get(PaymentRoster, first_id) is None

        # No conflict on the second generation — check_roster_exists returns
        # None because the row is gone (the unique key was released).
        svc = RosterService(db_sync)
        assert svc.check_roster_exists(config.id, "2024-06") is None

        regenerated = svc.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2024-06",
            roster_cycle=RosterCycle.MONTHLY,
            academic_year=113,
            created_by_user_id=admin.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=False,
        )
        db_sync.commit()

        # Deterministic roster_code is reused by design (_generate_roster_code
        # is pure of inputs that didn't change). The "fresh" property is that
        # `check_roster_exists` now resolves to the regenerated row — not the
        # deleted one (whose PK may or may not be reused depending on the
        # backend: SQLite reuses on an empty table, Postgres's SERIAL does
        # not, so we don't assert `regenerated.id != first_id` — that would
        # be a DB-engine-specific assertion, not a contract).
        assert regenerated.roster_code == first_code
        resolved = svc.check_roster_exists(config.id, "2024-06")
        assert resolved is not None
        assert resolved.id == regenerated.id
        # And the regenerated roster is in PROCESSING (fresh build state),
        # not COMPLETED/LOCKED carryover from the deleted predecessor.
        assert regenerated.status == RosterStatus.PROCESSING

        # Fresh audit chain — exactly one new log_roster_creation call
        # against the regenerated id, not the deleted one.
        regen_creation_calls = [
            c for c in audit_mock.log_roster_creation.call_args_list if c.kwargs.get("roster_id") == regenerated.id
        ]
        assert len(regen_creation_calls) == 1
        # And no `log_roster_operation(action=UPDATE)` against the
        # regenerated id — service.py:188 emits UPDATE only when an
        # existing_roster was reused. The CREATE branch firing instead
        # proves regenerate was treated as a genuine fresh build (no 409).
        update_calls = [
            c
            for c in audit_mock.log_roster_operation.call_args_list
            if c.kwargs.get("action") == RosterAuditAction.UPDATE and c.kwargs.get("roster_id") == regenerated.id
        ]
        assert update_calls == []

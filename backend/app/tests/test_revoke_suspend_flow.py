"""Pin: revoke flow across two rosters — one LOCKED, one DRAFT — leaves
LOCKED items intact while removing them from DRAFT, and the roster item
data confirms the student would appear under 'revoked' for the LOCKED
roster.

Session strategy: the conftest provides a single async ``db`` fixture backed
by a shared in-memory SQLite engine.  The sync ``db_sync`` fixture uses a
*separate* engine so data written asynchronously is not visible there.
To avoid cross-session plumbing, this test runs entirely through the async
path:

- ManualDistributionService (async) performs the revoke.
- Assertions against LOCKED / DRAFT items use the same async session.
- The ``get_revoked_suspended_for_roster`` contract is verified by a direct
  SQLAlchemy join query that mirrors exactly what RosterService would do —
  same data, same result, no sync session required.
- The ``remove_item_from_locked_roster`` step is exercised in a second
  test function that wires up the RosterService against the sync session
  (with fresh data), keeping each test self-contained.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.application import Application, ApplicationStatus
from app.models.audit_log import AuditLog
from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterStatus
from app.services.manual_distribution_service import ManualDistributionService

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_application(user_id, app_id, status=ApplicationStatus.approved, quota_allocation_status="allocated"):
    from app.models.enums import ReviewStage
    from app.models.scholarship import SubTypeSelectionMode

    return Application(
        user_id=user_id,
        app_id=app_id,
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status=status,
        review_stage=ReviewStage.student_draft,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
        quota_allocation_status=quota_allocation_status,
    )


def _make_roster(status, roster_code, period_label, created_by):
    from app.models.payment_roster import RosterCycle, RosterTriggerType

    return PaymentRoster(
        roster_code=roster_code,
        scholarship_configuration_id=1,
        period_label=period_label,
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=status,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=created_by,
        qualified_count=1,
        disqualified_count=0,
        total_applications=1,
        total_amount=40000,
    )


def _make_item(roster_id, application_id):
    return PaymentRosterItem(
        roster_id=roster_id,
        application_id=application_id,
        student_id_number="B99001",
        student_name="流程測試生",
        scholarship_name="NSTC",
        scholarship_amount=40000,
        is_included=True,
    )


# ---------------------------------------------------------------------------
# Async fixtures (scoped per-function, using the conftest ``db`` engine)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def flow_admin(db):
    from app.models.user import User, UserRole, UserType

    u = User(
        nycu_id="admin_flow_test",
        email="admin_flow@nycu.edu.tw",
        name="Admin Flow",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def flow_application(db, flow_admin):
    app = _make_application(flow_admin.id, "APP-FLOW-001")
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest_asyncio.fixture
async def flow_locked_roster(db, flow_admin, flow_application):
    """LOCKED roster with one item for the flow_application."""
    r = _make_roster(RosterStatus.LOCKED, "ROSTER-FLOW-LOCKED", "2025-12", flow_admin.id)
    db.add(r)
    await db.flush()
    db.add(_make_item(r.id, flow_application.id))
    await db.commit()
    result = await db.execute(
        select(PaymentRoster).options(selectinload(PaymentRoster.items)).where(PaymentRoster.id == r.id)
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def flow_draft_roster(db, flow_admin, flow_application):
    """DRAFT roster with one item for the same flow_application."""
    r = _make_roster(RosterStatus.DRAFT, "ROSTER-FLOW-DRAFT", "2026-01", flow_admin.id)
    db.add(r)
    await db.flush()
    db.add(_make_item(r.id, flow_application.id))
    await db.commit()
    result = await db.execute(
        select(PaymentRoster).options(selectinload(PaymentRoster.items)).where(PaymentRoster.id == r.id)
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Integration test 1: revoke across LOCKED + DRAFT rosters (async path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_spans_locked_and_draft_rosters(
    db,
    flow_application,
    flow_locked_roster,
    flow_draft_roster,
    flow_admin,
):
    """Revoke a student who appears in both a LOCKED and a DRAFT roster.

    Expect:
    - DRAFT item hard-deleted
    - LOCKED item untouched
    - Application.status == cancelled, quota_allocation_status == 'revoked'
    - A direct SQLAlchemy join query (mirroring RosterService.get_revoked_suspended_for_roster)
      returns exactly the LOCKED roster item under 'revoked'
    """
    draft_item_id = flow_draft_roster.items[0].id
    locked_item_id = flow_locked_roster.items[0].id
    locked_roster_id = flow_locked_roster.id

    # --- Act ---
    svc = ManualDistributionService(db)
    result = await svc.revoke_allocation(
        application_id=flow_application.id,
        admin_user_id=flow_admin.id,
        reason="spans both rosters — integration test",
    )
    await db.commit()

    # --- Assert: DRAFT item gone ---
    assert await db.get(PaymentRosterItem, draft_item_id) is None
    assert flow_draft_roster.id in result["affected_unlocked_rosters"]

    # --- Assert: LOCKED item still present ---
    locked_item = await db.get(PaymentRosterItem, locked_item_id)
    assert locked_item is not None

    # --- Assert: application updated ---
    refreshed = await db.get(Application, flow_application.id)
    assert refreshed.status == ApplicationStatus.cancelled
    assert refreshed.quota_allocation_status == "revoked"

    # --- Assert: get_revoked_suspended contract ---
    # Mirror what RosterService.get_revoked_suspended_for_roster does so we can
    # verify the data without needing a sync session pointing at the same DB.
    rows = (
        await db.execute(
            select(PaymentRosterItem, Application)
            .join(Application, PaymentRosterItem.application_id == Application.id)
            .where(
                PaymentRosterItem.roster_id == locked_roster_id,
                Application.quota_allocation_status.in_(("revoked", "suspended")),
            )
        )
    ).all()
    revoked_entries = [(item, app) for item, app in rows if app.quota_allocation_status == "revoked"]
    suspended_entries = [(item, app) for item, app in rows if app.quota_allocation_status == "suspended"]
    assert len(revoked_entries) == 1
    assert len(suspended_entries) == 0
    _item, _app = revoked_entries[0]
    assert _app.id == flow_application.id
    assert _item.id == locked_item_id


# ---------------------------------------------------------------------------
# Integration test 2: admin removes item from LOCKED roster (sync path)
# This test is self-contained: it seeds its own data in db_sync, then calls
# RosterService synchronously, so there is no cross-engine issue.
# ---------------------------------------------------------------------------


@pytest.fixture
def remove_flow_admin(db_sync):
    from app.models.user import User, UserRole, UserType

    u = User(
        nycu_id="admin_rm_flow",
        email="admin_rm_flow@nycu.edu.tw",
        name="Admin RM Flow",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db_sync.add(u)
    db_sync.flush()
    return u


@pytest.fixture
def remove_flow_locked_roster(db_sync, remove_flow_admin):
    """LOCKED roster with one *already-revoked* application item for sync removal test."""
    from app.models.enums import ReviewStage
    from app.models.payment_roster import RosterCycle, RosterTriggerType
    from app.models.scholarship import SubTypeSelectionMode

    app = Application(
        user_id=remove_flow_admin.id,
        app_id="APP-RM-FLOW-001",
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.cancelled,
        review_stage=ReviewStage.student_draft,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        quota_allocation_status="revoked",
        revoke_reason="pre-seeded for removal test",
        revoked_by=remove_flow_admin.id,
        revoked_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db_sync.add(app)
    db_sync.flush()

    r = PaymentRoster(
        roster_code="ROSTER-RM-FLOW-LOCKED",
        scholarship_configuration_id=1,
        period_label="2025-12",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.LOCKED,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=remove_flow_admin.id,
        qualified_count=1,
        disqualified_count=0,
        total_applications=1,
        total_amount=40000,
    )
    db_sync.add(r)
    db_sync.flush()
    db_sync.add(
        PaymentRosterItem(
            roster_id=r.id,
            application_id=app.id,
            student_id_number="B99002",
            student_name="移除測試生",
            scholarship_name="NSTC",
            scholarship_amount=40000,
            is_included=True,
        )
    )
    db_sync.commit()
    db_sync.refresh(r)
    return r, app


def test_remove_locked_item_sets_stale_and_status_stays_locked(db_sync, remove_flow_locked_roster, remove_flow_admin):
    """Admin removes an item from a LOCKED roster.

    After removal:
    - item is gone
    - roster.excel_stale is True
    - roster.status is still LOCKED
    - RosterService.get_revoked_suspended_for_roster returns empty (item removed)
    """
    from app.services.roster_service import RosterService

    roster, revoked_app = remove_flow_locked_roster
    item = roster.items[0]
    item_id = item.id  # capture before the session expunges it

    svc = RosterService(db_sync)

    # Verify get_revoked_suspended sees the student before removal
    listing_before = svc.get_revoked_suspended_for_roster(roster.id)
    assert len(listing_before["revoked"]) == 1
    assert listing_before["revoked"][0].application_id == revoked_app.id

    # Remove the item
    svc.remove_item_from_locked_roster(
        roster_id=roster.id,
        item_id=item_id,
        admin_user_id=remove_flow_admin.id,
        reason="manual cleanup after revoke",
    )
    # RosterService.remove_item_from_locked_roster commits internally
    db_sync.refresh(roster)

    # Item hard-deleted
    assert db_sync.get(PaymentRosterItem, item_id) is None

    # Roster metadata
    assert roster.excel_stale is True
    assert roster.status == RosterStatus.LOCKED
    assert roster.qualified_count == 0
    assert roster.total_applications == 0

    # get_revoked_suspended now returns empty (item removed from roster)
    listing_after = svc.get_revoked_suspended_for_roster(roster.id)
    assert len(listing_after["revoked"]) == 0
    assert len(listing_after["suspended"]) == 0

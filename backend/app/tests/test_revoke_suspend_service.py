"""Pin: revoke_allocation flips the right application columns, hard-deletes
non-LOCKED roster items, leaves LOCKED roster items alone, and writes an
audit log. Conflict + 400 paths surface as exceptions."""

import pytest
import pytest_asyncio
from datetime import datetime, timezone

from app.models.application import Application, ApplicationStatus
from app.models.audit_log import AuditLog
from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterStatus
from app.services.manual_distribution_service import ManualDistributionService

# ---------------------------------------------------------------------------
# Fixtures
# The conftest provides `db` as the async session (AsyncSession).
# The conftest's `admin_user` is a Mock object used for endpoint tests;
# we define `admin_db_user` here for a real DB-backed admin user.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_db_user(db):
    """Create a real DB-backed admin user for service tests."""
    from app.models.user import User, UserRole, UserType
    u = User(
        nycu_id="admin_svc_test",
        email="admin_svc@nycu.edu.tw",
        name="Admin Svc",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def allocated_application(db, admin_db_user):
    """An application in the post-finalize 'allocated' state.

    Note: scholarship_type_id and scholarship_configuration_id are FKs but
    SQLite in-memory testing does not enforce FK constraints by default, so
    we use id=1 as a placeholder without seeding those rows.
    """
    from app.models.scholarship import SubTypeSelectionMode
    from app.models.enums import ReviewStage
    app = Application(
        user_id=admin_db_user.id,
        app_id="APP-TEST-REVOKE-001",
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
    """An application without quota_allocation_status='allocated'."""
    from app.models.scholarship import SubTypeSelectionMode
    from app.models.enums import ReviewStage
    app = Application(
        user_id=admin_db_user.id,
        app_id="APP-TEST-REVOKE-002",
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


@pytest_asyncio.fixture
async def draft_roster_with_item(db, allocated_application, admin_db_user):
    """A DRAFT roster containing an item linked to allocated_application."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.payment_roster import RosterCycle, RosterTriggerType
    r = PaymentRoster(
        roster_code="ROSTER-TEST-DRAFT-SVC",
        scholarship_configuration_id=1,
        period_label="2026-01",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.DRAFT,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin_db_user.id,
    )
    item = PaymentRosterItem(
        roster=r,
        application_id=allocated_application.id,
        student_id_number="B12345",
        student_name="王小明",
        scholarship_name="NSTC",
        scholarship_amount=40000,
    )
    db.add_all([r, item])
    await db.commit()
    # Reload with items eagerly loaded so tests can access r.items[0] outside async context
    result = await db.execute(
        select(PaymentRoster)
        .options(selectinload(PaymentRoster.items))
        .where(PaymentRoster.id == r.id)
    )
    return result.scalar_one()


@pytest_asyncio.fixture
async def locked_roster_with_item(db, allocated_application, admin_db_user):
    """A LOCKED roster containing an item linked to allocated_application."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.payment_roster import RosterCycle, RosterTriggerType
    r = PaymentRoster(
        roster_code="ROSTER-TEST-LOCKED-SVC",
        scholarship_configuration_id=1,
        period_label="2025-12",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.LOCKED,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin_db_user.id,
    )
    item = PaymentRosterItem(
        roster=r,
        application_id=allocated_application.id,
        student_id_number="B12345",
        student_name="王小明",
        scholarship_name="NSTC",
        scholarship_amount=40000,
    )
    db.add_all([r, item])
    await db.commit()
    # Reload with items eagerly loaded so tests can access r.items[0] outside async context
    result = await db.execute(
        select(PaymentRoster)
        .options(selectinload(PaymentRoster.items))
        .where(PaymentRoster.id == r.id)
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Tests (6 as required by Task 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_sets_status_and_metadata(db, allocated_application, admin_db_user):
    svc = ManualDistributionService(db)
    await svc.revoke_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
        reason="violated terms",
    )
    await db.commit()
    await db.refresh(allocated_application)
    assert allocated_application.status == ApplicationStatus.cancelled
    assert allocated_application.quota_allocation_status == "revoked"
    assert allocated_application.revoke_reason == "violated terms"
    assert allocated_application.revoked_by == admin_db_user.id
    assert allocated_application.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_hard_deletes_items_from_non_locked_rosters(
    db, allocated_application, draft_roster_with_item, admin_db_user
):
    item_id = draft_roster_with_item.items[0].id
    svc = ManualDistributionService(db)
    result = await svc.revoke_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
        reason="x",
    )
    await db.commit()
    deleted = await db.get(PaymentRosterItem, item_id)
    assert deleted is None
    assert draft_roster_with_item.id in result["affected_unlocked_rosters"]


@pytest.mark.asyncio
async def test_revoke_leaves_locked_roster_items_intact(
    db, allocated_application, locked_roster_with_item, admin_db_user
):
    item_id = locked_roster_with_item.items[0].id
    svc = ManualDistributionService(db)
    await svc.revoke_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
        reason="x",
    )
    await db.commit()
    still_there = await db.get(PaymentRosterItem, item_id)
    assert still_there is not None


@pytest.mark.asyncio
async def test_revoke_twice_raises_conflict(db, allocated_application, admin_db_user):
    svc = ManualDistributionService(db)
    await svc.revoke_allocation(allocated_application.id, admin_db_user.id, "first")
    await db.commit()
    with pytest.raises(ValueError, match="already"):
        await svc.revoke_allocation(allocated_application.id, admin_db_user.id, "second")


@pytest.mark.asyncio
async def test_revoke_non_allocated_raises(db, unallocated_application, admin_db_user):
    svc = ManualDistributionService(db)
    with pytest.raises(ValueError, match="not.*allocated"):
        await svc.revoke_allocation(unallocated_application.id, admin_db_user.id, "x")


@pytest.mark.asyncio
async def test_revoke_writes_audit_log(db, allocated_application, admin_db_user):
    from sqlalchemy import select
    svc = ManualDistributionService(db)
    await svc.revoke_allocation(allocated_application.id, admin_db_user.id, "reason text")
    await db.commit()
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "application.revoke")
    )).scalars().all()
    assert len(rows) == 1
    log = rows[0]
    assert log.resource_id == str(allocated_application.id)
    assert log.user_id == admin_db_user.id
    assert log.new_values["reason"] == "reason text"
    assert "affected_unlocked_rosters" in log.new_values


# ---------------------------------------------------------------------------
# Task 4: Suspend-side coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suspend_sets_status_and_metadata(db, allocated_application, admin_db_user):
    svc = ManualDistributionService(db)
    await svc.suspend_allocation(allocated_application.id, admin_db_user.id, "leave")
    await db.commit()
    await db.refresh(allocated_application)
    assert allocated_application.status == ApplicationStatus.cancelled
    assert allocated_application.quota_allocation_status == "suspended"
    assert allocated_application.suspend_reason == "leave"
    assert allocated_application.suspended_by == admin_db_user.id


@pytest.mark.asyncio
async def test_suspend_then_revoke_raises_conflict(db, allocated_application, admin_db_user):
    svc = ManualDistributionService(db)
    await svc.suspend_allocation(allocated_application.id, admin_db_user.id, "first")
    await db.commit()
    with pytest.raises(ValueError, match="already"):
        await svc.revoke_allocation(allocated_application.id, admin_db_user.id, "second")


@pytest.mark.asyncio
async def test_suspend_writes_audit_log_with_suspend_action(db, allocated_application, admin_db_user):
    from sqlalchemy import select
    svc = ManualDistributionService(db)
    await svc.suspend_allocation(allocated_application.id, admin_db_user.id, "x")
    await db.commit()
    log = (await db.execute(
        select(AuditLog).where(AuditLog.action == "application.suspend")
    )).scalar_one()
    assert log.resource_id == str(allocated_application.id)

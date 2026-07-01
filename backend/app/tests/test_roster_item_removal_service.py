"""Pin: get_revoked_suspended_for_roster returns split lists per
quota_allocation_status; remove_item_from_locked_roster only works on
LOCKED rosters, recomputes totals, sets excel_stale, leaves status LOCKED,
and writes audit log."""

import pytest

from app.core.exceptions import RosterLockedError
from app.models.application import Application, ApplicationStatus
from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterStatus
from app.services.roster_service import RosterService

# ---------------------------------------------------------------------------
# Fixtures
# The conftest provides `db_sync` as a sync Session.
# We create a sync admin user here (no async needed for RosterService tests).
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_db_user_sync(db_sync):
    """Create a real DB-backed admin user for sync service tests."""
    from app.models.user import User, UserRole, UserType

    u = User(
        nycu_id="admin_roster_svc",
        email="admin_roster@nycu.edu.tw",
        name="Admin Roster Svc",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db_sync.add(u)
    db_sync.flush()
    return u


@pytest.fixture
def locked_roster_two_items(db_sync, admin_db_user_sync):
    from datetime import datetime, timezone

    from app.models.payment_roster import RosterCycle, RosterTriggerType
    from app.models.scholarship import SubTypeSelectionMode
    from app.models.enums import ReviewStage
    from app.models.user import User, UserRole, UserType

    # Create a second user so the unique constraint (user_id, scholarship_type_id,
    # academic_year, semester) is not violated across the two test applications.
    student2 = User(
        nycu_id="student_rs_002",
        email="student_rs_002@nycu.edu.tw",
        name="Student RS 002",
        role=UserRole.student,
        user_type=UserType.student,
    )
    db_sync.add(student2)
    db_sync.flush()

    a1 = Application(
        user_id=admin_db_user_sync.id,
        app_id="APP-TEST-RS-001",
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.cancelled,
        review_stage=ReviewStage.student_draft,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        quota_allocation_status="revoked",
        revoke_reason="bad",
        revoked_by=admin_db_user_sync.id,
        revoked_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    a2 = Application(
        user_id=student2.id,
        app_id="APP-TEST-RS-002",
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.cancelled,
        review_stage=ReviewStage.student_draft,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        quota_allocation_status="suspended",
        suspend_reason="leave",
        suspended_by=admin_db_user_sync.id,
        suspended_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    db_sync.add_all([a1, a2])
    db_sync.flush()

    r = PaymentRoster(
        roster_code="ROSTER-LOCK-RM-1",
        scholarship_configuration_id=1,
        period_label="2025-12",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.LOCKED,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin_db_user_sync.id,
        qualified_count=2,
        disqualified_count=0,
        total_applications=2,
        total_amount=80000,
    )
    db_sync.add(r)
    db_sync.flush()
    db_sync.add_all(
        [
            PaymentRosterItem(
                roster_id=r.id,
                application_id=a1.id,
                student_id_number="A123456789",
                student_name="W",
                scholarship_name="NSTC",
                scholarship_amount=40000,
                is_included=True,
            ),
            PaymentRosterItem(
                roster_id=r.id,
                application_id=a2.id,
                student_id_number="B987654321",
                student_name="L",
                scholarship_name="NSTC",
                scholarship_amount=40000,
                is_included=True,
            ),
        ]
    )
    db_sync.commit()
    db_sync.refresh(r)
    return r


def test_get_revoked_suspended_splits_by_status(db_sync, locked_roster_two_items):
    svc = RosterService(db_sync)
    out = svc.get_revoked_suspended_for_roster(locked_roster_two_items.id)
    assert len(out["revoked"]) == 1
    assert len(out["suspended"]) == 1
    # 身分證字號 is masked at the response boundary (keep first char + last 3),
    # so the needs-attention panel never receives the full national ID.
    assert out["revoked"][0].student_id_number == "A******789"
    assert out["suspended"][0].student_id_number == "B******321"


def test_remove_item_from_locked_roster_deletes_item_and_marks_stale(
    db_sync, locked_roster_two_items, admin_db_user_sync
):
    item = locked_roster_two_items.items[0]
    item_id = item.id  # capture before deletion expunges the object
    svc = RosterService(db_sync)
    svc.remove_item_from_locked_roster(
        roster_id=locked_roster_two_items.id,
        item_id=item_id,
        admin_user_id=admin_db_user_sync.id,
        reason="cleanup",
    )
    db_sync.commit()
    db_sync.refresh(locked_roster_two_items)
    refreshed = db_sync.get(PaymentRosterItem, item_id)
    assert refreshed is not None
    assert refreshed.is_included is False
    assert "鎖定後移除" in (refreshed.exclusion_reason or "")
    assert locked_roster_two_items.excel_stale is True
    assert locked_roster_two_items.status == RosterStatus.LOCKED
    assert locked_roster_two_items.qualified_count == 1
    # total_applications counts all rows (including soft-deleted); row survives
    assert locked_roster_two_items.total_applications == 2


def test_remove_suspended_item_from_locked_roster_deletes_item_and_marks_stale(
    db_sync, locked_roster_two_items, admin_db_user_sync
):
    """C2: a SUSPENDED student (not only revoked) can be removed from a LOCKED
    roster. remove_item_from_locked_roster is status-agnostic (deletes by
    item_id), so the suspend remove-path the new UI exposes behaves identically
    to the revoked one — recompute totals, set excel_stale, stay LOCKED."""
    suspended_item = next(i for i in locked_roster_two_items.items if i.student_id_number == "B987654321")
    item_id = suspended_item.id
    svc = RosterService(db_sync)
    svc.remove_item_from_locked_roster(
        roster_id=locked_roster_two_items.id,
        item_id=item_id,
        admin_user_id=admin_db_user_sync.id,
        reason="suspended cleanup",
    )
    db_sync.commit()
    db_sync.refresh(locked_roster_two_items)
    refreshed = db_sync.get(PaymentRosterItem, item_id)
    assert refreshed is not None
    assert refreshed.is_included is False
    assert "鎖定後移除" in (refreshed.exclusion_reason or "")
    assert locked_roster_two_items.excel_stale is True
    assert locked_roster_two_items.status == RosterStatus.LOCKED
    assert locked_roster_two_items.qualified_count == 1
    # total_applications counts all rows (including soft-deleted); row survives
    assert locked_roster_two_items.total_applications == 2


def test_remove_item_on_non_locked_roster_raises(db_sync, admin_db_user_sync):
    from app.models.payment_roster import RosterCycle, RosterTriggerType

    r = PaymentRoster(
        roster_code="ROSTER-DRAFT-RM-1",
        scholarship_configuration_id=1,
        period_label="2026-01",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.DRAFT,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin_db_user_sync.id,
    )
    db_sync.add(r)
    db_sync.flush()
    item = PaymentRosterItem(
        roster_id=r.id,
        application_id=1,
        student_id_number="X",
        student_name="X",
        scholarship_name="N",
        scholarship_amount=1,
    )
    db_sync.add(item)
    db_sync.commit()
    svc = RosterService(db_sync)
    with pytest.raises(RosterLockedError, match="LOCKED"):
        svc.remove_item_from_locked_roster(r.id, item.id, admin_db_user_sync.id, None)


def test_remove_item_writes_audit_log(db_sync, locked_roster_two_items, admin_db_user_sync):
    from app.models.roster_audit import RosterAuditAction, RosterAuditLog

    item = locked_roster_two_items.items[0]
    item_id = item.id
    svc = RosterService(db_sync)
    svc.remove_item_from_locked_roster(locked_roster_two_items.id, item_id, admin_db_user_sync.id, "cleanup")
    db_sync.commit()
    log = (
        db_sync.query(RosterAuditLog)
        .filter(
            RosterAuditLog.roster_id == locked_roster_two_items.id,
            RosterAuditLog.action == RosterAuditAction.ITEM_REMOVE,
        )
        .first()
    )
    assert log is not None
    assert log.audit_metadata["source"] == "locked_remove"


def test_remove_item_from_locked_roster_soft_deletes_and_audits(db_sync, locked_roster_two_items, admin_db_user_sync):
    from app.models.roster_audit import RosterAuditAction, RosterAuditLog

    roster = locked_roster_two_items
    target = roster.items[0]
    item_id = target.id
    svc = RosterService(db_sync)
    svc.remove_item_from_locked_roster(
        roster_id=roster.id, item_id=item_id, admin_user_id=admin_db_user_sync.id, reason="繳回"
    )
    refreshed = db_sync.get(PaymentRosterItem, item_id)
    assert refreshed is not None
    assert refreshed.is_included is False
    assert "鎖定後移除" in (refreshed.exclusion_reason or "")
    db_sync.refresh(roster)
    assert roster.status == RosterStatus.LOCKED
    assert roster.excel_stale is True
    log = (
        db_sync.query(RosterAuditLog)
        .filter(RosterAuditLog.roster_id == roster.id, RosterAuditLog.action == RosterAuditAction.ITEM_REMOVE)
        .first()
    )
    assert log is not None
    assert log.audit_metadata["source"] == "locked_remove"


def test_restore_item_reincludes_and_audits(db_sync, locked_roster_two_items, admin_db_user_sync):
    from app.models.roster_audit import RosterAuditAction, RosterAuditLog
    from app.models.payment_roster import PaymentRosterItem

    roster = locked_roster_two_items
    target = roster.items[0]
    # restore_item (#1081-K) only re-includes items whose application is still
    # approved. The shared fixture's application is cancelled/revoked, so put it in
    # the legitimate state this happy-path represents (the item was genuinely
    # re-approved and should be restored).
    app = db_sync.get(Application, target.application_id)
    app.status = ApplicationStatus.approved
    db_sync.flush()
    svc = RosterService(db_sync)
    svc.remove_item_from_locked_roster(roster.id, target.id, admin_db_user_sync.id, "繳回")

    result = svc.restore_item(roster.id, target.id, admin_db_user_sync.id, "誤刪回復")

    item = db_sync.get(PaymentRosterItem, target.id)
    assert item.is_included is True
    assert item.exclusion_reason is None
    db_sync.refresh(roster)
    assert roster.excel_stale is True  # locked roster → re-export needed
    log = (
        db_sync.query(RosterAuditLog)
        .filter(RosterAuditLog.roster_id == roster.id, RosterAuditLog.action == RosterAuditAction.ITEM_RESTORE)
        .first()
    )
    assert log is not None
    assert log.audit_metadata["source"] == "restore"
    assert result["excel_stale"] is True


def test_restore_item_rejects_already_included(db_sync, locked_roster_two_items, admin_db_user_sync):
    import pytest
    from app.core.exceptions import ConflictError

    roster = locked_roster_two_items
    svc = RosterService(db_sync)
    with pytest.raises(ConflictError):  # already included → 409
        svc.restore_item(roster.id, roster.items[0].id, admin_db_user_sync.id, "noop")


def test_restore_item_rejects_non_completed_or_locked_roster(db_sync, locked_roster_two_items, admin_db_user_sync):
    import pytest
    from app.models.payment_roster import RosterStatus

    roster = locked_roster_two_items
    target = roster.items[0]
    svc = RosterService(db_sync)
    # Soft-remove while LOCKED (allowed), then move roster to a non-restorable status.
    svc.remove_item_from_locked_roster(roster.id, target.id, admin_db_user_sync.id, "繳回")
    roster.status = RosterStatus.DRAFT
    db_sync.flush()
    with pytest.raises(ValueError):
        svc.restore_item(roster.id, target.id, admin_db_user_sync.id, "noop")


def test_restore_item_not_found_raises(db_sync, locked_roster_two_items, admin_db_user_sync):
    import pytest
    from app.core.exceptions import NotFoundError

    roster = locked_roster_two_items
    svc = RosterService(db_sync)
    with pytest.raises(NotFoundError):  # missing item → 404
        svc.restore_item(roster.id, 99999999, admin_db_user_sync.id, "x")


def test_restore_item_rejects_non_approved_application(db_sync, locked_roster_two_items, admin_db_user_sync):
    """SECURITY (#1081-K): an item whose application is no longer approved
    (withdrawn / rejected / revoked) must not be restorable — restoring it would
    silently re-inflate the student's received_months (PhD 36-month cap)."""
    import pytest

    roster = locked_roster_two_items
    target = roster.items[0]
    # The shared fixture leaves the application in `cancelled` (revoked) state.
    assert db_sync.get(Application, target.application_id).status == ApplicationStatus.cancelled
    svc = RosterService(db_sync)
    svc.remove_item_from_locked_roster(roster.id, target.id, admin_db_user_sync.id, "繳回")
    with pytest.raises(ValueError):
        svc.restore_item(roster.id, target.id, admin_db_user_sync.id, "誤刪回復")

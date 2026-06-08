"""Pin: _write_roster_item_audit emits one RosterAuditLog with operator
snapshot + structured audit_metadata."""

import pytest

from app.models.roster_audit import RosterAuditAction, RosterAuditLog
from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterStatus
from app.services.roster_service import RosterService

# ---------------------------------------------------------------------------
# Fixtures — duplicated from test_roster_item_removal_service.py so this
# file is self-contained and changes to the removal tests don't break here.
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_db_user_sync(db_sync):
    """Create a real DB-backed admin user for sync service tests."""
    from app.models.user import User, UserRole, UserType

    u = User(
        nycu_id="admin_audit_hlp",
        email="admin_audit_hlp@nycu.edu.tw",
        name="Admin Audit Helper",
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
    from app.models.application import Application, ApplicationStatus

    student2 = User(
        nycu_id="student_ah_002",
        email="student_ah_002@nycu.edu.tw",
        name="Student AH 002",
        role=UserRole.student,
        user_type=UserType.student,
    )
    db_sync.add(student2)
    db_sync.flush()

    a1 = Application(
        user_id=admin_db_user_sync.id,
        app_id="APP-TEST-AH-001",
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
        app_id="APP-TEST-AH-002",
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
        roster_code="ROSTER-AUDIT-HLP-1",
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
                student_id_number="C1",
                student_name="W",
                scholarship_name="NSTC",
                scholarship_amount=40000,
                is_included=True,
            ),
            PaymentRosterItem(
                roster_id=r.id,
                application_id=a2.id,
                student_id_number="C2",
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_write_roster_item_audit_records_metadata(db_sync, locked_roster_two_items, admin_db_user_sync):
    roster = locked_roster_two_items
    item = roster.items[0]
    svc = RosterService(db_sync)

    svc._write_roster_item_audit(
        roster_id=roster.id,
        action=RosterAuditAction.ITEM_REMOVE,
        item=item,
        admin_user_id=admin_db_user_sync.id,
        source="locked_remove",
        reason="測試移除",
    )
    db_sync.flush()

    log = (
        db_sync.query(RosterAuditLog)
        .filter(RosterAuditLog.roster_id == roster.id, RosterAuditLog.action == RosterAuditAction.ITEM_REMOVE)
        .order_by(RosterAuditLog.id.desc())
        .first()
    )
    assert log is not None
    assert log.user_id == admin_db_user_sync.id
    assert log.user_name == admin_db_user_sync.name
    assert log.audit_metadata["source"] == "locked_remove"
    assert log.audit_metadata["application_id"] == item.application_id
    assert log.audit_metadata["reason"] == "測試移除"
    assert log.affected_items_count == 1

"""G25 (#987): 學生領取歷史 must surface post-payment revocation context.

A student revoked AFTER the roster locked legitimately appears in payment
history (the disbursement was finalized) — but the row must carry the
revocation context instead of looking like an unqualified「已領取」.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.models.application import Application
from app.models.enums import ReviewStage
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.student_scholarship_history_service import (
    StudentScholarshipHistoryService,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

STUDENT_NO = "G25S001"


@pytest_asyncio.fixture
async def revoked_after_lock(db):
    admin = User(
        nycu_id="g25admin",
        name="G25 Admin",
        email="g25admin@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    student = User(
        nycu_id=STUDENT_NO,
        name="G25 學生",
        email="g25stu@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add_all([admin, student])
    await db.flush()
    stype = ScholarshipType(code="g25_test", name="G25 Test Scholarship")
    db.add(stype)
    await db.flush()
    cfg = ScholarshipConfiguration(
        config_code="G25-CFG",
        config_name="G25 Config",
        is_active=True,
        scholarship_type_id=stype.id,
        academic_year=114,
        amount=10000,
    )
    db.add(cfg)
    await db.flush()

    app_row = Application(
        app_id="APP-G25-RVK",
        user_id=student.id,
        scholarship_type_id=stype.id,
        scholarship_configuration_id=cfg.id,
        academic_year=114,
        status="cancelled",
        review_stage=ReviewStage.quota_distributed,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        quota_allocation_status="revoked",
        revoked_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        revoked_by=admin.id,
        revoke_reason="違反要點第七條",
    )
    db.add(app_row)
    await db.flush()

    roster = PaymentRoster(
        roster_code="G25-ROSTER",
        scholarship_configuration_id=cfg.id,
        period_label="114-02",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        trigger_type=RosterTriggerType.MANUAL,
        status=RosterStatus.LOCKED,
        created_by=admin.id,
    )
    db.add(roster)
    await db.flush()

    item = PaymentRosterItem(
        roster_id=roster.id,
        application_id=app_row.id,
        student_id_number=f"A{STUDENT_NO}",
        student_number=STUDENT_NO,
        student_name="G25 學生",
        scholarship_name="G25 Test Scholarship",
        scholarship_amount="10000",
        verification_status=StudentVerificationStatus.VERIFIED,
        is_included=True,
    )
    db.add(item)
    await db.commit()
    return app_row


async def test_revoked_after_lock_payment_carries_context(db, revoked_after_lock):
    svc = StudentScholarshipHistoryService()
    records, _ = await svc._fetch_paid_payments(db, STUDENT_NO)
    assert len(records) == 1
    rec = records[0]
    assert rec.quota_allocation_status == "revoked"
    assert rec.revoke_reason == "違反要點第七條"
    assert rec.revoked_at is not None
    assert rec.suspended_at is None

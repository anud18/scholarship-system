"""G15 (#977): soft-deleted applications must not leak into 學生領取歷史.

`_fetch_paid_payments` previously selected roster items by student_number
alone — an application that was soft-deleted AFTER its roster locked still
surfaced in the payment-history view. The fix outer-joins Application and
filters `deleted_at IS NULL`, while keeping items whose application row is
missing entirely (legacy/imported rows with dangling application_id) visible.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.models.application import Application
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.student_scholarship_history_service import (
    StudentScholarshipHistoryService,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

STUDENT_NO = "G15S001"


@pytest_asyncio.fixture
async def seeded(db):
    admin = User(
        nycu_id="g15admin",
        name="G15 Admin",
        email="g15admin@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    student = User(
        nycu_id=STUDENT_NO,
        name="G15 學生",
        email="g15stu@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add_all([admin, student])
    await db.flush()

    stype = ScholarshipType(code="g15_test", name="G15 Test Scholarship")
    db.add(stype)
    await db.flush()

    cfg = ScholarshipConfiguration(
        config_code="G15-CFG",
        config_name="G15 Config",
        is_active=True,
        scholarship_type_id=stype.id,
        academic_year=114,
        amount=10000,
    )
    db.add(cfg)
    await db.flush()

    def make_app(suffix: str, deleted: bool) -> Application:
        app = Application(
            app_id=f"APP-G15-{suffix}",
            user_id=student.id,
            scholarship_type_id=stype.id,
            scholarship_configuration_id=cfg.id,
            academic_year=114,
            sub_type_selection_mode="single",
            status="approved",
        )
        if deleted:
            app.status = "deleted"
            app.deleted_at = datetime.now(timezone.utc)
            app.deleted_by_id = admin.id
            app.deletion_reason = "G15 test soft delete"
        db.add(app)
        return app

    live_app = make_app("LIVE", deleted=False)
    dead_app = make_app("DEAD", deleted=True)
    await db.flush()

    roster = PaymentRoster(
        roster_code="G15-ROSTER",
        scholarship_configuration_id=cfg.id,
        period_label="114-10",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        trigger_type=RosterTriggerType.MANUAL,
        status=RosterStatus.LOCKED,
        created_by=admin.id,
    )
    db.add(roster)
    await db.flush()

    def make_item(application_id, name, amount):
        item = PaymentRosterItem(
            roster_id=roster.id,
            application_id=application_id,
            student_id_number=f"A{STUDENT_NO}",
            student_number=STUDENT_NO,
            student_name="G15 學生",
            scholarship_name=name,
            scholarship_amount=amount,
            verification_status=StudentVerificationStatus.VERIFIED,
            is_included=True,
        )
        db.add(item)
        return item

    make_item(live_app.id, "存活申請", "10000")
    make_item(dead_app.id, "已刪申請", "5000")
    # Dangling application_id (no Application row): legacy/imported items —
    # the outerjoin must KEEP these (SQLite test DB doesn't enforce the FK).
    make_item(987654321, "孤兒項目", "300")
    await db.commit()
    return {"live": live_app, "dead": dead_app}


async def test_soft_deleted_applications_payments_are_hidden(db, seeded):
    svc = StudentScholarshipHistoryService()
    records, snapshot_name = await svc._fetch_paid_payments(db, STUDENT_NO)
    names = {r.scholarship_name for r in records}
    assert "存活申請" in names
    assert "孤兒項目" in names, "items with a dangling application_id must stay visible"
    assert "已刪申請" not in names, "soft-deleted application's payment leaked into history (G15)"
    assert snapshot_name == "G15 學生"


async def test_undeleting_restores_visibility(db, seeded):
    # Sanity inverse: clearing deleted_at brings the payment back — proves the
    # filter keys on deleted_at, not on some incidental column.
    seeded["dead"].deleted_at = None
    seeded["dead"].status = "approved"
    await db.commit()

    svc = StudentScholarshipHistoryService()
    records, _ = await svc._fetch_paid_payments(db, STUDENT_NO)
    assert "已刪申請" in {r.scholarship_name for r in records}

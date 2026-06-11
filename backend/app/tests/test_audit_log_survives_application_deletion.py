"""G5 (#967): audit rows must survive application deletion, queryably.

The audit design stores attribution (scholarship_type_id / student_name /
app_id) in AuditLog.meta_data precisely so the trail keeps working after the
applications row is hard-deleted — but until now nothing pinned that
property end-to-end, so any refactor (an FK with CASCADE, an over-eager
cleanup) could silently destroy the legal trail. These tests delete real
application rows and assert the trail remains.

Also pins the FK delete policies from #979/#983 (G17/G21) at the model
level — the test DB does not enforce FKs, so the declared policy is the
testable contract and the alembic migration applies it to real databases.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.application import Application
from app.models.audit_log import AuditAction, AuditLog
from app.models.email_management import EmailHistory, ScheduledEmail
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.application_audit_service import ApplicationAuditService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def actors(db):
    admin = User(
        nycu_id="g5admin",
        name="G5 Admin",
        email="g5admin@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    student = User(
        nycu_id="g5stu001",
        name="G5 學生",
        email="g5stu@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add_all([admin, student])
    await db.flush()

    stype = ScholarshipType(code="g5_test", name="G5 Test Scholarship")
    db.add(stype)
    await db.flush()
    cfg = ScholarshipConfiguration(
        config_code="G5-CFG",
        config_name="G5 Config",
        is_active=True,
        scholarship_type_id=stype.id,
        academic_year=114,
        amount=1000,
    )
    db.add(cfg)
    await db.commit()
    return {"admin": admin, "student": student, "stype": stype, "cfg": cfg}


async def _make_application(db, actors, suffix: str) -> Application:
    app_row = Application(
        app_id=f"APP-G5-{suffix}",
        user_id=actors["student"].id,
        scholarship_type_id=actors["stype"].id,
        scholarship_configuration_id=actors["cfg"].id,
        academic_year=114,
        sub_type_selection_mode="single",
        status="draft",
    )
    db.add(app_row)
    await db.commit()
    await db.refresh(app_row)
    return app_row


async def _trail_for(db, application_db_id: int):
    res = await db.execute(
        select(AuditLog)
        .where(AuditLog.resource_type == "application", AuditLog.resource_id == str(application_db_id))
        .order_by(AuditLog.id)
    )
    return res.scalars().all()


async def test_audit_trail_survives_hard_delete(db, actors):
    app_row = await _make_application(db, actors, "HARD")
    app_db_id, app_id, stype_id = app_row.id, app_row.app_id, app_row.scholarship_type_id

    svc = ApplicationAuditService(db)
    await svc.log_application_create(
        application_id=app_db_id,
        app_id=app_id,
        user=actors["student"],
        scholarship_type=str(stype_id),
        is_draft=True,
    )
    await svc.log_delete_application(
        application_id=app_db_id,
        app_id=app_id,
        user=actors["admin"],
        reason="G5 hard-delete survival test",
        scholarship_type_id=stype_id,
        student_name="G5 學生",
    )

    # Hard-delete the application row itself.
    await db.delete(app_row)
    await db.commit()

    gone = await db.execute(select(Application).where(Application.id == app_db_id))
    assert gone.scalar_one_or_none() is None

    trail = await _trail_for(db, app_db_id)
    assert len(trail) == 2, "audit rows must survive the application hard-delete"
    actions = [row.action for row in trail]
    assert actions == [AuditAction.create.value, AuditAction.delete.value]

    delete_row = trail[-1]
    # Attribution must be reconstructable WITHOUT the applications row.
    assert delete_row.meta_data["app_id"] == app_id
    assert delete_row.meta_data["scholarship_type_id"] == stype_id
    assert delete_row.meta_data["student_name"] == "G5 學生"
    assert delete_row.meta_data["deletion_reason"] == "G5 hard-delete survival test"
    assert delete_row.user_id == actors["admin"].id


async def test_audit_trail_survives_soft_delete(db, actors):
    app_row = await _make_application(db, actors, "SOFT")
    app_db_id, app_id = app_row.id, app_row.app_id

    svc = ApplicationAuditService(db)
    await svc.log_delete_application(
        application_id=app_db_id,
        app_id=app_id,
        user=actors["admin"],
        reason="G5 soft-delete survival test",
        scholarship_type_id=app_row.scholarship_type_id,
        student_name="G5 學生",
    )

    app_row.status = "deleted"
    app_row.deleted_at = datetime.now(timezone.utc)
    app_row.deleted_by_id = actors["admin"].id
    app_row.deletion_reason = "G5 soft-delete survival test"
    await db.commit()

    trail = await _trail_for(db, app_db_id)
    assert len(trail) == 1
    assert trail[0].meta_data["deletion_reason"] == "G5 soft-delete survival test"


# ── FK delete-policy contracts (#979 G17 / #983 G21) ────────────────────
# The sqlite test DB doesn't enforce FKs, so the declared policy on the
# model metadata is the testable contract here; migration
# audit_evidence_fk_001 applies it to real databases.


def _fk_of(column):
    return next(iter(column.foreign_keys))


def test_email_history_application_fk_is_set_null():
    assert _fk_of(EmailHistory.__table__.c.application_id).ondelete == "SET NULL"


def test_scheduled_email_application_fk_is_set_null():
    assert _fk_of(ScheduledEmail.__table__.c.application_id).ondelete == "SET NULL"


def test_audit_log_user_fk_is_restrict_and_not_nullable():
    fk = _fk_of(AuditLog.__table__.c.user_id)
    assert fk.ondelete == "RESTRICT"
    assert AuditLog.__table__.c.user_id.nullable is False

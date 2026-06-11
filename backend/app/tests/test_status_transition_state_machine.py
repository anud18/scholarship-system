"""G16 (#978): PATCH-status transitions are validated by a state machine.

Previously any staff account could set ANY status (approved→draft,
submitted→approved without review, …) — the e2e suite even documented it.
Now: legal transitions pass; illegal ones need admin + a written reason;
draft/deleted are never settable here; reject/return/cancel clear
approved_at so「核准清單」period queries stay truthful.
"""

import pytest
import pytest_asyncio

from app.core.exceptions import ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.enums import ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.schemas.application import ApplicationStatusUpdate
from app.services.application_service import ApplicationService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def actors(db):
    admin = User(
        nycu_id="g16admin",
        name="G16 Admin",
        email="g16admin@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    professor = User(
        nycu_id="g16prof",
        name="G16 Prof",
        email="g16prof@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.professor,
    )
    student = User(
        nycu_id="g16stu001",
        name="G16 學生",
        email="g16stu@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add_all([admin, professor, student])
    await db.flush()
    stype = ScholarshipType(code="g16_test", name="G16 Test Scholarship")
    db.add(stype)
    await db.flush()
    cfg = ScholarshipConfiguration(
        config_code="G16-CFG",
        config_name="G16 Config",
        is_active=True,
        scholarship_type_id=stype.id,
        academic_year=114,
        amount=1000,
    )
    db.add(cfg)
    await db.commit()
    return {"admin": admin, "professor": professor, "student": student, "stype": stype, "cfg": cfg}


def _update(status, comments=None):
    return ApplicationStatusUpdate(status=status, comments=comments)


async def _make_app(db, actors, suffix, status):
    app_row = Application(
        app_id=f"APP-G16-{suffix}",
        user_id=actors["student"].id,
        scholarship_type_id=actors["stype"].id,
        scholarship_configuration_id=actors["cfg"].id,
        academic_year=114,
        status=status,
        review_stage=ReviewStage.student_submitted,
        sub_type_selection_mode=SubTypeSelectionMode.single,
    )
    db.add(app_row)
    await db.commit()
    await db.refresh(app_row)
    return app_row


async def test_legal_transition_submitted_to_returned(db, actors):
    app_row = await _make_app(db, actors, "LEGAL", "submitted")
    svc = ApplicationService(db)
    result = await svc.update_application_status(app_row.id, actors["admin"], _update("returned"))
    assert result is not None
    await db.refresh(app_row)
    assert app_row.status == ApplicationStatus.returned


async def test_illegal_transition_refused_for_non_admin(db, actors):
    app_row = await _make_app(db, actors, "PROF", "approved")
    svc = ApplicationService(db)
    with pytest.raises(ValidationError, match="不允許的狀態轉移"):
        await svc.update_application_status(app_row.id, actors["professor"], _update("submitted", "trying"))


async def test_illegal_transition_refused_for_admin_without_reason(db, actors):
    app_row = await _make_app(db, actors, "NOREASON", "rejected")
    svc = ApplicationService(db)
    with pytest.raises(ValidationError, match="不允許的狀態轉移"):
        await svc.update_application_status(app_row.id, actors["admin"], _update("approved"))


async def test_admin_override_with_reason_passes(db, actors):
    app_row = await _make_app(db, actors, "OVERRIDE", "rejected")
    svc = ApplicationService(db)
    await svc.update_application_status(
        app_row.id, actors["admin"], _update("approved", "申訴成功，依教務會議決議改核准")
    )
    await db.refresh(app_row)
    assert app_row.status == ApplicationStatus.approved
    assert app_row.approved_at is not None


async def test_draft_and_deleted_never_settable_even_by_admin(db, actors):
    svc = ApplicationService(db)
    for target in ("draft", "deleted"):
        app_row = await _make_app(db, actors, f"BAN-{target}", "submitted")
        with pytest.raises(ValidationError, match="不可經由狀態更新設定"):
            await svc.update_application_status(app_row.id, actors["admin"], _update(target, "even with reason"))


async def test_reject_clears_approved_at(db, actors):
    app_row = await _make_app(db, actors, "CLEAR", "submitted")
    svc = ApplicationService(db)
    await svc.update_application_status(app_row.id, actors["admin"], _update("approved"))
    await db.refresh(app_row)
    assert app_row.approved_at is not None

    # approved → rejected is an override (needs reason).
    await svc.update_application_status(app_row.id, actors["admin"], _update("rejected", "覆審不符資格"))
    await db.refresh(app_row)
    assert app_row.status == ApplicationStatus.rejected
    assert app_row.approved_at is None, "rejected applications must not keep approved_at (G16)"

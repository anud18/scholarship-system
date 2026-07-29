"""College-scope access control for applications (issue #1223 finding A).

`ApplicationService` lumped `UserRole.college` in with admin/super_admin and
applied NO college filter, so any authenticated 學院 user could reach any other
college's application by walking ids — reading it, and through the
update/status/delete/restore/assign/upload paths, WRITING it.

PR #1222 fixed exactly this class for the file proxy. These tests pin the same
rule across the application service, and pin the fail-closed edges that make the
rule safe: an unbound college account (no `college_code`) and an application with
no SIS snapshot both deny, rather than falling open to "see everything".
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService
from app.utils.college_scope import (
    college_user_may_access,
    get_application_college_code,
    get_user_college_code,
)

OWN_COLLEGE = "C"
OTHER_COLLEGE = "E"


# ---------------------------------------------------------------------------
# Pure helper contract
# ---------------------------------------------------------------------------


def _user(college_code):
    return User(
        nycu_id="u",
        name="u",
        email="u@u.edu",
        user_type=UserType.employee,
        role=UserRole.college,
        college_code=college_code,
    )


def _app(student_data):
    app = Application(app_id="APP-X", academic_year=114, sub_type_selection_mode="single")
    app.student_data = student_data
    return app


def test_matching_college_may_access():
    assert college_user_may_access(_user("C"), _app({"std_academyno": "C"})) is True


def test_mismatched_college_denied():
    assert college_user_may_access(_user("C"), _app({"std_academyno": "E"})) is False


@pytest.mark.parametrize("unbound", [None, "", "   "])
def test_unbound_college_user_denied(unbound):
    """A blank code must never satisfy the comparison — otherwise an unbound
    college account would match every application whose snapshot is also blank."""
    assert college_user_may_access(_user(unbound), _app({"std_academyno": "C"})) is False


@pytest.mark.parametrize("snapshot", [None, {}, {"std_academyno": ""}, {"std_cname": "no academy"}])
def test_application_without_resolvable_college_denied(snapshot):
    """Batch imports created during a SIS outage have no snapshot. Those rows are
    already invisible on every college LIST surface, so denying the read-by-id
    keeps the surfaces consistent instead of leaving a side channel."""
    assert college_user_may_access(_user("C"), _app(snapshot)) is False


@pytest.mark.parametrize("key", ["std_academyno", "academy_code", "college_code", "std_college"])
def test_every_fallback_key_is_honoured(key):
    """Key precedence must stay in lock-step with get_college_code_from_data, or an
    application is readable by id but missing from the list (or vice versa)."""
    assert college_user_may_access(_user("C"), _app({key: "C"})) is True


def test_code_extraction_helpers_normalise_whitespace():
    assert get_user_college_code(_user("  C  ")) == "C"
    assert get_application_college_code(_app({"std_academyno": "  C  "})) == "C"
    assert get_user_college_code(_user(None)) == ""
    assert get_application_college_code(_app(None)) == ""


# ---------------------------------------------------------------------------
# Service-level enforcement
# ---------------------------------------------------------------------------


async def _seed_user(db, *, role, nycu_id, college_code=None):
    u = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
        college_code=college_code,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _seed_config(db, *, suffix):
    st = ScholarshipType(code=f"cs_{suffix}", name=f"Type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"cs_cfg_{suffix}",
        config_name=f"Cfg {suffix}",
        academic_year=114,
        amount=0,
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def _seed_app(db, *, student, config, college_code, suffix, status=ApplicationStatus.under_review.value):
    app = Application(
        app_id=f"APP-CS-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        student_data={"std_academyno": college_code} if college_code else None,
        status=status,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.fixture
async def scoped(db: AsyncSession):
    """One application per college, plus a bound and an unbound college user."""
    cfg = await _seed_config(db, suffix="scope")
    own_student = await _seed_user(db, role=UserRole.student, nycu_id="cs_own_stu")
    other_student = await _seed_user(db, role=UserRole.student, nycu_id="cs_other_stu")
    return {
        "cfg": cfg,
        "college": await _seed_user(db, role=UserRole.college, nycu_id="cs_college_c", college_code=OWN_COLLEGE),
        "unbound": await _seed_user(db, role=UserRole.college, nycu_id="cs_college_none", college_code=None),
        "admin": await _seed_user(db, role=UserRole.admin, nycu_id="cs_admin"),
        "own_app": await _seed_app(db, student=own_student, config=cfg, college_code=OWN_COLLEGE, suffix="own"),
        "other_app": await _seed_app(db, student=other_student, config=cfg, college_code=OTHER_COLLEGE, suffix="other"),
    }


@pytest.mark.asyncio
async def test_college_can_read_own_college_application(db: AsyncSession, scoped):
    service = ApplicationService(db)
    result = await service._get_application_model(scoped["own_app"].id, scoped["college"])
    assert result is not None
    assert result.id == scoped["own_app"].id


@pytest.mark.asyncio
async def test_college_cannot_read_other_college_application(db: AsyncSession, scoped):
    """THE finding: walking ids across colleges. None -> the endpoints 404, which
    also avoids confirming that a hidden application id exists."""
    service = ApplicationService(db)
    assert await service._get_application_model(scoped["other_app"].id, scoped["college"]) is None


@pytest.mark.asyncio
async def test_unbound_college_user_can_read_nothing(db: AsyncSession, scoped):
    service = ApplicationService(db)
    assert await service._get_application_model(scoped["own_app"].id, scoped["unbound"]) is None
    assert await service._get_application_model(scoped["other_app"].id, scoped["unbound"]) is None


@pytest.mark.asyncio
async def test_admin_still_sees_every_college(db: AsyncSession, scoped):
    """The fix must not narrow admin — only college."""
    service = ApplicationService(db)
    assert await service._get_application_model(scoped["own_app"].id, scoped["admin"]) is not None
    assert await service._get_application_model(scoped["other_app"].id, scoped["admin"]) is not None


@pytest.mark.asyncio
async def test_review_queue_excludes_other_colleges(db: AsyncSession, scoped):
    service = ApplicationService(db)
    results = await service.get_applications_for_review(current_user=scoped["college"])
    returned = {r.id for r in results}
    assert scoped["own_app"].id in returned
    assert scoped["other_app"].id not in returned


@pytest.mark.asyncio
async def test_unbound_college_user_gets_empty_review_queue(db: AsyncSession, scoped):
    """Fail closed: an unbound account must see NOTHING, not everything."""
    service = ApplicationService(db)
    assert await service.get_applications_for_review(current_user=scoped["unbound"]) == []


@pytest.mark.asyncio
async def test_application_list_excludes_other_colleges(db: AsyncSession, scoped):
    service = ApplicationService(db)
    results = await service.get_applications(current_user=scoped["college"])
    returned = {r.id for r in results}
    assert scoped["own_app"].id in returned
    assert scoped["other_app"].id not in returned


@pytest.mark.asyncio
async def test_college_cannot_delete_other_college_application(db: AsyncSession, scoped):
    service = ApplicationService(db)
    with pytest.raises(AuthorizationError):
        await service.delete_application(scoped["other_app"].id, scoped["college"], reason="nope")


@pytest.mark.asyncio
async def test_college_delete_still_requires_a_reason_for_its_own_college(db: AsyncSession, scoped):
    """Splitting college out of the staff branch must not drop the mandatory
    deletion-reason rule."""
    from app.core.exceptions import ValidationError

    service = ApplicationService(db)
    with pytest.raises(ValidationError, match="reason"):
        await service.delete_application(scoped["own_app"].id, scoped["college"], reason=None)


@pytest.mark.asyncio
async def test_college_cannot_restore_other_college_application(db: AsyncSession, scoped):
    scoped["other_app"].status = ApplicationStatus.deleted
    await db.commit()

    service = ApplicationService(db)
    with pytest.raises(AuthorizationError):
        await service.restore_application(scoped["other_app"].id, scoped["college"])


@pytest.mark.asyncio
async def test_restore_still_denies_a_role_outside_the_allow_list(db: AsyncSession, scoped):
    """The deny-by-default catch-all must survive the college gate being added."""
    scoped["own_app"].status = ApplicationStatus.deleted
    await db.commit()
    outsider = await _seed_user(db, role=UserRole.student, nycu_id="cs_outsider")

    service = ApplicationService(db)
    with pytest.raises(AuthorizationError):
        await service.restore_application(scoped["own_app"].id, outsider)

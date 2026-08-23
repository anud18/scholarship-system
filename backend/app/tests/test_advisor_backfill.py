"""Advisor backfill: applications submitted before the advisor had an account.

`assign_professor_from_profile` runs at submission time and can only match an
advisor who already exists as a role=professor User. A student naming an advisor
who has never signed in produced an application with `professor_id IS NULL` that
reached nobody's review queue and stayed invisible until an admin noticed it.

Contract pinned here:

- `backfill_professor_assignments` claims exactly the orphaned, reviewable rows
  of THIS professor's advisees — never drafts, never someone else's advisees,
  never an application that already has a professor.
- It is a no-op for non-professor users (and safe on None).
- The professor review queue and the dashboard stats both apply the same claim,
  so an orphaned application surfaces on the professor's next load even when the
  account was created outside the SSO hook.
- Portal SSO login runs the claim for professor accounts.
"""

from datetime import datetime, timezone
from typing import Optional

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.models.user_profile import UserProfile
from app.services.application_builder import backfill_professor_assignments
from app.services.application_service import ApplicationService

PROF_NYCU_ID = "P900001"


async def _seed_user(db: AsyncSession, *, role: UserRole, nycu_id: str) -> User:
    user = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.student if role == UserRole.student else UserType.employee,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seed_student_with_advisor(db: AsyncSession, *, nycu_id: str, advisor_nycu_id: Optional[str]) -> User:
    student = await _seed_user(db, role=UserRole.student, nycu_id=nycu_id)
    db.add(UserProfile(user_id=student.id, advisor_nycu_id=advisor_nycu_id))
    await db.commit()
    return student


async def _seed_config(db: AsyncSession, *, suffix: str, requires_prof: bool = True) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"backfill_{suffix}", name=f"Backfill type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)

    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"backfill_cfg_{suffix}",
        config_name=f"Backfill cfg {suffix}",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        professor_review_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        professor_review_end=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=requires_prof,
        requires_college_review=False,
        amount=0,
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def _seed_app(
    db: AsyncSession,
    *,
    student: User,
    config: ScholarshipConfiguration,
    suffix: str,
    status: str = ApplicationStatus.submitted.value,
    professor_id: Optional[int] = None,
) -> Application:
    app = Application(
        app_id=f"APP-BACKFILL-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
        professor_id=professor_id,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def _professor_id_of(db: AsyncSession, application: Application) -> Optional[int]:
    """Read professor_id straight from the DB — the bulk UPDATE runs with
    synchronize_session=False, so the in-session object may be stale."""
    result = await db.execute(select(Application.professor_id).where(Application.id == application.id))
    return result.scalar_one()


# --- backfill_professor_assignments -----------------------------------------


@pytest.mark.asyncio
async def test_claims_orphaned_application_of_advisee(db: AsyncSession):
    student = await _seed_student_with_advisor(db, nycu_id="stu_claim", advisor_nycu_id=PROF_NYCU_ID)
    cfg = await _seed_config(db, suffix="claim")
    app = await _seed_app(db, student=student, config=cfg, suffix="claim")

    # The professor account appears only now — after the application was filed.
    professor = await _seed_user(db, role=UserRole.professor, nycu_id=PROF_NYCU_ID)

    claimed = await backfill_professor_assignments(db, professor)
    await db.commit()

    assert claimed == 1
    assert await _professor_id_of(db, app) == professor.id


@pytest.mark.asyncio
async def test_skips_drafts(db: AsyncSession):
    """A draft gets its professor at submission time from the profile as it
    reads then — claiming it early would pin a stale advisor."""
    student = await _seed_student_with_advisor(db, nycu_id="stu_draft", advisor_nycu_id=PROF_NYCU_ID)
    cfg = await _seed_config(db, suffix="draft")
    draft = await _seed_app(db, student=student, config=cfg, suffix="draft", status=ApplicationStatus.draft.value)
    professor = await _seed_user(db, role=UserRole.professor, nycu_id=PROF_NYCU_ID)

    claimed = await backfill_professor_assignments(db, professor)
    await db.commit()

    assert claimed == 0
    assert await _professor_id_of(db, draft) is None


@pytest.mark.parametrize(
    "status",
    [
        ApplicationStatus.approved.value,
        ApplicationStatus.partial_approved.value,
        ApplicationStatus.rejected.value,
    ],
)
@pytest.mark.asyncio
async def test_skips_already_decided_applications(db: AsyncSession, status: str):
    """A decided application would land in the professor's 待審核 bucket — which
    filters on "not reviewed by me", not on status — while the review endpoint
    refuses anything outside submitted/under_review. Claiming it would strand
    the row there with a permanent 403."""
    student = await _seed_student_with_advisor(db, nycu_id=f"stu_{status}", advisor_nycu_id=PROF_NYCU_ID)
    cfg = await _seed_config(db, suffix=status)
    app = await _seed_app(db, student=student, config=cfg, suffix=status, status=status)
    professor = await _seed_user(db, role=UserRole.professor, nycu_id=PROF_NYCU_ID)

    claimed = await backfill_professor_assignments(db, professor)
    await db.commit()

    assert claimed == 0
    assert await _professor_id_of(db, app) is None


@pytest.mark.asyncio
async def test_skips_soft_deleted_applications(db: AsyncSession):
    student = await _seed_student_with_advisor(db, nycu_id="stu_deleted", advisor_nycu_id=PROF_NYCU_ID)
    cfg = await _seed_config(db, suffix="deleted")
    app = await _seed_app(db, student=student, config=cfg, suffix="deleted")
    app.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    professor = await _seed_user(db, role=UserRole.professor, nycu_id=PROF_NYCU_ID)
    claimed = await backfill_professor_assignments(db, professor)
    await db.commit()

    assert claimed == 0
    assert await _professor_id_of(db, app) is None


@pytest.mark.asyncio
async def test_never_overwrites_an_existing_assignment(db: AsyncSession):
    student = await _seed_student_with_advisor(db, nycu_id="stu_taken", advisor_nycu_id=PROF_NYCU_ID)
    cfg = await _seed_config(db, suffix="taken")
    other_prof = await _seed_user(db, role=UserRole.professor, nycu_id="P900999")
    app = await _seed_app(db, student=student, config=cfg, suffix="taken", professor_id=other_prof.id)
    professor = await _seed_user(db, role=UserRole.professor, nycu_id=PROF_NYCU_ID)

    claimed = await backfill_professor_assignments(db, professor)
    await db.commit()

    assert claimed == 0
    assert await _professor_id_of(db, app) == other_prof.id


@pytest.mark.asyncio
async def test_ignores_applications_of_other_advisees(db: AsyncSession):
    mine = await _seed_student_with_advisor(db, nycu_id="stu_mine", advisor_nycu_id=PROF_NYCU_ID)
    theirs = await _seed_student_with_advisor(db, nycu_id="stu_theirs", advisor_nycu_id="P900888")
    no_advisor = await _seed_student_with_advisor(db, nycu_id="stu_none", advisor_nycu_id=None)
    cfg = await _seed_config(db, suffix="scope")

    mine_app = await _seed_app(db, student=mine, config=cfg, suffix="mine")
    theirs_app = await _seed_app(db, student=theirs, config=cfg, suffix="theirs")
    orphan_app = await _seed_app(db, student=no_advisor, config=cfg, suffix="none")

    professor = await _seed_user(db, role=UserRole.professor, nycu_id=PROF_NYCU_ID)
    claimed = await backfill_professor_assignments(db, professor)
    await db.commit()

    assert claimed == 1
    assert await _professor_id_of(db, mine_app) == professor.id
    assert await _professor_id_of(db, theirs_app) is None
    assert await _professor_id_of(db, orphan_app) is None


@pytest.mark.asyncio
async def test_accepts_raw_string_role(db: AsyncSession):
    """`role` reaches this helper as the enum member from a DB load but as a raw
    string from hand-built Users — both must count as a professor."""
    student = await _seed_student_with_advisor(db, nycu_id="stu_strrole", advisor_nycu_id=PROF_NYCU_ID)
    cfg = await _seed_config(db, suffix="strrole")
    app = await _seed_app(db, student=student, config=cfg, suffix="strrole")

    # No refresh() — that would replace the raw string with the enum member and
    # the test would stop covering what it is here to cover.
    professor = User(nycu_id=PROF_NYCU_ID, name="字串角色", user_type="employee", role="professor")
    db.add(professor)
    await db.commit()
    assert professor.role == "professor"

    assert await backfill_professor_assignments(db, professor) == 1
    await db.commit()
    assert await _professor_id_of(db, app) == professor.id


@pytest.mark.asyncio
async def test_no_op_for_non_professor_users(db: AsyncSession):
    student = await _seed_student_with_advisor(db, nycu_id="stu_nonprof", advisor_nycu_id="ADMIN01")
    cfg = await _seed_config(db, suffix="nonprof")
    app = await _seed_app(db, student=student, config=cfg, suffix="nonprof")

    # Same nycu_id the student named, but the account is not a professor.
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="ADMIN01")

    assert await backfill_professor_assignments(db, admin) == 0
    assert await backfill_professor_assignments(db, None) == 0
    assert await _professor_id_of(db, app) is None


# --- professor-facing queries (fallback advisor match) -----------------------


@pytest.mark.asyncio
async def test_review_queue_surfaces_previously_orphaned_application(db: AsyncSession):
    """The reported bug: student submits, advisor has no account, application
    never appears for the professor. Opening the queue must now surface it."""
    student = await _seed_student_with_advisor(db, nycu_id="stu_queue", advisor_nycu_id=PROF_NYCU_ID)
    cfg = await _seed_config(db, suffix="queue")
    app = await _seed_app(db, student=student, config=cfg, suffix="queue")
    professor = await _seed_user(db, role=UserRole.professor, nycu_id=PROF_NYCU_ID)

    service = ApplicationService(db)
    applications, total = await service.get_professor_applications_paginated(professor_id=professor.id)

    assert total == 1
    assert [a.app_id for a in applications] == [app.app_id]
    assert await _professor_id_of(db, app) == professor.id


@pytest.mark.asyncio
async def test_review_stats_count_previously_orphaned_application(db: AsyncSession):
    student = await _seed_student_with_advisor(db, nycu_id="stu_stats", advisor_nycu_id=PROF_NYCU_ID)
    cfg = await _seed_config(db, suffix="stats")
    await _seed_app(db, student=student, config=cfg, suffix="stats")
    professor = await _seed_user(db, role=UserRole.professor, nycu_id=PROF_NYCU_ID)

    service = ApplicationService(db)
    stats = await service.get_professor_review_stats(professor.id)

    assert stats["pending_reviews"] == 1


# --- Portal SSO login hook ---------------------------------------------------


@pytest.mark.asyncio
async def test_portal_sso_login_claims_pending_applications(db: AsyncSession, monkeypatch):
    """First SSO login creates the professor account — and adopts the
    applications that were waiting for it."""
    from app.services.portal_sso_service import PortalSSOService

    student = await _seed_student_with_advisor(db, nycu_id="stu_sso", advisor_nycu_id=PROF_NYCU_ID)
    cfg = await _seed_config(db, suffix="sso")
    app = await _seed_app(db, student=student, config=cfg, suffix="sso")

    service = PortalSSOService(db)

    async def _fake_verify(_token: str) -> dict:
        return {
            "txtID": PROF_NYCU_ID,
            "nycuID": PROF_NYCU_ID,
            "txtName": "王教授",
            "mail": "prof@nycu.edu.tw",
            "dept": "資訊工程學系",
            "deptCode": "5743",
            "userType": "employee",
            "employeestatus": "在職",
        }

    async def _fake_student_status(_nycu_id: str):
        return False, None

    monkeypatch.setattr(service, "verify_portal_token", _fake_verify)
    monkeypatch.setattr(service, "_verify_student_status", _fake_student_status)

    await service.process_portal_login("irrelevant-token")

    professor = (await db.execute(select(User).where(User.nycu_id == PROF_NYCU_ID))).scalar_one()
    assert professor.role == UserRole.professor
    assert await _professor_id_of(db, app) == professor.id


# --- best-effort contract: a failing claim must not take the caller down ----
#
# The claim's failure must roll back ONLY the claim. A session-level rollback()
# expires every loaded ORM object (expire_on_commit=False governs commit only),
# and the caller's next attribute read on `user` / `current_user` then needs a
# lazy refresh → MissingGreenlet under AsyncSession → HTTP 400/500 in exactly
# the situation the best-effort handlers exist to absorb.


async def _failing_backfill(db: AsyncSession, _professor):
    """Stand-in for a claim that dies mid-transaction (timeout, deadlock...)."""
    from sqlalchemy import text

    await db.execute(text("UPDATE no_such_table SET x = 1"))


@pytest.mark.asyncio
async def test_failed_claim_does_not_break_the_review_queue(db: AsyncSession, monkeypatch):
    import app.services.application_service as application_service_module

    professor = await _seed_user(db, role=UserRole.professor, nycu_id=PROF_NYCU_ID)
    student = await _seed_student_with_advisor(db, nycu_id="stu_qfail", advisor_nycu_id=PROF_NYCU_ID)
    cfg = await _seed_config(db, suffix="qfail")
    assigned = await _seed_app(db, student=student, config=cfg, suffix="qfail", professor_id=professor.id)
    # What the endpoint holds: the current_user loaded in this same session.
    current_user = await db.get(User, professor.id)

    monkeypatch.setattr(application_service_module, "backfill_professor_assignments", _failing_backfill)

    service = ApplicationService(db)
    applications, total = await service.get_professor_applications_paginated(professor_id=professor.id)
    stats = await service.get_professor_review_stats(professor.id)

    assert [a.app_id for a in applications] == [assigned.app_id]
    assert total == 1
    assert stats["pending_reviews"] == 1
    # The endpoint logs / serialises current_user after the call — must not raise.
    assert (current_user.id, current_user.nycu_id) == (professor.id, PROF_NYCU_ID)


@pytest.mark.asyncio
async def test_failed_claim_does_not_block_portal_sso_login(db: AsyncSession, monkeypatch):
    import app.services.portal_sso_service as portal_sso_module
    from app.services.portal_sso_service import PortalSSOService

    monkeypatch.setattr(portal_sso_module, "backfill_professor_assignments", _failing_backfill)

    service = PortalSSOService(db)

    async def _fake_verify(_token: str) -> dict:
        return {
            "txtID": PROF_NYCU_ID,
            "nycuID": PROF_NYCU_ID,
            "txtName": "王教授",
            "mail": "prof@nycu.edu.tw",
            "dept": "資訊工程學系",
            "deptCode": "5743",
            "userType": "employee",
            "employeestatus": "在職",
        }

    async def _fake_student_status(_nycu_id: str):
        return False, None

    monkeypatch.setattr(service, "verify_portal_token", _fake_verify)
    monkeypatch.setattr(service, "_verify_student_status", _fake_student_status)

    result = await service.process_portal_login("irrelevant-token")

    assert result["access_token"]
    professor = (await db.execute(select(User).where(User.nycu_id == PROF_NYCU_ID))).scalar_one()
    assert professor.role == UserRole.professor

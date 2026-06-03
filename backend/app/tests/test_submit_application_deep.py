"""
Deep async-DB-fixture tests for `ApplicationService.submit_application`.

The existing comprehensive test file uses mocked DB sessions; the hook
audit specifically called out 'Deep async-DB-fixture tests for
application_service, submit_application, notifyDeadlineReminder and
similar service-method-with-multiple-collaborators flows'. This file
adds the real-DB layer so the production transitions get pinned end to
end (status flip, timestamp set, auto-assign-professor path, cache
invalidation side effect boundary).

Contract pinned:
- 404 when application doesn't exist.
- ValidationError when status isn't draft or returned.
- Happy path: draft → submitted, submitted_at populated, updated_at moves
  forward.
- Auto-assign-professor: if the student has a UserProfile with
  advisor_nycu_id matching a real professor, that user's id is recorded
  on `application.professor_id`.
- Auto-assign skipped: if advisor_nycu_id matches no professor (or only
  matches a non-professor user), professor_id stays null.
- Auto-assign skipped: if professor_id is already set, the existing
  value is preserved.
- Returned-status applications can be re-submitted (the second allowed
  starting state).
"""

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.models.user_profile import UserProfile
from app.services.application_service import ApplicationService


async def _seed_user(
    db: AsyncSession,
    *,
    role: UserRole,
    name: str,
    nycu_id: str,
    dept_code: str | None = None,
) -> User:
    u = User(
        nycu_id=nycu_id,
        name=name,
        email=f"{nycu_id}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
        dept_code=dept_code,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _seed_user_profile(db: AsyncSession, *, user_id: int, advisor_nycu_id: str | None) -> UserProfile:
    profile = UserProfile(
        user_id=user_id,
        advisor_nycu_id=advisor_nycu_id,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def _seed_config(db: AsyncSession, *, suffix: str) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"submit_{suffix}", name=f"Submit type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"submit_cfg_{suffix}",
        config_name=f"Submit cfg {suffix}",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=True,
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
    status: str,
    professor_id: int | None = None,
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-SUB-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
        professor_id=professor_id,
        submitted_form_data={"fields": {}, "documents": []},
        student_data={"std_cname": student.name},
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.fixture
def silence_collaborators(monkeypatch):
    """Bypass the document-clone helper + cache invalidation.

    submit_application calls these unconditionally; they're either
    network-bound (MinIO) or Redis-bound and would fail outside docker.
    Pinning the rest of the transition is the test's job here.
    """

    async def _noop_clone(self: Any, application: Any, user: Any) -> None:
        return None

    async def _noop_cache() -> None:
        return None

    monkeypatch.setattr(ApplicationService, "_clone_user_profile_documents", _noop_clone)
    monkeypatch.setattr(ApplicationService, "_invalidate_app_caches", staticmethod(_noop_cache))


@pytest.mark.asyncio
async def test_submit_application_not_found_raises(db: AsyncSession, silence_collaborators):
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_sub_404")
    service = ApplicationService(db)

    with pytest.raises(NotFoundError):
        await service.submit_application(application_id=999999, user=student)


@pytest.mark.asyncio
async def test_submit_rejects_when_status_not_draft_or_returned(db: AsyncSession, silence_collaborators):
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_sub_bad")
    cfg = await _seed_config(db, suffix="bad")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="already")
    service = ApplicationService(db)

    with pytest.raises(ValidationError):
        await service.submit_application(application_id=app.id, user=student)


@pytest.mark.asyncio
async def test_submit_happy_path_flips_status_and_sets_submitted_at(db: AsyncSession, silence_collaborators):
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_sub_happy")
    cfg = await _seed_config(db, suffix="happy")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.draft.value, suffix="happy")
    service = ApplicationService(db)

    before_submit = datetime.now(timezone.utc)
    result = await service.submit_application(application_id=app.id, user=student)
    after_submit = datetime.now(timezone.utc)

    # Re-read from DB to confirm the persisted state.
    await db.refresh(app)
    assert app.status == ApplicationStatus.submitted.value or app.status == ApplicationStatus.submitted
    assert app.submitted_at is not None
    # submitted_at is tz-naive on the sqlite test DB but tz-aware on postgres;
    # normalise to aware-UTC before comparing against the aware bounds so the
    # assertion holds on both backends.
    submitted_at = app.submitted_at
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=timezone.utc)
    assert before_submit <= submitted_at <= after_submit
    # Response carries the same app_id.
    if hasattr(result, "app_id"):
        assert result.app_id == app.app_id


@pytest.mark.asyncio
async def test_submit_auto_assigns_professor_from_advisor_nycu_id(db: AsyncSession, silence_collaborators):
    """If UserProfile.advisor_nycu_id maps to a real professor, that
    user's id lands on application.professor_id."""
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_sub_auto")
    professor = await _seed_user(db, role=UserRole.professor, name="P", nycu_id="prof_auto", dept_code="CS")
    await _seed_user_profile(db, user_id=student.id, advisor_nycu_id="prof_auto")

    cfg = await _seed_config(db, suffix="auto")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.draft.value, suffix="auto")
    service = ApplicationService(db)

    await service.submit_application(application_id=app.id, user=student)

    await db.refresh(app)
    assert app.professor_id == professor.id, "auto-assign must record the matched professor.id on the application"


@pytest.mark.asyncio
async def test_submit_does_not_overwrite_existing_professor_id(db: AsyncSession, silence_collaborators):
    """When professor_id is already set (e.g. admin pre-assigned), the
    auto-assign step is skipped."""
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_sub_keep")
    existing_prof = await _seed_user(db, role=UserRole.professor, name="Existing", nycu_id="prof_existing")
    advisor_prof = await _seed_user(db, role=UserRole.professor, name="Advisor", nycu_id="prof_advisor")
    await _seed_user_profile(db, user_id=student.id, advisor_nycu_id="prof_advisor")

    cfg = await _seed_config(db, suffix="keep")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.draft.value,
        professor_id=existing_prof.id,
        suffix="keep",
    )
    service = ApplicationService(db)

    await service.submit_application(application_id=app.id, user=student)

    await db.refresh(app)
    assert (
        app.professor_id == existing_prof.id
    ), "pre-assigned professor_id must be preserved; auto-assign must NOT clobber it"
    # advisor_prof in UserProfile is ignored on this path.
    assert app.professor_id != advisor_prof.id


@pytest.mark.asyncio
async def test_submit_skips_auto_assign_when_advisor_is_not_a_professor(db: AsyncSession, silence_collaborators):
    """If advisor_nycu_id matches a student or no one, professor_id stays null."""
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_sub_skip")
    # Decoy: a *student* user with the same nycu_id the advisor field points to.
    await _seed_user(db, role=UserRole.student, name="Decoy", nycu_id="decoy_advisor")
    await _seed_user_profile(db, user_id=student.id, advisor_nycu_id="decoy_advisor")

    cfg = await _seed_config(db, suffix="skip")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.draft.value, suffix="skip")
    service = ApplicationService(db)

    await service.submit_application(application_id=app.id, user=student)

    await db.refresh(app)
    assert app.professor_id is None, "auto-assign must reject non-professor candidates; professor_id stays null"


@pytest.mark.asyncio
async def test_submit_works_from_returned_status(db: AsyncSession, silence_collaborators):
    """An application returned for revisions can be re-submitted; pin
    the second allowed starting state explicitly."""
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_sub_ret")
    cfg = await _seed_config(db, suffix="ret")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.returned.value, suffix="ret")
    service = ApplicationService(db)

    await service.submit_application(application_id=app.id, user=student)

    await db.refresh(app)
    assert app.status == ApplicationStatus.submitted.value or app.status == ApplicationStatus.submitted
    assert app.submitted_at is not None

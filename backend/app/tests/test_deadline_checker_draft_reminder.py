"""Tests for the one surviving scheduled reminder: draft + 3 days before deadline.

Pins the second of the system's three email trigger points:

    學生：狀態在暫存未送出（draft）且在申請截止日前三天

Contract pinned here:
- Fires at exactly 3 days out, not at 7 or 1 (the old WARNING_DAYS ladder).
- Only ``status = draft`` qualifies. The previous implementation also named
  ``ApplicationStatus.in_progress``, which does not exist on the enum — that
  raised AttributeError and took the whole daily job down, so a regression test
  for "draft only" is also the regression test for that crash.
- A renewal draft is matched against ``renewal_application_end_date`` and a
  general draft against ``application_end_date`` — never crosswise.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.email_automation_service import email_automation_service
from app.tasks.deadline_checker import DeadlineChecker


def _deadline_in(days: int) -> datetime:
    """A deadline `days` out, anchored at NOON of that day.

    The checker builds a window covering the whole UTC day that is N days from
    *its own* now(). Anchoring at noon — and computing it per call rather than
    once at import — keeps the value well inside that window no matter when in
    the day the suite runs or how long it takes to reach this test.
    """
    target = datetime.now(timezone.utc) + timedelta(days=days)
    return target.replace(hour=12, minute=0, second=0, microsecond=0)


@pytest.fixture
def captured_triggers(monkeypatch) -> List[Dict[str, Any]]:
    """Record trigger_deadline_approaching calls instead of queueing mail."""
    calls: List[Dict[str, Any]] = []

    async def _record(db, application_id: int, deadline_data: Dict[str, Any]) -> None:
        calls.append({"application_id": application_id, **deadline_data})

    monkeypatch.setattr(email_automation_service, "trigger_deadline_approaching", _record)
    return calls


def _for_app(calls: List[Dict[str, Any]], application: Application) -> List[Dict[str, Any]]:
    """Only the reminders for *application*.

    Scoped rather than asserting on the total: check_submission_deadlines scans
    every active config in the database, so a global count would couple this
    test to whatever else happens to be seeded.
    """
    return [c for c in calls if c["application_id"] == application.id]


async def _seed_student(db: AsyncSession, nycu_id: str) -> User:
    user = User(
        nycu_id=nycu_id,
        name=f"Student {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seed_config(
    db: AsyncSession,
    *,
    suffix: str,
    application_end_date: datetime | None = None,
    renewal_application_end_date: datetime | None = None,
) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"dl_{suffix}", name=f"Deadline type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)

    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"dl_cfg_{suffix}",
        config_name=f"Deadline cfg {suffix}",
        academic_year=114,
        application_start_date=datetime.now(timezone.utc) - timedelta(days=30),
        application_end_date=application_end_date,
        renewal_application_end_date=renewal_application_end_date,
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
    status: str = ApplicationStatus.draft.value,
    is_renewal: bool = False,
) -> Application:
    app = Application(
        app_id=f"APP-DL-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=config.academic_year,
        semester=config.semester,
        sub_type_selection_mode="single",
        status=status,
        is_renewal=is_renewal,
        student_data={"std_cname": student.name},
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.mark.asyncio
async def test_draft_is_reminded_three_days_before_general_deadline(db: AsyncSession, captured_triggers):
    student = await _seed_student(db, "dl_hit")
    cfg = await _seed_config(db, suffix="hit", application_end_date=_deadline_in(3))
    app = await _seed_app(db, student=student, config=cfg, suffix="hit")

    await DeadlineChecker(db).check_submission_deadlines()

    mine = _for_app(captured_triggers, app)
    assert len(mine) == 1
    assert mine[0]["deadline_type"] == "submission"
    assert mine[0]["days_remaining"] == "3"


@pytest.mark.asyncio
async def test_no_reminder_seven_days_out(db: AsyncSession, captured_triggers):
    student = await _seed_student(db, "dl_seven")
    cfg = await _seed_config(db, suffix="seven", application_end_date=_deadline_in(7))
    app = await _seed_app(db, student=student, config=cfg, suffix="seven")

    await DeadlineChecker(db).check_submission_deadlines()

    assert _for_app(captured_triggers, app) == []


@pytest.mark.asyncio
async def test_no_reminder_one_day_out(db: AsyncSession, captured_triggers):
    student = await _seed_student(db, "dl_one")
    cfg = await _seed_config(db, suffix="one", application_end_date=_deadline_in(1))
    app = await _seed_app(db, student=student, config=cfg, suffix="one")

    await DeadlineChecker(db).check_submission_deadlines()

    assert _for_app(captured_triggers, app) == []


@pytest.mark.asyncio
async def test_submitted_application_is_not_reminded(db: AsyncSession, captured_triggers):
    """Only 暫存未送出 qualifies — a submitted application already made it."""
    student = await _seed_student(db, "dl_submitted")
    cfg = await _seed_config(db, suffix="submitted", application_end_date=_deadline_in(3))
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        suffix="submitted",
        status=ApplicationStatus.submitted.value,
    )

    await DeadlineChecker(db).check_submission_deadlines()

    assert _for_app(captured_triggers, app) == []


@pytest.mark.asyncio
async def test_renewal_draft_matches_renewal_deadline_only(db: AsyncSession, captured_triggers):
    """A renewal draft answers to renewal_application_end_date, not the general one."""
    renewal_student = await _seed_student(db, "dl_renewal")
    general_student = await _seed_student(db, "dl_general")

    # Renewal closes in 3 days; the general deadline is far away.
    cfg = await _seed_config(
        db,
        suffix="split",
        application_end_date=_deadline_in(30),
        renewal_application_end_date=_deadline_in(3),
    )
    renewal_app = await _seed_app(db, student=renewal_student, config=cfg, suffix="renewal", is_renewal=True)
    general_app = await _seed_app(db, student=general_student, config=cfg, suffix="general", is_renewal=False)

    await DeadlineChecker(db).check_submission_deadlines()

    mine = _for_app(captured_triggers, renewal_app)
    assert len(mine) == 1
    assert mine[0]["deadline_type"] == "renewal_submission"
    # The general draft under the same config must NOT be pulled in.
    assert _for_app(captured_triggers, general_app) == []


@pytest.mark.asyncio
async def test_general_draft_not_reminded_by_renewal_deadline(db: AsyncSession, captured_triggers):
    student = await _seed_student(db, "dl_cross")
    cfg = await _seed_config(
        db,
        suffix="cross",
        application_end_date=_deadline_in(30),
        renewal_application_end_date=_deadline_in(3),
    )
    app = await _seed_app(db, student=student, config=cfg, suffix="cross", is_renewal=False)

    await DeadlineChecker(db).check_submission_deadlines()

    assert _for_app(captured_triggers, app) == []


@pytest.mark.asyncio
async def test_check_all_deadlines_runs_clean_with_a_matching_config(db: AsyncSession, captured_triggers):
    """Regression: the old ApplicationStatus.in_progress reference raised
    AttributeError as soon as any config's deadline landed on a boundary,
    which aborted the whole daily job."""
    student = await _seed_student(db, "dl_all")
    cfg = await _seed_config(db, suffix="all", application_end_date=_deadline_in(3))
    app = await _seed_app(db, student=student, config=cfg, suffix="all")

    await DeadlineChecker(db).check_all_deadlines()

    assert len(_for_app(captured_triggers, app)) == 1

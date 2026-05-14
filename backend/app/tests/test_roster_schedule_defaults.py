"""
Tests for the defaults + stats schemas in `app/schemas/roster_schedule.py`.

Wave 6a27 covered the field validators on RosterScheduleBase /
RosterScheduleUpdate (cron expression + notification email format).
This wave covers the OTHER pieces: default values and the stats /
validation response schemas.

Non-obvious defaults pinned:

  - **auto_lock=False** on RosterScheduleBase — schedules produce
    rosters in DRAFT state by default, NOT auto-locked. Flipping
    the default would freeze every auto-generated roster from
    further admin edits.
  - **student_verification_enabled=True** — same as roster.py /
    payment_roster.py operational flows.
  - **notification_enabled=True** — admins want to know when their
    schedules ran. Flipping default to False would silence the
    schedule-completion notifications.
  - **ScheduleExecutionStats** counters default to 0 and
    success_rate defaults to 0.0 (NOT None) so dashboard math
    doesn't crash on empty stats.

14 cases.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.payment_roster import RosterCycle
from app.models.roster_schedule import RosterScheduleStatus
from app.schemas.roster_schedule import (
    RosterScheduleBase,
    RosterScheduleStatusUpdate,
    ScheduleCronValidation,
    ScheduleCronValidationResponse,
    ScheduleDeleteResponse,
    ScheduleExecutionHistory,
    ScheduleExecutionResponse,
    ScheduleExecutionStats,
    SchedulerStatusResponse,
)


def _base_payload():
    return dict(
        schedule_name="Daily",
        scholarship_configuration_id=1,
        roster_cycle=RosterCycle.SEMI_YEARLY,
    )


# ─── RosterScheduleBase defaults ────────────────────────────────────


def test_auto_lock_defaults_false():
    # Pin: auto_lock=False — schedules produce DRAFT rosters by
    # default. Flipping would freeze every auto-roster from admin
    # edits (silent permission downgrade).
    s = RosterScheduleBase(**_base_payload())
    assert s.auto_lock is False


def test_student_verification_enabled_defaults_true():
    # Pin: verification ON — same as roster.py + payment_roster.py.
    s = RosterScheduleBase(**_base_payload())
    assert s.student_verification_enabled is True


def test_notification_enabled_defaults_true():
    # Pin: notification ON — admins must know when their schedules
    # ran. Flipping silences the completion notifications.
    s = RosterScheduleBase(**_base_payload())
    assert s.notification_enabled is True


def test_schedule_name_optional_with_min_length():
    # Pin: schedule_name is Optional[str] with min_length=1 — None
    # is allowed (auto-generated server-side), but empty string
    # rejects. Allow-vs-empty distinction is documented.
    s = RosterScheduleBase(
        scholarship_configuration_id=1,
        roster_cycle=RosterCycle.SEMI_YEARLY,
    )
    assert s.schedule_name is None

    with pytest.raises(ValidationError):
        RosterScheduleBase(
            scholarship_configuration_id=1,
            roster_cycle=RosterCycle.SEMI_YEARLY,
            schedule_name="",
        )


def test_schedule_name_max_length_100():
    # Pin: 100-char cap.
    with pytest.raises(ValidationError):
        RosterScheduleBase(
            scholarship_configuration_id=1,
            roster_cycle=RosterCycle.SEMI_YEARLY,
            schedule_name="x" * 101,
        )


# ─── RosterScheduleStatusUpdate ─────────────────────────────────────


def test_status_update_requires_status():
    # Pin: status is required — endpoint refuses no-op updates.
    with pytest.raises(ValidationError):
        RosterScheduleStatusUpdate()  # type: ignore[call-arg]


# ─── ScheduleExecutionStats defaults ────────────────────────────────


def test_stats_counters_default_zero():
    # Pin: counters default to 0, success_rate to 0.0 (NOT None).
    # Dashboard math (avg / max / pct) would crash on None.
    s = ScheduleExecutionStats()
    assert s.total_runs == 0
    assert s.successful_runs == 0
    assert s.failed_runs == 0
    assert s.success_rate == 0.0


def test_stats_optional_run_timestamps():
    # Pin: timestamps Optional — fresh schedule with no runs yet
    # surfaces as null.
    s = ScheduleExecutionStats()
    assert s.last_run_at is None
    assert s.next_run_at is None
    assert s.last_run_result is None


# ─── ScheduleCronValidationResponse ─────────────────────────────────


def test_cron_validation_response_requires_valid_flag():
    with pytest.raises(ValidationError):
        ScheduleCronValidationResponse()  # type: ignore[call-arg]


def test_cron_validation_response_optional_error_and_next_runs():
    # Pin: only `valid` is required. Error message and next-runs
    # preview are Optional since valid responses have no error and
    # invalid responses have no next-run schedule.
    r = ScheduleCronValidationResponse(valid=True)
    assert r.error_message is None
    assert r.next_run_times is None


def test_cron_validation_request_requires_expression():
    with pytest.raises(ValidationError):
        ScheduleCronValidation()  # type: ignore[call-arg]


# ─── SchedulerStatusResponse ────────────────────────────────────────


def test_scheduler_status_response_required_fields():
    # Pin: 4 required fields — success / scheduler_running /
    # total_jobs / jobs. The admin /admin/scheduler page reads each.
    with pytest.raises(ValidationError):
        SchedulerStatusResponse(  # type: ignore[call-arg]
            success=True,
            scheduler_running=True,
            total_jobs=5,
            # jobs missing
        )


# ─── ScheduleExecutionResponse / DeleteResponse ─────────────────────


def test_execution_response_required_fields():
    with pytest.raises(ValidationError):
        ScheduleExecutionResponse(success=True, message="ok")  # type: ignore[call-arg]


def test_delete_response_required_fields():
    with pytest.raises(ValidationError):
        ScheduleDeleteResponse(success=True)  # type: ignore[call-arg]


# ─── ScheduleExecutionHistory ───────────────────────────────────────


def test_history_required_anchor_fields():
    # Pin: id + schedule_id + started_at + status are required.
    # The nullable-but-required fields (completed_at / result /
    # error_message / roster_id / execution_time_seconds) must be
    # passed explicitly — None is accepted but the keys can't be
    # omitted because they have no default. This is intentional —
    # the endpoint always supplies these keys (set to None for
    # in-progress runs).
    h = ScheduleExecutionHistory(
        id=1,
        schedule_id=2,
        started_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
        status="running",
        completed_at=None,
        result=None,
        error_message=None,
        roster_id=None,
        execution_time_seconds=None,
    )
    assert h.id == 1
    assert h.status == "running"
    assert h.completed_at is None

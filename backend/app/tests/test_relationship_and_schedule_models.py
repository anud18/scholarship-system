"""
Pure-property tests for `ProfessorStudentRelationship` + `RosterSchedule`
models.

ProfessorStudentRelationship gates the per-professor view of student
applications. A wrong `has_permission` verdict either:
- Hides a student from their actual advisor → review queue gap
- Leaks application data to an unrelated professor → privacy breach

RosterSchedule drives the cron-based payment-roster generation pipeline.
Wrong state transitions can leave a paused schedule permanently
stuck or auto-recover an explicitly disabled schedule.

8 helpers covered (15 cases).
"""

from datetime import datetime, timezone

import pytest

from app.models.professor_student import ProfessorStudentRelationship
from app.models.roster_schedule import RosterSchedule, RosterScheduleStatus


def _rel(**overrides) -> ProfessorStudentRelationship:
    """Build a ProfessorStudentRelationship for pure-property tests.

    Uses SA __init__ (not object.__new__) so instrumented attribute descriptors
    have a valid _sa_instance_state and property reads don't raise AttributeError.
    """
    defaults = {
        "professor_id": 10,
        "student_id": 20,
        "relationship_type": "advisor",
        "is_active": True,
        "can_view_applications": True,
        "can_upload_documents": False,
        "can_review_applications": True,
    }
    defaults.update(overrides)
    return ProfessorStudentRelationship(**defaults)


def _schedule(**overrides) -> RosterSchedule:
    """Build a RosterSchedule for pure-property tests.

    Uses SA __init__ so instrumented attribute descriptors have a valid
    _sa_instance_state (same fix as _rel above).
    """
    defaults = {
        "status": RosterScheduleStatus.ACTIVE,
        "total_runs": None,
        "successful_runs": None,
        "failed_runs": None,
        "last_run_at": None,
        "last_run_result": None,
        "last_error_message": None,
        "cron_expression": "0 3 * * *",
    }
    defaults.update(overrides)
    return RosterSchedule(**defaults)


# ─── ProfessorStudentRelationship.is_advisor ─────────────────────────


def test_is_advisor_advisor_and_co_advisor():
    """Both 'advisor' and 'co_advisor' count as advisor — pin so a
    co-advisor doesn't get downgraded in advisor-only filters."""
    assert _rel(relationship_type="advisor").is_advisor is True
    assert _rel(relationship_type="co_advisor").is_advisor is True


def test_is_advisor_false_for_other_types():
    """supervisor / committee_member / unknown → not advisor."""
    for t in ("supervisor", "committee_member", "external"):
        assert _rel(relationship_type=t).is_advisor is False, f"type={t}"


# ─── can_access_sensitive_data ──────────────────────────────────────


def test_can_access_sensitive_data_active_advisor_types():
    """Active + advisor/co_advisor/supervisor → access granted.
    Pin so a committee_member (typically external) doesn't get sensitive
    data view."""
    for t in ("advisor", "co_advisor", "supervisor"):
        assert _rel(is_active=True, relationship_type=t).can_access_sensitive_data is True
    assert _rel(is_active=True, relationship_type="committee_member").can_access_sensitive_data is False


def test_can_access_sensitive_data_blocked_when_inactive():
    """SECURITY-CRITICAL: inactive relationship → no access regardless
    of type. The is_active flag is the kill-switch — pin so deactivated
    advisors don't retain access."""
    assert _rel(is_active=False, relationship_type="advisor").can_access_sensitive_data is False


# ─── has_permission ──────────────────────────────────────────────────


def test_has_permission_uses_per_permission_flags():
    """Maps permission name to the matching boolean column on the rel."""
    r = _rel(
        is_active=True,
        can_view_applications=True,
        can_upload_documents=False,
        can_review_applications=True,
    )
    assert r.has_permission("view_applications") is True
    assert r.has_permission("upload_documents") is False
    assert r.has_permission("review_applications") is True


def test_has_permission_inactive_blocks_everything():
    """Inactive relationship returns False for ALL permissions, even
    those that are True on the flag columns. Pin the kill-switch."""
    r = _rel(is_active=False, can_view_applications=True, can_review_applications=True)
    assert r.has_permission("view_applications") is False
    assert r.has_permission("review_applications") is False


def test_has_permission_unknown_returns_false():
    """Unknown permission name → False (no allow-by-default)."""
    assert _rel(is_active=True).has_permission("nonexistent") is False


# ─── RosterSchedule.update_execution_stats ──────────────────────────


def test_update_stats_success_increments_total_and_successful():
    """Success path: total + successful + 1; sets last_run_at + result."""
    s = _schedule(status=RosterScheduleStatus.ACTIVE)
    s.update_execution_stats(success=True)
    assert s.total_runs == 1
    assert s.successful_runs == 1
    assert s.failed_runs is None  # not touched
    assert s.last_run_result == "success"
    assert s.last_run_at is not None
    assert s.last_error_message is None


def test_update_stats_failure_increments_total_and_failed():
    """Failure path: increments failed + total, sets error message and
    transitions to ERROR status."""
    s = _schedule(status=RosterScheduleStatus.ACTIVE)
    s.update_execution_stats(success=False, error_message="DB connection refused")
    assert s.total_runs == 1
    assert s.failed_runs == 1
    assert s.last_run_result == "failed"
    assert s.last_error_message == "DB connection refused"
    assert s.status == RosterScheduleStatus.ERROR


def test_update_stats_success_after_error_recovers_status():
    """Pin: a successful run AFTER ERROR transitions back to ACTIVE.
    This is the auto-recovery contract — pin so future refactors
    don't accidentally make ERROR sticky requiring manual reset."""
    s = _schedule(status=RosterScheduleStatus.ERROR)
    s.update_execution_stats(success=True)
    assert s.status == RosterScheduleStatus.ACTIVE


def test_update_stats_success_doesnt_recover_disabled_or_paused():
    """SECURITY: a successful run MUST NOT auto-revive PAUSED or
    DISABLED schedules — only ERROR. Pin so an admin's explicit
    pause/disable isn't silently overridden."""
    s = _schedule(status=RosterScheduleStatus.PAUSED)
    s.update_execution_stats(success=True)
    # Status unchanged.
    assert s.status == RosterScheduleStatus.PAUSED

    s2 = _schedule(status=RosterScheduleStatus.DISABLED)
    s2.update_execution_stats(success=True)
    assert s2.status == RosterScheduleStatus.DISABLED


# ─── RosterSchedule state transitions ──────────────────────────────


def test_is_active_only_when_status_active():
    assert _schedule(status=RosterScheduleStatus.ACTIVE).is_active() is True
    for s in (RosterScheduleStatus.PAUSED, RosterScheduleStatus.DISABLED, RosterScheduleStatus.ERROR):
        assert _schedule(status=s).is_active() is False, f"status={s}"


def test_pause_sets_status():
    """pause() → PAUSED regardless of previous status. Pin so a refactor
    doesn't add 'can't pause an ERROR schedule' guard silently."""
    for prev in (RosterScheduleStatus.ACTIVE, RosterScheduleStatus.ERROR):
        s = _schedule(status=prev)
        s.pause()
        assert s.status == RosterScheduleStatus.PAUSED


def test_resume_only_works_from_paused():
    """resume() ONLY transitions from PAUSED → ACTIVE. Other statuses
    (DISABLED, ERROR) are NOT resumed silently. Pin so DISABLED state
    requires explicit admin action."""
    s = _schedule(status=RosterScheduleStatus.PAUSED)
    s.resume()
    assert s.status == RosterScheduleStatus.ACTIVE

    s2 = _schedule(status=RosterScheduleStatus.DISABLED)
    s2.resume()
    # DISABLED stays DISABLED — resume() is a no-op.
    assert s2.status == RosterScheduleStatus.DISABLED


def test_disable_sets_status():
    """disable() → DISABLED from any state."""
    for prev in (RosterScheduleStatus.ACTIVE, RosterScheduleStatus.PAUSED, RosterScheduleStatus.ERROR):
        s = _schedule(status=prev)
        s.disable()
        assert s.status == RosterScheduleStatus.DISABLED

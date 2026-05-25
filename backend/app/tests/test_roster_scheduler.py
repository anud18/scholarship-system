"""
Unit tests for `RosterSchedulerService` — scheduler lifecycle, event listeners,
and cron-expression parsing (issue #124 §6).

Coverage groups
───────────────
§6a  Cron parsing (pure unit)       — `_parse_cron_expression`
§6b  Job lifecycle (mocked scheduler) — remove / pause / resume / status / list
§6c  Event listeners                — executed / error / missed
§6d  add_schedule validation        — invalid cron ⇒ False; valid cron ⇒ True

Note: `test_roster_scheduler_cron.py` already covers `_parse_cron_expression`
via `__new__`; the §6a tests here use `patch.object(_setup_scheduler)` (the
approach specified in issue #124) to keep both styles in the suite and provide
independent cross-validation.  Reviewers may choose to consolidate the two
files once the wave merges.

Environment note
────────────────
LOCAL TESTING  uses SQLite (via conftest.py). These tests mock the scheduler
entirely, so they make no database or Redis calls and are safe to run in both
local SQLite and production PostgreSQL environments.

Run in the dev container:
  docker compose -f docker-compose.dev.yml exec backend \\
    python -m pytest app/tests/test_roster_scheduler.py -v
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.roster_scheduler_service import RosterSchedulerService

# ─────────────────────────────────────────────────────────────────────────────
# Shared fixture
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def svc():
    """
    RosterSchedulerService with `_setup_scheduler` patched out so no
    Redis connection or AsyncIOScheduler is created.  `scheduler` is
    replaced with a plain MagicMock so callers can inspect and control
    every APScheduler method.

    IMPORTANT — before running these tests always ensure Docker Compose
    containers are running via `./test-docker.sh` (or the equivalent
    `docker compose -f docker-compose.dev.yml up`).
    """
    with patch.object(RosterSchedulerService, "_setup_scheduler"):
        instance = RosterSchedulerService()
        instance.scheduler = MagicMock()
    return instance


# ─────────────────────────────────────────────────────────────────────────────
# §6a — Cron parsing  (pure unit, no external deps)
# ─────────────────────────────────────────────────────────────────────────────


class TestParseCronExpression:
    """
    `_parse_cron_expression` splits a 5-field cron string into the dict of
    APScheduler keyword arguments.  Tests here use the `patch.object` fixture
    style (§6 spec) as complementary coverage to test_roster_scheduler_cron.py.
    """

    def test_valid_5_field_keys(self, svc: RosterSchedulerService) -> None:
        """Standard daily expression returns exactly the five expected keys."""
        result = svc._parse_cron_expression("0 3 * * *")
        assert set(result.keys()) == {"minute", "hour", "day", "month", "day_of_week"}

    def test_valid_5_field_values(self, svc: RosterSchedulerService) -> None:
        """Field values map to the correct cron positions."""
        result = svc._parse_cron_expression("0 3 * * *")
        assert result == {
            "minute": "0",
            "hour": "3",
            "day": "*",
            "month": "*",
            "day_of_week": "*",
        }

    def test_extra_whitespace_between_fields(self, svc: RosterSchedulerService) -> None:
        """`str.split()` collapses runs of whitespace — multi-space still parses."""
        result = svc._parse_cron_expression("0  3  *  *  *")
        assert result["hour"] == "3"
        assert result["minute"] == "0"

    def test_four_fields_raises_value_error(self, svc: RosterSchedulerService) -> None:
        """Exactly 4 fields is rejected."""
        with pytest.raises(ValueError):
            svc._parse_cron_expression("0 3 * *")

    def test_six_fields_raises_value_error(self, svc: RosterSchedulerService) -> None:
        """Six fields (APScheduler's extended 7-part form) is rejected."""
        with pytest.raises(ValueError):
            svc._parse_cron_expression("0 3 * * * *")

    def test_day_and_month_specific(self, svc: RosterSchedulerService) -> None:
        """Day-of-month and month values are passed through verbatim."""
        result = svc._parse_cron_expression("0 3 31 * *")
        assert result["day"] == "31"
        assert result["month"] == "*"

    def test_day_of_week_specific(self, svc: RosterSchedulerService) -> None:
        """Day-of-week value 1 (Monday) is passed through correctly."""
        result = svc._parse_cron_expression("0 3 * * 1")
        assert result["day_of_week"] == "1"


# ─────────────────────────────────────────────────────────────────────────────
# §6b — Job lifecycle  (mocked scheduler)
# ─────────────────────────────────────────────────────────────────────────────


class TestRemoveSchedule:
    """remove_schedule — delegates to scheduler.remove_job only when job exists."""

    async def test_remove_existing_job_calls_remove_job(self, svc: RosterSchedulerService) -> None:
        svc.scheduler.get_job.return_value = MagicMock()  # job exists
        result = await svc.remove_schedule(42)
        svc.scheduler.remove_job.assert_called_once_with("roster_schedule_42")
        assert result is True

    async def test_remove_missing_job_skips_remove_job(self, svc: RosterSchedulerService) -> None:
        svc.scheduler.get_job.return_value = None  # job absent
        result = await svc.remove_schedule(42)
        svc.scheduler.remove_job.assert_not_called()
        assert result is True


class TestPauseSchedule:
    """pause_schedule — delegates to scheduler.pause_job only when job exists."""

    async def test_pause_existing_job_calls_pause_job(self, svc: RosterSchedulerService) -> None:
        svc.scheduler.get_job.return_value = MagicMock()
        result = await svc.pause_schedule(7)
        svc.scheduler.pause_job.assert_called_once_with("roster_schedule_7")
        assert result is True

    async def test_pause_missing_job_skips_pause_job(self, svc: RosterSchedulerService) -> None:
        svc.scheduler.get_job.return_value = None
        result = await svc.pause_schedule(7)
        svc.scheduler.pause_job.assert_not_called()
        assert result is True


class TestResumeSchedule:
    """resume_schedule — delegates to scheduler.resume_job only when job exists."""

    async def test_resume_existing_job_calls_resume_job(self, svc: RosterSchedulerService) -> None:
        svc.scheduler.get_job.return_value = MagicMock()
        result = await svc.resume_schedule(99)
        svc.scheduler.resume_job.assert_called_once_with("roster_schedule_99")
        assert result is True

    async def test_resume_missing_job_skips_resume_job(self, svc: RosterSchedulerService) -> None:
        svc.scheduler.get_job.return_value = None
        result = await svc.resume_schedule(99)
        svc.scheduler.resume_job.assert_not_called()
        assert result is True


class TestGetScheduleStatus:
    """get_schedule_status — returns a status dict or None."""

    def test_existing_job_returns_dict(self, svc: RosterSchedulerService) -> None:
        fake_job = MagicMock()
        fake_job.id = "roster_schedule_5"
        fake_job.next_run_time = None
        fake_job.trigger = MagicMock(__str__=lambda self: "cron[hour='3']")
        fake_job.pending = False
        svc.scheduler.get_job.return_value = fake_job

        status = svc.get_schedule_status(5)

        assert status is not None
        assert status["job_id"] == "roster_schedule_5"
        assert "next_run_time" in status
        assert "trigger" in status
        assert "pending" in status

    def test_missing_job_returns_none(self, svc: RosterSchedulerService) -> None:
        svc.scheduler.get_job.return_value = None
        assert svc.get_schedule_status(5) is None


class TestListAllJobs:
    """list_all_jobs — returns a list of dicts, one per APScheduler job."""

    def test_two_jobs_returns_two_dicts(self, svc: RosterSchedulerService) -> None:
        def _make_job(job_id: str, name: str):
            j = MagicMock()
            j.id = job_id
            j.name = name
            j.next_run_time = None
            j.trigger = MagicMock(__str__=lambda self: "cron[hour='3']")
            j.pending = False
            return j

        svc.scheduler.get_jobs.return_value = [
            _make_job("roster_schedule_1", "Job One"),
            _make_job("roster_schedule_2", "Job Two"),
        ]

        jobs = svc.list_all_jobs()

        assert len(jobs) == 2
        ids = {j["id"] for j in jobs}
        assert ids == {"roster_schedule_1", "roster_schedule_2"}
        for job_dict in jobs:
            assert "id" in job_dict
            assert "name" in job_dict
            assert "next_run_time" in job_dict
            assert "trigger" in job_dict
            assert "pending" in job_dict


# ─────────────────────────────────────────────────────────────────────────────
# §6c — Event listeners  (pure call verification)
# ─────────────────────────────────────────────────────────────────────────────


class TestEventListeners:
    """
    Event listeners only log — they must not raise under any circumstances
    (APScheduler swallows listener exceptions, but silence here would mask bugs).
    """

    def test_executed_listener_no_exception(self, svc: RosterSchedulerService) -> None:
        event = MagicMock()
        event.job_id = "roster_schedule_1"
        svc._job_executed_listener(event)  # must not raise

    def test_error_listener_no_exception(self, svc: RosterSchedulerService) -> None:
        event = MagicMock()
        event.job_id = "roster_schedule_2"
        event.exception = ValueError("boom")
        svc._job_error_listener(event)  # must not raise

    def test_missed_listener_no_exception(self, svc: RosterSchedulerService) -> None:
        event = MagicMock()
        event.job_id = "roster_schedule_3"
        svc._job_missed_listener(event)  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# §6d — add_schedule validation
# ─────────────────────────────────────────────────────────────────────────────


class TestAddScheduleValidation:
    """
    add_schedule validates the cron expression before enqueuing.

    DATABASE NOTE: `_add_schedule_job` is replaced with AsyncMock so no
    SQLite / PostgreSQL difference is exercised here — this is a pure
    service-layer guard test.
    """

    async def test_invalid_cron_returns_false(self, svc: RosterSchedulerService) -> None:
        """An expression that fails `croniter.is_valid` never reaches _add_schedule_job."""
        svc._add_schedule_job = AsyncMock()
        result = await svc.add_schedule({"cron_expression": "not a cron"})
        assert result is False
        svc._add_schedule_job.assert_not_awaited()

    async def test_valid_cron_calls_add_schedule_job(self, svc: RosterSchedulerService) -> None:
        """A valid cron expression results in _add_schedule_job being awaited."""
        svc._add_schedule_job = AsyncMock()
        schedule_data = {"id": 1, "cron_expression": "0 3 * * *"}
        result = await svc.add_schedule(schedule_data)
        assert result is True
        svc._add_schedule_job.assert_awaited_once_with(schedule_data)

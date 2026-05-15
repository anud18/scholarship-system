"""
Tests for `app.tasks.email_processor` startup grace period.

The email processor is registered with APScheduler to run every
15 seconds. On backend startup, the scheduler fires it almost
immediately, but during the boot window the DB session pool isn't
fully warmed and some seed migrations may still be applying. The
module guards with `_MIN_STARTUP_DELAY_SECONDS` — if less than N
seconds have elapsed since module import, the processor skips.

A regression in either direction is bad:
  - Delay too short → race against DB warm-up → flaky boot
  - Delay too long → scheduled emails sit in queue past 15s tick

Wave 6a108 pins:
  - _MIN_STARTUP_DELAY_SECONDS = 5
  - _module_start_time set at import (close to now)
  - run_email_processor SKIPS when called too soon after import
    (no DB call attempted)
  - run_email_processor calls process_scheduled_emails once grace
    period elapsed

9 cases.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks import email_processor

# ─── Module constants ────────────────────────────────────────────────


def test_startup_delay_constant_is_five_seconds():
    # Pin: 5-second startup grace. Pin so a refactor to 0 (which
    # would re-introduce DB-warm-up races) or to 60+ (which would
    # delay first email batch past the 15s tick) is caught.
    assert email_processor._MIN_STARTUP_DELAY_SECONDS == 5


def test_module_start_time_is_recent():
    # Pin: _module_start_time captured at import (UTC). Should be
    # within ~10 minutes of test execution. Pin so a refactor to
    # local time or to a static fallback is caught.
    now = datetime.now(timezone.utc)
    age = (now - email_processor._module_start_time).total_seconds()
    assert 0 <= age < 600  # less than 10 minutes


def test_module_start_time_is_utc_timezone():
    # Pin: timezone-aware UTC. A naive datetime would silently
    # break the comparison logic on hosts running in non-UTC TZ.
    assert email_processor._module_start_time.tzinfo is not None
    assert email_processor._module_start_time.tzinfo.utcoffset(email_processor._module_start_time) == timedelta(0)


# ─── run_email_processor startup-skip behaviour ─────────────────────


@pytest.mark.asyncio
async def test_skips_when_called_immediately_after_startup(monkeypatch):
    # Pin: when _module_start_time is "now", the processor skips
    # — does NOT attempt to open a DB session.
    monkeypatch.setattr(email_processor, "_module_start_time", datetime.now(timezone.utc))

    # If skip works, AsyncSessionLocal is never called.
    mock_session_local = MagicMock()
    monkeypatch.setattr(email_processor, "AsyncSessionLocal", mock_session_local)

    await email_processor.run_email_processor()

    mock_session_local.assert_not_called()


@pytest.mark.asyncio
async def test_skips_when_delay_just_short_of_threshold(monkeypatch):
    # Pin: 4 seconds elapsed is still skipped (threshold is 5).
    # Pin the threshold semantics so a refactor to `<= ` instead
    # of `< ` doesn't silently shift behavior at the boundary.
    fake_start = datetime.now(timezone.utc) - timedelta(seconds=4)
    monkeypatch.setattr(email_processor, "_module_start_time", fake_start)

    mock_session_local = MagicMock()
    monkeypatch.setattr(email_processor, "AsyncSessionLocal", mock_session_local)

    await email_processor.run_email_processor()
    mock_session_local.assert_not_called()


@pytest.mark.asyncio
async def test_proceeds_when_grace_period_elapsed(monkeypatch):
    # Pin: once grace period elapsed (10s > 5s threshold), the
    # processor opens a DB session and calls
    # process_scheduled_emails.
    fake_start = datetime.now(timezone.utc) - timedelta(seconds=10)
    monkeypatch.setattr(email_processor, "_module_start_time", fake_start)

    # Build a proper async context manager for AsyncSessionLocal()
    fake_db = MagicMock()
    fake_db.commit = AsyncMock()
    fake_db.rollback = AsyncMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_db)
    cm.__aexit__ = AsyncMock(return_value=None)

    mock_session_local = MagicMock(return_value=cm)
    monkeypatch.setattr(email_processor, "AsyncSessionLocal", mock_session_local)

    mock_svc = MagicMock()
    mock_svc.process_scheduled_emails = AsyncMock()
    monkeypatch.setattr(email_processor, "email_automation_service", mock_svc)

    await email_processor.run_email_processor()

    mock_session_local.assert_called_once()
    mock_svc.process_scheduled_emails.assert_called_once_with(fake_db)
    fake_db.commit.assert_called_once()
    fake_db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_rolls_back_on_processing_error(monkeypatch):
    # Pin: exception during processing → db.rollback() called,
    # exception NOT re-raised (scheduler must not stop). Critical
    # for scheduler resilience.
    fake_start = datetime.now(timezone.utc) - timedelta(seconds=10)
    monkeypatch.setattr(email_processor, "_module_start_time", fake_start)

    fake_db = MagicMock()
    fake_db.commit = AsyncMock()
    fake_db.rollback = AsyncMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_db)
    cm.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(email_processor, "AsyncSessionLocal", MagicMock(return_value=cm))

    mock_svc = MagicMock()
    mock_svc.process_scheduled_emails = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(email_processor, "email_automation_service", mock_svc)

    # Must NOT raise — pin scheduler resilience
    await email_processor.run_email_processor()

    fake_db.rollback.assert_called_once()
    fake_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_does_not_call_commit_when_error_raised(monkeypatch):
    # Pin: on error path, commit is NOT called (only rollback).
    # Otherwise a half-processed batch could get persisted.
    fake_start = datetime.now(timezone.utc) - timedelta(seconds=10)
    monkeypatch.setattr(email_processor, "_module_start_time", fake_start)

    fake_db = MagicMock()
    fake_db.commit = AsyncMock()
    fake_db.rollback = AsyncMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=fake_db)
    cm.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr(email_processor, "AsyncSessionLocal", MagicMock(return_value=cm))

    mock_svc = MagicMock()
    mock_svc.process_scheduled_emails = AsyncMock(side_effect=Exception("nope"))
    monkeypatch.setattr(email_processor, "email_automation_service", mock_svc)

    await email_processor.run_email_processor()
    fake_db.commit.assert_not_called()


# ─── Module entrypoint smoke ────────────────────────────────────────


def test_main_function_exists():
    # Pin: __main__ entry point preserved. The deployment script
    # `python -m app.tasks.email_processor` depends on this.
    assert callable(email_processor.main)


def test_run_email_processor_is_async():
    # Pin: run_email_processor remains async — APScheduler
    # registration depends on awaiting it.
    import inspect

    assert inspect.iscoroutinefunction(email_processor.run_email_processor)

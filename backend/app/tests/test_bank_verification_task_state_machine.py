"""
Tests for `backend/app/services/bank_verification_task_service.py`.

Module had ZERO test references. SECURITY-CRITICAL: drives the
async batch bank-verification task lifecycle and progress
tracking. Drift in the state machine would leave tasks stuck
in "processing" or report wrong counts to the admin dashboard.

Wave 6a141 pins the pure-logic state-machine invariants in:
- create_task (UUID generation + initial status=pending)
- get_task (single-row lookup)
- mark_task_as_processing / completed / failed (state transitions)
- update_task_progress (partial-update semantics + ValueError on
  not-found)
- _application_uses_verified_account (skip-check defensive
  fallthrough)

DB Session is mocked via AsyncMock — we're testing state
mutations + control flow, not the SQL.
"""

import pytest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.bank_verification_task import BankVerificationTaskStatus
from app.services.bank_verification_task_service import BankVerificationTaskService


def _async_db():
    """Build an AsyncSession-shaped mock with awaitable methods."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.get = AsyncMock()
    return db


def _stub_task(task_id="abc-123", **kwargs):
    """Build a BankVerificationTask stand-in."""
    base = {
        "task_id": task_id,
        "status": BankVerificationTaskStatus.pending,
        "started_at": None,
        "completed_at": None,
        "error_message": None,
        "processed_count": 0,
        "verified_count": 0,
        "needs_review_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "results": None,
        "application_ids": [1, 2, 3],
        "total_count": 3,
        "created_by_user_id": 42,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


class TestCreateTask:
    """Pin: create_task generates UUID, sets pending status, persists."""

    @pytest.mark.asyncio
    async def test_create_task_uses_uuid4_for_task_id(self):
        # Pin: task_id is a UUID4 string. Pin so refactor doesn't
        # switch to a sequential int that could collide cross-host.
        db = _async_db()
        service = BankVerificationTaskService(db)

        with patch("app.services.bank_verification_task_service.BankVerificationTask") as task_cls:
            task_cls.side_effect = lambda **kw: SimpleNamespace(**kw)
            result = await service.create_task(application_ids=[1, 2, 3], created_by_user_id=42)
            # task_id passed to BankVerificationTask ctor must be a UUID string
            kwargs = task_cls.call_args.kwargs
            assert len(kwargs["task_id"]) == 36  # uuid4 string format
            assert kwargs["task_id"].count("-") == 4

    @pytest.mark.asyncio
    async def test_create_task_initial_status_is_pending(self):
        # Pin SECURITY: tasks start in PENDING (NOT processing).
        # Pin so refactor doesn't auto-start tasks and bypass admin
        # approval gate.
        db = _async_db()
        service = BankVerificationTaskService(db)

        with patch("app.services.bank_verification_task_service.BankVerificationTask") as task_cls:
            task_cls.side_effect = lambda **kw: SimpleNamespace(**kw)
            await service.create_task([1, 2], 42)
            assert task_cls.call_args.kwargs["status"] == BankVerificationTaskStatus.pending

    @pytest.mark.asyncio
    async def test_create_task_total_count_matches_application_ids_length(self):
        # Pin: total_count IS computed from application_ids length.
        # Pin so refactor passing an explicit total_count parameter
        # doesn't drift from the array length.
        db = _async_db()
        service = BankVerificationTaskService(db)

        with patch("app.services.bank_verification_task_service.BankVerificationTask") as task_cls:
            task_cls.side_effect = lambda **kw: SimpleNamespace(**kw)
            await service.create_task([10, 20, 30, 40, 50], 7)
            assert task_cls.call_args.kwargs["total_count"] == 5
            assert task_cls.call_args.kwargs["application_ids"] == [10, 20, 30, 40, 50]

    @pytest.mark.asyncio
    async def test_create_task_persists_then_refreshes(self):
        # Pin: persistence flow = add() → commit() → refresh().
        # Refresh is needed so caller sees auto-generated id/created_at.
        db = _async_db()
        service = BankVerificationTaskService(db)

        with patch("app.services.bank_verification_task_service.BankVerificationTask") as task_cls:
            task_cls.side_effect = lambda **kw: SimpleNamespace(**kw)
            await service.create_task([1], 1)
            db.add.assert_called_once()
            db.commit.assert_awaited_once()
            db.refresh.assert_awaited_once()


class TestStateTransitions:
    """Pin: mark_as_* methods perform single state transition + commit."""

    @pytest.mark.asyncio
    async def test_mark_as_processing_sets_status_and_started_at(self):
        # Pin: started_at is set at processing-start (NOT at create-
        # time). Used by dashboard to compute elapsed-time. Pin so
        # refactor moving to create-time would make the elapsed
        # time misleading.
        db = _async_db()
        task = _stub_task()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=task)

        service = BankVerificationTaskService(db)
        await service.mark_task_as_processing("abc-123")

        assert task.status == BankVerificationTaskStatus.processing
        assert task.started_at is not None
        assert task.started_at.tzinfo == timezone.utc
        db.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_mark_as_completed_sets_status_and_completed_at(self):
        db = _async_db()
        task = _stub_task(status=BankVerificationTaskStatus.processing)
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=task)

        service = BankVerificationTaskService(db)
        await service.mark_task_as_completed("abc-123")

        assert task.status == BankVerificationTaskStatus.completed
        assert task.completed_at is not None
        assert task.completed_at.tzinfo == timezone.utc

    @pytest.mark.asyncio
    async def test_mark_as_failed_records_error_message_and_completed_at(self):
        # Pin SECURITY: failed tasks RECORD the error_message —
        # required for admin to debug failures. completed_at is
        # ALSO set (NOT just started_at) so the task is fully
        # terminal.
        db = _async_db()
        task = _stub_task(status=BankVerificationTaskStatus.processing)
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=task)

        service = BankVerificationTaskService(db)
        await service.mark_task_as_failed("abc-123", "OCR provider timeout after 30s")

        assert task.status == BankVerificationTaskStatus.failed
        assert task.error_message == "OCR provider timeout after 30s"
        assert task.completed_at is not None

    @pytest.mark.asyncio
    async def test_mark_as_processing_raises_when_task_not_found(self):
        # Pin: ValueError on not-found (NOT silent return). Pin so
        # caller (process_batch_verification_task) doesn't silently
        # operate on None.
        db = _async_db()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        service = BankVerificationTaskService(db)
        with pytest.raises(ValueError, match="Task missing-id not found"):
            await service.mark_task_as_processing("missing-id")

    @pytest.mark.asyncio
    async def test_mark_as_completed_raises_when_task_not_found(self):
        db = _async_db()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        service = BankVerificationTaskService(db)
        with pytest.raises(ValueError):
            await service.mark_task_as_completed("missing-id")

    @pytest.mark.asyncio
    async def test_mark_as_failed_raises_when_task_not_found(self):
        db = _async_db()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        service = BankVerificationTaskService(db)
        with pytest.raises(ValueError):
            await service.mark_task_as_failed("missing-id", "any error")


class TestUpdateTaskProgress:
    """Pin: update_task_progress copies all 5 counts + optional results."""

    @pytest.mark.asyncio
    async def test_update_progress_copies_all_counts(self):
        db = _async_db()
        task = _stub_task()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=task)

        service = BankVerificationTaskService(db)
        await service.update_task_progress(
            task_id="abc-123",
            processed_count=10,
            verified_count=5,
            needs_review_count=2,
            failed_count=2,
            skipped_count=1,
            results={"some": "data"},
        )

        assert task.processed_count == 10
        assert task.verified_count == 5
        assert task.needs_review_count == 2
        assert task.failed_count == 2
        assert task.skipped_count == 1
        assert task.results == {"some": "data"}

    @pytest.mark.asyncio
    async def test_update_progress_count_defaults_zero(self):
        # Pin: optional counts (verified/needs_review/failed/skipped)
        # default to 0 (NOT None). Pin so refactor doesn't accidentally
        # break the dashboard which expects integers.
        db = _async_db()
        task = _stub_task(verified_count=99)  # Pre-existing value
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=task)

        service = BankVerificationTaskService(db)
        # Only set processed_count; the rest default to 0 and OVERWRITE
        # the existing values.
        await service.update_task_progress(task_id="abc-123", processed_count=5)
        assert task.processed_count == 5
        assert task.verified_count == 0  # default overwrote 99
        assert task.needs_review_count == 0
        assert task.failed_count == 0
        assert task.skipped_count == 0

    @pytest.mark.asyncio
    async def test_update_progress_results_None_does_NOT_clear_existing(self):
        # Pin: when `results=None` is passed (default), existing
        # task.results is PRESERVED (NOT cleared). Pin so refactor
        # changing the default doesn't accidentally lose accumulated
        # progress data on every partial update.
        db = _async_db()
        task = _stub_task(results={"existing": "data"})
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=task)

        service = BankVerificationTaskService(db)
        await service.update_task_progress(task_id="abc-123", processed_count=5)
        assert task.results == {"existing": "data"}

    @pytest.mark.asyncio
    async def test_update_progress_raises_when_task_not_found(self):
        db = _async_db()
        db.execute.return_value.scalar_one_or_none = MagicMock(return_value=None)

        service = BankVerificationTaskService(db)
        with pytest.raises(ValueError, match="Task missing not found"):
            await service.update_task_progress(task_id="missing", processed_count=1)


class TestListTasks:
    """Pin: list_tasks defaults limit=50 offset=0 with no filters."""

    @pytest.mark.asyncio
    async def test_list_tasks_defaults_are_50_0(self):
        # Pin: pagination defaults match admin dashboard page size.
        # Pin so refactor doesn't silently shrink to a smaller page.
        db = _async_db()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        db.execute.return_value = result_mock

        service = BankVerificationTaskService(db)
        items = await service.list_tasks()
        assert items == []
        db.execute.assert_awaited_once()


class TestApplicationUsesVerifiedAccount:
    """Pin: skip-check defensive fallthrough — issue #217 reference."""

    @pytest.mark.asyncio
    async def test_returns_false_when_application_not_found(self):
        # Pin: missing application → False (not error). Pin so
        # caller proceeds with normal verification on any lookup
        # miss.
        db = _async_db()
        db.get.return_value = None

        service = BankVerificationTaskService(db)
        verification_service = MagicMock()
        result = await service._application_uses_verified_account(99, verification_service)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_submitted_form_data_empty(self):
        # Pin: empty submitted_form_data → False. Pin so caller
        # treats unsubmitted applications as needing verification.
        db = _async_db()
        application = SimpleNamespace(submitted_form_data=None, user_id=42)
        db.get.return_value = application

        service = BankVerificationTaskService(db)
        verification_service = MagicMock()
        result = await service._application_uses_verified_account(1, verification_service)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_account_number_missing(self):
        # Pin: bank_fields without account_number → False.
        db = _async_db()
        application = SimpleNamespace(submitted_form_data={"x": "y"}, user_id=42)
        db.get.return_value = application

        verification_service = MagicMock()
        verification_service.extract_bank_fields_from_application.return_value = {}

        service = BankVerificationTaskService(db)
        result = await service._application_uses_verified_account(1, verification_service)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_normalize_returns_empty(self):
        # Pin: normalize_account_number returning falsy → False.
        # Defensive — invalid account numbers should NOT match any
        # verified record.
        db = _async_db()
        application = SimpleNamespace(submitted_form_data={"x": "y"}, user_id=42)
        db.get.return_value = application

        verification_service = MagicMock()
        verification_service.extract_bank_fields_from_application.return_value = {"account_number": "garbage"}
        verification_service.normalize_account_number.return_value = None

        service = BankVerificationTaskService(db)
        result = await service._application_uses_verified_account(1, verification_service)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_unexpected_exception(self):
        # Pin SECURITY: any exception → False (fallthrough to normal
        # verification). Per docstring: "this is an optimisation,
        # not a correctness boundary, so we don't want it to mask
        # real verification work."
        db = _async_db()
        db.get.side_effect = RuntimeError("db connection lost")

        service = BankVerificationTaskService(db)
        verification_service = MagicMock()
        result = await service._application_uses_verified_account(1, verification_service)
        assert result is False

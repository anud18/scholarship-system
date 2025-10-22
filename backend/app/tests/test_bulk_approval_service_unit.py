from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.application import ApplicationStatus
from app.services.bulk_approval_service import BulkApprovalService


class StubScalarSequence:
    def __init__(self, values):
        self._values = list(values)

    def all(self):
        return list(self._values)


class StubResult:
    def __init__(self, scalars=None):
        self._scalars = scalars or []

    def scalars(self):
        return StubScalarSequence(self._scalars)


class StubSession:
    def __init__(self, results=None):
        self._results = list(results or [])
        self.commits = 0
        self.rollbacks = 0
        self.added_objects = []

    async def execute(self, stmt):
        if not self._results:
            raise AssertionError("No stubbed result available")
        return self._results.pop(0)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    def add(self, obj):
        """Add object to session (for ApplicationReview records)"""
        self.added_objects.append(obj)


class StubNotificationService:
    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self.status_calls = []
        self.batch_calls = []

    async def send_status_change_notification(self, application, old_status, new_status):
        self.status_calls.append((application.app_id, old_status, new_status))
        if self._responses:
            response = self._responses.pop(0)
        else:
            response = True
        if isinstance(response, Exception):
            raise response
        return response

    async def send_batch_processing_notification(self, admin_email, payload):
        self.batch_calls.append((admin_email, payload))


class StubEligibilityService:
    def __init__(self, db):
        self.db = db


class DummyApplication:
    def __init__(self, app_id, status, **kwargs):
        self.id = kwargs.get("id", hash(app_id) % 1000)
        self.app_id = app_id
        self.status = status
        self.student_data = kwargs.get("student_data", {"student_id": f"stu-{app_id}"})
        self.priority_score = kwargs.get("priority_score", 10)
        self.is_renewal = kwargs.get("is_renewal", False)
        # gpa removed - should be validated by ScholarshipRule system
        self.class_ranking_percent = kwargs.get("class_ranking_percent", "20")
        self.scholarship_type_id = kwargs.get("scholarship_type_id", 1)
        self.main_scholarship_type = kwargs.get("main_type", "MAIN")
        self.sub_scholarship_type = kwargs.get("sub_type", "SUB")
        self.semester = kwargs.get("semester", "FIRST")
        self.submitted_at = kwargs.get("submitted_at", datetime(2024, 1, 1, tzinfo=timezone.utc))
        self.approved_at = kwargs.get("approved_at")
        self.decision_date = kwargs.get("decision_date")
        self.admin_notes = kwargs.get("admin_notes")
        self.reviewer_id = kwargs.get("reviewer_id")
        self.final_approver_id = kwargs.get("final_approver_id")
        self.updated_at = kwargs.get("updated_at")
        self.rejection_reason = kwargs.get("rejection_reason")
        self.calculate_calls = 0

    def calculate_priority_score(self):
        self.calculate_calls += 1
        return self.priority_score


def make_service(session, notification=None):
    service = BulkApprovalService(session)
    service.notification_service = notification or StubNotificationService()
    service.eligibility_service = StubEligibilityService(session)
    return service


@pytest.mark.asyncio
async def test_bulk_approve_applications_success(monkeypatch):
    app1 = DummyApplication("APP-1", ApplicationStatus.submitted.value)
    app2 = DummyApplication("APP-2", ApplicationStatus.under_review.value)
    session = StubSession([StubResult([app1, app2])])
    notification_stub = StubNotificationService(responses=[True, False])
    service = make_service(session, notification_stub)

    result = await service.bulk_approve_applications([app1.id, app2.id], approver_user_id=99, approval_notes="note")

    assert result["total_requested"] == 2
    assert len(result["successful_approvals"]) == 2
    assert result["notifications_sent"] == 1
    assert result["notifications_failed"] == 1
    assert session.commits == 2
    # Note: priority_score calculation removed - no longer needed
    assert all(item["new_status"] == ApplicationStatus.approved.value for item in result["successful_approvals"])


@pytest.mark.asyncio
async def test_bulk_approve_applications_handles_invalid_status():
    app = DummyApplication("APP-3", ApplicationStatus.cancelled.value)
    session = StubSession([StubResult([app])])
    service = make_service(session)

    result = await service.bulk_approve_applications([app.id], approver_user_id=1)

    assert result["successful_approvals"] == []
    assert result["failed_approvals"][0]["reason"].startswith("Invalid status")
    assert session.commits == 0


@pytest.mark.asyncio
async def test_bulk_approve_handles_missing_ids_and_no_notifications():
    app = DummyApplication("APP-missing", ApplicationStatus.submitted.value)
    session = StubSession([StubResult([app])])
    service = make_service(session)

    result = await service.bulk_approve_applications([app.id, 999], approver_user_id=2, send_notifications=False)

    assert result["total_requested"] == 2
    assert len(result["successful_approvals"]) == 1
    assert result["notifications_sent"] == 0
    assert result["notifications_failed"] == 0


@pytest.mark.asyncio
async def test_bulk_approve_records_notification_error(monkeypatch):
    app = DummyApplication("APP-4", ApplicationStatus.recommended.value)
    session = StubSession([StubResult([app])])
    notification_stub = StubNotificationService(responses=[RuntimeError("boom")])
    service = make_service(session, notification_stub)

    result = await service.bulk_approve_applications([app.id], approver_user_id=5)

    assert result["notifications_failed"] == 1
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_bulk_approve_handles_commit_failure():
    app = DummyApplication("APP-commit", ApplicationStatus.submitted.value)
    session = StubSession([StubResult([app])])

    async def failing_commit():
        session.commits += 1
        raise RuntimeError("db write failure")

    session.commit = failing_commit
    service = make_service(session)

    result = await service.bulk_approve_applications([app.id], approver_user_id=1)

    assert result["successful_approvals"] == []
    assert result["failed_approvals"][0]["app_id"] == app.app_id
    assert "Approval failed" in result["failed_approvals"][0]["reason"]
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_bulk_approve_outer_exception_triggers_rollback():
    session = StubSession()

    async def failing_execute(_):
        raise RuntimeError("query failed")

    session.execute = failing_execute
    service = make_service(session)

    with pytest.raises(RuntimeError):
        await service.bulk_approve_applications([1], approver_user_id=1)

    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_bulk_reject_applications_success():
    app = DummyApplication("APP-5", ApplicationStatus.submitted.value)
    session = StubSession([StubResult([app])])
    notification_stub = StubNotificationService(responses=[True])
    service = make_service(session, notification_stub)

    result = await service.bulk_reject_applications([app.id], rejector_user_id=7, rejection_reason="missing docs")

    assert len(result["successful_rejections"]) == 1
    assert result["notifications_sent"] == 1
    # Note: rejection_reason moved to ApplicationReview model
    assert len(session.added_objects) == 1  # ApplicationReview record created
    assert session.added_objects[0].decision_reason == "missing docs"


@pytest.mark.asyncio
async def test_bulk_reject_handles_failure():
    app = DummyApplication("APP-6", ApplicationStatus.approved.value)
    session = StubSession([StubResult([app])])
    service = make_service(session)

    result = await service.bulk_reject_applications([app.id], rejector_user_id=8, rejection_reason="late")

    assert result["successful_rejections"] == []
    assert result["failed_rejections"][0]["reason"].startswith("Invalid status")


@pytest.mark.asyncio
async def test_bulk_reject_commit_failure():
    app = DummyApplication("APP-reject", ApplicationStatus.submitted.value)
    session = StubSession([StubResult([app])])

    async def failing_commit():
        session.commits += 1
        raise RuntimeError("write failed")

    session.commit = failing_commit
    service = make_service(session)

    result = await service.bulk_reject_applications([app.id], rejector_user_id=3, rejection_reason="reason")

    assert result["successful_rejections"] == []
    assert result["failed_rejections"][0]["app_id"] == app.app_id
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_bulk_reject_no_notifications():
    app = DummyApplication("APP-reject2", ApplicationStatus.under_review.value)
    session = StubSession([StubResult([app])])
    service = make_service(session)

    result = await service.bulk_reject_applications(
        [app.id], rejector_user_id=5, rejection_reason="late", send_notifications=False
    )

    assert result["notifications_sent"] == 0
    assert result["notifications_failed"] == 0


@pytest.mark.asyncio
async def test_auto_approve_by_criteria_filters(monkeypatch):
    app1 = DummyApplication("APP-7", ApplicationStatus.submitted.value, priority_score=50)
    app2 = DummyApplication("APP-8", ApplicationStatus.under_review.value, priority_score=5)
    session = StubSession([StubResult([app1, app2])])
    service = make_service(session)

    def fake_meets(app, criteria):
        return app.priority_score >= criteria["min_priority_score"]

    monkeypatch.setattr(service, "_meets_approval_criteria", fake_meets)

    result = await service.auto_approve_by_criteria(min_priority_score=10, approval_criteria={"min_priority_score": 10})

    assert result["success_count"] == 1
    assert result["auto_approved"][0]["app_id"] == "APP-7"
    assert session.commits == 1


@pytest.mark.asyncio
async def test_auto_approve_by_criteria_commit_failure():
    app = DummyApplication("APP-commit-fail", ApplicationStatus.submitted.value)
    session = StubSession([StubResult([app])])

    async def failing_commit():
        session.commits += 1
        raise RuntimeError("commit boom")

    session.commit = failing_commit
    service = make_service(session)

    result = await service.auto_approve_by_criteria()

    assert result["success_count"] == 0
    assert result["failure_count"] == 1
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_auto_approve_by_criteria_execute_failure():
    session = StubSession()

    async def failing_execute(_):
        raise RuntimeError("select failed")

    session.execute = failing_execute
    service = make_service(session)

    with pytest.raises(RuntimeError):
        await service.auto_approve_by_criteria()


def test_meets_approval_criteria_checks_values(caplog):
    application = DummyApplication(
        "APP-9",
        ApplicationStatus.submitted.value,
        gpa="2.5",
        class_ranking_percent="50",
        is_renewal=False,
        priority_score=3,
    )
    service = make_service(StubSession())

    # GPA removed from criteria - should be validated by ScholarshipRule system
    criteria = {
        "max_ranking": 40,
        "require_renewal": True,
        "min_priority_score": 10,
    }

    assert service._meets_approval_criteria(application, criteria) is False

    # Error handling path - GPA removed
    broken_app = SimpleNamespace(id=999, class_ranking_percent=None, is_renewal=True, priority_score=None)
    assert service._meets_approval_criteria(broken_app, {}) is True  # No criteria to fail


def test_meets_approval_criteria_happy_path():
    app = DummyApplication(
        "APP-criteria",
        ApplicationStatus.submitted.value,
        # gpa removed - should be validated by ScholarshipRule system
        class_ranking_percent="25",
        is_renewal=True,
        priority_score=42,
    )
    service = make_service(StubSession())

    # GPA removed from criteria - should be validated by ScholarshipRule system
    assert (
        service._meets_approval_criteria(
            app,
            {
                "max_ranking": 30,
                "require_renewal": True,
                "min_priority_score": 20,
                "require_complete_documents": True,
            },
        )
        is True
    )


@pytest.mark.asyncio
async def test_bulk_status_update_success():
    app = DummyApplication("APP-10", ApplicationStatus.submitted.value)
    session = StubSession([StubResult([app])])
    service = make_service(session)

    result = await service.bulk_status_update(
        [app.id], ApplicationStatus.rejected.value, updater_user_id=55, update_notes="quality"
    )

    assert result["success_count"] == 1
    assert result["successful_updates"][0]["old_status"] == ApplicationStatus.submitted.value
    assert session.commits == 1
    assert app.reviewer_id == 55


@pytest.mark.asyncio
async def test_bulk_status_update_commit_failure():
    app = DummyApplication("APP-status", ApplicationStatus.submitted.value)
    session = StubSession([StubResult([app])])

    async def failing_commit():
        session.commits += 1
        raise RuntimeError("commit failed")

    session.commit = failing_commit
    service = make_service(session)

    result = await service.bulk_status_update([app.id], ApplicationStatus.approved.value, updater_user_id=9)

    assert result["failure_count"] == 1
    assert session.rollbacks == 1


@pytest.mark.asyncio
async def test_bulk_status_update_invalid_status():
    session = StubSession()
    service = make_service(session)

    with pytest.raises(ValueError):
        await service.bulk_status_update([1], "INVALID", updater_user_id=1)


@pytest.mark.asyncio
async def test_batch_process_with_notifications(monkeypatch):
    app = DummyApplication("APP-11", ApplicationStatus.submitted.value)
    session = StubSession([StubResult([app])])
    notification_stub = StubNotificationService(responses=[True])
    service = make_service(session, notification_stub)

    params = {"approval_notes": "done", "send_notifications": True}
    result = await service.batch_process_with_notifications(
        "approve", [app.id], operator_user_id=1, operation_params=params, admin_email="admin@example.com"
    )

    assert result["operation_metadata"]["operation_type"] == "approve"
    assert notification_stub.batch_calls == []  # bulk approve payload lacks success_count key


@pytest.mark.asyncio
async def test_batch_process_with_notifications_admin_email(monkeypatch):
    session = StubSession()
    notification_stub = StubNotificationService()
    service = make_service(session, notification_stub)

    service.bulk_approve_applications = AsyncMock(
        return_value={"success_count": 2, "failure_count": 0, "total_requested": 2}
    )

    await service.batch_process_with_notifications(
        "approve",
        [1, 2],
        operator_user_id=42,
        operation_params={"approval_notes": "ok", "send_notifications": True},
        admin_email="ops@example.com",
    )

    assert notification_stub.batch_calls[0][0] == "ops@example.com"

    # Invalid operation should raise
    with pytest.raises(ValueError):
        await service.batch_process_with_notifications("unknown", [1], operator_user_id=1, operation_params={})


@pytest.mark.asyncio
async def test_batch_process_with_notifications_reject_path(monkeypatch):
    session = StubSession()
    service = make_service(session)

    service.bulk_reject_applications = AsyncMock(
        return_value={"success_count": 1, "failure_count": 0, "total_requested": 1}
    )

    result = await service.batch_process_with_notifications(
        "reject",
        [1],
        operator_user_id=9,
        operation_params={"rejection_reason": "bad docs", "send_notifications": False},
    )

    assert result["operation_metadata"]["operation_type"] == "reject"
    service.bulk_reject_applications.assert_awaited()


@pytest.mark.asyncio
async def test_batch_process_with_notifications_update_status(monkeypatch):
    session = StubSession()
    service = make_service(session)

    service.bulk_status_update = AsyncMock(return_value={"success_count": 0, "failure_count": 1, "total_requested": 1})

    result = await service.batch_process_with_notifications(
        "update_status",
        [1],
        operator_user_id=9,
        operation_params={"new_status": ApplicationStatus.rejected.value, "update_notes": "note"},
    )

    assert result["operation_metadata"]["operation_type"] == "update_status"
    service.bulk_status_update.assert_awaited()

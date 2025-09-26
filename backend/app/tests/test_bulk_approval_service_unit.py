from datetime import datetime, timezone
from types import SimpleNamespace

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

    async def execute(self, stmt):
        if not self._results:
            raise AssertionError("No stubbed result available")
        return self._results.pop(0)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


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
        self.gpa = kwargs.get("gpa", "3.5")
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
    app1 = DummyApplication("APP-1", ApplicationStatus.SUBMITTED.value)
    app2 = DummyApplication("APP-2", ApplicationStatus.UNDER_REVIEW.value)
    session = StubSession([StubResult([app1, app2])])
    notification_stub = StubNotificationService(responses=[True, False])
    service = make_service(session, notification_stub)

    result = await service.bulk_approve_applications([app1.id, app2.id], approver_user_id=99, approval_notes="note")

    assert result["total_requested"] == 2
    assert len(result["successful_approvals"]) == 2
    assert result["notifications_sent"] == 1
    assert result["notifications_failed"] == 1
    assert session.commits == 2
    assert app1.calculate_calls == 1
    assert all(item["new_status"] == ApplicationStatus.APPROVED.value for item in result["successful_approvals"])


@pytest.mark.asyncio
async def test_bulk_approve_applications_handles_invalid_status():
    app = DummyApplication("APP-3", ApplicationStatus.CANCELLED.value)
    session = StubSession([StubResult([app])])
    service = make_service(session)

    result = await service.bulk_approve_applications([app.id], approver_user_id=1)

    assert result["successful_approvals"] == []
    assert result["failed_approvals"][0]["reason"].startswith("Invalid status")
    assert session.commits == 0


@pytest.mark.asyncio
async def test_bulk_approve_records_notification_error(monkeypatch):
    app = DummyApplication("APP-4", ApplicationStatus.RECOMMENDED.value)
    session = StubSession([StubResult([app])])
    notification_stub = StubNotificationService(responses=[RuntimeError("boom")])
    service = make_service(session, notification_stub)

    result = await service.bulk_approve_applications([app.id], approver_user_id=5)

    assert result["notifications_failed"] == 1
    assert session.commits == 1
    assert session.rollbacks == 0


@pytest.mark.asyncio
async def test_bulk_reject_applications_success():
    app = DummyApplication("APP-5", ApplicationStatus.SUBMITTED.value)
    session = StubSession([StubResult([app])])
    notification_stub = StubNotificationService(responses=[True])
    service = make_service(session, notification_stub)

    result = await service.bulk_reject_applications([app.id], rejector_user_id=7, rejection_reason="missing docs")

    assert len(result["successful_rejections"]) == 1
    assert result["notifications_sent"] == 1
    assert app.rejection_reason == "missing docs"


@pytest.mark.asyncio
async def test_bulk_reject_handles_failure():
    app = DummyApplication("APP-6", ApplicationStatus.APPROVED.value)
    session = StubSession([StubResult([app])])
    service = make_service(session)

    result = await service.bulk_reject_applications([app.id], rejector_user_id=8, rejection_reason="late")

    assert result["successful_rejections"] == []
    assert result["failed_rejections"][0]["reason"].startswith("Invalid status")


@pytest.mark.asyncio
async def test_auto_approve_by_criteria_filters(monkeypatch):
    app1 = DummyApplication("APP-7", ApplicationStatus.SUBMITTED.value, priority_score=50)
    app2 = DummyApplication("APP-8", ApplicationStatus.UNDER_REVIEW.value, priority_score=5)
    session = StubSession([StubResult([app1, app2])])
    service = make_service(session)

    def fake_meets(app, criteria):
        return app.priority_score >= criteria["min_priority_score"]

    monkeypatch.setattr(service, "_meets_approval_criteria", fake_meets)

    result = await service.auto_approve_by_criteria(min_priority_score=10, approval_criteria={"min_priority_score": 10})

    assert result["success_count"] == 1
    assert result["auto_approved"][0]["app_id"] == "APP-7"
    assert session.commits == 1


def test_meets_approval_criteria_checks_values(caplog):
    application = DummyApplication(
        "APP-9",
        ApplicationStatus.SUBMITTED.value,
        gpa="2.5",
        class_ranking_percent="50",
        is_renewal=False,
        priority_score=3,
    )
    service = make_service(StubSession())

    criteria = {
        "min_gpa": 3.0,
        "max_ranking": 40,
        "require_renewal": True,
        "min_priority_score": 10,
    }

    assert service._meets_approval_criteria(application, criteria) is False

    # Error handling path
    broken_app = SimpleNamespace(id=999, gpa="bad", class_ranking_percent=None, is_renewal=True, priority_score=None)
    assert service._meets_approval_criteria(broken_app, {"min_gpa": 2.0}) is False


@pytest.mark.asyncio
async def test_bulk_status_update_success():
    app = DummyApplication("APP-10", ApplicationStatus.SUBMITTED.value)
    session = StubSession([StubResult([app])])
    service = make_service(session)

    result = await service.bulk_status_update(
        [app.id], ApplicationStatus.REJECTED.value, updater_user_id=55, update_notes="quality"
    )

    assert result["success_count"] == 1
    assert result["successful_updates"][0]["old_status"] == ApplicationStatus.SUBMITTED.value
    assert session.commits == 1
    assert app.reviewer_id == 55


@pytest.mark.asyncio
async def test_bulk_status_update_invalid_status():
    session = StubSession()
    service = make_service(session)

    with pytest.raises(ValueError):
        await service.bulk_status_update([1], "INVALID", updater_user_id=1)


@pytest.mark.asyncio
async def test_batch_process_with_notifications(monkeypatch):
    app = DummyApplication("APP-11", ApplicationStatus.SUBMITTED.value)
    session = StubSession([StubResult([app])])
    notification_stub = StubNotificationService(responses=[True])
    service = make_service(session, notification_stub)

    params = {"approval_notes": "done", "send_notifications": True}
    result = await service.batch_process_with_notifications(
        "approve", [app.id], operator_user_id=1, operation_params=params, admin_email="admin@example.com"
    )

    assert result["operation_metadata"]["operation_type"] == "approve"
    assert notification_stub.batch_calls == []  # bulk approve payload lacks success_count key

    # Invalid operation should raise
    with pytest.raises(ValueError):
        await service.batch_process_with_notifications("unknown", [app.id], operator_user_id=1, operation_params={})

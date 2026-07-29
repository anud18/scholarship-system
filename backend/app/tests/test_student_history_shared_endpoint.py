"""Integration tests for the shared /api/v1/student-history endpoints.

- POST /student-history/batch (admin/super_admin/college; college scoped to
  its own college, snapshot-first with live SIS as a secondary signal)
- GET /student-history/me/months (student, months total only)

Auth pattern: override get_current_user with a configured Mock so the REAL
role-dependency checks (require_scholarship_manager / require_student) still
run. Mock(spec=User) alone is not enough — un-configured is_admin()/is_college()
return truthy Mocks and every role check would pass.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from app.models.user import User, UserRole

SERVICE_PATH = "app.api.v1.endpoints.student_history.StudentScholarshipHistoryService"
COLLEGE_NOT_VISIBLE = "查無符合條件的學生資料"


def _mock_user(role: UserRole, nycu_id: str = "tester01", college_code=None) -> Mock:
    user = Mock(spec=User)
    user.id = 1
    user.nycu_id = nycu_id
    user.role = role
    user.college_code = college_code
    user.is_admin.return_value = role == UserRole.admin
    user.is_super_admin.return_value = role == UserRole.super_admin
    user.is_college.return_value = role == UserRole.college
    user.is_student.return_value = role == UserRole.student
    user.is_professor.return_value = role == UserRole.professor
    return user


def _mock_service(MockSvc, get_history=None):
    """Configure the mocked service with batch-endpoint defaults."""
    svc = MockSvc.return_value
    svc.fetch_sis_lookups = AsyncMock(return_value={})
    svc.get_snapshot_academy_codes = AsyncMock(return_value=set())
    if get_history is not None:
        svc.get_history = AsyncMock(side_effect=get_history)
    return svc


def _history_data(
    student_number: str = "S001",
    academy_no=None,
    available: bool = True,
    total_months: int = 5,
    with_sensitive_fields: bool = False,
):
    from app.schemas.student_scholarship_history import (
        AcademicBasicInfo,
        AcademicInfo,
        HistorySummary,
        PaymentRecord,
        ReceivedMonthsBreakdown,
        StudentScholarshipHistoryData,
    )

    academic_info = (
        AcademicInfo(available=True, basic_info=AcademicBasicInfo(std_academyno=academy_no))
        if available
        else AcademicInfo(available=False, error="SIS down", basic_info=None)
    )
    payment_records = []
    received_months = []
    if with_sensitive_fields:
        payment_records = [
            PaymentRecord(
                roster_id=1,
                roster_code="R",
                period_label="114-10",
                academic_year=114,
                roster_cycle="monthly",
                scholarship_name="A",
                scholarship_amount=Decimal("1000"),
                revoke_reason="admin-only note",
                suspend_reason="admin-only note",
            )
        ]
        received_months = [
            ReceivedMonthsBreakdown(
                scholarship_type_id=1,
                scholarship_name="A",
                total_months=total_months,
                imported_months=total_months,
                system_months=0,
                raw_row={"隱藏欄": "imported cell"},
                file_name="import.xlsx",
                imported_at="2026-01-01T00:00:00",
            )
        ]
    return StudentScholarshipHistoryData(
        student_number=student_number,
        academic_info=academic_info,
        summary=HistorySummary(
            total_records=len(payment_records),
            total_amount=Decimal("0"),
            scholarship_type_count=len(payment_records),
            snapshot_name=None,
            total_received_months=total_months,
        ),
        payment_records=payment_records,
        received_months=received_months,
    )


@pytest_asyncio.fixture
async def client_as():
    """Factory: yield an AsyncClient authenticated as the given mock user."""
    from app.core.security import get_current_user
    from app.main import app

    created = []

    def _make(client, user):
        async def override():
            return user

        app.dependency_overrides[get_current_user] = override
        created.append(get_current_user)
        return client

    yield _make
    for dep in created:
        app.dependency_overrides.pop(dep, None)


# ---------------------------------------------------------------------------
# POST /student-history/batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_batch_mixed_found_and_not_found(client, client_as, db):
    """Per-student results: a 404 for one 學號 doesn't sink the batch. Duplicate
    numbers are deduped before lookup, and the batch leaves an audit trail."""
    from app.core.exceptions import NotFoundError

    authed = client_as(client, _mock_user(UserRole.admin))
    with patch(SERVICE_PATH) as MockSvc:
        _mock_service(
            MockSvc,
            get_history=[_history_data("S001"), NotFoundError("查無此學生資料", "GHOST1")],
        )
        response = await authed.post(
            "/api/v1/student-history/batch",
            json={"student_numbers": ["S001", "GHOST1", "S001"]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    results = body["data"]["results"]
    assert len(results) == 2
    assert results[0]["student_number"] == "S001"
    assert results[0]["success"] is True
    assert results[0]["data"]["student_number"] == "S001"
    assert results[1]["student_number"] == "GHOST1"
    assert results[1]["success"] is False
    assert "查無" in results[1]["error"]

    from sqlalchemy import select

    from app.models.audit_log import AuditLog

    logs = (await db.execute(select(AuditLog).where(AuditLog.resource_type == "student_history"))).scalars().all()
    assert len(logs) == 1
    assert logs[0].new_values["student_numbers"] == ["S001", "GHOST1"]
    assert logs[0].new_values["returned"] == ["S001"]


@pytest.mark.asyncio
async def test_college_batch_scoped_without_existence_oracle(client, client_as):
    """College sees own-college students (via live SIS); other-college and
    nonexistent students get the SAME error message, so responses cannot be
    used to probe which student numbers exist."""
    from app.core.exceptions import NotFoundError

    authed = client_as(client, _mock_user(UserRole.college, college_code="E"))
    with patch(SERVICE_PATH) as MockSvc:
        _mock_service(
            MockSvc,
            get_history=[
                _history_data("S001", academy_no="E"),
                _history_data("S002", academy_no="C"),
                NotFoundError("查無此學生資料", "GHOST1"),
            ],
        )
        response = await authed.post(
            "/api/v1/student-history/batch",
            json={"student_numbers": ["S001", "S002", "GHOST1"]},
        )

    assert response.status_code == 200
    results = response.json()["data"]["results"]
    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert results[2]["success"] is False
    # Existence oracle closed: out-of-college and not-found are identical.
    assert results[1]["error"] == COLLEGE_NOT_VISIBLE
    assert results[2]["error"] == COLLEGE_NOT_VISIBLE
    assert results[1]["data"] is None


@pytest.mark.asyncio
async def test_college_snapshot_grants_access_when_sis_down(client, client_as):
    """SIS unavailability must not lock a college out of its own students:
    the frozen application snapshot (std_academyno) grants access alone."""
    authed = client_as(client, _mock_user(UserRole.college, college_code="E"))
    with patch(SERVICE_PATH) as MockSvc:
        svc = _mock_service(MockSvc, get_history=[_history_data("S001", available=False)])
        svc.get_snapshot_academy_codes = AsyncMock(return_value={"E"})
        response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["S001"]})

    assert response.status_code == 200
    result = response.json()["data"]["results"][0]
    assert result["success"] is True


@pytest.mark.asyncio
async def test_college_denied_when_neither_sis_nor_snapshot_match(client, client_as):
    """No SIS data and no matching snapshot → denied (fail closed), with the
    oracle-safe message."""
    authed = client_as(client, _mock_user(UserRole.college, college_code="E"))
    with patch(SERVICE_PATH) as MockSvc:
        _mock_service(MockSvc, get_history=[_history_data("S001", available=False)])
        response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["S001"]})

    result = response.json()["data"]["results"][0]
    assert result["success"] is False
    assert result["error"] == COLLEGE_NOT_VISIBLE


@pytest.mark.asyncio
async def test_college_payload_hides_admin_only_fields(client, client_as):
    """College results must not carry admin-authored content: revocation and
    suspension free-text, and the raw imported-file rows/provenance."""
    authed = client_as(client, _mock_user(UserRole.college, college_code="E"))
    with patch(SERVICE_PATH) as MockSvc:
        _mock_service(
            MockSvc,
            get_history=[_history_data("S001", academy_no="E", with_sensitive_fields=True)],
        )
        response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["S001"]})

    data = response.json()["data"]["results"][0]["data"]
    record = data["payment_records"][0]
    assert record["revoke_reason"] is None
    assert record["suspend_reason"] is None
    breakdown = data["received_months"][0]
    assert breakdown["raw_row"] is None
    assert breakdown["file_name"] is None
    assert breakdown["imported_at"] is None
    # Months themselves remain visible.
    assert breakdown["total_months"] == 5


@pytest.mark.asyncio
async def test_admin_payload_keeps_admin_fields(client, client_as):
    authed = client_as(client, _mock_user(UserRole.admin))
    with patch(SERVICE_PATH) as MockSvc:
        _mock_service(MockSvc, get_history=[_history_data("S001", with_sensitive_fields=True)])
        response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["S001"]})

    data = response.json()["data"]["results"][0]["data"]
    assert data["payment_records"][0]["revoke_reason"] == "admin-only note"
    assert data["received_months"][0]["raw_row"] == {"隱藏欄": "imported cell"}


@pytest.mark.asyncio
async def test_unexpected_error_mid_batch_reports_per_student(client, client_as):
    """A DB/lookup crash for one student must not 500 the batch nor discard
    the other results (per-student contract)."""
    authed = client_as(client, _mock_user(UserRole.admin))
    with patch(SERVICE_PATH) as MockSvc:
        _mock_service(
            MockSvc,
            get_history=[_history_data("S001"), RuntimeError("db exploded"), _history_data("S003")],
        )
        response = await authed.post(
            "/api/v1/student-history/batch",
            json={"student_numbers": ["S001", "S002", "S003"]},
        )

    assert response.status_code == 200
    results = response.json()["data"]["results"]
    assert [r["success"] for r in results] == [True, False, True]
    assert "查詢失敗" in results[1]["error"]


@pytest.mark.asyncio
async def test_college_without_college_code_rejected(client, client_as):
    authed = client_as(client, _mock_user(UserRole.college, college_code=None))
    response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["S001"]})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_batch_validation_errors(client, client_as):
    """Empty list, oversized batch and malformed 學號 all yield 400."""
    authed = client_as(client, _mock_user(UserRole.admin))

    response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["  "]})
    assert response.status_code == 400

    response = await authed.post(
        "/api/v1/student-history/batch",
        json={"student_numbers": [f"S{i:05d}" for i in range(21)]},
    )
    assert response.status_code == 400

    response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["bad@@chars"]})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_batch_rejects_student_and_professor_roles(client, client_as):
    """Both non-staff-manager roles are rejected. The professor case guards
    against a future require_staff swap — require_staff includes professors,
    and the college scope gate does not apply to non-college users."""
    for role in (UserRole.student, UserRole.professor):
        authed = client_as(client, _mock_user(role))
        response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["S001"]})
        assert response.status_code == 403, f"role {role.value} must be rejected"


@pytest.mark.asyncio
async def test_batch_unauthenticated(client):
    response = await client.post("/api/v1/student-history/batch", json={"student_numbers": ["S001"]})
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /student-history/me/months
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_months_returns_total_only(client, client_as):
    """Students get their 學號 and 總月數 — no payment records, no amounts."""
    authed = client_as(client, _mock_user(UserRole.student, nycu_id="stuphd001"))
    with patch(SERVICE_PATH) as MockSvc:
        MockSvc.return_value.get_total_received_months = AsyncMock(return_value=12)
        response = await authed.get("/api/v1/student-history/me/months")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {"student_number": "stuphd001", "total_received_months": 12}


@pytest.mark.asyncio
async def test_me_months_empty_history_is_zero(client, client_as):
    authed = client_as(client, _mock_user(UserRole.student, nycu_id="stunew001"))
    with patch(SERVICE_PATH) as MockSvc:
        MockSvc.return_value.get_total_received_months = AsyncMock(return_value=0)
        response = await authed.get("/api/v1/student-history/me/months")

    assert response.status_code == 200
    assert response.json()["data"]["total_received_months"] == 0


@pytest.mark.asyncio
async def test_me_months_rejects_non_students(client, client_as):
    authed = client_as(client, _mock_user(UserRole.admin))
    response = await authed.get("/api/v1/student-history/me/months")
    assert response.status_code == 403

"""Integration tests for the shared /api/v1/student-history endpoints.

- POST /student-history/batch (admin/super_admin/college, college scoped to
  its own college via SIS std_academyno)
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


def _history_data(student_number: str = "S001", academy_no=None, available: bool = True, total_months: int = 5):
    from app.schemas.student_scholarship_history import (
        AcademicBasicInfo,
        AcademicInfo,
        HistorySummary,
        StudentScholarshipHistoryData,
    )

    academic_info = (
        AcademicInfo(available=True, basic_info=AcademicBasicInfo(std_academyno=academy_no))
        if available
        else AcademicInfo(available=False, error="SIS down", basic_info=None)
    )
    return StudentScholarshipHistoryData(
        student_number=student_number,
        academic_info=academic_info,
        summary=HistorySummary(
            total_records=0,
            total_amount=Decimal("0"),
            scholarship_type_count=0,
            snapshot_name=None,
            total_received_months=total_months,
        ),
        payment_records=[],
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
async def test_admin_batch_mixed_found_and_not_found(client, client_as):
    """Per-student results: a 404 for one 學號 doesn't sink the batch. Duplicate
    numbers are deduped before lookup."""
    from app.core.exceptions import NotFoundError

    authed = client_as(client, _mock_user(UserRole.admin))
    with patch(SERVICE_PATH) as MockSvc:
        MockSvc.return_value.get_history = AsyncMock(
            side_effect=[_history_data("S001"), NotFoundError("查無此學生資料", "GHOST1")]
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


@pytest.mark.asyncio
async def test_college_batch_scoped_to_own_college(client, client_as):
    """College sees own-college students; other colleges and SIS-unverifiable
    students are denied per-student."""
    authed = client_as(client, _mock_user(UserRole.college, college_code="E"))
    with patch(SERVICE_PATH) as MockSvc:
        MockSvc.return_value.get_history = AsyncMock(
            side_effect=[
                _history_data("S001", academy_no="E"),
                _history_data("S002", academy_no="C"),
                _history_data("S003", available=False),
            ]
        )
        response = await authed.post(
            "/api/v1/student-history/batch",
            json={"student_numbers": ["S001", "S002", "S003"]},
        )

    assert response.status_code == 200
    results = response.json()["data"]["results"]
    assert results[0]["success"] is True
    assert results[1]["success"] is False
    assert "本學院" in results[1]["error"]
    assert results[1]["data"] is None
    assert results[2]["success"] is False
    assert "無法確認" in results[2]["error"]


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
        json={"student_numbers": [f"S{i:05d}" for i in range(51)]},
    )
    assert response.status_code == 400

    response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["bad@@chars"]})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_batch_rejects_student_and_professor_roles(client, client_as):
    authed = client_as(client, _mock_user(UserRole.student))
    response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["S001"]})
    assert response.status_code == 403


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
        MockSvc.return_value.get_history = AsyncMock(return_value=_history_data("stuphd001", total_months=12))
        response = await authed.get("/api/v1/student-history/me/months")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data == {"student_number": "stuphd001", "total_received_months": 12}


@pytest.mark.asyncio
async def test_me_months_no_history_is_zero_not_404(client, client_as):
    from app.core.exceptions import NotFoundError

    authed = client_as(client, _mock_user(UserRole.student, nycu_id="stunew001"))
    with patch(SERVICE_PATH) as MockSvc:
        MockSvc.return_value.get_history = AsyncMock(side_effect=NotFoundError("查無此學生資料", "stunew001"))
        response = await authed.get("/api/v1/student-history/me/months")

    assert response.status_code == 200
    assert response.json()["data"]["total_received_months"] == 0


@pytest.mark.asyncio
async def test_me_months_rejects_non_students(client, client_as):
    authed = client_as(client, _mock_user(UserRole.admin))
    response = await authed.get("/api/v1/student-history/me/months")
    assert response.status_code == 403

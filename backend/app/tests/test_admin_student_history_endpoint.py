"""Integration tests for GET /api/v1/admin/student-history/{student_number}.

Auth pattern follows test_admin_endpoints.py — overrides require_admin per test
class. The conftest `client` fixture is unauthenticated; the conftest
`admin_client` only sets a header (no dependency override), so we wire our own.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def authed_admin_client(client, admin_user):
    """AsyncClient with require_admin overridden to return the mock admin_user."""
    from app.core.security import require_admin
    from app.main import app

    async def override_require_admin():
        return admin_user

    app.dependency_overrides[require_admin] = override_require_admin
    yield client
    del app.dependency_overrides[require_admin]


@pytest.mark.asyncio
async def test_invalid_student_number_format_returns_400(authed_admin_client):
    """Invalid chars in path → 400 from regex validation."""
    response = await authed_admin_client.get("/api/v1/admin/student-history/bad@@chars")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_nonexistent_student_returns_404(authed_admin_client):
    """No SIS data + no roster records → 404."""
    from app.core.exceptions import NotFoundError

    with patch(
        "app.api.v1.endpoints.admin.student_history.StudentScholarshipHistoryService"
    ) as MockSvc:
        MockSvc.return_value.get_history = AsyncMock(
            side_effect=NotFoundError("查無此學生資料: GHOST")
        )
        response = await authed_admin_client.get("/api/v1/admin/student-history/GHOST1")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_valid_student_returns_wrapped_api_response(authed_admin_client):
    """Successful path returns ApiResponse-wrapped data per CLAUDE.md §5."""
    from decimal import Decimal

    from app.schemas.student_scholarship_history import (
        AcademicInfo,
        HistorySummary,
        PaymentRecord,
        StudentScholarshipHistoryData,
    )

    fake_data = StudentScholarshipHistoryData(
        student_number="S001",
        academic_info=AcademicInfo(available=True, basic_info=None),
        summary=HistorySummary(
            total_records=1,
            total_amount=Decimal("1000"),
            scholarship_type_count=1,
            snapshot_name="王小明",
        ),
        payment_records=[
            PaymentRecord(
                roster_id=1,
                roster_code="R",
                period_label="114-10",
                academic_year=114,
                roster_cycle="monthly",
                scholarship_name="A",
                scholarship_amount=Decimal("1000"),
            )
        ],
    )

    with patch(
        "app.api.v1.endpoints.admin.student_history.StudentScholarshipHistoryService"
    ) as MockSvc:
        MockSvc.return_value.get_history = AsyncMock(return_value=fake_data)
        response = await authed_admin_client.get("/api/v1/admin/student-history/S001")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["student_number"] == "S001"
    assert body["data"]["summary"]["total_records"] == 1
    assert body["data"]["payment_records"][0]["scholarship_name"] == "A"


@pytest.mark.asyncio
async def test_unauthenticated_returns_401_or_403(client):
    """Bare client (no admin override) → require_admin rejects."""
    response = await client.get("/api/v1/admin/student-history/S001")
    assert response.status_code in (401, 403)

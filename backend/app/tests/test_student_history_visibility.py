"""Tests for the admin switches gating 學生領獎紀錄查詢.

Two independent settings decide whether students may see their own 總月數 and
whether colleges may look up their students' 領獎紀錄. Admin access is never
gated by them.

Auth pattern mirrors test_student_history_shared_endpoint.py: override
get_current_user with a fully configured Mock so the REAL role dependencies
still run.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from app.models.user import User, UserRole
from app.services.student_history_visibility import (
    COLLEGE_VISIBILITY_KEY,
    STUDENT_VISIBILITY_KEY,
    get_student_history_visibility,
    set_student_history_visibility,
)

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
# Service layer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_rows_read_as_open(db):
    """A database that predates the feature keeps behaving as it did."""
    visibility = await get_student_history_visibility(db)
    assert visibility.student_enabled is True
    assert visibility.college_enabled is True


@pytest.mark.asyncio
async def test_switches_are_independent(db):
    """Writing one audience must never touch the other — they are decided
    separately, and a concurrent toggle must not be clobbered."""
    await set_student_history_visibility(db, user_id=1, student_enabled=False, college_enabled=True)
    visibility = await get_student_history_visibility(db)
    assert visibility.student_enabled is False
    assert visibility.college_enabled is True

    # Only the college switch is sent this time.
    await set_student_history_visibility(db, user_id=1, college_enabled=False)
    visibility = await get_student_history_visibility(db)
    assert visibility.student_enabled is False, "student switch must survive a college-only update"
    assert visibility.college_enabled is False

    await set_student_history_visibility(db, user_id=1, student_enabled=True)
    visibility = await get_student_history_visibility(db)
    assert visibility.student_enabled is True
    assert visibility.college_enabled is False


@pytest.mark.asyncio
async def test_updates_are_audited(db):
    """Changes go through ConfigurationService, so 系統設定 audit history sees
    them like any other setting change."""
    from sqlalchemy import select

    from app.models.system_setting import ConfigurationAuditLog

    await set_student_history_visibility(db, user_id=7, college_enabled=False)

    logs = (
        (
            await db.execute(
                select(ConfigurationAuditLog).where(ConfigurationAuditLog.setting_key == COLLEGE_VISIBILITY_KEY)
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].new_value == "false"
    assert logs[0].changed_by == 7


@pytest.mark.asyncio
async def test_stored_values_are_boolean_typed(db):
    """Stored as a real boolean setting so the generic 系統設定 editor renders
    and round-trips it correctly."""
    from sqlalchemy import select

    from app.models.system_setting import ConfigCategory, ConfigDataType, SystemSetting

    await set_student_history_visibility(db, user_id=1, student_enabled=False)
    setting = (
        (await db.execute(select(SystemSetting).where(SystemSetting.key == STUDENT_VISIBILITY_KEY))).scalars().one()
    )
    assert setting.value == "false"
    assert setting.data_type == ConfigDataType.boolean
    assert setting.category == ConfigCategory.features


# ---------------------------------------------------------------------------
# GET/PUT /student-history/visibility
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_visibility_open_to_any_authenticated_role(client, client_as, db):
    """The student card and college tab need the flags before making a gated
    request, so every logged-in role may read them."""
    await set_student_history_visibility(db, user_id=1, student_enabled=False, college_enabled=True)

    for role in (UserRole.student, UserRole.college, UserRole.professor, UserRole.admin):
        authed = client_as(client, _mock_user(role))
        response = await authed.get("/api/v1/student-history/visibility")
        assert response.status_code == 200, f"role {role.value} must be able to read the flags"
        assert response.json()["data"] == {"student_enabled": False, "college_enabled": True}


@pytest.mark.asyncio
async def test_get_visibility_unauthenticated(client):
    response = await client.get("/api/v1/student-history/visibility")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_updates_one_switch_at_a_time(client, client_as, db):
    authed = client_as(client, _mock_user(UserRole.admin))

    response = await authed.put("/api/v1/student-history/visibility", json={"college_enabled": False})
    assert response.status_code == 200
    # The response carries BOTH switches so the UI never guesses the other.
    assert response.json()["data"] == {"student_enabled": True, "college_enabled": False}

    response = await authed.put("/api/v1/student-history/visibility", json={"student_enabled": False})
    assert response.status_code == 200
    assert response.json()["data"] == {"student_enabled": False, "college_enabled": False}

    visibility = await get_student_history_visibility(db)
    assert visibility.student_enabled is False
    assert visibility.college_enabled is False


@pytest.mark.asyncio
async def test_update_visibility_rejects_non_admin_roles(client, client_as):
    for role in (UserRole.student, UserRole.college, UserRole.professor):
        authed = client_as(client, _mock_user(role, college_code="E"))
        response = await authed.put("/api/v1/student-history/visibility", json={"college_enabled": True})
        assert response.status_code == 403, f"role {role.value} must not change the switches"


@pytest.mark.asyncio
async def test_update_visibility_requires_a_field(client, client_as):
    authed = client_as(client, _mock_user(UserRole.admin))
    response = await authed.put("/api/v1/student-history/visibility", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Enforcement on the gated endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_college_batch_blocked_when_closed(client, client_as, db):
    await set_student_history_visibility(db, user_id=1, college_enabled=False)

    authed = client_as(client, _mock_user(UserRole.college, college_code="E"))
    with patch(SERVICE_PATH) as MockSvc:
        MockSvc.return_value.fetch_sis_lookups = AsyncMock(return_value={})
        response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["S001"]})

    assert response.status_code == 403
    # No lookup work is done once the feature is closed to colleges.
    MockSvc.return_value.fetch_sis_lookups.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_batch_unaffected_by_switches(client, client_as, db):
    """The switches open the feature to OTHERS; admins always keep access."""
    from decimal import Decimal

    from app.schemas.student_scholarship_history import (
        AcademicInfo,
        HistorySummary,
        StudentScholarshipHistoryData,
    )

    await set_student_history_visibility(db, user_id=1, student_enabled=False, college_enabled=False)

    authed = client_as(client, _mock_user(UserRole.admin))
    with patch(SERVICE_PATH) as MockSvc:
        svc = MockSvc.return_value
        svc.fetch_sis_lookups = AsyncMock(return_value={})
        svc.get_snapshot_academy_codes = AsyncMock(return_value=set())
        svc.get_history = AsyncMock(
            return_value=StudentScholarshipHistoryData(
                student_number="S001",
                academic_info=AcademicInfo(available=False, error="SIS down", basic_info=None),
                summary=HistorySummary(
                    total_records=0,
                    total_amount=Decimal("0"),
                    scholarship_type_count=0,
                    total_received_months=0,
                ),
                payment_records=[],
                received_months=[],
            )
        )
        response = await authed.post("/api/v1/student-history/batch", json={"student_numbers": ["S001"]})

    assert response.status_code == 200
    assert response.json()["data"]["results"][0]["success"] is True


@pytest.mark.asyncio
async def test_me_months_blocked_when_closed(client, client_as, db):
    await set_student_history_visibility(db, user_id=1, student_enabled=False)

    authed = client_as(client, _mock_user(UserRole.student, nycu_id="stuphd001"))
    with patch(SERVICE_PATH) as MockSvc:
        MockSvc.return_value.get_total_received_months = AsyncMock(return_value=12)
        response = await authed.get("/api/v1/student-history/me/months")

    assert response.status_code == 403
    MockSvc.return_value.get_total_received_months.assert_not_awaited()


@pytest.mark.asyncio
async def test_me_months_allowed_when_open(client, client_as, db):
    """Closing 學院查詢 must not close the student's own view."""
    await set_student_history_visibility(db, user_id=1, student_enabled=True, college_enabled=False)

    authed = client_as(client, _mock_user(UserRole.student, nycu_id="stuphd001"))
    with patch(SERVICE_PATH) as MockSvc:
        MockSvc.return_value.get_total_received_months = AsyncMock(return_value=12)
        response = await authed.get("/api/v1/student-history/me/months")

    assert response.status_code == 200
    assert response.json()["data"]["total_received_months"] == 12

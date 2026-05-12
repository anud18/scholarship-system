"""Tests for GET /api/v1/college-review/applications/department-summary-export.

Approach: FastAPI TestClient with dependency_overrides for require_college and get_db.
We use synchronous TestClient (not AsyncClient) since all tests here are synchronous
at the test layer — the app itself is async but TestClient handles that transparently.

We bypass JWT auth entirely by overriding require_college (and get_db) directly on
app.dependency_overrides, which is the standard FastAPI testing pattern and avoids the
need to generate real JWT tokens or seed an SSO-authenticated user.

The DB is in-memory SQLite (via TestingSessionLocal from conftest helpers), seeded with
just the rows each test needs: Department, ScholarshipType, and optionally Application.
"""

from __future__ import annotations

import os

import pytest

# Ensure test mode before any app import
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("PYTEST_CURRENT_TEST", "true")

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings

# Override DB URLs
_TEST_SYNC = "sqlite:///:memory:"
_TEST_ASYNC = "sqlite+aiosqlite:///:memory:"
settings.database_url_sync = _TEST_SYNC
settings.database_url = _TEST_ASYNC

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import require_college  # noqa: E402
from app.db.base_class import Base  # noqa: E402
from app.db.deps import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.scholarship import ScholarshipType  # noqa: E402
from app.models.student import Department  # noqa: E402
from app.models.user import EmployeeStatus, User, UserRole, UserType  # noqa: E402

# ---------------------------------------------------------------------------
# In-process test DB (one sync engine per test via setup/teardown helpers)
# ---------------------------------------------------------------------------

_sync_engine = create_engine(
    _TEST_SYNC,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_async_engine = create_async_engine(
    _TEST_ASYNC,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_AsyncSession = async_sessionmaker(_async_engine, class_=AsyncSession, expire_on_commit=False)


def _run_async(coro):
    import asyncio
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


def _create_tables():
    async def _impl():
        async with _async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    _run_async(_impl())


def _drop_tables():
    async def _impl():
        async with _async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    _run_async(_impl())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_admin_user() -> User:
    return User(
        id=9001,
        nycu_id="admin_export",
        name="Export Admin",
        email="admin_export@test.nycu.edu.tw",
        user_type=UserType.employee,
        status=EmployeeStatus.active,
        role=UserRole.admin,
    )


def _make_college_user(college_code: str = "CE") -> User:
    return User(
        id=9002,
        nycu_id="college_export",
        name="College Export",
        email="college_export@test.nycu.edu.tw",
        user_type=UserType.employee,
        status=EmployeeStatus.active,
        role=UserRole.college,
        college_code=college_code,
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestDepartmentSummaryExportEndpoint:
    """Integration tests for the single-department 申請總表 export endpoint."""

    def setup_method(self):
        _create_tables()

    def teardown_method(self):
        _drop_tables()
        app.dependency_overrides.clear()

    def _client_with_user(self, user: User) -> TestClient:
        """Return a TestClient that bypasses auth and uses an in-process DB session."""

        async def _fake_db():
            async with _AsyncSession() as session:
                yield session

        def _fake_auth():
            return user

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[require_college] = _fake_auth
        return TestClient(app, raise_server_exceptions=True)

    def _seed_department_and_scholarship(self, dept_code: str = "CE4460", academy_code: str = "CE"):
        """Insert a Department + ScholarshipType into the async in-memory DB."""

        async def _impl():
            async with _AsyncSession() as session:
                dept = Department(code=dept_code, name="土木工程學系", academy_code=academy_code)
                stype = ScholarshipType(
                    id=1,
                    code="phd_scholarship",
                    name="博士生獎學金",
                )
                session.add(dept)
                session.add(stype)
                await session.commit()

        _run_async(_impl())

    # ------------------------------------------------------------------
    # Happy-path test: admin downloads an empty (no applications) XLSX
    # ------------------------------------------------------------------

    def test_admin_happy_path_empty_xlsx(self):
        """Admin user can export a department that exists; empty workbook returned."""
        self._seed_department_and_scholarship(dept_code="CE4460", academy_code="CE")

        admin = _make_admin_user()
        client = self._client_with_user(admin)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export",
            params={
                "scholarship_type_id": 1,
                "academic_year": 114,
                "department_code": "CE4460",
            },
        )

        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        # RFC 5987 encoded filename present
        assert "filename*=UTF-8''" in response.headers["content-disposition"]
        assert "114" in response.headers["content-disposition"]
        # Non-empty bytes (openpyxl XLSX always has ZIP magic bytes PK)
        assert response.content[:2] == b"PK"
        # Content-Length header must be present and match body size
        assert "content-length" in response.headers
        assert int(response.headers["content-length"]) == len(response.content)

    # ------------------------------------------------------------------
    # Auth rejection: college user for a different academy gets 403
    # ------------------------------------------------------------------

    def test_college_user_cross_academy_rejected(self):
        """College user whose college_code != dept.academy_code receives 403."""
        self._seed_department_and_scholarship(dept_code="CE4460", academy_code="CE")

        wrong_college_user = _make_college_user(college_code="EE")  # different academy
        client = self._client_with_user(wrong_college_user)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export",
            params={
                "scholarship_type_id": 1,
                "academic_year": 114,
                "department_code": "CE4460",
            },
        )

        assert response.status_code == 403
        body = response.json()
        # App exception handler wraps HTTPException as {"success": False, "message": ...}
        assert "無權限" in body.get("message", body.get("detail", ""))

    # ------------------------------------------------------------------
    # 404: unknown department code
    # ------------------------------------------------------------------

    def test_unknown_department_returns_404(self):
        """Unknown department_code produces a 404 with Chinese message."""
        self._seed_department_and_scholarship(dept_code="CE4460", academy_code="CE")

        admin = _make_admin_user()
        client = self._client_with_user(admin)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export",
            params={
                "scholarship_type_id": 1,
                "academic_year": 114,
                "department_code": "NOSUCHDEPT",
            },
        )

        assert response.status_code == 404
        body = response.json()
        assert "NOSUCHDEPT" in body.get("message", body.get("detail", ""))

    # ------------------------------------------------------------------
    # 404: unknown scholarship type
    # ------------------------------------------------------------------

    def test_unknown_scholarship_type_returns_404(self):
        """Unknown scholarship_type_id produces a 404."""
        self._seed_department_and_scholarship(dept_code="CE4460", academy_code="CE")

        admin = _make_admin_user()
        client = self._client_with_user(admin)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export",
            params={
                "scholarship_type_id": 999,
                "academic_year": 114,
                "department_code": "CE4460",
            },
        )

        assert response.status_code == 404
        body = response.json()
        msg = body.get("message", body.get("detail", ""))
        assert "999" in msg

    # ------------------------------------------------------------------
    # College user for correct academy succeeds
    # ------------------------------------------------------------------

    def test_college_user_same_academy_succeeds(self):
        """College user whose college_code matches dept.academy_code gets 200."""
        self._seed_department_and_scholarship(dept_code="CE4460", academy_code="CE")

        college_user = _make_college_user(college_code="CE")
        client = self._client_with_user(college_user)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export",
            params={
                "scholarship_type_id": 1,
                "academic_year": 114,
                "department_code": "CE4460",
            },
        )

        assert response.status_code == 200
        assert response.content[:2] == b"PK"

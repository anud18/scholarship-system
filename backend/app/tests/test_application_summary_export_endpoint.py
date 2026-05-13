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

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.config import settings

# Override DB URLs
_TEST_SYNC = "sqlite:///:memory:"
_TEST_ASYNC = "sqlite+aiosqlite:///:memory:"
settings.database_url_sync = _TEST_SYNC
settings.database_url = _TEST_ASYNC

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import require_scholarship_manager  # noqa: E402
from app.db.base_class import Base  # noqa: E402
from app.db.deps import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models.scholarship import ScholarshipType  # noqa: E402
from app.models.student import Department  # noqa: E402
from app.models.user import EmployeeStatus, User, UserRole, UserType  # noqa: E402

# ---------------------------------------------------------------------------
# In-process test DB (one sync engine per test via setup/teardown helpers)
# ---------------------------------------------------------------------------

_async_engine = create_async_engine(
    _TEST_ASYNC,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_AsyncSession = async_sessionmaker(_async_engine, class_=AsyncSession, expire_on_commit=False)


def _run_async(coro):
    import asyncio

    return asyncio.run(coro)


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


def _seed_college_permissions(
    user_id: int = 9002,
    scholarship_type_id: int = 1,
    academic_year: int = 114,
):
    """Seed AdminScholarship + ScholarshipConfiguration so _check_*_permission passes
    for a college user.  SQLite does not enforce FKs by default so the user row
    itself does not need to exist in the DB."""

    async def _impl():
        async with _AsyncSession() as session:
            session.add(
                AdminScholarship(
                    admin_id=user_id,
                    scholarship_id=scholarship_type_id,
                )
            )
            session.add(
                ScholarshipConfiguration(
                    id=500,
                    scholarship_type_id=scholarship_type_id,
                    academic_year=academic_year,
                    config_name="Test Config",
                    config_code=f"test_cfg_{scholarship_type_id}_{academic_year}",
                    amount=0,
                    is_active=True,
                )
            )
            await session.commit()

    _run_async(_impl())


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
        app.dependency_overrides[require_scholarship_manager] = _fake_auth
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
        _seed_college_permissions(user_id=9002, scholarship_type_id=1, academic_year=114)

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


# ---------------------------------------------------------------------------
# Bulk ZIP endpoint tests
# ---------------------------------------------------------------------------

from app.models.application import Application  # noqa: E402
from app.models.enums import SubTypeSelectionMode  # noqa: E402
from app.models.scholarship import ScholarshipConfiguration  # noqa: E402
from app.models.user import AdminScholarship  # noqa: E402


class TestDepartmentSummaryExportBulkEndpoint:
    """Integration tests for the bulk ZIP 申請總表 export endpoint."""

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
        app.dependency_overrides[require_scholarship_manager] = _fake_auth
        return TestClient(app, raise_server_exceptions=True)

    def _seed_base(self):
        """Seed two departments (same academy CE) + one scholarship type."""

        async def _impl():
            async with _AsyncSession() as session:
                session.add(Department(code="CE4460", name="土木工程學系", academy_code="CE"))
                session.add(Department(code="CE4461", name="環境工程學系", academy_code="CE"))
                session.add(ScholarshipType(id=1, code="phd_scholarship", name="博士生獎學金"))
                await session.commit()

        _run_async(_impl())

    def _seed_applications(self):
        """Seed one application per department under CE academy."""

        async def _impl():
            async with _AsyncSession() as session:
                session.add(
                    Application(
                        id=1001,
                        app_id="APP-114-1-00001",
                        user_id=101,
                        scholarship_type_id=1,
                        academic_year=114,
                        semester="first",
                        status="submitted",
                        sub_type_selection_mode=SubTypeSelectionMode.single,
                        student_data={"std_depno": "CE4460", "std_stdcode": "S001"},
                    )
                )
                session.add(
                    Application(
                        id=1002,
                        app_id="APP-114-1-00002",
                        user_id=102,
                        scholarship_type_id=1,
                        academic_year=114,
                        semester="first",
                        status="submitted",
                        sub_type_selection_mode=SubTypeSelectionMode.single,
                        student_data={"std_depno": "CE4461", "std_stdcode": "S002"},
                    )
                )
                await session.commit()

        _run_async(_impl())

    # ------------------------------------------------------------------
    # 1. Admin scope=all returns a ZIP with one XLSX per department
    # ------------------------------------------------------------------

    def test_bulk_admin_scope_all_returns_zip(self):
        """Admin user, scope=all: returns 200 ZIP containing 2 xlsx files (one per dept)."""
        self._seed_base()
        self._seed_applications()

        admin = _make_admin_user()
        client = self._client_with_user(admin)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export-bulk",
            params={
                "scholarship_type_id": 1,
                "academic_year": 114,
                "semester": "first",
                "scope": "all",
            },
        )

        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/zip")
        content_disposition = response.headers["content-disposition"]
        assert "filename*=UTF-8''" in content_disposition
        # "全部" URL-encoded is %E5%85%A8%E9%83%A8
        assert "%E5%85%A8%E9%83%A8" in content_disposition or "全部" in content_disposition

        # ZIP magic bytes
        assert response.content[:2] == b"PK"

        # ZIP should contain 2 xlsx files
        import io as _io
        import zipfile as _zf

        with _zf.ZipFile(_io.BytesIO(response.content)) as z:
            names = z.namelist()

        assert len(names) == 2
        assert all(n.endswith(".xlsx") for n in names)

    # ------------------------------------------------------------------
    # 2. College user scope=college returns ZIP filtered to their academy
    # ------------------------------------------------------------------

    def test_bulk_college_user_scope_college(self):
        """College user (CE), scope=college: ZIP contains entries for CE academy depts."""
        self._seed_base()
        self._seed_applications()
        _seed_college_permissions(user_id=9002, scholarship_type_id=1, academic_year=114)

        college_user = _make_college_user(college_code="CE")
        client = self._client_with_user(college_user)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export-bulk",
            params={
                "scholarship_type_id": 1,
                "academic_year": 114,
                "semester": "first",
                "scope": "college",
            },
        )

        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/zip")

        import io as _io
        import zipfile as _zf

        with _zf.ZipFile(_io.BytesIO(response.content)) as z:
            names = z.namelist()

        # Both departments belong to CE academy, so both files should appear
        assert len(names) == 2
        assert all(n.endswith(".xlsx") for n in names)

    # ------------------------------------------------------------------
    # 3. College user requesting scope=all gets 403
    # ------------------------------------------------------------------

    def test_bulk_college_user_scope_all_forbidden(self):
        """College user with no scholarship permission, scope=all → 403.

        With the new _check_scholarship_permission gate added in PR #203, the
        permission check fires before the scope guard for college users that have
        no AdminScholarship row.  Seed permissions and test the scope guard
        separately from the scholarship-permission guard.
        """
        self._seed_base()
        _seed_college_permissions(user_id=9002, scholarship_type_id=1, academic_year=114)

        college_user = _make_college_user(college_code="CE")
        client = self._client_with_user(college_user)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export-bulk",
            params={
                "scholarship_type_id": 1,
                "academic_year": 114,
                "scope": "all",
            },
        )

        assert response.status_code == 403
        body = response.json()
        msg = body.get("message", body.get("detail", ""))
        # After the permission gates pass, the scope=all guard fires with
        # this message for non-admin users.
        assert "學院使用者" in msg

    # ------------------------------------------------------------------
    # 4. No matching applications → 404
    # ------------------------------------------------------------------

    def test_bulk_no_matches_returns_404(self):
        """Admin, academic_year=9999 (no apps): 404 with 找不到 in message."""
        self._seed_base()
        # No applications seeded for year 9999

        admin = _make_admin_user()
        client = self._client_with_user(admin)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export-bulk",
            params={
                "scholarship_type_id": 1,
                "academic_year": 9999,
                "scope": "all",
            },
        )

        assert response.status_code == 404
        body = response.json()
        msg = body.get("message", body.get("detail", ""))
        assert "找不到" in msg

    # ------------------------------------------------------------------
    # 5. Admin without college_code requesting scope=college → 400
    # ------------------------------------------------------------------

    def test_bulk_admin_no_college_code_scope_college_400(self):
        """Admin without college_code, scope=college → 400."""
        self._seed_base()

        # Admin user has no college_code set
        admin = _make_admin_user()
        client = self._client_with_user(admin)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export-bulk",
            params={
                "scholarship_type_id": 1,
                "academic_year": 114,
                "scope": "college",
            },
        )

        assert response.status_code == 400
        body = response.json()
        msg = body.get("message", body.get("detail", ""))
        assert "未設定學院" in msg

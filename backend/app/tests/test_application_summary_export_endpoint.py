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

    # ------------------------------------------------------------------
    # Bundled code group: same-name departments exported together
    # ------------------------------------------------------------------

    def _seed_extra_department(self, code: str, academy_code: str, name: str = "資訊工程學系"):
        """Add one more Department row (the scholarship type is seeded separately)."""

        async def _impl():
            async with _AsyncSession() as session:
                session.add(Department(code=code, name=name, academy_code=academy_code))
                await session.commit()

        _run_async(_impl())

    def _seed_application(self, app_pk: int, depno: str, stdcode: str):
        async def _impl():
            async with _AsyncSession() as session:
                session.add(
                    Application(
                        id=app_pk,
                        app_id=f"APP-114-1-{app_pk:05d}",
                        user_id=app_pk,
                        scholarship_type_id=1,
                        academic_year=114,
                        semester="first",
                        status="submitted",
                        sub_type_selection_mode=SubTypeSelectionMode.single,
                        student_data={"std_depno": depno, "std_stdcode": stdcode},
                    )
                )
                await session.commit()

        _run_async(_impl())

    def test_college_user_foreign_code_in_group_rejected(self):
        """SECURITY: a college user who slips a foreign-academy code into the group
        is fully rejected (403) — no partial export of the codes they DO own."""
        self._seed_department_and_scholarship(dept_code="CE4460", academy_code="CE")
        self._seed_extra_department(code="EE5500", academy_code="EE")  # foreign academy
        _seed_college_permissions(user_id=9002, scholarship_type_id=1, academic_year=114)

        college_user = _make_college_user(college_code="CE")
        client = self._client_with_user(college_user)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export",
            params={
                "scholarship_type_id": 1,
                "academic_year": 114,
                "department_code": "CE4460,EE5500",  # own + foreign
            },
        )

        assert response.status_code == 403, response.text
        assert "無權限" in response.json().get("message", "")

    def test_admin_group_unions_applicants_into_one_workbook(self):
        """A comma-separated group exports applicants across ALL its codes in one xlsx."""
        self._seed_department_and_scholarship(dept_code="CE4460", academy_code="CE")
        self._seed_extra_department(code="CE4461", academy_code="CE")
        self._seed_application(app_pk=2001, depno="CE4460", stdcode="S001")
        self._seed_application(app_pk=2002, depno="CE4461", stdcode="S002")

        admin = _make_admin_user()
        client = self._client_with_user(admin)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export",
            params={
                "scholarship_type_id": 1,
                "academic_year": 114,
                "semester": "first",
                "department_code": "CE4460,CE4461",
            },
        )

        assert response.status_code == 200, response.text
        import io
        import zipfile

        z = zipfile.ZipFile(io.BytesIO(response.content))
        blob = b"".join(z.read(n) for n in z.namelist() if n.endswith(".xml"))
        # Both departments' applicants appear in the single bundled workbook.
        assert b"S001" in blob and b"S002" in blob

    def test_group_with_missing_code_returns_404(self):
        """If any code in the group does not exist, 404 names the missing code."""
        self._seed_department_and_scholarship(dept_code="CE4460", academy_code="CE")

        admin = _make_admin_user()
        client = self._client_with_user(admin)

        response = client.get(
            "/api/v1/college-review/applications/department-summary-export",
            params={
                "scholarship_type_id": 1,
                "academic_year": 114,
                "department_code": "CE4460,NOSUCHDEPT",
            },
        )

        assert response.status_code == 404
        assert "NOSUCHDEPT" in response.json().get("message", "")


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

    # ------------------------------------------------------------------
    # 6. 系所/年級 cells and grouping follow the API 1 department code
    # ------------------------------------------------------------------

    def _seed_app(self, app_pk: int, student_data: dict):
        async def _impl():
            async with _AsyncSession() as session:
                session.add(
                    Application(
                        id=app_pk,
                        app_id=f"APP-114-1-{app_pk:05d}",
                        user_id=app_pk,
                        scholarship_type_id=1,
                        academic_year=114,
                        semester="first",
                        status="submitted",
                        sub_type_selection_mode=SubTypeSelectionMode.single,
                        student_data=student_data,
                    )
                )
                await session.commit()

        _run_async(_impl())

    def test_bulk_rows_named_and_grouped_by_the_api1_department(self):
        """A transferred student (term row still on CE4460) lands in the CE4461
        workbook with 環境工程學系 in its 系所 cell; a student whose term lookup
        failed (std_* only) still gets 系所 and 年級."""
        import io as _io
        import zipfile as _zf

        from openpyxl import load_workbook

        from app.services.college_ranking_export_service import STATIC_HEADERS

        self._seed_base()
        self._seed_app(
            3001,
            {
                "std_depno": "CE4461",
                "std_stdcode": "S101",
                "trm_depno": "CE4460",
                "trm_depname": "土木工程學系",
                "trm_termcount": 4,
            },
        )
        self._seed_app(3002, {"std_depno": "CE4461", "std_stdcode": "S102", "std_termcount": 5})

        client = self._client_with_user(_make_admin_user())
        response = client.get(
            "/api/v1/college-review/applications/department-summary-export-bulk",
            params={"scholarship_type_id": 1, "academic_year": 114, "semester": "first", "scope": "all"},
        )
        assert response.status_code == 200, response.text

        with _zf.ZipFile(_io.BytesIO(response.content)) as z:
            names = z.namelist()
            assert len(names) == 1 and names[0].endswith("_環境工程學系_CE4461.xlsx")
            ws = load_workbook(_io.BytesIO(z.read(names[0]))).active

        code_col = STATIC_HEADERS.index("學號") + 1
        dept_col = STATIC_HEADERS.index("系所") + 1
        grade_col = STATIC_HEADERS.index("年級") + 1
        rows = {
            ws.cell(row=r, column=code_col).value: (
                ws.cell(row=r, column=dept_col).value,
                ws.cell(row=r, column=grade_col).value,
            )
            for r in range(3, ws.max_row + 1)
        }
        assert rows == {"S101": ("環境工程學系", 2), "S102": ("環境工程學系", 3)}


# ---------------------------------------------------------------------------
# 學生匯款帳號 column: the application's effective 郵局帳號
# ---------------------------------------------------------------------------

from app.models.user_profile import UserProfile  # noqa: E402

_PROFILE_ACCOUNT = "99999999999999"


def _account_form(**values):
    return {"fields": {key: {"field_id": key, "value": value} for key, value in values.items()}}


class TestSummaryExportAccountColumn:
    def setup_method(self):
        _create_tables()

    def teardown_method(self):
        _drop_tables()
        app.dependency_overrides.clear()

    def _seed(self, applications, profiles, extra_rows=()):
        async def _impl():
            async with _AsyncSession() as session:
                session.add(Department(code="CE4460", name="土木工程學系", academy_code="CE"))
                session.add(ScholarshipType(id=1, code="phd_scholarship", name="博士生獎學金"))
                for user_id, account in profiles.items():
                    session.add(UserProfile(user_id=user_id, account_number=account))
                session.add_all(extra_rows)
                for app_pk, user_id, stdcode, form in applications:
                    session.add(
                        Application(
                            id=app_pk,
                            app_id=f"APP-114-1-{app_pk:05d}",
                            user_id=user_id,
                            scholarship_type_id=1,
                            academic_year=114,
                            semester="first",
                            status="submitted",
                            sub_type_selection_mode=SubTypeSelectionMode.single,
                            student_data={"std_depno": "CE4460", "std_stdcode": stdcode},
                            submitted_form_data=form,
                        )
                    )
                await session.commit()

        _run_async(_impl())

    def _exported_accounts(self):
        return self._exported_column("學生匯款帳號")

    def _exported_column(self, header):
        import io as _io

        from openpyxl import load_workbook

        async def _fake_db():
            async with _AsyncSession() as session:
                yield session

        app.dependency_overrides[get_db] = _fake_db
        app.dependency_overrides[require_scholarship_manager] = _make_admin_user
        response = TestClient(app, raise_server_exceptions=True).get(
            "/api/v1/college-review/applications/department-summary-export",
            params={"scholarship_type_id": 1, "academic_year": 114, "semester": "first", "department_code": "CE4460"},
        )
        assert response.status_code == 200, response.text
        ws = load_workbook(_io.BytesIO(response.content)).active
        headers = [cell.value for cell in ws[2]]
        code_col = headers.index("學號") + 1
        value_col = headers.index(header) + 1
        return sorted(
            (ws.cell(row=r, column=code_col).value, ws.cell(row=r, column=value_col).value)
            for r in range(3, ws.max_row + 1)
        )

    def test_each_application_of_one_student_gets_its_own_account_and_advisor(self):
        # One student may hold a renewal and a new application in the same
        # term (separate partial unique indexes). SQLite ignores the partial
        # predicates, so the loader is driven directly with two in-memory rows.
        from types import SimpleNamespace

        from app.api.v1.endpoints.college_review._helpers import load_export_aux_data

        self._seed([], profiles={401: _PROFILE_ACCOUNT})
        renewal = SimpleNamespace(
            id=4001, user_id=401, submitted_form_data=_account_form(account_number="1" * 14, advisor_name="甲教授")
        )
        new = SimpleNamespace(
            id=4002, user_id=401, submitted_form_data=_account_form(account_number="2" * 14, advisor_name="乙教授")
        )

        async def _load():
            async with _AsyncSession() as session:
                return await load_export_aux_data(session, scholarship_type=None, applications=[renewal, new])

        _, _, profile_fields_by_application, advisor_by_application = _run_async(_load())
        assert {app_id: fields.postal_account for app_id, fields in profile_fields_by_application.items()} == {
            4001: "1" * 14,
            4002: "2" * 14,
        }
        assert advisor_by_application == {4001: "甲教授", 4002: "乙教授"}

    def test_staff_edited_account_beats_the_profile(self):
        self._seed(
            [(4003, 403, "S403", _account_form(account_number="33333333333333", postal_account="44444444444444"))],
            profiles={403: _PROFILE_ACCOUNT},
        )
        assert self._exported_accounts() == [("S403", "33333333333333")]

    def test_imported_application_without_profile_exports_its_postal_account(self):
        self._seed([(4004, 404, "S404", _account_form(postal_account="55555555555555"))], profiles={})
        assert self._exported_accounts() == [("S404", "55555555555555")]

    def test_profile_account_fills_in_when_the_application_has_none(self):
        self._seed([(4005, 405, "S405", _account_form(contact_phone="0912345678"))], profiles={405: _PROFILE_ACCOUNT})
        assert self._exported_accounts() == [("S405", _PROFILE_ACCOUNT)]

    def test_advisor_column_falls_back_to_the_submitted_advisor(self):
        self._seed([(4006, 406, "S406", _account_form(advisor_name="李教授"))], profiles={})
        assert self._exported_column("指導教授姓名") == [("S406", "李教授")]

    def test_advisor_column_prefers_the_curated_relationship(self):
        from app.models.professor_student import ProfessorStudentRelationship

        professor = User(
            id=9100,
            nycu_id="prof_chen",
            name="陳教授",
            email="chen@test.nycu.edu.tw",
            user_type=UserType.employee,
            status=EmployeeStatus.active,
            role=UserRole.professor,
        )
        relationship = ProfessorStudentRelationship(
            professor_id=9100, student_id=407, relationship_type="advisor", is_active=True
        )
        self._seed(
            [(4007, 407, "S407", _account_form(advisor_name="李教授"))],
            profiles={},
            extra_rows=[professor, relationship, UserProfile(user_id=407, advisor_name="王教授")],
        )
        assert self._exported_column("指導教授姓名") == [("S407", "陳教授")]

    def test_flagged_profile_owned_columns_show_the_effective_values(self):
        from app.models.application_field import ApplicationField

        def _flagged(field_name, label):
            return ApplicationField(
                scholarship_type="phd_scholarship",
                field_name=field_name,
                fixed_key=field_name,
                field_label=label,
                field_type="text",
                is_active=True,
                include_in_college_export=True,
                export_column_label=f"匯出{label}",
            )

        self._seed(
            [
                (
                    4008,
                    408,
                    "S408",
                    _account_form(
                        account_number="11111111111111", postal_account="33333333333333", advisor_name="舊教授"
                    ),
                )
            ],
            profiles={},
            extra_rows=[
                _flagged("postal_account", "郵局帳號"),
                _flagged("advisor_name", "指導教授"),
                UserProfile(user_id=408, account_number=_PROFILE_ACCOUNT, advisor_name="王教授"),
            ],
        )
        assert self._exported_column("匯出郵局帳號") == [("S408", "11111111111111")]
        assert self._exported_column("匯出指導教授") == [("S408", "王教授")]

    def test_flagged_advisor_column_shows_a_profile_only_advisor(self):
        from app.models.application_field import ApplicationField

        self._seed(
            [(4009, 409, "S409", _account_form(contact_phone="0912345678"))],
            profiles={},
            extra_rows=[
                ApplicationField(
                    scholarship_type="phd_scholarship",
                    field_name="advisor_name",
                    field_label="指導教授",
                    field_type="text",
                    is_active=True,
                    include_in_college_export=True,
                ),
                UserProfile(user_id=409, advisor_name="王教授"),
            ],
        )
        assert self._exported_column("指導教授") == [("S409", "王教授")]

"""
Integration tests for Renewal Import API endpoints.

Covers the renewal-window gate (upload is rejected outside the renewal period)
and the upload happy path (only 是 + 通過 rows are imported).
"""

import io
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_user
from app.main import app
from app.models.application import Application, ApplicationStatus
from app.models.batch_import import BatchImport
from app.models.enums import BatchImportStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole

# Router is mounted under this prefix in app/api/v1/api.py
BASE = "/api/v1/college-review/renewal-import"


def _override_user(user: User):
    """Override the get_current_user dependency to return the given user.

    require_admin still executes (role gating preserved); only the
    underlying get_current_user dependency is replaced. The conftest `client`
    fixture clears all overrides at teardown.
    """
    app.dependency_overrides[get_current_user] = lambda: user


def _make_config(scholarship_type_id: int, *, renewal_open: bool) -> ScholarshipConfiguration:
    """Build a phd config for AY 114 / first semester with an open or closed renewal window."""
    now = datetime.now(timezone.utc)
    if renewal_open:
        start = now - timedelta(days=1)
        end = now + timedelta(days=7)
    else:
        start = now - timedelta(days=30)
        end = now - timedelta(days=1)
    return ScholarshipConfiguration(
        scholarship_type_id=scholarship_type_id,
        academic_year=114,
        semester="first",
        config_name="PhD 114-1",
        config_code="phd_114_1",
        amount=40000,
        renewal_application_start_date=start,
        renewal_application_end_date=end,
    )


def _renewal_sheet() -> bytes:
    """A 2-row renewal sheet: one 否 (skipped), one 是 + 通過 (imported)."""
    df = pd.DataFrame(
        [
            {
                "編號": 1,
                "學院": "電機學院",
                "系所": "電機工程學系",
                "學生姓名": "王小明",
                "學號": "111111111",
                "學生年級": "博一",
                "學生是否申請續領": "否",
                "續領審核結果": "領獎期滿，無續領",
                "獎學金類別": "",
                "郵局帳號": "",
                "指導教授本校人事編號": "",
            },
            {
                "編號": 2,
                "學院": "電機學院",
                "系所": "電機工程學系",
                "學生姓名": "陳小華",
                "學號": "222222222",
                "學生年級": "博二",
                "學生是否申請續領": "是",
                "續領審核結果": "通過",
                "獎學金類別": "國科會",
                "郵局帳號": "1234567890123",
                "指導教授本校人事編號": "P001234",
            },
        ]
    )
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    buffer.seek(0)
    return buffer.getvalue()


class TestRenewalImportEndpoints:
    """Test cases for renewal import API endpoints."""

    @pytest.fixture
    async def admin_user(self, db: AsyncSession) -> User:
        user = User(
            nycu_id="admin_renewal",
            name="Admin Renewal User",
            email="admin.renewal@test.com",
            role=UserRole.admin,
            user_type="employee",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @pytest.fixture
    async def phd_scholarship(self, db: AsyncSession) -> ScholarshipType:
        scholarship = ScholarshipType(
            code="phd",
            name="PhD Scholarship",
            sub_type_list=["nstc", "moe_1w"],
            sub_type_selection_mode="single",
        )
        db.add(scholarship)
        await db.commit()
        await db.refresh(scholarship)
        return scholarship

    @pytest.mark.asyncio
    async def test_upload_rejects_outside_renewal_period(
        self, client: AsyncClient, db: AsyncSession, admin_user: User, phd_scholarship: ScholarshipType
    ):
        """Uploading against a config whose renewal window is CLOSED -> 400."""
        db.add(_make_config(phd_scholarship.id, renewal_open=False))
        await db.commit()

        _override_user(admin_user)
        response = await client.post(
            f"{BASE}/upload",
            params={"scholarship_type": "phd", "academic_year": 114, "semester": "first"},
            files={
                "file": (
                    "r.xlsx",
                    b"placeholder-bytes",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # The app wraps HTTPException.detail into the standard ApiResponse "message" field.
        assert "續領期間" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_upload_missing_config_returns_404(
        self, client: AsyncClient, db: AsyncSession, admin_user: User, phd_scholarship: ScholarshipType
    ):
        """No config for the (year, semester) -> 404 before any file read."""
        _override_user(admin_user)
        response = await client.post(
            f"{BASE}/upload",
            params={"scholarship_type": "phd", "academic_year": 114, "semester": "first"},
            files={
                "file": (
                    "r.xlsx",
                    b"placeholder-bytes",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_upload_happy_path_filters_non_passing_rows(
        self, client: AsyncClient, db: AsyncSession, admin_user: User, phd_scholarship: ScholarshipType, monkeypatch
    ):
        """Open renewal window + a 2-row sheet -> 200, 1 imported, 1 skipped."""
        db.add(_make_config(phd_scholarship.id, renewal_open=True))
        await db.commit()

        # Disable the external SIS lookup so validate_and_preview is deterministic.
        monkeypatch.setattr(settings, "student_api_enabled", False, raising=False)

        _override_user(admin_user)
        response = await client.post(
            f"{BASE}/upload",
            params={"scholarship_type": "phd", "academic_year": 114, "semester": "first"},
            files={
                "file": (
                    "renewals.xlsx",
                    _renewal_sheet(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["total_records"] == 1
        assert data["skipped_records"] == 1
        assert len(data["preview_data"]) == 1
        assert data["preview_data"][0]["student_id"] == "222222222"
        assert data["preview_data"][0]["sub_type"] == "nstc"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "role,user_type",
        [(UserRole.student, "student"), (UserRole.college, "employee")],
    )
    async def test_upload_requires_admin_role(
        self, client: AsyncClient, phd_scholarship: ScholarshipType, role: UserRole, user_type: str
    ):
        """Upload endpoint is admin / super_admin only — students AND college users get 403."""
        non_admin_user = User(
            id=999,
            nycu_id="non_admin_renewal",
            name="Non Admin User",
            email="non.admin.renewal@test.com",
            role=role,
            college_code="E" if role == UserRole.college else None,
            user_type=user_type,
        )
        _override_user(non_admin_user)
        response = await client.post(
            f"{BASE}/upload",
            params={"scholarship_type": "phd", "academic_year": 114, "semester": "first"},
            files={
                "file": (
                    "r.xlsx",
                    b"placeholder-bytes",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_download_template(self, client: AsyncClient, admin_user: User, phd_scholarship: ScholarshipType):
        """Template download returns an .xlsx attachment."""
        _override_user(admin_user)
        response = await client.get(f"{BASE}/template", params={"scholarship_type": "phd"})

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        content_disposition = response.headers.get("content-disposition", "")
        assert "attachment" in content_disposition
        assert ".xlsx" in content_disposition

    @pytest.mark.asyncio
    async def test_confirm_rejects_non_renewal_batch(self, client: AsyncClient, db: AsyncSession, admin_user: User):
        """The renewal confirm endpoint must reject a non-renewal batch (import_type='application') -> 404."""
        batch = BatchImport(
            importer_id=admin_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=114,
            semester="first",
            file_name="app.xlsx",
            total_records=1,
            import_status=BatchImportStatus.pending.value,
            import_type="application",
            parsed_data={"data": [{"student_id": "111111111"}], "errors": []},
        )
        db.add(batch)
        await db.commit()
        await db.refresh(batch)

        _override_user(admin_user)
        response = await client.post(
            f"{BASE}/{batch.id}/confirm",
            json={"batch_id": batch.id, "confirm": True},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_confirm_rejects_non_owner(self, client: AsyncClient, db: AsyncSession, admin_user: User):
        """A different non-super-admin admin cannot confirm someone else's renewal batch -> 403."""
        batch = BatchImport(
            importer_id=admin_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=114,
            semester="first",
            file_name="renewal.xlsx",
            total_records=1,
            import_status=BatchImportStatus.pending.value,
            import_type="renewal",
            parsed_data={"data": [{"student_id": "111111111"}], "errors": []},
        )
        db.add(batch)
        await db.commit()
        await db.refresh(batch)

        # A DIFFERENT admin user (not the importer, not super_admin) — passes
        # require_admin, so the 403 comes from the ownership check.
        other_user = User(
            id=999,
            nycu_id="other_admin",
            name="Other Admin User",
            email="other.admin@test.com",
            role=UserRole.admin,
            user_type="employee",
        )
        _override_user(other_user)
        response = await client.post(
            f"{BASE}/{batch.id}/confirm",
            json={"batch_id": batch.id, "confirm": True},
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_confirm_happy_path_creates_approved_renewals(
        self, client: AsyncClient, db: AsyncSession, admin_user: User, phd_scholarship: ScholarshipType, monkeypatch
    ):
        """Confirming a pending renewal batch creates an approved is_renewal Application."""
        # Config for the (year, semester) is required by create_renewals_from_batch.
        db.add(_make_config(phd_scholarship.id, renewal_open=True))
        # Pre-create the student User so _get_or_create_users_bulk needs no SIS lookup.
        db.add(
            User(
                nycu_id="413271002",
                name="曾美麗",
                email="mei@test.com",
                role=UserRole.student,
                user_type="student",
            )
        )
        batch = BatchImport(
            importer_id=admin_user.id,
            college_code="E",
            scholarship_type_id=phd_scholarship.id,
            academic_year=114,
            semester="first",
            file_name="renewal.xlsx",
            total_records=1,
            import_status=BatchImportStatus.pending.value,
            import_type="renewal",
            parsed_data={
                "data": [
                    {
                        "student_id": "413271002",
                        "student_name": "曾美麗",
                        "sub_type": "nstc",
                        "postal_account": "1234567890123",
                        "advisor_nycu_id": "P001",
                        "advisor_name": "張教授",
                        "row_number": 2,
                    }
                ],
                "errors": [],
                "skipped": [],
                "warnings": [],
            },
        )
        db.add(batch)
        await db.commit()
        await db.refresh(batch)

        # A renewal row without a SIS snapshot now fails the whole batch (spec §6:
        # it could not be rostered). Return a valid snapshot so confirm succeeds and
        # the created Application has student_data populated.
        async def _fake_snapshot(*args, **kwargs):
            return {"std_stdcode": "413271002", "std_cname": "曾美麗", "std_pid": "A123456789"}

        monkeypatch.setattr(
            "app.services.student_service.StudentService.get_student_snapshot",
            _fake_snapshot,
        )
        # Keep the user-bulk path off the network; the student User is pre-created.
        monkeypatch.setattr(settings, "student_api_enabled", False, raising=False)

        _override_user(admin_user)
        response = await client.post(
            f"{BASE}/{batch.id}/confirm",
            json={"batch_id": batch.id, "confirm": True},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["success_count"] >= 1
        assert data["failed_count"] == 0

        created = (await db.execute(select(Application).where(Application.batch_import_id == batch.id))).scalars().all()
        assert len(created) >= 1
        app_row = created[0]
        assert app_row.is_renewal is True
        # Enum column: a fresh DB read yields the member; the in-session object holds the value.
        assert app_row.status in (ApplicationStatus.approved, ApplicationStatus.approved.value)
        assert app_row.import_source == "renewal_import"
        assert app_row.student_data is not None
        assert app_row.student_data.get("std_stdcode") == "413271002"

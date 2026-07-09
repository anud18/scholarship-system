"""
Integration tests for Batch Import API endpoints

Tests upload, confirm, history, details, and template download endpoints.
"""

import io
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd
import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.main import app
from app.models.application import Application, ApplicationStatus
from app.models.batch_import import BatchImport
from app.models.enums import BatchImportStatus, ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole

# Router is mounted under this prefix in app/api/v1/api.py
BASE = "/api/v1/college-review/batch-import"


def _override_user(user: User):
    """Override the get_current_user dependency to return the given user.

    require_college_role still executes (so role gating is preserved); only the
    underlying get_current_user dependency is replaced. The conftest `client`
    fixture clears all overrides at teardown.
    """
    app.dependency_overrides[get_current_user] = lambda: user


class TestBatchImportEndpoints:
    """Test cases for batch import API endpoints"""

    @pytest.fixture
    async def college_user(self, db: AsyncSession):
        """Create a college role user for testing"""
        user = User(
            nycu_id="college_test",
            name="College Test User",
            email="college@test.com",
            role=UserRole.college,
            college_code="E",
            user_type="employee",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @pytest.fixture
    async def super_admin_user(self, db: AsyncSession):
        """Create a super admin user for testing"""
        user = User(
            nycu_id="super_admin_test",
            name="Super Admin",
            email="admin@test.com",
            role=UserRole.super_admin,
            user_type="employee",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @pytest.fixture
    async def test_scholarship(self, db: AsyncSession):
        """Create a test scholarship type.

        academic_year/semester/amount/main_type live on ScholarshipConfiguration,
        not ScholarshipType, so only the columns that exist on ScholarshipType are
        set here.
        """
        scholarship = ScholarshipType(
            code="test_scholarship",
            name="Test Scholarship",
            sub_type_list=["type_a", "type_b"],
            sub_type_selection_mode="single",
        )
        db.add(scholarship)
        await db.commit()
        await db.refresh(scholarship)
        return scholarship

    @pytest.fixture
    def valid_excel_file(self):
        """Create a valid Excel file for testing"""
        # test_scholarship defines real sub-types (type_a, type_b), so each
        # row MUST mark a sub-type or parse rejects it with missing_sub_type.
        df = pd.DataFrame(
            {
                "student_id": ["111111111", "222222222"],
                "student_name": ["王小明", "陳小華"],
                "dept_code": ["5201", "5202"],
                "bank_account": ["1234567890", "9876543210"],
                "sub_type_type_a": ["V", "V"],
            }
        )

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        buffer.seek(0)
        return buffer.getvalue()

    @pytest.mark.asyncio
    async def test_upload_batch_import_success(
        self, client: AsyncClient, college_user: User, test_scholarship: ScholarshipType, valid_excel_file
    ):
        """Test successful batch import upload"""
        _override_user(college_user)
        response = await client.post(
            f"{BASE}/upload-data",
            params={
                "scholarship_type": test_scholarship.code,
                "academic_year": 113,
                "semester": "first",
            },
            files={
                "file": (
                    "test.xlsx",
                    valid_excel_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        data = body["data"]
        assert "batch_id" in data
        assert data["total_records"] == 2
        assert len(data["preview_data"]) == 2

    @pytest.mark.asyncio
    async def test_upload_batch_import_surfaces_eligibility_warnings(
        self, client: AsyncClient, college_user: User, test_scholarship: ScholarshipType, valid_excel_file
    ):
        """Eligibility/professor warnings from bulk_check_eligibility must
        surface in the upload response's validation_summary.warnings."""
        _override_user(college_user)

        fake_warning = {
            "row_number": 2,
            "student_id": "111111111",
            "field": "eligibility",
            "warning_type": "eligibility_failed",
            "message": "學生 111111111 資格預檢未通過：GPA 未達標準（不影響匯入，請人工審查把關）。",
        }

        with patch(
            "app.services.batch_import_service.BatchImportService.bulk_check_eligibility",
            new_callable=AsyncMock,
            return_value=[fake_warning],
        ):
            response = await client.post(
                f"{BASE}/upload-data",
                params={
                    "scholarship_type": test_scholarship.code,
                    "academic_year": 113,
                    "semester": "first",
                },
                files={
                    "file": (
                        "test.xlsx",
                        valid_excel_file,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )

        assert response.status_code == status.HTTP_200_OK
        warnings = response.json()["data"]["validation_summary"]["warnings"]
        assert any("GPA 未達標準" in (w.get("message") or "") for w in warnings)

    @pytest.mark.asyncio
    async def test_upload_batch_import_file_too_large(
        self, client: AsyncClient, college_user: User, test_scholarship: ScholarshipType
    ):
        """Test file size validation"""
        # Create a file larger than 10MB
        large_file = b"x" * (11 * 1024 * 1024)  # 11MB

        _override_user(college_user)
        response = await client.post(
            f"{BASE}/upload-data",
            params={
                "scholarship_type": test_scholarship.code,
                "academic_year": 113,
                "semester": "first",
            },
            files={
                "file": (
                    "large.xlsx",
                    large_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        assert response.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        assert "超過限制" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_upload_batch_import_invalid_file_type(
        self, client: AsyncClient, college_user: User, test_scholarship: ScholarshipType
    ):
        """Test file type validation"""
        # PNG magic header -> libmagic reports image/png, which is not an allowed
        # Excel/CSV MIME type.
        invalid_file = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

        _override_user(college_user)
        response = await client.post(
            f"{BASE}/upload-data",
            params={
                "scholarship_type": test_scholarship.code,
                "academic_year": 113,
                "semester": "first",
            },
            files={"file": ("test.png", invalid_file, "image/png")},
        )

        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        assert "不支援的檔案格式" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_upload_batch_import_no_college_code(
        self, client: AsyncClient, test_scholarship: ScholarshipType, valid_excel_file
    ):
        """Test upload fails when user has no college code"""
        user_without_college = User(
            id=999,
            nycu_id="no_college",
            name="No College User",
            email="nocollege@test.com",
            role=UserRole.college,
            college_code=None,
        )

        _override_user(user_without_college)
        response = await client.post(
            f"{BASE}/upload-data",
            params={
                "scholarship_type": test_scholarship.code,
                "academic_year": 113,
                "semester": "first",
            },
            files={
                "file": (
                    "test.xlsx",
                    valid_excel_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "未設定學院代碼" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_confirm_batch_import_success(self, client: AsyncClient, db: AsyncSession, college_user: User):
        """Test successful batch import confirmation"""
        # Create a batch import record
        batch_import = BatchImport(
            importer_id=college_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            file_name="test.xlsx",
            total_records=2,
            import_status=BatchImportStatus.pending.value,
            parsed_data={
                "data": [
                    {"student_id": "111111111", "student_name": "Test Student 1"},
                    {"student_id": "222222222", "student_name": "Test Student 2"},
                ]
            },
        )
        db.add(batch_import)
        await db.commit()
        await db.refresh(batch_import)

        # Mock service so no real application creation runs
        _override_user(college_user)
        with patch("app.api.v1.endpoints.batch_import.BatchImportService") as mock_service_class:
            mock_service = Mock()
            mock_service.create_applications_from_batch = AsyncMock(return_value=([1, 2], []))
            mock_service.update_batch_import_status = AsyncMock()
            mock_service_class.return_value = mock_service

            response = await client.post(
                f"{BASE}/{batch_import.id}/confirm",
                json={"batch_id": batch_import.id, "confirm": True},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["success_count"] == 2
        assert data["failed_count"] == 0

    @pytest.mark.asyncio
    async def test_confirm_batch_import_keeps_review_flow_status(
        self, client: AsyncClient, db: AsyncSession, college_user: User
    ):
        """Regression (review-flow parity): the confirm endpoint must NOT
        mutate the status the service sets. A stale
        ``UPDATE applications SET status='under_review'`` used to run after
        creation and stomped the submitted / student_submitted values,
        defeating batch-import review-flow parity. This drives the REAL
        service (not a mock) through the endpoint and reads the created
        applications back from the DB.
        """
        scholarship = ScholarshipType(
            code="phd_confirm_status",
            name="PhD Confirm Status",
            sub_type_list=["nstc"],
            sub_type_selection_mode="single",
        )
        db.add(scholarship)
        await db.flush()
        db.add(
            ScholarshipConfiguration(
                scholarship_type_id=scholarship.id,
                academic_year=114,
                semester=None,
                config_name="PhD Confirm Status 114",
                config_code="phd_confirm_status_114",
                amount=40000,
            )
        )

        batch = BatchImport(
            importer_id=college_user.id,
            college_code="E",
            scholarship_type_id=scholarship.id,
            academic_year=114,
            file_name="confirm.xlsx",
            total_records=1,
            import_status=BatchImportStatus.pending.value,
            parsed_data={
                "data": [
                    {
                        "student_id": "313559001",
                        "student_name": "王小明",
                        "sub_types": ["nstc"],
                        "custom_fields": {},
                        "row_number": 2,
                    }
                ],
                "errors": [],
            },
        )
        db.add(batch)
        await db.commit()
        await db.refresh(batch)

        _override_user(college_user)
        # Neutralize SIS so no network call — the endpoint builds its own
        # BatchImportService(db) internally, so patch the StudentService it
        # constructs rather than injecting a stub.
        stub_sis = Mock()
        stub_sis.get_student_snapshot = AsyncMock(return_value=None)
        stub_sis.get_student_basic_info = AsyncMock(return_value=None)
        with patch("app.services.batch_import_service.StudentService", return_value=stub_sis):
            response = await client.post(
                f"{BASE}/{batch.id}/confirm",
                json={"batch_id": batch.id, "confirm": True},
            )

        assert response.status_code == status.HTTP_200_OK
        created_ids = response.json()["data"]["created_application_ids"]
        assert len(created_ids) == 1

        # Fresh DB re-read so enum columns come back as enum members.
        db.expunge_all()
        created = await db.get(Application, created_ids[0])
        assert created.status == ApplicationStatus.submitted
        assert created.review_stage == ReviewStage.student_submitted

    @pytest.mark.asyncio
    async def test_confirm_batch_import_cancel(self, client: AsyncClient, db: AsyncSession, college_user: User):
        """Test batch import cancellation"""
        batch_import = BatchImport(
            importer_id=college_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            file_name="test.xlsx",
            total_records=2,
            import_status=BatchImportStatus.pending.value,
            parsed_data={"data": []},
        )
        db.add(batch_import)
        await db.commit()
        await db.refresh(batch_import)

        _override_user(college_user)
        response = await client.post(
            f"{BASE}/{batch_import.id}/confirm",
            json={"batch_id": batch_import.id, "confirm": False},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["success_count"] == 0

        # Verify status updated
        await db.refresh(batch_import)
        assert batch_import.import_status == BatchImportStatus.cancelled

    @pytest.mark.asyncio
    async def test_confirm_batch_import_wrong_status(self, client: AsyncClient, db: AsyncSession, college_user: User):
        """Test confirming batch with wrong status"""
        batch_import = BatchImport(
            importer_id=college_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            file_name="test.xlsx",
            total_records=2,
            import_status=BatchImportStatus.completed.value,
            parsed_data={"data": []},
        )
        db.add(batch_import)
        await db.commit()
        await db.refresh(batch_import)

        _override_user(college_user)
        response = await client.post(
            f"{BASE}/{batch_import.id}/confirm",
            json={"batch_id": batch_import.id, "confirm": True},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "無法再次確認" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_get_batch_import_history_college(self, client: AsyncClient, db: AsyncSession, college_user: User):
        """Test getting batch import history as college user"""
        # Create batch imports (only confirmed statuses appear in history)
        batch1 = BatchImport(
            importer_id=college_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            file_name="test1.xlsx",
            total_records=10,
            import_status=BatchImportStatus.completed,
        )
        batch2 = BatchImport(
            importer_id=college_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            file_name="test2.xlsx",
            total_records=20,
            import_status=BatchImportStatus.partial,
        )
        db.add_all([batch1, batch2])
        await db.commit()

        _override_user(college_user)
        response = await client.get(f"{BASE}/history")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_batch_import_history_super_admin(
        self, client: AsyncClient, db: AsyncSession, college_user: User, super_admin_user: User
    ):
        """Test super admin can see all batch imports"""
        # Create batch from college user (confirmed status so it shows in history)
        batch = BatchImport(
            importer_id=college_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            file_name="test.xlsx",
            total_records=10,
            import_status=BatchImportStatus.completed,
        )
        db.add(batch)
        await db.commit()

        _override_user(super_admin_user)
        response = await client.get(f"{BASE}/history")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["total"] >= 1  # Should see college user's batch

    @pytest.mark.asyncio
    async def test_get_batch_import_details(self, client: AsyncClient, db: AsyncSession, college_user: User):
        """Test getting batch import details"""
        batch = BatchImport(
            importer_id=college_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            file_name="test.xlsx",
            total_records=10,
            success_count=8,
            failed_count=2,
            import_status=BatchImportStatus.partial.value,
            error_summary={"total_errors": 2},
        )
        db.add(batch)
        await db.commit()
        await db.refresh(batch)

        _override_user(college_user)
        response = await client.get(f"{BASE}/{batch.id}/details")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["id"] == batch.id
        assert data["total_records"] == 10
        assert data["success_count"] == 8
        assert data["failed_count"] == 2

    @pytest.mark.asyncio
    async def test_download_template(self, client: AsyncClient, college_user: User, test_scholarship: ScholarshipType):
        """Test template download"""
        _override_user(college_user)
        response = await client.get(
            f"{BASE}/template",
            params={"scholarship_type": test_scholarship.code},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        # Template is served as an .xlsx attachment named after the scholarship.
        content_disposition = response.headers.get("content-disposition", "")
        assert "attachment" in content_disposition
        assert ".xlsx" in content_disposition
        # Filename is derived from the scholarship name ("Test Scholarship" -> "Test%20Scholarship").
        assert "Test" in content_disposition

    @pytest.mark.asyncio
    async def test_upload_accepts_empty_semester_for_yearly(
        self, client: AsyncClient, college_user: User, test_scholarship: ScholarshipType, valid_excel_file
    ):
        """Yearly scholarships have no semester part in their period, so the
        UI sends semester="" — that must normalize to None (yearly), not die
        in the query-pattern check with a generic 422 "Validation failed"."""
        _override_user(college_user)
        response = await client.post(
            f"{BASE}/upload-data",
            params={"scholarship_type": test_scholarship.code, "academic_year": 114, "semester": ""},
            files={
                "file": (
                    "test.xlsx",
                    valid_excel_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_downloaded_template_round_trips_through_upload(
        self, client: AsyncClient, college_user: User, test_scholarship: ScholarshipType
    ):
        """下載的範本必須「原樣可匯入」：GET /template 的檔案直接餵回
        upload-data 不得產生任何驗證錯誤。

        Covers the custom sub-type gap: test_scholarship uses raw codes
        (type_a/type_b) with no Chinese label, so the template writes the
        code itself as the column header — the parser must accept it, or
        every sample row dies with missing_sub_type.
        """
        _override_user(college_user)

        template_resp = await client.get(f"{BASE}/template", params={"scholarship_type": test_scholarship.code})
        assert template_resp.status_code == status.HTTP_200_OK

        upload_resp = await client.post(
            f"{BASE}/upload-data",
            params={"scholarship_type": test_scholarship.code, "academic_year": 113, "semester": "first"},
            files={
                "file": (
                    "template.xlsx",
                    template_resp.content,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        assert upload_resp.status_code == status.HTTP_200_OK
        data = upload_resp.json()["data"]
        assert data["validation_summary"]["errors"] == []
        assert data["validation_summary"]["invalid_count"] == 0
        # Both sample rows survive as importable records with sub-types parsed.
        assert len(data["preview_data"]) == 2
        assert all(row["sub_types"] for row in data["preview_data"])

    @pytest.mark.asyncio
    async def test_upload_requires_college_role(
        self, client: AsyncClient, test_scholarship: ScholarshipType, valid_excel_file
    ):
        """Test upload endpoint requires college or super_admin role"""
        student_user = User(
            id=999,
            nycu_id="student_test",
            name="Student User",
            email="student@test.com",
            role=UserRole.student,
            user_type="student",
        )

        _override_user(student_user)
        response = await client.post(
            f"{BASE}/upload-data",
            params={
                "scholarship_type": test_scholarship.code,
                "academic_year": 113,
                "semester": "first",
            },
            files={
                "file": (
                    "test.xlsx",
                    valid_excel_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN

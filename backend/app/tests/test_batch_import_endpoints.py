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

from app.models.batch_import import BatchImport
from app.models.enums import BatchImportStatus
from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole


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
        """Create a test scholarship"""
        scholarship = ScholarshipType(
            code="test_scholarship",
            name="Test Scholarship",
            category="general",
            academic_year=113,
            semester="first",
            amount=10000,
            main_type="general",
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
        df = pd.DataFrame(
            {
                "student_id": ["111111111", "222222222"],
                "student_name": ["王小明", "陳小華"],
                "dept_code": ["5201", "5202"],
                "bank_account": ["1234567890", "9876543210"],
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
        # Mock auth to return college user
        with patch("app.core.security.get_current_user", return_value=college_user):
            response = await client.post(
                "/api/v1/college/batch-import/upload-data",
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
        data = response.json()
        assert "batch_id" in data
        assert data["total_records"] == 2
        assert len(data["preview_data"]) == 2

    @pytest.mark.asyncio
    async def test_upload_batch_import_file_too_large(
        self, client: AsyncClient, college_user: User, test_scholarship: ScholarshipType
    ):
        """Test file size validation"""
        # Create a file larger than 10MB
        large_file = b"x" * (11 * 1024 * 1024)  # 11MB

        with patch("app.core.security.get_current_user", return_value=college_user):
            response = await client.post(
                "/api/v1/college/batch-import/upload-data",
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
        assert "超過限制" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_upload_batch_import_invalid_file_type(
        self, client: AsyncClient, college_user: User, test_scholarship: ScholarshipType
    ):
        """Test file type validation"""
        invalid_file = b"This is not an Excel file"

        with patch("app.core.security.get_current_user", return_value=college_user):
            response = await client.post(
                "/api/v1/college/batch-import/upload-data",
                params={
                    "scholarship_type": test_scholarship.code,
                    "academic_year": 113,
                    "semester": "first",
                },
                files={"file": ("test.txt", invalid_file, "text/plain")},
            )

        assert response.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        assert "不支援的檔案格式" in response.json()["detail"]

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

        with patch("app.core.security.get_current_user", return_value=user_without_college):
            response = await client.post(
                "/api/v1/college/batch-import/upload-data",
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
        assert "未設定學院代碼" in response.json()["detail"]

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

        # Mock scholarship and service
        with (
            patch("app.core.security.get_current_user", return_value=college_user),
            patch("app.api.v1.endpoints.batch_import.BatchImportService") as mock_service_class,
        ):
            mock_service = Mock()
            mock_service.create_applications_from_batch = AsyncMock(return_value=([1, 2], []))
            mock_service.update_batch_import_status = AsyncMock()
            mock_service_class.return_value = mock_service

            response = await client.post(
                f"/api/v1/college/batch-import/{batch_import.id}/confirm",
                json={"batch_id": batch_import.id, "confirm": True},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success_count"] == 2
        assert data["failed_count"] == 0

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

        with patch("app.core.security.get_current_user", return_value=college_user):
            response = await client.post(
                f"/api/v1/college/batch-import/{batch_import.id}/confirm",
                json={"batch_id": batch_import.id, "confirm": False},
            )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success_count"] == 0

        # Verify status updated
        await db.refresh(batch_import)
        assert batch_import.import_status == BatchImportStatus.cancelled.value

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

        with patch("app.core.security.get_current_user", return_value=college_user):
            response = await client.post(
                f"/api/v1/college/batch-import/{batch_import.id}/confirm",
                json={"batch_id": batch_import.id, "confirm": True},
            )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "無法再次確認" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_batch_import_history_college(self, client: AsyncClient, db: AsyncSession, college_user: User):
        """Test getting batch import history as college user"""
        # Create batch imports
        batch1 = BatchImport(
            importer_id=college_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            file_name="test1.xlsx",
            total_records=10,
            import_status=BatchImportStatus.completed.value,
        )
        batch2 = BatchImport(
            importer_id=college_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            file_name="test2.xlsx",
            total_records=20,
            import_status=BatchImportStatus.pending.value,
        )
        db.add_all([batch1, batch2])
        await db.commit()

        with patch("app.core.security.get_current_user", return_value=college_user):
            response = await client.get("/api/v1/college/batch-import/history")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_batch_import_history_super_admin(
        self, client: AsyncClient, db: AsyncSession, college_user: User, super_admin_user: User
    ):
        """Test super admin can see all batch imports"""
        # Create batch from college user
        batch = BatchImport(
            importer_id=college_user.id,
            college_code="E",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            file_name="test.xlsx",
            total_records=10,
            import_status=BatchImportStatus.completed.value,
        )
        db.add(batch)
        await db.commit()

        with patch("app.core.security.get_current_user", return_value=super_admin_user):
            response = await client.get("/api/v1/college/batch-import/history")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
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

        with patch("app.core.security.get_current_user", return_value=college_user):
            response = await client.get(f"/api/v1/college/batch-import/{batch.id}/details")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == batch.id
        assert data["total_records"] == 10
        assert data["success_count"] == 8
        assert data["failed_count"] == 2

    @pytest.mark.asyncio
    async def test_download_template(self, client: AsyncClient, college_user: User, test_scholarship: ScholarshipType):
        """Test template download"""
        with patch("app.core.security.get_current_user", return_value=college_user):
            response = await client.get(
                "/api/v1/college/batch-import/template",
                params={"scholarship_type": test_scholarship.code},
            )

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert "batch_import_template" in response.headers.get("content-disposition", "")

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

        with patch("app.core.security.get_current_user", return_value=student_user):
            response = await client.post(
                "/api/v1/college/batch-import/upload-data",
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

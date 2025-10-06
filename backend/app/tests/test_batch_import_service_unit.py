"""
Unit tests for BatchImportService

Tests file parsing, validation, bulk operations, and transaction rollback.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BatchImportError
from app.models.batch_import import BatchImport
from app.models.enums import BatchImportStatus
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.schemas.batch_import import BatchImportValidationError
from app.services.batch_import_service import BatchImportService


class TestBatchImportService:
    """Test cases for BatchImportService"""

    @pytest.fixture
    def service(self, db: AsyncSession):
        """Create BatchImportService instance for testing"""
        return BatchImportService(db)

    @pytest.fixture
    def mock_scholarship(self):
        """Mock scholarship type"""
        scholarship = Mock(spec=ScholarshipType)
        scholarship.id = 1
        scholarship.name = "Test Scholarship"
        scholarship.amount = 10000
        scholarship.main_type = "general"
        scholarship.sub_type_selection_mode = "single"
        return scholarship

    @pytest.fixture
    def sample_excel_data(self):
        """Sample parsed Excel data"""
        return [
            {
                "student_id": "111111111",
                "student_name": "王小明",
                "dept_code": "5201",
                "bank_account": "1234567890",
                "account_holder": "王小明",
                "bank_name": "台灣銀行",
                "gpa": 3.8,
                "sub_types": ["type_a"],
            },
            {
                "student_id": "222222222",
                "student_name": "陳小華",
                "dept_code": "5202",
                "bank_account": "9876543210",
                "account_holder": "陳小華",
                "bank_name": "第一銀行",
                "gpa": 3.9,
                "sub_types": [],
            },
        ]

    @pytest.mark.asyncio
    async def test_parse_excel_file_success(self, service):
        """Test successful Excel file parsing"""
        # Create valid Excel content (minimal valid XLSX)
        import io

        import pandas as pd

        df = pd.DataFrame(
            {
                "student_id": ["111111111", "222222222"],
                "student_name": ["王小明", "陳小華"],
                "dept_code": ["5201", "5202"],
            }
        )

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        file_content = buffer.getvalue()

        # Parse file
        parsed_data, errors = await service.parse_excel_file(
            file_content=file_content, scholarship_type_id=1, academic_year=113, semester="first"
        )

        # Assertions
        assert len(parsed_data) == 2
        assert len(errors) == 0
        assert parsed_data[0]["student_id"] == "111111111"
        assert parsed_data[0]["student_name"] == "王小明"

    @pytest.mark.asyncio
    async def test_parse_excel_file_missing_columns(self, service):
        """Test Excel parsing with missing required columns"""
        import io

        import pandas as pd

        # Missing student_name column
        df = pd.DataFrame({"student_id": ["111111111"]})

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        file_content = buffer.getvalue()

        # Parse file
        parsed_data, errors = await service.parse_excel_file(
            file_content=file_content, scholarship_type_id=1, academic_year=113, semester="first"
        )

        # Assertions
        assert len(parsed_data) == 0
        assert len(errors) == 1
        assert errors[0].error_type == "missing_columns"
        assert "student_name" in errors[0].message

    @pytest.mark.asyncio
    async def test_get_or_create_users_bulk_existing(self, service, sample_excel_data):
        """Test bulk user fetching when users already exist"""
        # Mock existing users
        existing_user_1 = Mock(spec=User)
        existing_user_1.nycu_id = "111111111"
        existing_user_1.id = 1

        existing_user_2 = Mock(spec=User)
        existing_user_2.nycu_id = "222222222"
        existing_user_2.id = 2

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [existing_user_1, existing_user_2]

        with patch.object(service.db, "execute", return_value=mock_result):
            user_map = await service._get_or_create_users_bulk(sample_excel_data)

            assert len(user_map) == 2
            assert user_map["111111111"].id == 1
            assert user_map["222222222"].id == 2

    @pytest.mark.asyncio
    async def test_get_or_create_users_bulk_create_new(self, service, sample_excel_data):
        """Test bulk user creation when users don't exist"""
        # Mock no existing users
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []

        with patch.object(service.db, "execute", return_value=mock_result), patch.object(
            service.db, "add"
        ) as mock_add, patch.object(service.db, "flush", new_callable=AsyncMock) as mock_flush:
            user_map = await service._get_or_create_users_bulk(sample_excel_data)

            # Should create 2 new users
            assert mock_add.call_count == 2
            assert mock_flush.call_count == 1
            assert len(user_map) == 2

    @pytest.mark.asyncio
    async def test_create_applications_from_batch_success(self, service, mock_scholarship, sample_excel_data):
        """Test successful application creation from batch"""
        batch_import = Mock(spec=BatchImport)
        batch_import.id = 1
        batch_import.importer_id = 10

        # Mock user map
        user_1 = Mock(spec=User)
        user_1.id = 1
        user_1.nycu_id = "111111111"

        user_2 = Mock(spec=User)
        user_2.id = 2
        user_2.nycu_id = "222222222"

        user_map = {"111111111": user_1, "222222222": user_2}

        with patch.object(service.db, "get", return_value=mock_scholarship), patch.object(
            service, "_get_or_create_users_bulk", return_value=user_map
        ), patch.object(service.db, "add") as mock_add, patch.object(service.db, "flush", new_callable=AsyncMock):
            created_ids, errors = await service.create_applications_from_batch(
                batch_import=batch_import,
                parsed_data=sample_excel_data,
                scholarship_type_id=1,
                academic_year=113,
                semester="first",
            )

            # Should create 2 applications
            assert mock_add.call_count == 2
            assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_create_applications_from_batch_rollback_on_error(self, service, mock_scholarship, sample_excel_data):
        """Test transaction rollback on error"""
        batch_import = Mock(spec=BatchImport)
        batch_import.id = 1
        batch_import.importer_id = 10

        with patch.object(service.db, "get", return_value=mock_scholarship), patch.object(
            service, "_get_or_create_users_bulk", side_effect=Exception("Database error")
        ), patch.object(service.db, "rollback", new_callable=AsyncMock) as mock_rollback, patch.object(
            service.db, "commit", new_callable=AsyncMock
        ):
            with pytest.raises(BatchImportError) as exc_info:
                await service.create_applications_from_batch(
                    batch_import=batch_import,
                    parsed_data=sample_excel_data,
                    scholarship_type_id=1,
                    academic_year=113,
                    semester="first",
                )

            # Should rollback transaction
            assert mock_rollback.call_count == 1
            assert "Database error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_applications_from_batch_no_scholarship(self, service, sample_excel_data):
        """Test error when scholarship type doesn't exist"""
        batch_import = Mock(spec=BatchImport)
        batch_import.id = 1

        with patch.object(service.db, "get", return_value=None):
            with pytest.raises(BatchImportError) as exc_info:
                await service.create_applications_from_batch(
                    batch_import=batch_import,
                    parsed_data=sample_excel_data,
                    scholarship_type_id=999,
                    academic_year=113,
                    semester="first",
                )

            assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_validate_college_permission_success(self, service):
        """Test successful college permission validation"""
        from app.models.student import Department

        # Mock student
        student = Mock(spec=User)
        student.nycu_id = "111111111"
        student.dept_code = "5201"
        student.raw_data = {"deptCode": "5201"}

        # Mock department
        dept = Mock(spec=Department)
        dept.code = "5201"
        dept.academy_code = "E"  # Engineering college

        with patch.object(service.db, "execute") as mock_execute:
            # Setup mock returns
            student_result = Mock()
            student_result.scalar_one_or_none.return_value = student

            dept_result = Mock()
            dept_result.scalar_one_or_none.return_value = dept

            mock_execute.side_effect = [student_result, dept_result]

            is_valid, error_msg = await service.validate_college_permission(
                student_id="111111111", college_code="E", dept_code="5201"
            )

            assert is_valid is True
            assert error_msg is None

    @pytest.mark.asyncio
    async def test_validate_college_permission_mismatch(self, service):
        """Test college permission validation with mismatch"""
        from app.models.student import Department

        # Mock student
        student = Mock(spec=User)
        student.nycu_id = "111111111"
        student.dept_code = "5201"
        student.raw_data = {"deptCode": "5201"}

        # Mock department - different college
        dept = Mock(spec=Department)
        dept.code = "5201"
        dept.academy_code = "C"  # Computer Science college

        with patch.object(service.db, "execute") as mock_execute:
            student_result = Mock()
            student_result.scalar_one_or_none.return_value = student

            dept_result = Mock()
            dept_result.scalar_one_or_none.return_value = dept

            mock_execute.side_effect = [student_result, dept_result]

            is_valid, error_msg = await service.validate_college_permission(
                student_id="111111111", college_code="E", dept_code="5201"
            )

            assert is_valid is False
            assert "不符" in error_msg

    @pytest.mark.asyncio
    async def test_check_duplicate_application_exists(self, service):
        """Test duplicate application detection"""
        from app.models.application import Application

        # Mock existing application
        existing_app = Mock(spec=Application)
        existing_app.id = 100

        with patch.object(service.db, "execute") as mock_execute:
            # Mock user exists
            user_result = Mock()
            user_result.scalar_one_or_none.return_value = Mock(id=1)

            # Mock application exists
            app_result = Mock()
            app_result.scalar_one_or_none.return_value = existing_app

            mock_execute.side_effect = [user_result, app_result]

            is_duplicate, error_msg = await service.check_duplicate_application(
                student_id="111111111", scholarship_type_id=1, academic_year=113, semester="first"
            )

            assert is_duplicate is True
            assert "APP-100" in error_msg

    @pytest.mark.asyncio
    async def test_check_duplicate_application_not_exists(self, service):
        """Test no duplicate when application doesn't exist"""
        with patch.object(service.db, "execute") as mock_execute:
            # Mock user exists
            user_result = Mock()
            user_result.scalar_one_or_none.return_value = Mock(id=1)

            # Mock no application
            app_result = Mock()
            app_result.scalar_one_or_none.return_value = None

            mock_execute.side_effect = [user_result, app_result]

            is_duplicate, error_msg = await service.check_duplicate_application(
                student_id="111111111", scholarship_type_id=1, academic_year=113, semester="first"
            )

            assert is_duplicate is False
            assert error_msg is None

    @pytest.mark.asyncio
    async def test_create_batch_import_record(self, service):
        """Test batch import record creation"""
        with patch.object(service.db, "add") as mock_add, patch.object(
            service.db, "flush", new_callable=AsyncMock
        ) as mock_flush:
            batch_import = await service.create_batch_import_record(
                importer_id=10,
                college_code="E",
                scholarship_type_id=1,
                academic_year=113,
                semester="first",
                file_name="test.xlsx",
                total_records=50,
            )

            assert batch_import.importer_id == 10
            assert batch_import.college_code == "E"
            assert batch_import.total_records == 50
            assert batch_import.import_status == BatchImportStatus.pending.value
            assert mock_add.call_count == 1
            assert mock_flush.call_count == 1

    @pytest.mark.asyncio
    async def test_update_batch_import_status(self, service):
        """Test batch import status update"""
        batch_import = Mock(spec=BatchImport)
        errors = [
            BatchImportValidationError(
                row_number=2,
                student_id="111111111",
                field="bank_account",
                error_type="validation_error",
                message="Invalid format",
            )
        ]

        with patch.object(service.db, "commit", new_callable=AsyncMock):
            await service.update_batch_import_status(
                batch_import=batch_import,
                success_count=45,
                failed_count=5,
                errors=errors,
                status="partial",
            )

            assert batch_import.success_count == 45
            assert batch_import.failed_count == 5
            assert batch_import.import_status == "partial"
            assert batch_import.error_summary["total_errors"] == 1

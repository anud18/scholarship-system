"""
Unit tests for StudentService
"""

from datetime import date
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

# Student model removed - student data from external API
from app.core.exceptions import NotFoundError
from app.services.student_service import StudentService


class TestStudentService:
    """Test cases for StudentService"""

    @pytest.fixture
    def service(self, db: AsyncSession):
        """Create StudentService instance for testing"""
        return StudentService(db)

    @pytest.fixture
    def mock_student(self):
        """Mock student object for testing"""
        student = Mock(spec=Student)
        student.id = 1
        student.std_stdno = "112550001"
        student.std_stdcode = "112550001"
        student.std_pid = "A123456789"
        student.std_cname = "王小明"
        student.std_ename = "Wang, Xiao Ming"
        student.std_degree = "學士"
        student.std_studingstatus = "就學中"
        student.std_sex = "M"
        student.std_enrollyear = 112
        student.std_enrollterm = 1
        student.std_termcount = 4
        student.std_nation = "中華民國"
        student.std_schoolid = "NYCU"
        student.std_identity = "本國生"
        student.std_depno = "CS"
        student.std_depname = "資訊工程學系"
        student.std_aca_no = "EE"
        student.std_aca_cname = "電機學院"
        student.std_highestschname = "陽明交通大學"
        student.com_cellphone = "0912345678"
        student.com_email = "test@nycu.edu.tw"
        student.com_commzip = "30010"
        student.com_commadd = "新竹市大學路1001號"
        student.std_enrolled_date = date(2023, 9, 1)
        student.std_bank_account = "1234567890123456"
        student.notes = "Test notes"
        student.get_student_type.return_value = "undergraduate"
        return student

    @pytest.fixture
    def mock_student_data(self):
        """Mock student data for creation"""
        return {
            "std_stdno": "112550002",
            "std_stdcode": "112550002",
            "std_pid": "B987654321",
            "std_cname": "李小華",
            "std_ename": "Lee, Xiao Hua",
            "std_degree": "學士",
            "std_studingstatus": "就學中",
            "std_sex": "F",
            "std_enrollyear": 112,
            "std_enrollterm": 1,
            "std_termcount": 2,
            "std_nation": "中華民國",
            "std_schoolid": "NYCU",
            "std_identity": "本國生",
            "std_depno": "EE",
            "std_depname": "電機工程學系",
            "std_aca_no": "EE",
            "std_aca_cname": "電機學院",
            "com_cellphone": "0987654321",
            "com_email": "test2@nycu.edu.tw",
        }

    @pytest.mark.asyncio
    async def test_get_student_snapshot_with_student_object(
        self, service, mock_student
    ):
        """Test getting student snapshot with Student object"""
        result = await service.get_student_snapshot(mock_student)

        # Verify all expected fields are present
        expected_fields = [
            "id",
            "std_stdno",
            "std_stdcode",
            "std_pid",
            "std_cname",
            "std_ename",
            "std_degree",
            "std_studingstatus",
            "std_sex",
            "std_enrollyear",
            "std_enrollterm",
            "std_termcount",
            "std_nation",
            "std_schoolid",
            "std_identity",
            "std_depno",
            "std_depname",
            "std_aca_no",
            "std_aca_cname",
            "std_highestschname",
            "com_cellphone",
            "com_email",
            "com_commzip",
            "com_commadd",
            "std_enrolled_date",
            "std_bank_account",
            "notes",
            "student_type",
        ]

        for field in expected_fields:
            assert field in result

        # Verify specific values
        assert result["id"] == mock_student.id
        assert result["std_stdcode"] == mock_student.std_stdcode
        assert result["std_cname"] == mock_student.std_cname
        assert result["student_type"] == "undergraduate"
        assert result["std_enrolled_date"] == mock_student.std_enrolled_date.isoformat()

    @pytest.mark.asyncio
    async def test_get_student_snapshot_with_student_id(self, service, mock_student):
        """Test getting student snapshot with student ID"""
        student_id = 1

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalar_one.return_value = mock_student

            result = await service.get_student_snapshot(student_id)

            # Verify database was queried
            mock_execute.assert_called_once()

            # Verify result structure
            assert result["id"] == mock_student.id
            assert result["std_stdcode"] == mock_student.std_stdcode
            assert result["student_type"] == "undergraduate"

    @pytest.mark.asyncio
    async def test_get_student_snapshot_handles_none_date(self, service, mock_student):
        """Test student snapshot handling when enrolled_date is None"""
        mock_student.std_enrolled_date = None

        result = await service.get_student_snapshot(mock_student)

        assert result["std_enrolled_date"] is None

    @pytest.mark.asyncio
    async def test_get_student_by_id_success(self, service, mock_student):
        """Test successfully getting student by ID"""
        student_id = 1

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = mock_student

            result = await service.get_student_by_id(student_id)

            assert result == mock_student
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_student_by_id_not_found(self, service):
        """Test getting student by ID when student not found"""
        student_id = 999

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = None

            result = await service.get_student_by_id(student_id)

            assert result is None
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_student_by_stdcode_success(self, service, mock_student):
        """Test successfully getting student by student code"""
        stdcode = "112550001"

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = mock_student

            result = await service.get_student_by_stdcode(stdcode)

            assert result == mock_student
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_student_by_stdcode_not_found(self, service):
        """Test getting student by student code when student not found"""
        stdcode = "999999999"

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalar_one_or_none.return_value = None

            result = await service.get_student_by_stdcode(stdcode)

            assert result is None
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_student_info_success(self, service, mock_student):
        """Test successfully updating student information"""
        student_id = 1
        update_info = {
            "com_cellphone": "0911111111",
            "com_email": "newemail@nycu.edu.tw",
            "notes": "Updated notes",
        }

        with patch.object(
            service, "get_student_by_id", return_value=mock_student
        ), patch.object(service.db, "commit") as mock_commit, patch.object(
            service.db, "refresh"
        ) as mock_refresh:
            result = await service.update_student_info(student_id, update_info)

            # Verify student attributes were updated
            assert mock_student.com_cellphone == "0911111111"
            assert mock_student.com_email == "newemail@nycu.edu.tw"
            assert mock_student.notes == "Updated notes"

            # Verify database operations
            mock_commit.assert_called_once()
            mock_refresh.assert_called_once_with(mock_student)
            assert result == mock_student

    @pytest.mark.asyncio
    async def test_update_student_info_student_not_found(self, service):
        """Test updating student information when student not found"""
        student_id = 999
        update_info = {"com_cellphone": "0911111111"}

        with patch.object(service, "get_student_by_id", return_value=None):
            with pytest.raises(NotFoundError, match="Student 999 not found"):
                await service.update_student_info(student_id, update_info)

    @pytest.mark.asyncio
    async def test_update_student_info_ignores_invalid_fields(
        self, service, mock_student
    ):
        """Test that updating student info ignores fields that don't exist on model"""
        student_id = 1
        update_info = {
            "com_cellphone": "0911111111",  # Valid field
            "invalid_field": "should_be_ignored",  # Invalid field
            "another_invalid": "also_ignored",  # Invalid field
        }

        # Mock hasattr to return False for invalid fields
        original_hasattr = hasattr

        def mock_hasattr(obj, attr):
            if attr in ["invalid_field", "another_invalid"]:
                return False
            return original_hasattr(obj, attr)

        with patch.object(
            service, "get_student_by_id", return_value=mock_student
        ), patch.object(service.db, "commit"), patch.object(
            service.db, "refresh"
        ), patch(
            "builtins.hasattr", side_effect=mock_hasattr
        ):
            result = await service.update_student_info(student_id, update_info)

            # Verify valid field was updated
            assert mock_student.com_cellphone == "0911111111"

            # Verify invalid fields were not set
            assert not hasattr(mock_student, "invalid_field")
            assert not hasattr(mock_student, "another_invalid")

    @pytest.mark.asyncio
    async def test_create_student_success(self, service, mock_student_data):
        """Test successfully creating a new student"""
        with patch.object(service.db, "add") as mock_add, patch.object(
            service.db, "commit"
        ) as mock_commit, patch.object(service.db, "refresh") as mock_refresh:
            # Mock the created student
            created_student = Mock(spec=Student)
            created_student.id = 2
            created_student.std_stdcode = mock_student_data["std_stdcode"]

            with patch("app.models.student.Student", return_value=created_student):
                result = await service.create_student(mock_student_data)

                # Verify database operations
                mock_add.assert_called_once_with(created_student)
                mock_commit.assert_called_once()
                mock_refresh.assert_called_once_with(created_student)

                # Verify result
                assert result == created_student

    @pytest.mark.asyncio
    async def test_get_students_by_department_success(self, service):
        """Test successfully getting students by department"""
        depno = "CS"
        mock_students = [Mock(spec=Student) for _ in range(3)]

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalars.return_value.all.return_value = (
                mock_students
            )

            result = await service.get_students_by_department(depno)

            assert result == mock_students
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_students_by_department_empty_result(self, service):
        """Test getting students by department when no students found"""
        depno = "NONEXISTENT"

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalars.return_value.all.return_value = []

            result = await service.get_students_by_department(depno)

            assert result == []
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_students_by_academy_success(self, service):
        """Test successfully getting students by academy"""
        aca_no = "EE"
        mock_students = [Mock(spec=Student) for _ in range(5)]

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalars.return_value.all.return_value = (
                mock_students
            )

            result = await service.get_students_by_academy(aca_no)

            assert result == mock_students
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_students_by_academy_empty_result(self, service):
        """Test getting students by academy when no students found"""
        aca_no = "NONEXISTENT"

        with patch.object(service.db, "execute") as mock_execute:
            mock_execute.return_value.scalars.return_value.all.return_value = []

            result = await service.get_students_by_academy(aca_no)

            assert result == []
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_student_snapshot_all_field_types(self, service):
        """Test student snapshot handles different field types correctly"""
        # Create a student with various field types including None values
        student = Mock(spec=Student)
        student.id = 1
        student.std_stdcode = "112550001"
        student.std_cname = "測試學生"
        student.std_enrollyear = 112
        student.std_termcount = None  # None integer
        student.std_enrolled_date = None  # None date
        student.notes = ""  # Empty string
        student.com_cellphone = "0912345678"
        student.get_student_type.return_value = "master"

        # Set all other required fields to avoid AttributeError
        for field in [
            "std_stdno",
            "std_pid",
            "std_ename",
            "std_degree",
            "std_studingstatus",
            "std_sex",
            "std_enrollterm",
            "std_nation",
            "std_schoolid",
            "std_identity",
            "std_depno",
            "std_depname",
            "std_aca_no",
            "std_aca_cname",
            "std_highestschname",
            "com_email",
            "com_commzip",
            "com_commadd",
            "std_bank_account",
        ]:
            setattr(student, field, f"test_{field}")

        result = await service.get_student_snapshot(student)

        # Verify None values are handled correctly
        assert result["std_termcount"] is None
        assert result["std_enrolled_date"] is None
        assert result["notes"] == ""
        assert result["student_type"] == "master"
        assert result["std_cname"] == "測試學生"  # Unicode support

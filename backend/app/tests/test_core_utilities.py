"""
Unit tests for core utility functions

Tests utility modules including:
- Security functions
- Database utilities
- Configuration management
- Exception handling
- Date/time utilities
- Validation helpers
"""

from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.core.config import settings
from app.core.exceptions import AuthorizationError, BusinessLogicError, FileStorageError, NotFoundError, ValidationError
from app.core.security import create_access_token

# Note: These utilities are defined in the tests for demonstration
# In a real project, these would be imported from actual utility modules


def parse_date_string(value: str) -> datetime:
    """Parse ISO-8601 (with optional date-only) strings into aware datetimes."""
    if not value:
        raise ValueError("Date string cannot be empty")

    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:  # pragma: no cover - exercised via tests
        raise ValueError(f"Invalid date string: {value}") from exc


def format_date_for_display(date: datetime, *, format_string: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetimes for UI display using the given format string."""
    if date.tzinfo is None:
        # Ensure consistent formatting by assuming UTC for naive datetimes in tests
        date = date.replace(tzinfo=timezone.utc)
    return date.astimezone(timezone.utc).strftime(format_string)


def get_academic_year_from_date(date: datetime) -> int:
    """Convert a Gregorian date into ROC academic year."""
    roc_year = date.year - 1911
    # Academic year rolls over in August; months before August belong to previous year
    if date.month < 8:
        roc_year -= 1
    return roc_year


def is_within_application_period(start_date: datetime, end_date: datetime) -> bool:
    """Return True when the current time falls between start and end dates."""
    now = datetime.now(timezone.utc)
    return start_date <= now <= end_date


_DEPARTMENT_DIRECTORY = {
    "CS": {"name": "Computer Science", "college": "資訊學院"},
    "CSIE": {"name": "Computer Science & Information Engineering", "college": "資訊學院"},
    "EE": {"name": "Electrical Engineering", "college": "電機學院"},
    "ECE": {"name": "Electrical and Computer Engineering", "college": "電機學院"},
    "ME": {"name": "Mechanical Engineering", "college": "工學院"},
    "CE": {"name": "Civil Engineering", "college": "工學院"},
}

_COLLEGE_TO_SYSTEM_CODE = {
    "工學院": "ENG",
    "電機學院": "EECS",
    "資訊學院": "CS",
    "理學院": "SCI",
}


def get_college_code(department_code: str) -> str | None:
    """Return the college code associated with a department code."""
    if department_code is None:
        return None
    info = _DEPARTMENT_DIRECTORY.get(department_code.upper())
    if not info:
        return "UNKNOWN"
    return _COLLEGE_TO_SYSTEM_CODE.get(info["college"], "UNKNOWN")


def get_department_info(department_code: str) -> dict | None:
    """Return metadata for a department if it exists."""
    if not department_code:
        return None
    return _DEPARTMENT_DIRECTORY.get(department_code.upper())


def validate_student_department(department_code: str) -> bool:
    """Check whether the given department code is recognised."""
    return bool(get_department_info(department_code))


def map_college_to_system_code(college_name: str) -> str | None:
    """Map a human-readable college name to the system code used in integrations."""
    if not college_name:
        return None
    return _COLLEGE_TO_SYSTEM_CODE.get(college_name, "UNKNOWN")


@pytest.mark.unit
class TestSecurityFunctions:
    """Test suite for security utility functions"""

    def test_create_access_token_success(self):
        """Test successful access token creation"""
        # Arrange
        data = {"sub": "user@university.edu", "role": "student"}
        expires_delta = timedelta(minutes=30)

        # Act
        token = create_access_token(data=data, expires_delta=expires_delta)

        # Assert
        assert isinstance(token, str)
        assert len(token) > 0

        # Verify token can be decoded
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert payload["sub"] == "user@university.edu"
        assert payload["role"] == "student"
        assert "exp" in payload

    def test_create_access_token_default_expiry(self):
        """Test access token creation with default expiry"""
        # Arrange
        data = {"sub": "user@university.edu"}

        # Act
        token = create_access_token(data=data)

        # Assert
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        assert "exp" in payload

        # Verify expiry is set to default (15 minutes from now)
        exp_time = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        expected_exp = now + timedelta(minutes=15)

        # Allow 1 minute tolerance for test execution time
        assert abs((exp_time - expected_exp).total_seconds()) < 60

    def test_token_decode_verification(self):
        """Test token creation produces decodable JWT"""
        # Arrange
        data = {"sub": "user@university.edu", "role": "admin"}
        token = create_access_token(data=data)

        # Act - Decode the token manually for verification
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])

        # Assert
        assert payload["sub"] == "user@university.edu"
        assert payload["role"] == "admin"
        assert "exp" in payload

    def test_token_expiration_format(self):
        """Test token expiration is set correctly"""
        # Arrange
        data = {"sub": "user@university.edu"}
        custom_expiry = timedelta(minutes=60)

        # Act
        token = create_access_token(data=data, expires_delta=custom_expiry)
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])

        # Assert
        exp_time = datetime.fromtimestamp(payload["exp"])
        now = datetime.utcnow()
        expected_exp = now + custom_expiry

        # Allow 1 minute tolerance for test execution time
        assert abs((exp_time - expected_exp).total_seconds()) < 60


@pytest.mark.unit
class TestCustomExceptions:
    """Test suite for custom exception classes"""

    def test_validation_error_creation(self):
        """Test ValidationError creation and attributes"""
        # Arrange
        message = "Invalid input data"
        details = {"field": "email", "error": "Invalid format"}

        # Act
        error = ValidationError(message, details=details)

        # Assert
        assert str(error) == message
        assert error.details == details

    def test_not_found_error_creation(self):
        """Test NotFoundError creation"""
        # Arrange
        message = "Resource not found"
        resource_type = "User"
        resource_id = "123"

        # Act
        error = NotFoundError(message, resource_type=resource_type, resource_id=resource_id)

        # Assert
        assert str(error) == message
        assert error.resource_type == resource_type
        assert error.resource_id == resource_id

    def test_authorization_error_creation(self):
        """Test AuthorizationError creation"""
        # Arrange
        message = "Insufficient permissions"
        required_permission = "admin_access"

        # Act
        error = AuthorizationError(message, required_permission=required_permission)

        # Assert
        assert str(error) == message
        assert error.required_permission == required_permission

    def test_business_logic_error_creation(self):
        """Test BusinessLogicError creation"""
        # Arrange
        message = "Business rule violation"
        error_code = "DUPLICATE_APPLICATION"

        # Act
        error = BusinessLogicError(message, error_code=error_code)

        # Assert
        assert str(error) == message
        assert error.error_code == error_code

    def test_file_storage_error_creation(self):
        """Test FileStorageError creation"""
        # Arrange
        message = "File upload failed"
        file_name = "document.pdf"
        storage_path = "/uploads/documents/"

        # Act
        error = FileStorageError(message, file_name=file_name, storage_path=storage_path)

        # Assert
        assert str(error) == message
        assert error.file_name == file_name
        assert error.storage_path == storage_path


@pytest.mark.unit
class TestDateUtilities:
    """Test suite for date utility functions"""

    def test_parse_date_string_iso_format(self):
        """Test parsing ISO format date string"""
        # Arrange
        date_string = "2024-03-15T10:30:00Z"

        # Act
        result = parse_date_string(date_string)

        # Assert
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_parse_date_string_simple_format(self):
        """Test parsing simple date format"""
        # Arrange
        date_string = "2024-03-15"

        # Act
        result = parse_date_string(date_string)

        # Assert
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 15

    def test_parse_date_string_invalid_format(self):
        """Test parsing invalid date string"""
        # Arrange
        invalid_date_string = "invalid-date"

        # Act & Assert
        with pytest.raises(ValueError):
            parse_date_string(invalid_date_string)

    def test_format_date_for_display_default(self):
        """Test date formatting for display with default format"""
        # Arrange
        date = datetime(2024, 3, 15, 14, 30, 0, tzinfo=timezone.utc)

        # Act
        result = format_date_for_display(date)

        # Assert
        assert isinstance(result, str)
        assert "2024" in result
        assert "03" in result or "3" in result
        assert "15" in result

    def test_format_date_for_display_custom_format(self):
        """Test date formatting with custom format"""
        # Arrange
        date = datetime(2024, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
        custom_format = "%B %d, %Y"

        # Act
        result = format_date_for_display(date, format_string=custom_format)

        # Assert
        assert result == "March 15, 2024"

    def test_get_academic_year_from_date_first_semester(self):
        """Test academic year calculation for first semester"""
        # Arrange - Date in September (start of academic year)
        date = datetime(2024, 9, 15)

        # Act
        academic_year = get_academic_year_from_date(date)

        # Assert
        assert academic_year == 113  # 2024 - 1911 = 113

    def test_get_academic_year_from_date_second_semester(self):
        """Test academic year calculation for second semester"""
        # Arrange - Date in February (second semester)
        date = datetime(2024, 2, 15)

        # Act
        academic_year = get_academic_year_from_date(date)

        # Assert
        # February 2024 belongs to academic year 112 (started in 2023)
        assert academic_year == 112

    def test_is_within_application_period_active(self):
        """Test application period check for active period"""
        # Arrange
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=5)
        end_date = now + timedelta(days=25)

        # Act
        result = is_within_application_period(start_date, end_date)

        # Assert
        assert result is True

    def test_is_within_application_period_expired(self):
        """Test application period check for expired period"""
        # Arrange
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=35)
        end_date = now - timedelta(days=5)

        # Act
        result = is_within_application_period(start_date, end_date)

        # Assert
        assert result is False

    def test_is_within_application_period_future(self):
        """Test application period check for future period"""
        # Arrange
        now = datetime.now(timezone.utc)
        start_date = now + timedelta(days=5)
        end_date = now + timedelta(days=35)

        # Act
        result = is_within_application_period(start_date, end_date)

        # Assert
        assert result is False


@pytest.mark.unit
class TestCollegeMappings:
    """Test suite for college mapping utilities"""

    def test_get_college_code_valid_department(self):
        """Test getting college code for valid department"""
        # Arrange
        department_codes = ["CS", "CSIE", "EE", "ECE"]

        # Act & Assert
        for dept_code in department_codes:
            college_code = get_college_code(dept_code)
            assert isinstance(college_code, str)
            assert len(college_code) > 0

    def test_get_college_code_invalid_department(self):
        """Test getting college code for invalid department"""
        # Arrange
        invalid_dept_code = "INVALID_DEPT"

        # Act
        college_code = get_college_code(invalid_dept_code)

        # Assert
        assert college_code is None or college_code == "UNKNOWN"

    def test_get_department_info_existing(self):
        """Test getting department info for existing department"""
        # Arrange
        dept_code = "CSIE"

        # Act
        dept_info = get_department_info(dept_code)

        # Assert
        assert isinstance(dept_info, dict)
        assert "name" in dept_info
        assert "college" in dept_info
        assert isinstance(dept_info["name"], str)
        assert len(dept_info["name"]) > 0

    def test_get_department_info_nonexistent(self):
        """Test getting department info for non-existent department"""
        # Arrange
        invalid_dept_code = "NONEXISTENT"

        # Act
        dept_info = get_department_info(invalid_dept_code)

        # Assert
        assert dept_info is None

    def test_validate_student_department_valid(self):
        """Test department validation for valid department"""
        # Arrange
        valid_dept_codes = ["CSIE", "EE", "ME", "CE"]

        # Act & Assert
        for dept_code in valid_dept_codes:
            assert validate_student_department(dept_code) is True

    def test_validate_student_department_invalid(self):
        """Test department validation for invalid department"""
        # Arrange
        invalid_dept_codes = ["INVALID", "", None, "123"]

        # Act & Assert
        for dept_code in invalid_dept_codes:
            assert validate_student_department(dept_code) is False

    def test_map_college_to_system_code(self):
        """Test mapping college to system code"""
        # Arrange
        college_names = ["工學院", "電機學院", "資訊學院", "理學院"]

        # Act & Assert
        for college_name in college_names:
            system_code = map_college_to_system_code(college_name)
            assert isinstance(system_code, str)
            assert len(system_code) > 0


@pytest.mark.unit
class TestConfigurationSettings:
    """Test suite for configuration management"""

    def test_settings_environment_detection(self):
        """Test environment detection in settings"""
        # Act & Assert
        assert hasattr(settings, "environment")
        assert isinstance(settings.environment, str)

    def test_settings_database_url_format(self):
        """Test database URL format validation"""
        # Act & Assert
        assert hasattr(settings, "database_url")
        if settings.database_url:
            assert isinstance(settings.database_url, str)
            assert any(protocol in settings.database_url for protocol in ["postgresql", "sqlite"])

    def test_settings_security_configurations(self):
        """Test security-related configuration presence"""
        # Act & Assert
        assert hasattr(settings, "secret_key")
        assert hasattr(settings, "algorithm")
        assert hasattr(settings, "access_token_expire_minutes")

        assert isinstance(settings.secret_key, str)
        assert len(settings.secret_key) >= 32  # Minimum recommended length
        assert settings.algorithm in ["HS256", "RS256"]
        assert isinstance(settings.access_token_expire_minutes, int)
        assert settings.access_token_expire_minutes > 0

    def test_settings_email_configurations(self):
        """Test email-related configuration presence"""
        # Act & Assert
        assert hasattr(settings, "smtp_host")
        assert hasattr(settings, "smtp_port")
        assert hasattr(settings, "smtp_username")

        if settings.smtp_host:
            assert isinstance(settings.smtp_host, str)
            assert len(settings.smtp_host) > 0

        if settings.smtp_port:
            assert isinstance(settings.smtp_port, int)
            assert 1 <= settings.smtp_port <= 65535

    def test_settings_storage_configurations(self):
        """Test storage-related configuration presence"""
        # Act & Assert
        assert hasattr(settings, "minio_endpoint")
        assert hasattr(settings, "minio_access_key")
        assert hasattr(settings, "minio_secret_key")

        # Note: These might be None in test environment
        if settings.minio_endpoint:
            assert isinstance(settings.minio_endpoint, str)


@pytest.mark.unit
class TestValidationHelpers:
    """Test suite for validation helper functions"""

    def test_validate_email_format_valid(self):
        """Test email validation with valid formats"""
        # Arrange
        valid_emails = [
            "user@university.edu",
            "student.name@nycu.edu.tw",
            "test+label@example.com",
            "admin@domain.org",
        ]

        # Act & Assert
        from email_validator import validate_email

        for email in valid_emails:
            try:
                validate_email(email)
                is_valid = True
            except Exception:
                is_valid = False
            assert is_valid is True

    def test_validate_email_format_invalid(self):
        """Test email validation with invalid formats"""
        # Arrange
        invalid_emails = [
            "invalid-email",
            "@domain.com",
            "user@",
            "user space@domain.com",
            "",
        ]

        # Act & Assert
        from email_validator import EmailNotValidError, validate_email

        for email in invalid_emails:
            with pytest.raises(EmailNotValidError):
                validate_email(email)

    def test_validate_nycu_id_format(self):
        """Test NYCU ID validation"""

        # Arrange
        def validate_nycu_id(nycu_id: str) -> bool:
            """Simple NYCU ID validation for testing"""
            if not nycu_id:
                return False
            return len(nycu_id) >= 8 and nycu_id.isalnum()

        valid_ids = ["11011001", "10912345", "G110123456"]
        invalid_ids = ["123", "abc", "", "11011001@", "too-long-id-string"]

        # Act & Assert
        for nycu_id in valid_ids:
            assert validate_nycu_id(nycu_id) is True

        for nycu_id in invalid_ids:
            assert validate_nycu_id(nycu_id) is False

    def test_validate_gpa_range(self):
        """Test GPA validation"""

        # Arrange
        def validate_gpa(gpa: float) -> bool:
            """GPA validation for testing"""
            return 0.0 <= gpa <= 4.0

        valid_gpas = [0.0, 2.5, 3.85, 4.0]
        invalid_gpas = [-0.1, 4.1, 5.0, -1.0]

        # Act & Assert
        for gpa in valid_gpas:
            assert validate_gpa(gpa) is True

        for gpa in invalid_gpas:
            assert validate_gpa(gpa) is False

    def test_sanitize_filename(self):
        """Test filename sanitization"""

        # Arrange
        def sanitize_filename(filename: str) -> str:
            """Filename sanitization for testing"""
            import re

            # Remove potentially dangerous characters
            sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename)
            # Remove leading/trailing whitespace and dots
            sanitized = sanitized.strip(" .")
            return sanitized

        test_cases = [
            ("normal_file.pdf", "normal_file.pdf"),
            ("file with spaces.txt", "file with spaces.txt"),
            ("file<>:pipe.doc", "file___pipe.doc"),
            ("../../../etc/passwd", "..___..___.._etc_passwd"),
            ("  .dotfile.txt  ", "dotfile.txt"),
        ]

        # Act & Assert
        for input_filename, expected_output in test_cases:
            result = sanitize_filename(input_filename)
            assert result == expected_output

    # TODO: Add tests for rate limiting utilities
    # TODO: Add tests for data encryption/decryption helpers
    # TODO: Add tests for API response formatting utilities
    # TODO: Add tests for pagination helpers
    # TODO: Add performance tests for utility functions with large inputs

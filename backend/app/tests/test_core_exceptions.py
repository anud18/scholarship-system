"""
Unit tests for core exceptions
"""

from unittest.mock import Mock

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (  # Specific business logic exceptions
    ApplicationDeadlineError,
    AuthenticationError,
    AuthorizationError,
    BusinessLogicError,
    ConflictError,
    DuplicateApplicationError,
    EmailError,
    FileSizeExceededError,
    FileUploadError,
    InsufficientGpaError,
    InvalidApplicationStatusError,
    InvalidFileTypeError,
    MaxFilesExceededError,
    NotFoundError,
    OCRError,
    ScholarshipException,
    ValidationError,
    scholarship_exception_handler,
)


class TestBaseException:
    """Test cases for base ScholarshipException"""

    def test_scholarship_exception_basic(self):
        """Test basic ScholarshipException creation"""
        message = "Test error message"
        exc = ScholarshipException(message)

        assert str(exc) == message
        assert exc.message == message
        assert exc.status_code == 400
        assert exc.error_code is None
        assert exc.details == {}

    def test_scholarship_exception_with_all_params(self):
        """Test ScholarshipException with all parameters"""
        message = "Custom error"
        status_code = 422
        error_code = "CUSTOM_ERROR"
        details = {"field": "value", "reason": "invalid"}

        exc = ScholarshipException(
            message=message,
            status_code=status_code,
            error_code=error_code,
            details=details,
        )

        assert exc.message == message
        assert exc.status_code == status_code
        assert exc.error_code == error_code
        assert exc.details == details

    def test_scholarship_exception_with_none_details(self):
        """Test ScholarshipException with None details"""
        exc = ScholarshipException("Test message", details=None)

        assert exc.details == {}  # Should default to empty dict


class TestValidationError:
    """Test cases for ValidationError"""

    def test_validation_error_basic(self):
        """Test basic ValidationError creation"""
        message = "Invalid input"
        exc = ValidationError(message)

        assert exc.message == message
        assert exc.status_code == 422
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.field is None

    def test_validation_error_with_field(self):
        """Test ValidationError with field specification"""
        message = "Email is required"
        field = "email"
        details = {"constraint": "required"}

        exc = ValidationError(message, field=field, details=details)

        assert exc.message == message
        assert exc.field == field
        assert exc.details == details
        assert exc.status_code == 422
        assert exc.error_code == "VALIDATION_ERROR"


class TestAuthenticationError:
    """Test cases for AuthenticationError"""

    def test_authentication_error_default(self):
        """Test AuthenticationError with default message"""
        exc = AuthenticationError()

        assert exc.message == "Authentication failed"
        assert exc.status_code == 401
        assert exc.error_code == "AUTHENTICATION_ERROR"

    def test_authentication_error_custom_message(self):
        """Test AuthenticationError with custom message"""
        message = "Invalid credentials"
        exc = AuthenticationError(message)

        assert exc.message == message
        assert exc.status_code == 401
        assert exc.error_code == "AUTHENTICATION_ERROR"


class TestAuthorizationError:
    """Test cases for AuthorizationError"""

    def test_authorization_error_default(self):
        """Test AuthorizationError with default message"""
        exc = AuthorizationError()

        assert exc.message == "Access denied"
        assert exc.status_code == 403
        assert exc.error_code == "AUTHORIZATION_ERROR"

    def test_authorization_error_custom_message(self):
        """Test AuthorizationError with custom message"""
        message = "Insufficient permissions"
        exc = AuthorizationError(message)

        assert exc.message == message
        assert exc.status_code == 403
        assert exc.error_code == "AUTHORIZATION_ERROR"


class TestNotFoundError:
    """Test cases for NotFoundError"""

    def test_not_found_error_resource_only(self):
        """Test NotFoundError with resource name only"""
        resource = "User"
        exc = NotFoundError(resource)

        assert exc.message == "User not found"
        assert exc.status_code == 404
        assert exc.error_code == "NOT_FOUND"

    def test_not_found_error_with_identifier(self):
        """Test NotFoundError with resource and identifier"""
        resource = "Application"
        identifier = "123"
        exc = NotFoundError(resource, identifier)

        assert exc.message == "Application not found: 123"
        assert exc.status_code == 404
        assert exc.error_code == "NOT_FOUND"

    def test_not_found_error_empty_identifier(self):
        """Test NotFoundError with empty identifier"""
        resource = "Scholarship"
        identifier = ""
        exc = NotFoundError(resource, identifier)

        assert exc.message == "Scholarship not found"


class TestConflictError:
    """Test cases for ConflictError"""

    def test_conflict_error(self):
        """Test ConflictError creation"""
        message = "Resource already exists"
        exc = ConflictError(message)

        assert exc.message == message
        assert exc.status_code == 409
        assert exc.error_code == "CONFLICT"


class TestBusinessLogicError:
    """Test cases for BusinessLogicError"""

    def test_business_logic_error_basic(self):
        """Test basic BusinessLogicError creation"""
        message = "Business rule violation"
        exc = BusinessLogicError(message)

        assert exc.message == message
        assert exc.status_code == 422
        assert exc.error_code == "BUSINESS_LOGIC_ERROR"
        assert exc.details is None

    def test_business_logic_error_with_details(self):
        """Test BusinessLogicError with details"""
        message = "Invalid operation"
        details = {"rule": "minimum_gpa", "required": 3.0, "actual": 2.5}

        exc = BusinessLogicError(message, details=details)

        assert exc.message == message
        assert exc.details == details


class TestFileUploadError:
    """Test cases for FileUploadError"""

    def test_file_upload_error(self):
        """Test FileUploadError creation"""
        message = "File too large"
        exc = FileUploadError(message)

        assert exc.message == message
        assert exc.status_code == 400
        assert exc.error_code == "FILE_UPLOAD_ERROR"


class TestOCRError:
    """Test cases for OCRError"""

    def test_ocr_error(self):
        """Test OCRError creation"""
        message = "OCR processing failed"
        exc = OCRError(message)

        assert exc.message == message
        assert exc.status_code == 500
        assert exc.error_code == "OCR_ERROR"


class TestEmailError:
    """Test cases for EmailError"""

    def test_email_error(self):
        """Test EmailError creation"""
        message = "Failed to send email"
        exc = EmailError(message)

        assert exc.message == message
        assert exc.status_code == 500
        assert exc.error_code == "EMAIL_ERROR"


class TestSpecificBusinessLogicExceptions:
    """Test cases for specific business logic exceptions"""

    def test_insufficient_gpa_error(self):
        """Test InsufficientGpaError creation"""
        current_gpa = 2.8
        required_gpa = 3.5
        scholarship_type = "Academic Excellence"

        exc = InsufficientGpaError(current_gpa, required_gpa, scholarship_type)

        expected_message = (
            f"GPA {current_gpa} does not meet requirement of {required_gpa} for {scholarship_type} scholarship"
        )
        assert exc.message == expected_message
        assert exc.status_code == 422
        assert exc.error_code == "BUSINESS_LOGIC_ERROR"

    def test_application_deadline_error(self):
        """Test ApplicationDeadlineError creation"""
        scholarship_name = "Merit Scholarship"
        deadline = "2024-01-15"

        exc = ApplicationDeadlineError(scholarship_name, deadline)

        expected_message = f"Application deadline for {scholarship_name} has passed (deadline: {deadline})"
        assert exc.message == expected_message
        assert exc.status_code == 422

    def test_duplicate_application_error(self):
        """Test DuplicateApplicationError creation"""
        scholarship_name = "Research Fellowship"

        exc = DuplicateApplicationError(scholarship_name)

        expected_message = f"Student has already applied for {scholarship_name} scholarship"
        assert exc.message == expected_message
        assert exc.status_code == 409
        assert exc.error_code == "CONFLICT"

    def test_invalid_application_status_error(self):
        """Test InvalidApplicationStatusError creation"""
        current_status = "approved"
        target_status = "draft"

        exc = InvalidApplicationStatusError(current_status, target_status)

        expected_message = f"Cannot change application status from {current_status} to {target_status}"
        assert exc.message == expected_message
        assert exc.status_code == 422

    def test_max_files_exceeded_error(self):
        """Test MaxFilesExceededError creation"""
        max_files = 5

        exc = MaxFilesExceededError(max_files)

        expected_message = f"Maximum number of files ({max_files}) exceeded for application"
        assert exc.message == expected_message
        assert exc.status_code == 400
        assert exc.error_code == "FILE_UPLOAD_ERROR"

    def test_invalid_file_type_error(self):
        """Test InvalidFileTypeError creation"""
        file_type = "exe"
        allowed_types = ["pdf", "doc", "jpg"]

        exc = InvalidFileTypeError(file_type, allowed_types)

        expected_message = f"File type '{file_type}' not allowed. Allowed types: pdf, doc, jpg"
        assert exc.message == expected_message
        assert exc.status_code == 400

    def test_file_size_exceeded_error(self):
        """Test FileSizeExceededError creation"""
        file_size = 10485760  # 10MB
        max_size = 5242880  # 5MB

        exc = FileSizeExceededError(file_size, max_size)

        expected_message = f"File size {file_size} bytes exceeds maximum size of {max_size} bytes"
        assert exc.message == expected_message
        assert exc.status_code == 400


class TestExceptionHandler:
    """Test cases for exception handler"""

    @pytest.mark.asyncio
    async def test_scholarship_exception_handler_basic(self):
        """Test exception handler with basic exception"""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.trace_id = "test-trace-123"

        exc = ScholarshipException(
            message="Test error",
            status_code=422,
            error_code="TEST_ERROR",
            details={"field": "value"},
        )

        response = await scholarship_exception_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 422

        # Check response content structure
        # Note: We can't easily test the exact content without accessing private attributes
        # but we can verify the response type and status code

    @pytest.mark.asyncio
    async def test_scholarship_exception_handler_no_trace_id(self):
        """Test exception handler when request has no trace_id"""
        request = Mock(spec=Request)
        request.state = Mock()
        # No trace_id attribute

        exc = ValidationError("Test validation error")

        response = await scholarship_exception_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_scholarship_exception_handler_complex_exception(self):
        """Test exception handler with complex exception details"""
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.trace_id = "complex-trace-456"

        exc = BusinessLogicError(
            message="Complex business logic error",
            details={
                "violations": ["rule1", "rule2"],
                "context": {"user_id": 123, "resource": "application"},
                "suggestions": ["check field A", "verify field B"],
            },
        )

        response = await scholarship_exception_handler(request, exc)

        assert isinstance(response, JSONResponse)
        assert response.status_code == 422


class TestExceptionInheritance:
    """Test cases for exception inheritance"""

    def test_validation_error_is_scholarship_exception(self):
        """Test that ValidationError inherits from ScholarshipException"""
        exc = ValidationError("Test message")
        assert isinstance(exc, ScholarshipException)
        assert isinstance(exc, Exception)

    def test_business_logic_errors_inheritance(self):
        """Test that specific business logic errors inherit correctly"""
        gpa_error = InsufficientGpaError(2.0, 3.0, "Test")
        deadline_error = ApplicationDeadlineError("Test", "2024-01-01")

        assert isinstance(gpa_error, BusinessLogicError)
        assert isinstance(gpa_error, ScholarshipException)

        assert isinstance(deadline_error, BusinessLogicError)
        assert isinstance(deadline_error, ScholarshipException)

    def test_file_upload_errors_inheritance(self):
        """Test that file upload errors inherit correctly"""
        max_files_error = MaxFilesExceededError(5)
        file_type_error = InvalidFileTypeError("exe", ["pdf"])
        file_size_error = FileSizeExceededError(1000, 500)

        assert isinstance(max_files_error, FileUploadError)
        assert isinstance(max_files_error, ScholarshipException)

        assert isinstance(file_type_error, FileUploadError)
        assert isinstance(file_type_error, ScholarshipException)

        assert isinstance(file_size_error, FileUploadError)
        assert isinstance(file_size_error, ScholarshipException)

    def test_conflict_errors_inheritance(self):
        """Test that conflict errors inherit correctly"""
        duplicate_error = DuplicateApplicationError("Test Scholarship")

        assert isinstance(duplicate_error, ConflictError)
        assert isinstance(duplicate_error, ScholarshipException)

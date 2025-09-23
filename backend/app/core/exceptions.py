"""
Custom exceptions for scholarship management system
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from typing import Optional, Dict, Any, List


class ScholarshipException(Exception):
    """Base exception for scholarship system"""
    
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}
        super().__init__(message)


class ValidationError(ScholarshipException):
    """Validation error exception"""
    
    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            status_code=422,
            error_code="VALIDATION_ERROR",
            details=details or {}
        )
        self.field = field


class AuthenticationError(ScholarshipException):
    """Authentication error exception"""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            status_code=401,
            error_code="AUTHENTICATION_ERROR"
        )


class AuthorizationError(ScholarshipException):
    """Authorization error exception"""
    
    def __init__(self, message: str = "Access denied"):
        super().__init__(
            message=message,
            status_code=403,
            error_code="AUTHORIZATION_ERROR"
        )


class NotFoundError(ScholarshipException):
    """Resource not found exception"""
    
    def __init__(self, resource: str, identifier: str = ""):
        message = f"{resource} not found"
        if identifier:
            message += f": {identifier}"
        super().__init__(
            message=message,
            status_code=404,
            error_code="NOT_FOUND"
        )


class ConflictError(ScholarshipException):
    """Resource conflict exception"""
    
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=409,
            error_code="CONFLICT"
        )


class BusinessLogicError(ScholarshipException):
    """Business logic error exception"""
    
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            status_code=422,
            error_code="BUSINESS_LOGIC_ERROR",
            details=details
        )


class FileUploadError(ScholarshipException):
    """File upload error exception"""
    
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=400,
            error_code="FILE_UPLOAD_ERROR"
        )


class OCRError(ScholarshipException):
    """OCR processing error exception"""
    
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=500,
            error_code="OCR_ERROR"
        )


class EmailError(ScholarshipException):
    """Email sending error exception"""
    
    def __init__(self, message: str):
        super().__init__(
            message=message,
            status_code=500,
            error_code="EMAIL_ERROR"
        )


class ServiceUnavailableError(ScholarshipException):
    """Service unavailable error exception"""
    
    def __init__(self, message: str = "Service temporarily unavailable"):
        super().__init__(
            message=message,
            status_code=503,
            error_code="SERVICE_UNAVAILABLE"
        )


# Exception handler for custom exceptions
async def scholarship_exception_handler(request: Request, exc: ScholarshipException) -> JSONResponse:
    """Handle custom scholarship exceptions"""
    content = {
        "success": False,
        "message": exc.message,
        "error_code": exc.error_code,
        "details": exc.details,
        "trace_id": getattr(request.state, 'trace_id', None)
    }
    
    return JSONResponse(
        status_code=exc.status_code,
        content=content
    )


# Specific business logic exceptions for scholarship system
class InsufficientGpaError(BusinessLogicError):
    """Raised when student's GPA doesn't meet scholarship requirements"""
    
    def __init__(self, current_gpa: float, required_gpa: float, scholarship_type: str):
        message = f"GPA {current_gpa} does not meet requirement of {required_gpa} for {scholarship_type} scholarship"
        super().__init__(message)


class ApplicationDeadlineError(BusinessLogicError):
    """Raised when trying to submit application after deadline"""
    
    def __init__(self, scholarship_name: str, deadline: str):
        message = f"Application deadline for {scholarship_name} has passed (deadline: {deadline})"
        super().__init__(message)


class DuplicateApplicationError(ConflictError):
    """Raised when student tries to apply for same scholarship twice"""
    
    def __init__(self, scholarship_name: str):
        message = f"Student has already applied for {scholarship_name} scholarship"
        super().__init__(message)


class InvalidApplicationStatusError(BusinessLogicError):
    """Raised when trying to perform invalid status transition"""
    
    def __init__(self, current_status: str, target_status: str):
        message = f"Cannot change application status from {current_status} to {target_status}"
        super().__init__(message)


class MaxFilesExceededError(FileUploadError):
    """Raised when file upload limit is exceeded"""
    
    def __init__(self, max_files: int):
        message = f"Maximum number of files ({max_files}) exceeded for application"
        super().__init__(message)


class InvalidFileTypeError(FileUploadError):
    """Raised when uploaded file type is not allowed"""
    
    def __init__(self, file_type: str, allowed_types: List[str]):
        message = f"File type '{file_type}' not allowed. Allowed types: {', '.join(allowed_types)}"
        super().__init__(message)


class FileSizeExceededError(FileUploadError):
    """Raised when uploaded file size exceeds limit"""
    
    def __init__(self, file_size: int, max_size: int):
        message = f"File size {file_size} bytes exceeds maximum size of {max_size} bytes"
        super().__init__(message) 
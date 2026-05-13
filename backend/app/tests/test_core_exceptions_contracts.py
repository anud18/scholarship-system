"""
Contract tests for `app.core.exceptions` exception classes.

Every exception's status_code + error_code feeds into the JSON
response shape the frontend parses. A bug where ValidationError
returns 500 instead of 422 means frontend's "show inline error" path
breaks → users see a generic error toast instead of helpful guidance.

Pinning every status_code + error_code so a future refactor (e.g.,
collapsing exception hierarchy) surfaces the change explicitly.

15+ exception classes covered (24 cases).
"""

import pytest

from app.core.exceptions import (
    ApplicationDeadlineError,
    AuthenticationError,
    AuthorizationError,
    BatchImportError,
    BatchImportParseError,
    BatchImportPermissionError,
    BatchImportStatusError,
    BatchImportValidationError,
    BusinessLogicError,
    ConflictError,
    DuplicateApplicationError,
    EmailError,
    FileSizeExceededError,
    FileStorageError,
    FileUploadError,
    InsufficientGpaError,
    InvalidApplicationStatusError,
    InvalidFileTypeError,
    MaxFilesExceededError,
    NotFoundError,
    OCRError,
    RosterAlreadyExistsError,
    RosterGenerationError,
    RosterLockedError,
    RosterNotFoundError,
    ScholarshipException,
    ServiceUnavailableError,
    StudentVerificationError,
    ValidationError,
)

# ─── Base + 4xx exceptions ───────────────────────────────────────────


def test_scholarship_exception_base_defaults():
    """Base defaults: status=400, error_code=None, details={}."""
    exc = ScholarshipException("err")
    assert exc.message == "err"
    assert exc.status_code == 400
    assert exc.error_code is None
    assert exc.details == {}


def test_validation_error_is_422_with_field():
    """ValidationError → 422 + VALIDATION_ERROR + field attached."""
    exc = ValidationError("bad input", field="gpa")
    assert exc.status_code == 422
    assert exc.error_code == "VALIDATION_ERROR"
    assert exc.field == "gpa"


def test_authentication_error_is_401():
    """AuthenticationError → 401 + AUTHENTICATION_ERROR. Default message OK."""
    exc = AuthenticationError()
    assert exc.status_code == 401
    assert exc.error_code == "AUTHENTICATION_ERROR"


def test_authorization_error_is_403():
    """AuthorizationError → 403 + AUTHORIZATION_ERROR."""
    exc = AuthorizationError()
    assert exc.status_code == 403
    assert exc.error_code == "AUTHORIZATION_ERROR"


def test_not_found_error_is_404_with_identifier():
    """NotFoundError formats 'X not found: id'; pin format so users see
    consistent messaging across resources."""
    exc = NotFoundError("User", "42")
    assert exc.status_code == 404
    assert exc.error_code == "NOT_FOUND"
    assert "User" in exc.message
    assert "42" in exc.message


def test_not_found_error_no_identifier_omits_colon():
    """Without identifier, no trailing colon. Pin so 'User not found' stays
    clean (not 'User not found: ')."""
    exc = NotFoundError("User")
    assert exc.message == "User not found"


def test_conflict_error_is_409():
    """ConflictError → 409 + CONFLICT (RESTful semantics)."""
    exc = ConflictError("duplicate")
    assert exc.status_code == 409
    assert exc.error_code == "CONFLICT"


def test_business_logic_error_is_422():
    """BusinessLogicError → 422 + BUSINESS_LOGIC_ERROR."""
    exc = BusinessLogicError("invalid op")
    assert exc.status_code == 422
    assert exc.error_code == "BUSINESS_LOGIC_ERROR"


# ─── 5xx exceptions ──────────────────────────────────────────────────


def test_file_storage_error_is_500_with_details():
    """FileStorageError → 500 + FILE_STORAGE_ERROR + file_name/path in
    details (admin sees which file failed in trace)."""
    exc = FileStorageError("upload failed", file_name="x.pdf", storage_path="/tmp/x.pdf")
    assert exc.status_code == 500
    assert exc.error_code == "FILE_STORAGE_ERROR"
    assert exc.details == {"file_name": "x.pdf", "storage_path": "/tmp/x.pdf"}


def test_file_storage_error_no_details_omits_keys():
    """Optional file_name/storage_path skipped when None — pin so empty
    keys don't pollute the JSON response."""
    exc = FileStorageError("network down")
    assert exc.details == {}


def test_ocr_error_is_500():
    exc = OCRError("model failed")
    assert exc.status_code == 500
    assert exc.error_code == "OCR_ERROR"


def test_email_error_is_500():
    exc = EmailError("smtp down")
    assert exc.status_code == 500
    assert exc.error_code == "EMAIL_ERROR"


def test_service_unavailable_is_503():
    """503 is the right status for transient external API failures —
    triggers client retries via Retry-After."""
    exc = ServiceUnavailableError()
    assert exc.status_code == 503
    assert exc.error_code == "SERVICE_UNAVAILABLE"


# ─── BusinessLogicError descendants ──────────────────────────────────


def test_insufficient_gpa_error_formats_message():
    """Message includes current + required GPA + scholarship type — pin
    so admin support can match user reports to log entries."""
    exc = InsufficientGpaError(3.2, 3.5, "PHD")
    assert "3.2" in exc.message
    assert "3.5" in exc.message
    assert "PHD" in exc.message
    assert exc.status_code == 422  # inherited from BusinessLogicError


def test_application_deadline_error_includes_deadline():
    """Deadline timestamp surfaced to user so they know what they missed."""
    exc = ApplicationDeadlineError("PHD", "2025-09-30")
    assert "PHD" in exc.message
    assert "2025-09-30" in exc.message


def test_duplicate_application_error_is_409():
    """Inherits from ConflictError → 409."""
    exc = DuplicateApplicationError("PHD")
    assert exc.status_code == 409
    assert "PHD" in exc.message


def test_invalid_application_status_error_shows_transition():
    """Message lists both current + target status — admin triage hint."""
    exc = InvalidApplicationStatusError("submitted", "draft")
    assert "submitted" in exc.message
    assert "draft" in exc.message


# ─── File upload errors ─────────────────────────────────────────────


def test_max_files_exceeded_error_includes_limit():
    exc = MaxFilesExceededError(5)
    assert "5" in exc.message
    assert exc.error_code == "FILE_UPLOAD_ERROR"


def test_invalid_file_type_error_lists_allowed():
    exc = InvalidFileTypeError("exe", ["pdf", "jpg"])
    assert "exe" in exc.message
    assert "pdf" in exc.message
    assert "jpg" in exc.message


def test_file_size_exceeded_error_includes_sizes():
    exc = FileSizeExceededError(1000000, 500000)
    assert "1000000" in exc.message
    assert "500000" in exc.message


# ─── Roster exceptions ──────────────────────────────────────────────


def test_roster_generation_error_is_500():
    exc = RosterGenerationError("DB lock")
    assert exc.status_code == 500
    assert exc.error_code == "ROSTER_GENERATION_ERROR"


def test_roster_not_found_inherits_404():
    """Inherits from NotFoundError → 404 + 'Roster not found: id'."""
    exc = RosterNotFoundError("ROSTER-001")
    assert exc.status_code == 404
    assert "Roster" in exc.message
    assert "ROSTER-001" in exc.message


def test_roster_already_exists_is_409():
    exc = RosterAlreadyExistsError("dup")
    assert exc.status_code == 409
    assert exc.error_code == "CONFLICT"


# ─── Batch import exceptions ────────────────────────────────────────


def test_batch_import_validation_error_collects_details():
    """Validation error attaches row_number + student_id + field if set —
    pin so admin troubleshooting UI gets all the fields it needs."""
    exc = BatchImportValidationError("bad row", row_number=5, student_id="S1", field="gpa")
    assert exc.details == {"row_number": 5, "student_id": "S1", "field": "gpa"}


def test_batch_import_permission_error_inherits_403_and_carries_college():
    """Permission error → 403, with college_code attached on demand."""
    exc = BatchImportPermissionError("denied", college_code="A")
    assert exc.status_code == 403
    assert exc.details.get("college_code") == "A"

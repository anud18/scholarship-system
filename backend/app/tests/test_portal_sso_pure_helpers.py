"""
Pure-function tests for `PortalSSOService` helpers.

This is the bridge to NYCU Portal SSO. The enum mappers turn the
portal's user-type / status strings into our internal role / type /
employee-status enums — bugs there mean students log in as professors,
graduated employees show up as 'active' on roster screens, or worse.

5 helpers covered (15 cases):
- `_validate_portal_response`  : required-field gate
- `_get_test_portal_data`      : dev-mode stub shape
- `_map_user_type_to_role`     : portal type → UserRole
- `_map_user_type_to_enum`     : portal type → UserType
- `_map_status_to_enum`        : portal 在學/在職/退休/畢業 → EmployeeStatus
"""

import pytest

from app.models.user import EmployeeStatus, UserRole, UserType
from app.services.portal_sso_service import PortalSSOService


@pytest.fixture
def service():
    """Helpers under test don't touch self.db, so a None session is fine.
    AuthService and StudentService get constructed but only their .api_enabled
    / instance state matters for these tests, not their methods."""
    return PortalSSOService(db=None)  # type: ignore[arg-type]


# ─── _validate_portal_response ───────────────────────────────────────


def test_validate_portal_response_with_all_required(service):
    assert service._validate_portal_response({"nycuID": "abc", "txtName": "Alice"}) is True


def test_validate_portal_response_missing_nycuid(service):
    assert service._validate_portal_response({"txtName": "Alice"}) is False


def test_validate_portal_response_missing_txtname(service):
    assert service._validate_portal_response({"nycuID": "abc"}) is False


def test_validate_portal_response_empty_value_rejected(service):
    """Empty string is falsy ⇒ rejected. Portal sometimes returns blanks
    for missing fields, and we don't want to log them in as a user with
    an empty name."""
    assert service._validate_portal_response({"nycuID": "abc", "txtName": ""}) is False
    assert service._validate_portal_response({"nycuID": "", "txtName": "Alice"}) is False


# ─── _get_test_portal_data ───────────────────────────────────────────


def test_test_portal_data_has_all_required_fields(service):
    data = service._get_test_portal_data()
    # Every field the production code reads must be present in the dev stub.
    for k in ("nycuID", "txtName", "mail", "userType", "employeestatus"):
        assert k in data and data[k]


def test_test_portal_data_passes_validate(service):
    """Round-trip: the dev stub must satisfy `_validate_portal_response`."""
    assert service._validate_portal_response(service._get_test_portal_data()) is True


# ─── _map_user_type_to_role ──────────────────────────────────────────


def test_map_user_type_to_role_student(service):
    assert service._map_user_type_to_role("student") == UserRole.student


def test_map_user_type_to_role_employee_to_professor(service):
    """Portal says 'employee' but we default that to professor (most employees
    interacting with this system are faculty)."""
    assert service._map_user_type_to_role("employee") == UserRole.professor


def test_map_user_type_to_role_case_insensitive(service):
    assert service._map_user_type_to_role("STUDENT") == UserRole.student
    assert service._map_user_type_to_role("Staff") == UserRole.admin


def test_map_user_type_to_role_unknown_defaults_to_student(service):
    """Unknown / future portal types fall through to student (least-privilege
    default — don't auto-elevate unknown user types)."""
    assert service._map_user_type_to_role("alumni") == UserRole.student


# ─── _map_user_type_to_enum ──────────────────────────────────────────


def test_map_user_type_to_enum_staff_is_employee(service):
    """Staff → employee (not its own UserType — only two values: student / employee)."""
    assert service._map_user_type_to_enum("staff") == UserType.employee


def test_map_user_type_to_enum_unknown_defaults_to_student(service):
    assert service._map_user_type_to_enum("alumni") == UserType.student


# ─── _map_status_to_enum ─────────────────────────────────────────────


def test_map_status_to_enum_chinese_values(service):
    """The Portal returns Chinese status strings — pin every mapping."""
    assert service._map_status_to_enum("在學") == EmployeeStatus.student
    assert service._map_status_to_enum("在職") == EmployeeStatus.active
    assert service._map_status_to_enum("退休") == EmployeeStatus.retired
    assert service._map_status_to_enum("畢業") == EmployeeStatus.graduated


def test_map_status_to_enum_unknown_defaults_to_student(service):
    """An unknown Chinese / English status string ⇒ student (least-privilege
    default; don't show 'active' or 'retired' for users we can't classify)."""
    assert service._map_status_to_enum("unknown") == EmployeeStatus.student
    assert service._map_status_to_enum("") == EmployeeStatus.student

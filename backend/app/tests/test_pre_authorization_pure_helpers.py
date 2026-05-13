"""
Pure-function tests for `PreAuthorizationService` enum mappers.

Pre-authorization runs at first portal login — these helpers decide
the role / type / status that gets seeded into the user row. A wrong
mapping here would either grant inflated privileges or block legitimate
users from logging in.

Note: `PortalSSOService` has a parallel mapper (already tested in
test_portal_sso_pure_helpers.py). The two services have different
default-policies and must remain independent — this file pins
PreAuthorizationService's defaults so a refactor that consolidates the
mappers surfaces the policy divergence.

3 mappers covered (10 cases):
- `_get_default_role_from_portal`  : userType → UserRole (student | professor)
- `_map_user_type`                 : userType → UserType
- `_map_employee_status`           : Chinese status → EmployeeStatus
"""

import pytest

from app.models.user import EmployeeStatus, UserRole, UserType
from app.services.pre_authorization_service import PreAuthorizationService


@pytest.fixture
def service():
    return PreAuthorizationService(db=None)  # type: ignore[arg-type]


# ─── _get_default_role_from_portal ───────────────────────────────────


def test_default_role_student(service):
    assert service._get_default_role_from_portal({"userType": "student"}) == UserRole.student


def test_default_role_employee_defaults_to_professor(service):
    """Note: PreAuthService defaults ALL non-student userTypes to professor —
    different from PortalSSOService which maps 'staff' → admin."""
    assert service._get_default_role_from_portal({"userType": "employee"}) == UserRole.professor
    assert service._get_default_role_from_portal({"userType": "staff"}) == UserRole.professor


def test_default_role_missing_user_type(service):
    """No userType in portal payload → falls into 'else' → professor.
    This means an attacker who can submit a portal_data with no userType
    gets *elevated* to professor on pre-auth. Pinning the behavior so a
    future hardening pass (e.g. defaulting to student) is intentional."""
    assert service._get_default_role_from_portal({}) == UserRole.professor


# ─── _map_user_type ──────────────────────────────────────────────────


def test_map_user_type_student(service):
    assert service._map_user_type("student") == UserType.student


def test_map_user_type_employee(service):
    assert service._map_user_type("employee") == UserType.employee


def test_map_user_type_unknown_or_none_defaults_to_employee(service):
    """Unknown / None / 'staff' → employee (the SAFE default for type since
    UserType only has 2 values; non-student is 'employee')."""
    assert service._map_user_type("staff") == UserType.employee
    assert service._map_user_type(None) == UserType.employee


# ─── _map_employee_status ────────────────────────────────────────────


def test_map_employee_status_all_four_chinese_values(service):
    """Pin every Chinese status string the portal sends."""
    assert service._map_employee_status("在職") == EmployeeStatus.active
    assert service._map_employee_status("退休") == EmployeeStatus.retired
    assert service._map_employee_status("在學") == EmployeeStatus.student
    assert service._map_employee_status("畢業") == EmployeeStatus.graduated


def test_map_employee_status_unknown_defaults_to_active(service):
    """PreAuthService defaults unknown/None → active. Differs from
    PortalSSOService which defaults to student. The divergence reflects
    different use cases: pre-auth runs for employees only (admin-initiated),
    SSO runs for everyone (least-privilege defaults to student)."""
    assert service._map_employee_status("unknown") == EmployeeStatus.active
    assert service._map_employee_status(None) == EmployeeStatus.active
    assert service._map_employee_status("") == EmployeeStatus.active

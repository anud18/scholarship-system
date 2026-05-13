"""
Tests for `MockSSOService._map_role_to_user_type` — the role → portal-userType
mapping used in mock-SSO dev-login responses.

In production, the real `PortalSSOService` (covered in wave 6x) decides
the userType. In development, this mock mirror produces the SAME shape
so the local dev-login UI behaves identically. A drift between the two
services would cause dev-only behavior that doesn't reproduce in
staging/prod.

Single helper covered (5 cases). Pure mapping table.
"""

import pytest

from app.models.user import UserRole
from app.services.mock_sso_service import MockSSOService


# Instantiate without DB by setting db=None and auth_service=None on a
# pre-allocated instance. The mapper doesn't touch either.
def _service() -> MockSSOService:
    svc = object.__new__(MockSSOService)
    svc.db = None  # type: ignore[assignment]
    svc.auth_service = None  # type: ignore[assignment]
    return svc


def test_student_maps_to_student():
    """Pin: student role → 'student' portal userType.
    The only role that maps to 'student' in the portal contract."""
    assert _service()._map_role_to_user_type(UserRole.student) == "student"


def test_professor_maps_to_employee():
    """Pin: professor → 'employee'. The portal SSO treats all staff
    roles (professor / college / admin) as 'employee' uniformly."""
    assert _service()._map_role_to_user_type(UserRole.professor) == "employee"


def test_college_reviewer_maps_to_employee():
    """Pin: college role → 'employee'. Same employee bucket."""
    assert _service()._map_role_to_user_type(UserRole.college) == "employee"


def test_admin_and_super_admin_map_to_employee():
    """Pin: admin + super_admin both → 'employee'. The portal doesn't
    have a separate 'admin' userType — privilege is determined by the
    role field, not user_type."""
    assert _service()._map_role_to_user_type(UserRole.admin) == "employee"
    assert _service()._map_role_to_user_type(UserRole.super_admin) == "employee"


def test_unknown_role_falls_back_to_employee():
    """Pin: defensive default — unknown roles default to 'employee'
    (safer for the portal, treats them as restricted-access staff).
    A 'student' default would accidentally grant student-side features
    to a misconfigured role."""

    class _FakeRole:
        pass

    # Pass something not in the mapping dict
    result = _service()._map_role_to_user_type(_FakeRole())  # type: ignore[arg-type]
    assert result == "employee"

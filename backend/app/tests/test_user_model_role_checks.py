"""
Pure-function tests for `User` model role + permission methods.

Every protected endpoint runs an authorization check through one of
these methods. Drift here = security gate broken.

Coverage spans:
- 5 role predicates (is_admin/student/professor/college/super_admin)
- Composite: is_employee (everyone except students)
- Permission-gating helpers: can_manage_scholarships, can_assign_roles
- has_permission() lookup against the 13-permission map (CRITICAL —
  this is the central role-based ACL)
- has_role() generic check

Bugs cause:
- Students get admin pages (can_assign_roles returns True for student)
  → privilege escalation
- Professors can't review their assigned applications (is_employee
  excludes them) → outage for reviewers

11 methods covered (18 cases).
"""

import pytest

from app.models.user import User, UserRole


def _user(role: UserRole) -> User:
    """Construct an in-memory User (no DB session)."""
    return User(role=role, id=1, name="Test", nycu_id="test1")


# ─── Role predicates ─────────────────────────────────────────────────


def test_is_admin_only_admin_role():
    """is_admin → True only for UserRole.admin (NOT super_admin)."""
    assert _user(UserRole.admin).is_admin() is True
    # super_admin is a distinct role — pin so a refactor doesn't
    # accidentally collapse them.
    assert _user(UserRole.super_admin).is_admin() is False
    assert _user(UserRole.student).is_admin() is False


def test_is_student_only_student_role():
    assert _user(UserRole.student).is_student() is True
    for r in (UserRole.professor, UserRole.college, UserRole.admin, UserRole.super_admin):
        assert _user(r).is_student() is False


def test_is_professor_only_professor_role():
    assert _user(UserRole.professor).is_professor() is True
    assert _user(UserRole.admin).is_professor() is False


def test_is_college_only_college_role():
    assert _user(UserRole.college).is_college() is True
    assert _user(UserRole.admin).is_college() is False


def test_is_super_admin_only_super_admin_role():
    """super_admin distinct from admin — pin (privilege escalation guard)."""
    assert _user(UserRole.super_admin).is_super_admin() is True
    assert _user(UserRole.admin).is_super_admin() is False


# ─── Composite: is_employee ──────────────────────────────────────────


def test_is_employee_excludes_only_student():
    """is_employee = everyone except students. Pin so students never
    accidentally get bumped into employee-only flows (e.g., the
    pre-authorization service)."""
    for r in (UserRole.professor, UserRole.college, UserRole.admin, UserRole.super_admin):
        assert _user(r).is_employee() is True, f"role={r} should be employee"
    assert _user(UserRole.student).is_employee() is False


# ─── can_manage_scholarships ────────────────────────────────────────


def test_can_manage_scholarships_three_roles_only():
    """Pin the 3-role allowlist (college/admin/super_admin). Students and
    professors must NOT manage scholarships."""
    for r in (UserRole.college, UserRole.admin, UserRole.super_admin):
        assert _user(r).can_manage_scholarships() is True
    for r in (UserRole.student, UserRole.professor):
        assert _user(r).can_manage_scholarships() is False


# ─── can_assign_roles ────────────────────────────────────────────────


def test_can_assign_roles_admins_only():
    """CRITICAL: can_assign_roles is the gate to user-management screens.
    Only admin + super_admin. Students/professors/college MUST NOT have
    this — privilege escalation if they do."""
    assert _user(UserRole.admin).can_assign_roles() is True
    assert _user(UserRole.super_admin).can_assign_roles() is True
    for r in (UserRole.student, UserRole.professor, UserRole.college):
        assert _user(r).can_assign_roles() is False, f"role={r} unexpectedly can assign roles"


# ─── has_role ────────────────────────────────────────────────────────


def test_has_role_exact_match():
    """has_role is equality check, not inheritance — admin doesn't
    'have' student role just because they're more privileged."""
    student = _user(UserRole.student)
    assert student.has_role(UserRole.student) is True
    assert student.has_role(UserRole.admin) is False

    admin = _user(UserRole.admin)
    assert admin.has_role(UserRole.admin) is True
    # Pin: admin doesn't implicitly have student role.
    assert admin.has_role(UserRole.student) is False


# ─── has_permission (the central ACL) ────────────────────────────────


def test_has_permission_roster_create_admins_only():
    """SECURITY-CRITICAL: roster_create = admin + super_admin. Anyone
    else creating a roster would corrupt the payment workflow."""
    assert _user(UserRole.admin).has_permission("roster_create") is True
    assert _user(UserRole.super_admin).has_permission("roster_create") is True
    for r in (UserRole.student, UserRole.professor, UserRole.college):
        assert _user(r).has_permission("roster_create") is False


def test_has_permission_roster_delete_super_admin_only():
    """SECURITY: only super_admin can delete a roster. Admin alone CAN
    NOT — pinning this protects against accidental destructive ops."""
    assert _user(UserRole.super_admin).has_permission("roster_delete") is True
    assert _user(UserRole.admin).has_permission("roster_delete") is False


def test_has_permission_application_create_student_only():
    """Only students create applications. Pin so a refactor that adds
    'admin can create on behalf of student' is intentional."""
    assert _user(UserRole.student).has_permission("application_create") is True
    for r in (UserRole.professor, UserRole.college, UserRole.admin, UserRole.super_admin):
        assert _user(r).has_permission("application_create") is False


def test_has_permission_application_view_all_authenticated_roles():
    """All 5 roles can view applications (with their own scope)."""
    for r in (UserRole.student, UserRole.professor, UserRole.college, UserRole.admin, UserRole.super_admin):
        assert _user(r).has_permission("application_view") is True


def test_has_permission_application_review_excludes_students():
    """Students can't review — the gate that keeps students from seeing
    review controls in their own application UI."""
    for r in (UserRole.professor, UserRole.college, UserRole.admin, UserRole.super_admin):
        assert _user(r).has_permission("application_review") is True
    assert _user(UserRole.student).has_permission("application_review") is False


def test_has_permission_user_manage_admins_only():
    """Only admin + super_admin manage users. Same security tier as
    can_assign_roles."""
    for r in (UserRole.admin, UserRole.super_admin):
        assert _user(r).has_permission("user_manage") is True
    for r in (UserRole.student, UserRole.professor, UserRole.college):
        assert _user(r).has_permission("user_manage") is False


def test_has_permission_unknown_permission_returns_false():
    """Unknown permission key → empty allowed_roles list → False (no
    accidental allow-by-default). Defensive — a typo in caller code
    must NOT grant access."""
    for r in (UserRole.student, UserRole.admin, UserRole.super_admin):
        assert _user(r).has_permission("nonexistent_permission_xyz") is False


def test_has_permission_roster_view_includes_college():
    """Pin specifically that college role has roster_view_all — they
    review their college's payment roster. Removing this breaks the
    college reviewer workflow."""
    assert _user(UserRole.college).has_permission("roster_view_all") is True
    assert _user(UserRole.professor).has_permission("roster_view_all") is False

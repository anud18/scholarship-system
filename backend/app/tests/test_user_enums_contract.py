"""
Tests for the 3 user-related enums in `app.models.user` and the
EmployeeStatus.display_name property.

These enums are special per CLAUDE.md §4:
- UserRole, UserType: standard lowercase English values
- EmployeeStatus: **Chinese-string values** (在職/退休/在學/畢業) — the
  ONLY enum in the system with non-ASCII values. CLAUDE.md §4 explicitly
  documents this exception.

Bugs cause:
- UserRole value rename → role-based access control queries return
  empty results
- UserType value rename → portal SSO can't match user type to internal
  role mapping
- EmployeeStatus value Anglicization (turning '在職' to 'active') → DB
  filter '在職' returns nothing; admin dashboards show empty status

3 enums + 1 property (8 cases). Pure, no DB.
"""

from app.models.user import EmployeeStatus, UserRole, UserType

# ─── UserRole ────────────────────────────────────────────────────────


def test_user_role_values():
    """Pin: 5 user role values matching CLAUDE.md §4. RBAC depends on
    these exact strings."""
    assert UserRole.student.value == "student"
    assert UserRole.professor.value == "professor"
    assert UserRole.college.value == "college"
    assert UserRole.admin.value == "admin"
    assert UserRole.super_admin.value == "super_admin"
    assert len(list(UserRole)) == 5


def test_user_role_super_admin_uses_underscore_not_dash():
    """Pin: 'super_admin' uses underscore (not 'super-admin').
    Defensive against a naming-convention refactor — JWT claims +
    middleware filters depend on this exact spelling."""
    assert UserRole.super_admin.value == "super_admin"
    assert "-" not in UserRole.super_admin.value


# ─── UserType ────────────────────────────────────────────────────────


def test_user_type_values():
    """Pin: portal SSO maps users into one of these 2 types. CLAUDE.md
    §4 documents the exact values."""
    assert UserType.student.value == "student"
    assert UserType.employee.value == "employee"
    assert len(list(UserType)) == 2


# ─── EmployeeStatus — Chinese values (CLAUDE.md §4 exception) ────────


def test_employee_status_chinese_values():
    """Pin: EmployeeStatus is the ONLY enum with non-ASCII (Chinese)
    values per CLAUDE.md §4 explicit exception. The Chinese strings
    come from the upstream NYCU portal API directly.

    A regression that Anglicizes these (e.g., 'active', 'retired')
    would break:
    - DB filter queries that pass the Chinese string literally
    - Admin dashboard display logic that compares status to '在學'
    - Portal SSO mapping when populating User.status on login"""
    assert EmployeeStatus.active.value == "在職"
    assert EmployeeStatus.retired.value == "退休"
    assert EmployeeStatus.student.value == "在學"
    assert EmployeeStatus.graduated.value == "畢業"
    assert len(list(EmployeeStatus)) == 4


def test_employee_status_member_names_are_english():
    """Pin: Python identifiers (the names you write code with) ARE
    English. Only the .value strings are Chinese. A regression that
    renames `EmployeeStatus.active` to `EmployeeStatus.在職` would break
    every import statement."""
    assert EmployeeStatus.active.name == "active"
    assert EmployeeStatus.retired.name == "retired"
    assert EmployeeStatus.student.name == "student"
    assert EmployeeStatus.graduated.name == "graduated"


# ─── EmployeeStatus.display_name property ────────────────────────────


def test_employee_status_display_name_returns_chinese_value():
    """Pin: display_name returns the Chinese value directly (no
    translation layer). This is the string the admin dashboard renders."""
    assert EmployeeStatus.active.display_name == "在職"
    assert EmployeeStatus.retired.display_name == "退休"
    assert EmployeeStatus.student.display_name == "在學"
    assert EmployeeStatus.graduated.display_name == "畢業"


def test_employee_status_display_name_equals_value():
    """Pin: display_name === value for all members. Defensive
    invariant — a regression that introduces a separate display
    mapping would surface here."""
    for member in EmployeeStatus:
        assert member.display_name == member.value


# ─── Cross-enum sanity: distinct enum-spaces ─────────────────────────


def test_user_role_and_user_type_share_no_values_except_student():
    """Pin: UserRole and UserType both have 'student' as a value, by
    design (a student-role user is also a student-type user). All
    other UserRole values must NOT collide with UserType values —
    otherwise the auth middleware could conflate role/type."""
    role_values = {r.value for r in UserRole}
    type_values = {t.value for t in UserType}
    overlap = role_values & type_values
    assert overlap == {"student"}, f"Unexpected overlap between UserRole and UserType: {overlap}"

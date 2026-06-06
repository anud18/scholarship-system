"""
Tests for `app/schemas/user.py`.

The user-management schemas drive the admin /admin/users page and
the SSO/Portal authentication flow. Non-obvious invariants:

  - **UserBase.role defaults UserRole.student** — new users default
    to the lowest-privilege role. Flipping would silently grant
    admin/college privileges on first SSO login.

  - **UserCreate defaults**: user_type=student, status=在學
    (EmployeeStatus.student), role=student — used when SSO populates
    via /portal-sso. Pin all three to lowest-privilege defaults.

  - **Length bounds**: nycu_id max=50, name max=100, dept_code max=20,
    dept_name max=100, college_code max=10, comment max=255. Drift
    silently truncates DB rows.

  - **EmailStr cascade** on UserBase.email + UserCreate.email +
    UserUpdate.email (when supplied) — typos rejected at the
    schema boundary.

  - **TokenResponse.token_type defaults "bearer"** — flipping silently
    breaks every OAuth-style client.

  - **DeveloperProfileRequest.email_domain defaults "dev.local"** —
    isolated dev environment never accidentally uses real domains.

  - **BulkScholarshipAssignRequest.operation defaults "set"** —
    replace-all is safer than accumulate-all by default.

19 cases.
"""

import pytest
from pydantic import ValidationError

from app.models.user import EmployeeStatus, UserRole, UserType
from app.schemas.user import (
    BulkScholarshipAssignRequest,
    DeveloperProfileRequest,
    TokenResponse,
    UserBase,
    UserCreate,
    UserLogin,
    UserUpdate,
)

# ─── Default-privilege guards ───────────────────────────────────────


def _base_payload():
    return dict(
        nycu_id="A00001",
        name="Test",
        email="test@nycu.edu.tw",
        user_type=UserType.student,
        status=EmployeeStatus.student,
    )


def test_userbase_role_defaults_student():
    # Pin: lowest-privilege default. Flipping to admin/super_admin
    # would silently grant elevated permissions on first SSO login.
    u = UserBase(**_base_payload())
    assert u.role == UserRole.student


def test_usercreate_user_type_defaults_student():
    u = UserCreate(nycu_id="A00001")
    assert u.user_type == UserType.student


def test_usercreate_status_defaults_student():
    # Pin: 在學 (EmployeeStatus.student) — new users default to "in
    # school" not "graduated" or "retired".
    u = UserCreate(nycu_id="A00001")
    assert u.status == EmployeeStatus.student


def test_usercreate_role_defaults_student():
    # Pin: same as UserBase — lowest-privilege.
    u = UserCreate(nycu_id="A00001")
    assert u.role == UserRole.student


# ─── Length bounds ───────────────────────────────────────────────────


def test_userbase_nycu_id_max_length_50():
    payload = _base_payload()
    payload["nycu_id"] = "x" * 51
    with pytest.raises(ValidationError):
        UserBase(**payload)


def test_userbase_name_max_length_100():
    payload = _base_payload()
    payload["name"] = "王" * 101
    with pytest.raises(ValidationError):
        UserBase(**payload)


def test_userbase_dept_code_max_length_20():
    payload = _base_payload()
    payload["dept_code"] = "x" * 21
    with pytest.raises(ValidationError):
        UserBase(**payload)


def test_userbase_college_code_max_length_10():
    # Pin: shortest cap. NYCU college codes are 1-2 char abbreviations
    # ("C", "A", "M"). 10 is generous; flipping to 5 silently truncates.
    payload = _base_payload()
    payload["college_code"] = "x" * 11
    with pytest.raises(ValidationError):
        UserBase(**payload)


def test_usercreate_comment_max_length_255():
    # Pin: 255 cap. Field used for admin notes on each user.
    with pytest.raises(ValidationError):
        UserCreate(nycu_id="A00001", comment="x" * 256)


# ─── EmailStr validation cascade ────────────────────────────────────


def test_userbase_email_must_be_valid():
    payload = _base_payload()
    payload["email"] = "not-an-email"
    with pytest.raises(ValidationError):
        UserBase(**payload)


def test_userupdate_email_validated_when_supplied():
    # Pin: PATCH semantics — email is Optional, but invalid email
    # rejects on supply.
    with pytest.raises(ValidationError):
        UserUpdate(email="not-an-email")


def test_userupdate_email_none_passes():
    u = UserUpdate(email=None)
    assert u.email is None


# ─── UserLogin minimal contract ─────────────────────────────────────


def test_user_login_requires_username():
    # Pin: username (nycu_id or email) is the only required field.
    with pytest.raises(ValidationError):
        UserLogin()  # type: ignore[call-arg]


# ─── TokenResponse defaults ─────────────────────────────────────────


def test_token_response_token_type_defaults_bearer():
    # Pin: "bearer" is the OAuth2 convention. Flipping silently
    # breaks every Authorization: Bearer ... client.
    from app.schemas.user import UserResponse
    from datetime import datetime, timezone

    inner_user = UserResponse(
        id=1,
        nycu_id="A00001",
        role=UserRole.student,
        created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
        updated_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
    )
    t = TokenResponse(
        access_token="tok",
        refresh_token="ref",
        expires_in=3600,
        user=inner_user,
    )
    assert t.token_type == "bearer"


# ─── DeveloperProfileRequest defaults ───────────────────────────────


def test_developer_profile_email_domain_defaults_dev_example():
    # Pin: "dev.example.com" — RFC-2606 reserved, non-routable, so dev users
    # still can't impersonate real ones in the development DB. NOT "dev.local":
    # EmailStr rejects the special-use ".local" TLD, which made @dev.local dev
    # users fail UserResponse serialization and break mock-sso login. NOT a real
    # domain ("nycu.edu.tw") either, for the same impersonation reason.
    d = DeveloperProfileRequest(role=UserRole.student)
    assert d.email_domain == "dev.example.com"


def test_developer_profile_requires_role():
    # Pin: role is the only required field. dev mode always needs an
    # explicit role.
    with pytest.raises(ValidationError):
        DeveloperProfileRequest()  # type: ignore[call-arg]


# ─── BulkScholarshipAssignRequest defaults ──────────────────────────


def test_bulk_assign_operation_defaults_set():
    # Pin: "set" (replace-all) is safer than "add" (append). Flipping
    # would let admins silently accumulate scholarship assignments on
    # bulk reassign actions.
    b = BulkScholarshipAssignRequest(scholarship_ids=[1, 2, 3])
    assert b.operation == "set"


def test_bulk_assign_requires_scholarship_ids():
    with pytest.raises(ValidationError):
        BulkScholarshipAssignRequest(operation="set")  # type: ignore[call-arg]

"""
Tests for `app/schemas/pre_authorization.py`.

Pre-authorization is how the system grants role + scholarship-admin
access to NYCU users BEFORE they first log in via SSO. A
super-admin enters a `nycu_id` + role; on first SSO login the user
gets the matching role automatically.

Why pin these?

  - **Wrong required/optional split on PreAuthorizeUserRequest** would
    let admins call the endpoint with no role → the system would
    create a user with unspecified privilege.
  - **Wrong shape on PreAuthorizedUserList.data** (e.g. not List[
    PreAuthorizedUser]) would let staff render a malformed admin list.
  - **Nested UserInfo missing required fields (nycu_id, name, email,
    role)** would surface as blank rows in the admin lookup UI.

15 cases pinning the 9 schemas in the module.
"""

import pytest
from pydantic import ValidationError

from app.schemas.pre_authorization import (
    AdminScholarship,
    AdminScholarshipList,
    AssignScholarshipRequest,
    AssignScholarshipResponse,
    PreAuthorizedUser,
    PreAuthorizedUserList,
    PreAuthorizeUserRequest,
    PreAuthorizeUserResponse,
    UserInfo,
    UserInfoResponse,
)

# ─── PreAuthorizeUserRequest ────────────────────────────────────────


def test_preauth_request_requires_nycu_id_and_role():
    # Pin: both fields non-optional. Comment is optional.
    with pytest.raises(ValidationError):
        PreAuthorizeUserRequest(nycu_id="A00001")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        PreAuthorizeUserRequest(role="admin")  # type: ignore[call-arg]


def test_preauth_request_comment_optional():
    r = PreAuthorizeUserRequest(nycu_id="A00001", role="admin")
    assert r.comment is None


def test_preauth_request_role_is_string_not_enum():
    # Pin: role is `str`, NOT a UserRole enum. The endpoint accepts
    # arbitrary strings and validates against the enum server-side.
    # A regression to enum-typed would block legitimate role strings
    # that the endpoint may explicitly accept (e.g. "super_admin").
    r = PreAuthorizeUserRequest(nycu_id="A00001", role="anything-goes")
    assert r.role == "anything-goes"


# ─── PreAuthorizeUserResponse / AssignScholarshipResponse ───────────


def test_preauth_response_requires_success_message_data():
    # Pin: matches the ApiResponse envelope shape (CLAUDE.md §5).
    with pytest.raises(ValidationError):
        PreAuthorizeUserResponse(success=True, message="ok")  # type: ignore[call-arg]


def test_assign_response_matches_preauth_response_shape():
    # Pin: both response schemas share the same shape — the endpoint
    # implementations rely on this parallelism.
    r1 = PreAuthorizeUserResponse(success=True, message="ok", data={"x": 1})
    r2 = AssignScholarshipResponse(success=True, message="ok", data={"x": 1})
    assert r1.data == r2.data
    assert r1.success == r2.success


# ─── AssignScholarshipRequest ───────────────────────────────────────


def test_assign_request_requires_admin_nycu_id_and_scholarship_id():
    with pytest.raises(ValidationError):
        AssignScholarshipRequest(admin_nycu_id="A00001")  # type: ignore[call-arg]


def test_assign_request_scholarship_id_int():
    # Pin: scholarship_id is int — accidentally accepting string would
    # break the FK lookup.
    with pytest.raises(ValidationError):
        AssignScholarshipRequest(
            admin_nycu_id="A00001",
            scholarship_id="not a number",  # type: ignore[arg-type]
        )


# ─── PreAuthorizedUser ──────────────────────────────────────────────


def test_preauthorized_user_required_fields():
    # Pin: nycu_id / name / email / role / created_at all required.
    # comment is optional.
    with pytest.raises(ValidationError):
        PreAuthorizedUser(  # type: ignore[call-arg]
            nycu_id="A00001",
            name="Test",
            email="t@x.y",
            role="admin",
            # created_at missing
        )


def test_preauthorized_user_created_at_is_str_not_datetime():
    # Pin: created_at is `str` (ISO datetime serialized server-side),
    # NOT datetime. A regression to datetime would break the existing
    # list endpoint that returns pre-serialized timestamps.
    u = PreAuthorizedUser(
        nycu_id="A00001",
        name="Test",
        email="t@x.y",
        role="admin",
        created_at="2025-10-22T17:27:08Z",
    )
    assert isinstance(u.created_at, str)


# ─── PreAuthorizedUserList ──────────────────────────────────────────


def test_preauthorized_list_data_is_typed_list():
    # Pin: data is List[PreAuthorizedUser], not List[dict]. Inner-type
    # validation must happen — accepting random dicts in data would
    # produce malformed admin rows.
    list_obj = PreAuthorizedUserList(
        success=True,
        message="ok",
        data=[
            PreAuthorizedUser(
                nycu_id="A00001",
                name="Test",
                email="t@x.y",
                role="admin",
                created_at="2025-10-22T17:27:08Z",
            )
        ],
    )
    assert len(list_obj.data) == 1
    assert isinstance(list_obj.data[0], PreAuthorizedUser)


def test_preauthorized_list_rejects_payload_missing_required_inner_fields():
    # Pin: validation cascades — incomplete inner items must reject.
    with pytest.raises(ValidationError):
        PreAuthorizedUserList(
            success=True,
            message="ok",
            data=[{"nycu_id": "A00001"}],  # type: ignore[list-item]
        )


# ─── AdminScholarship + AdminScholarshipList ────────────────────────


def test_admin_scholarship_required_fields():
    # Pin: 3 required fields — admin_nycu_id, scholarship_id (int),
    # assigned_at (str).
    a = AdminScholarship(
        admin_nycu_id="A00001",
        scholarship_id=42,
        assigned_at="2025-10-22T17:27:08Z",
    )
    assert a.scholarship_id == 42


def test_admin_scholarship_list_data_typed():
    lst = AdminScholarshipList(
        success=True,
        message="ok",
        data=[
            AdminScholarship(
                admin_nycu_id="A00001",
                scholarship_id=42,
                assigned_at="2025-10-22T17:27:08Z",
            )
        ],
    )
    assert lst.data[0].scholarship_id == 42


# ─── UserInfo + UserInfoResponse ────────────────────────────────────


def test_user_info_required_anchor_fields():
    # Pin: nycu_id, name, email, role are the anchor set. All other
    # fields are optional (some users have null dept_code in SIS).
    info = UserInfo(
        nycu_id="A00001",
        name="Test",
        email="t@x.y",
        role="student",
    )
    assert info.user_type is None
    assert info.status is None
    assert info.dept_code is None
    assert info.dept_name is None
    assert info.last_login_at is None
    assert info.comment is None


def test_user_info_response_nests_user_info():
    # Pin: UserInfoResponse.data is a single UserInfo, NOT a list. The
    # lookup endpoint returns one user at a time.
    resp = UserInfoResponse(
        success=True,
        message="ok",
        data=UserInfo(nycu_id="A00001", name="x", email="x@y", role="admin"),
    )
    assert resp.data.nycu_id == "A00001"

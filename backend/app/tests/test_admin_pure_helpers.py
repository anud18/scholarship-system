"""
Tests for pure helpers in `app.api.v1.endpoints.admin`.

Two helpers tested here:

  - **convert_student_to_dict(user)** (admin/students.py): turns
    a User ORM model with student role into the API response
    dict. Critical because the admin student-list page reads
    every field directly — a regression that drops a field or
    changes its shape breaks the admin UI table.

  - **apply_scholarship_filter(stmt, column, allowed_ids)**
    (admin/_helpers.py): permission gate that scopes any
    SQLAlchemy SELECT to the scholarship IDs an admin can see.
    SECURITY: empty allowed_ids list = super-admin (sees all);
    non-empty list = scope filter applied. Pin both branches so
    a regression doesn't accidentally either (a) silently expose
    cross-college data when it should be scoped, or (b) hide all
    data from super_admin when filter falsely fires.

14 cases.
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import column, select

from app.api.v1.endpoints.admin._helpers import apply_scholarship_filter
from app.api.v1.endpoints.admin.students import convert_student_to_dict

# ─── convert_student_to_dict ─────────────────────────────────────────


def _user(**overrides):
    """Build a User-like SimpleNamespace with .value enum accessors."""
    base = {
        "id": 1,
        "nycu_id": "310460031",
        "name": "王小明",
        "email": "test@nycu.edu.tw",
        "user_type": SimpleNamespace(value="student"),
        "status": SimpleNamespace(value="在學"),
        "dept_code": "4460",
        "dept_name": "教育博",
        "college_code": "A",
        "role": SimpleNamespace(value="student"),
        "comment": None,
        "created_at": datetime(2026, 1, 1, 10, 0, 0),
        "updated_at": datetime(2026, 1, 2, 10, 0, 0),
        "last_login_at": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_convert_returns_all_documented_keys():
    # Pin: 15 keys in the response dict. If a column gets added
    # to User the admin endpoint needs to add it here AND update
    # this test — the explicit count catches silent omissions.
    out = convert_student_to_dict(_user())
    expected_keys = {
        "id",
        "nycu_id",
        "name",
        "email",
        "user_type",
        "status",
        "dept_code",
        "dept_name",
        "college_code",
        "role",
        "comment",
        "applied_scholarships",
        "created_at",
        "updated_at",
        "last_login_at",
    }
    assert set(out.keys()) == expected_keys


def test_convert_applied_scholarships_defaults_to_empty_list():
    # Pin: omitted applied_scholarships → [] (not None). The admin
    # student list frontend maps over this field unconditionally.
    out = convert_student_to_dict(_user())
    assert out["applied_scholarships"] == []


def test_convert_applied_scholarships_passes_through():
    # Pin: provided aggregation list is embedded verbatim.
    applied = [
        {
            "scholarship_configuration_id": 1,
            "config_code": "phd_114",
            "name": "博士生獎學金 114學年",
            "application_count": 2,
        }
    ]
    out = convert_student_to_dict(_user(), applied_scholarships=applied)
    assert out["applied_scholarships"] == applied


def test_convert_enums_emit_value_not_name():
    # Pin: enum fields emit .value (lowercase wire shape per
    # CLAUDE.md §4). Regression to .name would break frontend
    # enum mapping on the student list page.
    out = convert_student_to_dict(_user())
    assert out["user_type"] == "student"
    assert out["status"] == "在學"  # EmployeeStatus uses Chinese values
    assert out["role"] == "student"


def test_convert_none_enums_emit_none():
    # Pin: missing enum value → None (not empty string, not
    # crash). Defensive against partially-populated User rows.
    out = convert_student_to_dict(_user(user_type=None, status=None))
    assert out["user_type"] is None
    assert out["status"] is None


def test_convert_datetime_emits_isoformat():
    # Pin: datetime → ISO 8601 string. Frontend Date constructor
    # depends on this exact format.
    out = convert_student_to_dict(_user())
    assert out["created_at"] == "2026-01-01T10:00:00"
    assert out["updated_at"] == "2026-01-02T10:00:00"


def test_convert_none_datetime_emits_none():
    # Pin: null timestamps stay null (not "None" string).
    out = convert_student_to_dict(_user())
    assert out["last_login_at"] is None


def test_convert_role_string_fallback():
    # Pin: if role doesn't have .value attribute (legacy / mocks),
    # falls back to str(role). The hasattr check pins this branch.
    out = convert_student_to_dict(_user(role="legacy_string_role"))
    assert out["role"] == "legacy_string_role"


def test_convert_passes_string_fields_through():
    # Pin: nycu_id / name / email / dept_code / dept_name / comment
    # pass through without transformation.
    out = convert_student_to_dict(_user(comment="some admin note", nycu_id="abc-123"))
    assert out["comment"] == "some admin note"
    assert out["nycu_id"] == "abc-123"
    assert out["name"] == "王小明"


# ─── apply_scholarship_filter ────────────────────────────────────────


def test_filter_empty_list_returns_stmt_unchanged():
    # Pin: empty allowed_ids = super_admin → NO filter applied.
    # The statement passes through. CRITICAL — super_admin must
    # see all data; accidentally applying an empty IN() clause
    # would hide everything.
    stmt = select(column("id"))
    col = column("scholarship_type_id")

    out = apply_scholarship_filter(stmt, col, [])

    # Statement is returned as-is (no .where call)
    assert out is stmt


def test_filter_non_empty_list_adds_where_clause():
    # Pin: non-empty allowed_ids → .where(col.in_(ids)) applied.
    # SECURITY: non-super-admin must be scoped to their allowed
    # scholarships.
    stmt = select(column("id"))
    col = column("scholarship_type_id")

    out = apply_scholarship_filter(stmt, col, [1, 2, 3])

    # Different statement object (modified by .where)
    assert out is not stmt
    # SQL contains the IN clause
    sql_str = str(out.compile(compile_kwargs={"literal_binds": True}))
    assert "scholarship_type_id IN" in sql_str


def test_filter_single_id_still_applies():
    # Pin: even a single allowed ID applies the filter (truthy
    # non-empty list).
    stmt = select(column("id"))
    col = column("scholarship_type_id")

    out = apply_scholarship_filter(stmt, col, [42])

    assert out is not stmt
    sql_str = str(out.compile(compile_kwargs={"literal_binds": True}))
    assert "42" in sql_str


def test_filter_empty_list_is_falsy_check():
    # Pin: the function uses truthy check (`if allowed_scholarship_ids`)
    # not `if allowed_scholarship_ids is None`. So an explicit
    # empty list takes the no-filter branch — same as super_admin.
    stmt = select(column("id"))
    col = column("scholarship_type_id")

    assert apply_scholarship_filter(stmt, col, []) is stmt

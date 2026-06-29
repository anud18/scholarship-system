"""Unit tests for the pure quota-matrix validator (sync — runs in the unit suite)."""

from app.utils.quota_validation import MAX_CELL_QUOTA, validate_quota_matrix

ALLOWED_SUB = ["nstc", "moe_1w"]
ALLOWED_COL = ["C", "E"]


def test_valid_matrix_returns_no_errors():
    assert validate_quota_matrix({"nstc": {"C": 5, "E": 4}}, ALLOWED_SUB, ALLOWED_COL) == []


def test_unknown_sub_type_is_error():
    errors = validate_quota_matrix({"ghost": {"C": 1}}, ALLOWED_SUB, ALLOWED_COL)
    assert any("ghost" in e for e in errors)


def test_unknown_college_is_error():
    errors = validate_quota_matrix({"nstc": {"ZZ": 1}}, ALLOWED_SUB, ALLOWED_COL)
    assert any("ZZ" in e for e in errors)


def test_negative_value_is_error():
    assert validate_quota_matrix({"nstc": {"C": -1}}, ALLOWED_SUB, ALLOWED_COL)


def test_value_over_max_is_error():
    assert validate_quota_matrix({"nstc": {"C": MAX_CELL_QUOTA + 1}}, ALLOWED_SUB, ALLOWED_COL)


def test_boolean_is_not_a_valid_int():
    # bool is a subclass of int in Python; it must be rejected.
    assert validate_quota_matrix({"nstc": {"C": True}}, ALLOWED_SUB, ALLOWED_COL)


def test_non_dict_quotas_is_error():
    assert validate_quota_matrix([], ALLOWED_SUB, ALLOWED_COL)
    assert validate_quota_matrix({"nstc": 5}, ALLOWED_SUB, ALLOWED_COL)

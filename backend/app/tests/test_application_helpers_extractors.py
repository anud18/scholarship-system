"""
Tests for the data-extractor helpers in `app.utils.application_helpers`.

These helpers normalize student data lookups across three schema
generations (the same OR chain appears in `ApplicationEnricherService`
and several presentational components). If they drift, students see
"Unknown" in some surfaces but their real name in others — a confusing
inconsistency that erodes admin trust.

The snapshot variants (`get_snapshot_*`) read from `application.student_data`
which is duck-typed in tests as a SimpleNamespace; the `_from_data`
variants take the dict directly.

11 extractors covered (24 cases):
- `get_snapshot_*` (4 fns)        : guard on missing student_data
- `get_*_from_data` (7 fns)       : multi-alias OR chain
"""

from types import SimpleNamespace

import pytest

from app.utils.application_helpers import (
    get_academy_code_from_data,
    get_college_code_from_data,
    get_department_code_from_data,
    get_email_from_data,
    get_nycu_id_from_data,
    get_snapshot_college_code,
    get_snapshot_email,
    get_snapshot_nycu_id,
    get_snapshot_student_name,
    get_student_name_from_data,
    get_term_count_from_data,
)


def _app(student_data):
    """Duck-typed Application — just needs .student_data."""
    return SimpleNamespace(student_data=student_data)


# ─── get_snapshot_* (Application-wrapper variants) ───────────────────


def test_snapshot_student_name_returns_unknown_when_no_data():
    """Missing student_data ⇒ literal 'Unknown' (NOT None) — admin UI
    expects a string for the name column, never null."""
    assert get_snapshot_student_name(_app(None)) == "Unknown"
    assert get_snapshot_student_name(_app({})) == "Unknown"
    # Non-dict student_data (e.g. malformed migration data) ⇒ 'Unknown'.
    assert get_snapshot_student_name(_app("not-a-dict")) == "Unknown"


def test_snapshot_student_name_prefers_std_cname():
    """std_cname (Chinese name from SIS API) wins over name/student_name."""
    app = _app({"std_cname": "王小明", "name": "Other", "student_name": "Other2"})
    assert get_snapshot_student_name(app) == "王小明"


def test_snapshot_student_name_falls_through_aliases():
    """No std_cname ⇒ try name, then student_name."""
    assert get_snapshot_student_name(_app({"name": "Alice"})) == "Alice"
    assert get_snapshot_student_name(_app({"student_name": "Bob"})) == "Bob"


def test_snapshot_college_code_priorities():
    """std_academyno (SIS field) is the canonical one — pin precedence."""
    app = _app({"std_academyno": "A", "academy_code": "B", "college_code": "C"})
    assert get_snapshot_college_code(app) == "A"


def test_snapshot_college_code_none_when_missing():
    """No data / non-dict ⇒ None (vs 'Unknown' for name — name field is
    required in UI; college code is optional)."""
    assert get_snapshot_college_code(_app(None)) is None
    assert get_snapshot_college_code(_app({})) is None


def test_snapshot_nycu_id_priorities():
    """std_stdcode is canonical; fallback to nycu_id then student_id."""
    app = _app({"nycu_id": "S2", "student_id": "S3"})
    assert get_snapshot_nycu_id(app) == "S2"

    app = _app({"std_stdcode": "S1", "nycu_id": "S2"})
    assert get_snapshot_nycu_id(app) == "S1"


def test_snapshot_email_priorities():
    """com_email (SIS) wins over generic email."""
    app = _app({"com_email": "a@u.tw", "email": "b@u.tw"})
    assert get_snapshot_email(app) == "a@u.tw"

    assert get_snapshot_email(_app({"email": "b@u.tw"})) == "b@u.tw"
    assert get_snapshot_email(_app({})) is None


# ─── *_from_data (dict-input variants) ───────────────────────────────


def test_student_name_from_data_unknown_for_non_dict():
    """Same Unknown semantics as the snapshot variant."""
    assert get_student_name_from_data(None) == "Unknown"
    assert get_student_name_from_data({}) == "Unknown"
    assert get_student_name_from_data("not-a-dict") == "Unknown"


def test_student_name_from_data_priorities():
    """std_cname > name > student_name."""
    assert get_student_name_from_data({"std_cname": "王", "name": "X"}) == "王"
    assert get_student_name_from_data({"name": "Alice"}) == "Alice"
    assert get_student_name_from_data({"student_name": "Bob"}) == "Bob"


def test_college_code_from_data_four_aliases():
    """std_academyno > academy_code > college_code > std_college."""
    assert get_college_code_from_data({"std_academyno": "A"}) == "A"
    assert get_college_code_from_data({"academy_code": "B"}) == "B"
    assert get_college_code_from_data({"college_code": "C"}) == "C"
    assert get_college_code_from_data({"std_college": "D"}) == "D"


def test_nycu_id_from_data_three_aliases():
    """std_stdcode > nycu_id > student_id."""
    assert get_nycu_id_from_data({"std_stdcode": "S1"}) == "S1"
    assert get_nycu_id_from_data({"nycu_id": "S2"}) == "S2"
    assert get_nycu_id_from_data({"student_id": "S3"}) == "S3"
    assert get_nycu_id_from_data({}) is None


def test_email_from_data_two_aliases():
    """com_email > email."""
    assert get_email_from_data({"com_email": "a@u.tw"}) == "a@u.tw"
    assert get_email_from_data({"email": "b@u.tw"}) == "b@u.tw"
    assert get_email_from_data({}) is None


def test_department_code_from_data_term_then_std():
    """trm_depno (term data) preferred over std_depno (basic data) —
    term data is fresher (refreshed every term, vs std_* which is the
    initial enrollment record)."""
    assert get_department_code_from_data({"trm_depno": "4460", "std_depno": "9999"}) == "4460"
    assert get_department_code_from_data({"std_depno": "9999"}) == "9999"
    assert get_department_code_from_data({}) is None


def test_academy_code_from_data_term_then_std():
    """Same precedence: trm_academyno > std_academyno."""
    assert get_academy_code_from_data({"trm_academyno": "A", "std_academyno": "B"}) == "A"
    assert get_academy_code_from_data({"std_academyno": "B"}) == "B"
    assert get_academy_code_from_data({}) is None


def test_term_count_priority_chain():
    """trm_termcount > std_termcount > term_count (legacy).
    Order matters — using the wrong field shows the wrong year on
    the export ('114年' vs '113年' is one term off)."""
    assert get_term_count_from_data({"trm_termcount": 5, "std_termcount": 4, "term_count": 3}) == 5
    assert get_term_count_from_data({"std_termcount": 4, "term_count": 3}) == 4
    assert get_term_count_from_data({"term_count": 3}) == 3
    assert get_term_count_from_data({}) is None


def test_extractors_return_none_for_non_dict_input():
    """All `_from_data` extractors (except name) return None for
    non-dict input — they don't crash with AttributeError."""
    for fn in (
        get_college_code_from_data,
        get_nycu_id_from_data,
        get_email_from_data,
        get_department_code_from_data,
        get_academy_code_from_data,
        get_term_count_from_data,
    ):
        assert fn(None) is None
        assert fn("not-a-dict") is None
        assert fn(42) is None

"""
Tests for `RosterService._get_student_field_value` — the field-lookup
priority chain used by every scholarship eligibility rule.

Lookup order (the priority MUST be preserved — pinning that here):
  1. `fresh_api_data` (current SIS-API pull) — only for `std_*` / `trm_*`
     fields. Most accurate for active-semester checks.
  2. `application.student_data` (snapshot at submission) — also only for
     `std_*` / `trm_*` fields.
  3. `field_mapping` dict — friendly aliases (gpa, ranking, nationality,
     department, grade, student_type, term_count, previous_scholarship).
     These pull from the student/application objects directly.
  4. `getattr(student, field_name)` — direct attribute fallback.
  5. `getattr(application, field_name)` — final attribute fallback.
  6. None + warning log for unknown fields.

A regression in this method silently disqualifies students (returns
None → eligibility operator returns False) or pulls a stale value from
the snapshot when fresh data was available. We test it directly with
a `MagicMock` session — no DB access happens inside `_get_student_field_value`.

Wave 6a157.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.roster_service import RosterService


@pytest.fixture
def lookup():
    """Return the bound `_get_student_field_value` method on a service
    instance with a mocked DB session (the method never touches `self.db`)."""
    return RosterService(db=MagicMock())._get_student_field_value


@pytest.fixture
def student():
    """Minimal stub student object with a few attributes for the
    field_mapping dict + getattr fallback paths."""
    return SimpleNamespace(
        gpa=3.85,
        ranking=12,
        nationality="TW",
        department="CSIE",
        grade=2,
        student_type="undergraduate",
        # An attribute NOT in field_mapping — exercises the
        # `hasattr(student, field_name)` fallback.
        extra_attr="from_student",
    )


@pytest.fixture
def application():
    """Application stub with both student_data + submission-level fields."""
    return SimpleNamespace(
        student_data={
            "std_stdcode": "310460031",
            "std_cname": "王小明",
            "trm_year": 114,
            "trm_ascore_gpa": 3.7,  # NOTE: differs from student.gpa on purpose
        },
        # Attributes for the field_mapping dict
        term_count=4,
        previous_scholarship="moe_1w",
        # An attribute on application but not student — exercises the
        # `hasattr(application, field_name)` fallback.
        only_on_application="from_application",
    )


# ---------------------------------------------------------------------------
# 1. fresh_api_data priority — wins over student_data for std_/trm_ fields
# ---------------------------------------------------------------------------


def test_fresh_api_data_wins_over_snapshot(lookup, student, application):
    """Pin: fresh API data (current SIS pull) takes precedence over the
    snapshot at application time. If a student's GPA went up after
    submission, the eligibility check should use the new value.
    """
    fresh = {"trm_ascore_gpa": 3.95}
    assert lookup("trm_ascore_gpa", student, application, fresh_api_data=fresh) == 3.95


def test_fresh_api_data_only_for_std_or_trm_prefix(lookup, student, application):
    """Pin: fresh_api_data is ignored for non-`std_`/`trm_` fields. A
    refactor that broadens the fresh-data check would silently start
    overriding `gpa` (the friendly alias) with an unrelated SIS field.
    """
    fresh = {"gpa": 99.0}  # nonsense override, but field doesn't have std/trm prefix
    assert lookup("gpa", student, application, fresh_api_data=fresh) == 3.85


def test_fresh_api_data_none_value_falls_through_to_snapshot(lookup, student, application):
    """Pin: if fresh API returns None for a field, fall through to the
    snapshot. The check is `if value is not None`, NOT truthiness — so
    explicit None means "absent", but 0 / "" / False should still win.
    """
    fresh = {"trm_ascore_gpa": None}
    assert lookup("trm_ascore_gpa", student, application, fresh_api_data=fresh) == 3.7


def test_fresh_api_data_falsy_zero_still_wins(lookup, student, application):
    """Pin: fresh value 0 (e.g. zero suspended-terms) is NOT treated as
    absent. Pin so a refactor to `if value:` doesn't silently fall through
    on legitimate zero values.
    """
    fresh = {"trm_year": 0}
    assert lookup("trm_year", student, application, fresh_api_data=fresh) == 0


# ---------------------------------------------------------------------------
# 2. application.student_data snapshot fallback
# ---------------------------------------------------------------------------


def test_snapshot_used_when_fresh_missing(lookup, student, application):
    """Pin: no fresh_api_data → fall back to snapshot."""
    assert lookup("std_cname", student, application) == "王小明"


def test_snapshot_used_when_fresh_lacks_field(lookup, student, application):
    """Pin: fresh dict missing the field → snapshot wins."""
    fresh = {"some_other_field": "ignored"}
    assert lookup("std_stdcode", student, application, fresh_api_data=fresh) == "310460031"


def test_snapshot_only_for_std_or_trm_prefix(lookup, student, application):
    """Pin: snapshot is also gated by the std_/trm_ prefix. A non-prefixed
    field gets none of the JSON-lookup behavior even if it happens to
    be keyed in `student_data`.
    """
    # Insert a fake non-prefixed key to prove the prefix check actually filters
    application.student_data["custom_field"] = "should_not_be_returned"
    # falls through to field_mapping (not in there), then getattr(student) — None
    result = lookup("custom_field", student, application)
    assert result != "should_not_be_returned"


# ---------------------------------------------------------------------------
# 3. field_mapping dict (8 friendly aliases)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field_name,expected_attr,expected_value",
    [
        ("gpa", "gpa", 3.85),
        ("ranking", "ranking", 12),
        ("nationality", "nationality", "TW"),
        ("department", "department", "CSIE"),
        ("grade", "grade", 2),
        ("student_type", "student_type", "undergraduate"),
    ],
)
def test_field_mapping_student_attrs(lookup, student, application, field_name, expected_attr, expected_value):
    """Pin: 6 of the 8 friendly aliases pull from `student.<attr>`. Pin
    so a refactor that drops one of these names breaks eligibility checks
    using the alias instead of the full SIS field name.
    """
    assert lookup(field_name, student, application) == expected_value


def test_field_mapping_term_count_from_application(lookup, student, application):
    """Pin: `term_count` is one of two aliases that pull from the
    application object rather than the student object."""
    assert lookup("term_count", student, application) == 4


def test_field_mapping_previous_scholarship_from_application(lookup, student, application):
    """Pin: `previous_scholarship` also pulls from application."""
    assert lookup("previous_scholarship", student, application) == "moe_1w"


# ---------------------------------------------------------------------------
# 4. getattr fallbacks (student → application)
# ---------------------------------------------------------------------------


def test_getattr_student_fallback(lookup, student, application):
    """Pin: an unknown field name falls through to `getattr(student, ...)`
    if the student object has that attribute. Useful for ad-hoc SIS fields
    that get added to the Student model without explicit field_mapping
    entries.
    """
    assert lookup("extra_attr", student, application) == "from_student"


def test_getattr_application_fallback(lookup, student, application):
    """Pin: student lookup fails → fall through to `getattr(application, ...)`."""
    assert lookup("only_on_application", student, application) == "from_application"


# ---------------------------------------------------------------------------
# 5. Unknown field → None (never raises)
# ---------------------------------------------------------------------------


def test_unknown_field_returns_none(lookup, student, application):
    """Pin: a completely unknown field returns None (with a warning log),
    never raises. Pin so a typo in a rule config doesn't crash the whole
    monthly roster generation."""
    assert lookup("totally_unknown_field", student, application) is None


def test_unknown_field_logs_warning(lookup, student, application, caplog):
    """Pin: the warning log fires so admin can spot the typo in their
    rule config."""
    import logging

    with caplog.at_level(logging.WARNING):
        lookup("totally_unknown_field", student, application)
    assert any("Unknown field name" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# 6. Edge cases
# ---------------------------------------------------------------------------


def test_application_with_no_student_data_falls_through(lookup, student):
    """Pin: `application.student_data` may be None for legacy applications.
    Pin so the snapshot-lookup `if application.student_data and ...` guard
    doesn't crash with AttributeError on None.
    """
    app = SimpleNamespace(
        student_data=None,
        term_count=99,
        previous_scholarship=None,
    )
    # std_/trm_ field with no fresh data and no snapshot → field_mapping
    # doesn't have std_stdcode → getattr(student) doesn't have it → getattr(app)
    # doesn't have it → None
    assert lookup("std_stdcode", student, app) is None
    # But term_count still resolves through the field_mapping → application path
    assert lookup("term_count", student, app) == 99


def test_fresh_api_data_none_argument_safe(lookup, student, application):
    """Pin: `fresh_api_data=None` (default) doesn't crash. Pin so the
    `if fresh_api_data and ...` guard stays — refactor to truthiness-only
    would still work, but a hypothetical refactor to `if fresh_api_data is
    not None` only (without `and`) would crash on the .get() below.
    """
    # Should work identically to omitting the kwarg
    assert lookup("std_cname", student, application, fresh_api_data=None) == "王小明"

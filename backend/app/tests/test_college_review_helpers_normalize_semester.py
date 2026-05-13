"""
Tests for `normalize_semester_value` in
`app.api.v1.endpoints.college_review._helpers`.

This normalizer canonicalizes the many forms a "semester" value can
arrive in (None / enum / 'Semester.FIRST' / 'YEARLY') to one of:
- None (yearly scholarship — no semester filter)
- 'first' / 'second' (lowercase enum value)

Bugs cause:
- 'yearly' not collapsing to None → queries filter on the literal
  string 'yearly' which doesn't exist in DB enum → empty results in
  the college dashboard
- Enum repr `'Semester.first'` not stripped → same as above
- Case-sensitive comparison → 'First' from URL query string doesn't
  match → wrong-period applications shown

12 cases. Pure, no DB.
"""

from app.api.v1.endpoints.college_review._helpers import normalize_semester_value
from app.models.enums import Semester

# ─── None / yearly / empty → None ────────────────────────────────────


def test_none_passes_through_as_none():
    """Pin: None → None. Sentinel for 'no semester filter' (yearly scholarship)."""
    assert normalize_semester_value(None) is None


def test_yearly_string_collapses_to_none():
    """Pin: 'yearly' → None. CRITICAL: yearly scholarships have no
    semester column value in the DB, so the filter must drop the
    parameter entirely. Otherwise queries find nothing."""
    assert normalize_semester_value("yearly") is None


def test_yearly_uppercase_collapses_to_none():
    """Pin: case-insensitive — 'YEARLY' from URL query string also
    treated as None."""
    assert normalize_semester_value("YEARLY") is None


def test_empty_string_collapses_to_none():
    """Pin: '' → None (defends against unset form fields)."""
    assert normalize_semester_value("") is None


def test_whitespace_only_collapses_to_none():
    """Pin: '   ' → None (after strip, becomes empty)."""
    assert normalize_semester_value("   ") is None


def test_string_none_literal_collapses_to_none():
    """Pin: the literal string 'None' (from accidental str(None))
    collapses correctly to actual None sentinel."""
    assert normalize_semester_value("None") is None
    assert normalize_semester_value("none") is None


# ─── Enum object → .value ────────────────────────────────────────────


def test_enum_first_returns_first_value():
    assert normalize_semester_value(Semester.first) == "first"


def test_enum_second_returns_second_value():
    assert normalize_semester_value(Semester.second) == "second"


def test_enum_yearly_collapses_to_none():
    """Pin: Semester.yearly is treated as a no-op filter (yearly
    scholarship). After .value extraction we'd get 'yearly', which
    matches the yearly→None branch."""
    assert normalize_semester_value(Semester.yearly) is None


# ─── 'Semester.X' enum repr stripping ────────────────────────────────


def test_enum_repr_prefix_stripped():
    """Pin: 'Semester.first' → 'first'. Some serializers (e.g., logging)
    emit the enum's str() form; the normalizer must accept this."""
    assert normalize_semester_value("Semester.first") == "first"


def test_enum_repr_with_uppercase_member_stripped():
    """Pin: 'Semester.FIRST' (some Python versions or older serialization)
    also normalized to 'first' (lowercase)."""
    assert normalize_semester_value("Semester.FIRST") == "first"


# ─── Case normalization for plain strings ────────────────────────────


def test_first_capitalized_lowered():
    """Pin: 'First' → 'first'. Defensive against URL params like
    `?semester=First` from a UI that title-cases display strings."""
    assert normalize_semester_value("First") == "first"


def test_second_uppercase_lowered():
    assert normalize_semester_value("SECOND") == "second"


def test_first_with_surrounding_whitespace_stripped():
    """Pin: '  first  ' → 'first'. Defends against form fields with
    accidental padding."""
    assert normalize_semester_value("  first  ") == "first"

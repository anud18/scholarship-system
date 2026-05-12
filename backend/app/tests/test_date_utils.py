"""
Tests for `app.utils.date_utils` — pure date / datetime helpers.

These three helpers parse, format, and range-check dates throughout the
codebase:

- `parse_date_field` — used wherever student-submitted form data or SIS
  API responses include a date string (forms, audit logs, application
  submission timestamps). A regression here would corrupt dates at the
  storage boundary.
- `format_date_for_display` — used by Excel exports and email templates;
  None-handling matters because optional date fields are common.
- `is_within_date_range` — used to gate application-period eligibility
  and bank-verification expiry windows.

Wave 2c of the production-readiness rollout. All tests run without any
DB / network — `pytest.mark.smoke`.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.utils.date_utils import (
    format_date_for_display,
    is_within_date_range,
    parse_date_field,
)

pytestmark = pytest.mark.smoke


# ---------------------------------------------------------------------------
# parse_date_field
# ---------------------------------------------------------------------------


class TestParseDateField:
    """Multi-format date parser; tolerates None, datetime, and several string
    shapes. Throws ValueError on truly unparseable input."""

    def test_none_returns_none(self) -> None:
        assert parse_date_field(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert parse_date_field("") is None

    def test_datetime_passthrough(self) -> None:
        """A datetime input is returned as-is, no re-parsing."""
        dt = datetime(2026, 3, 25, 14, 30, 0)
        assert parse_date_field(dt) is dt

    def test_iso_format_with_z(self) -> None:
        """The Z suffix means UTC; the parser swaps it for +00:00."""
        result = parse_date_field("2024-03-25T14:30:00Z")
        assert result is not None
        assert result.year == 2024
        assert result.month == 3
        assert result.day == 25
        assert result.hour == 14
        assert result.minute == 30
        # tzinfo should be set after Z→+00:00 conversion
        assert result.tzinfo is not None

    def test_iso_format_without_tz(self) -> None:
        result = parse_date_field("2024-03-25T14:30:00")
        assert result is not None
        assert (result.year, result.month, result.day) == (2024, 3, 25)
        assert (result.hour, result.minute) == (14, 30)

    def test_date_only(self) -> None:
        """`2024-03-25` form — 10 chars with a hyphen — parses as midnight."""
        result = parse_date_field("2024-03-25")
        assert result == datetime(2024, 3, 25)

    def test_datetime_with_space(self) -> None:
        result = parse_date_field("2024-03-25 14:30:00")
        assert result == datetime(2024, 3, 25, 14, 30, 0)

    def test_dateutil_fallback_for_other_formats(self) -> None:
        """Anything else falls through to dateutil.parser; verify it works
        on a common natural-language format."""
        result = parse_date_field("March 25, 2024")
        assert result is not None
        assert (result.year, result.month, result.day) == (2024, 3, 25)

    def test_invalid_string_raises(self) -> None:
        """Truly garbage input must raise ValueError, NOT silently return None
        — per CLAUDE.md §1 (no fallback data on parse failure)."""
        with pytest.raises(ValueError):
            parse_date_field("this is not a date at all")

    def test_other_type_returns_none(self) -> None:
        """An int or list isn't a parseable input; the function returns None
        rather than raise (current documented behavior — types other than
        str/datetime/None fall through to the bottom)."""
        assert parse_date_field(12345) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# format_date_for_display
# ---------------------------------------------------------------------------


class TestFormatDateForDisplay:
    """Used by Excel exports and email templates. Must handle None gracefully."""

    def test_none_returns_default(self) -> None:
        assert format_date_for_display(None) == "N/A"

    def test_none_custom_default(self) -> None:
        assert format_date_for_display(None, default="—") == "—"

    def test_default_iso_date_format(self) -> None:
        dt = datetime(2026, 3, 25, 14, 30, 0)
        assert format_date_for_display(dt) == "2026-03-25"

    def test_custom_format(self) -> None:
        dt = datetime(2026, 3, 25, 14, 30, 0)
        assert format_date_for_display(dt, format_string="%Y/%m/%d %H:%M") == "2026/03/25 14:30"

    def test_format_with_locale_friendly_string(self) -> None:
        dt = datetime(2026, 3, 25)
        assert format_date_for_display(dt, format_string="%d %b %Y") == "25 Mar 2026"


# ---------------------------------------------------------------------------
# is_within_date_range
# ---------------------------------------------------------------------------


class TestIsWithinDateRange:
    """Range check with open bounds. Both bounds are inclusive when present."""

    def _d(self, day: int) -> datetime:
        """Shorthand for a date in 2026-03."""
        return datetime(2026, 3, day)

    def test_inside_closed_range(self) -> None:
        assert is_within_date_range(self._d(15), self._d(10), self._d(20)) is True

    def test_at_lower_bound_inclusive(self) -> None:
        """Exactly equal to the start should count as in-range."""
        assert is_within_date_range(self._d(10), self._d(10), self._d(20)) is True

    def test_at_upper_bound_inclusive(self) -> None:
        """Exactly equal to the end should count as in-range."""
        assert is_within_date_range(self._d(20), self._d(10), self._d(20)) is True

    def test_before_lower_bound(self) -> None:
        assert is_within_date_range(self._d(5), self._d(10), self._d(20)) is False

    def test_after_upper_bound(self) -> None:
        assert is_within_date_range(self._d(25), self._d(10), self._d(20)) is False

    def test_no_lower_bound_means_unbounded_below(self) -> None:
        """None start = no lower bound; only end_date constrains."""
        assert is_within_date_range(self._d(5), None, self._d(20)) is True

    def test_no_upper_bound_means_unbounded_above(self) -> None:
        """None end = no upper bound; only start_date constrains."""
        assert is_within_date_range(self._d(25), self._d(10), None) is True

    def test_both_none_always_true(self) -> None:
        """Range with both ends open accepts everything."""
        assert is_within_date_range(self._d(15), None, None) is True

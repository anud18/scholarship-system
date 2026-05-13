"""
Tests for `ApplicationSequence.format_app_id` and `get_semester_code`.

These are pure static helpers that encode the project-wide application-ID
contract (`APP-{year}-{semester_code}-{sequence:05d}`) documented in
CLAUDE.md §6. Pinning the format with explicit assertions prevents silent
breakage of:

- Downstream search / filter UIs that pattern-match on `APP-{year}-...`
- Excel exports that group rows by parsing the app_id
- Operator-facing dashboards relying on lexicographic ordering

Wave 2a of the production-readiness rollout (issue tracker covers the
remaining application_service.py path coverage in a future PR).
"""

from __future__ import annotations

import pytest

from app.models.application_sequence import ApplicationSequence

pytestmark = pytest.mark.smoke


class TestGetSemesterCode:
    """`get_semester_code` maps the Python Semester enum values to a single
    digit. Cover every documented mapping plus the unknown-semester fallback."""

    def test_first_maps_to_1(self) -> None:
        assert ApplicationSequence.get_semester_code("first") == "1"

    def test_second_maps_to_2(self) -> None:
        assert ApplicationSequence.get_semester_code("second") == "2"

    def test_yearly_maps_to_0(self) -> None:
        assert ApplicationSequence.get_semester_code("yearly") == "0"

    @pytest.mark.parametrize(
        "unknown",
        ["", "annual", "summer", "FIRST", "First", "1", "0"],
    )
    def test_unknown_falls_back_to_0(self, unknown: str) -> None:
        """Any non-canonical value falls back to '0' (yearly).

        This is the only documented fallback path; the alternative — raising —
        would surface as a 500 in app-id generation. Per CLAUDE.md §1
        (no fallback data) this fallback is acceptable because the value is
        derived, not retrieved.
        """
        assert ApplicationSequence.get_semester_code(unknown) == "0"


class TestFormatAppId:
    """Pin the exact format produced by `format_app_id`."""

    def test_format_first_semester(self) -> None:
        assert ApplicationSequence.format_app_id(113, "first", 1) == "APP-113-1-00001"

    def test_format_second_semester(self) -> None:
        assert ApplicationSequence.format_app_id(113, "second", 125) == "APP-113-2-00125"

    def test_format_yearly(self) -> None:
        assert ApplicationSequence.format_app_id(114, "yearly", 1) == "APP-114-0-00001"

    def test_sequence_pads_to_five_digits(self) -> None:
        """Sequences below 10000 are zero-padded to five digits to preserve
        lexicographic ordering."""
        assert ApplicationSequence.format_app_id(113, "first", 1) == "APP-113-1-00001"
        assert ApplicationSequence.format_app_id(113, "first", 9) == "APP-113-1-00009"
        assert ApplicationSequence.format_app_id(113, "first", 10) == "APP-113-1-00010"
        assert ApplicationSequence.format_app_id(113, "first", 99) == "APP-113-1-00099"
        assert ApplicationSequence.format_app_id(113, "first", 9999) == "APP-113-1-09999"

    def test_sequence_above_99999_uses_natural_width(self) -> None:
        """Per the {sequence:05d} spec, sequences ≥ 100000 are NOT truncated —
        they overflow to natural width. This is intentional (we'd rather have
        a wider but unique app_id than silently lose data)."""
        assert ApplicationSequence.format_app_id(113, "first", 100000) == "APP-113-1-100000"

    def test_unknown_semester_falls_back_to_yearly_code(self) -> None:
        """If something upstream passes a bogus semester, the format still
        produces a syntactically valid app_id with the yearly code ('0')."""
        assert ApplicationSequence.format_app_id(113, "summer", 5) == "APP-113-0-00005"

    @pytest.mark.parametrize(
        "year,semester,seq,expected",
        [
            (113, "first", 1, "APP-113-1-00001"),
            (113, "second", 125, "APP-113-2-00125"),
            (114, "yearly", 1, "APP-114-0-00001"),
            (115, "first", 1, "APP-115-1-00001"),
            (100, "yearly", 12345, "APP-100-0-12345"),
        ],
    )
    def test_format_matrix_matches_docs(self, year: int, semester: str, seq: int, expected: str) -> None:
        """Matrix that mirrors the examples in CLAUDE.md §6. If anyone changes
        the format without updating CLAUDE.md, this regression fails first."""
        assert ApplicationSequence.format_app_id(year, semester, seq) == expected


class TestRoundTripParsability:
    """Sanity-check that generated app_ids match a stable parsing regex.

    Several downstream consumers (Excel exports, audit log filters) split the
    app_id by '-' and assume exactly 4 segments. Pin that here so a future
    rename like `APP-V2-...` would fail the test before reaching production.
    """

    @pytest.mark.parametrize(
        "year,semester,seq",
        [
            (113, "first", 1),
            (113, "second", 999),
            (114, "yearly", 12345),
        ],
    )
    def test_app_id_splits_into_four_parts(self, year: int, semester: str, seq: int) -> None:
        app_id = ApplicationSequence.format_app_id(year, semester, seq)
        parts = app_id.split("-")
        assert len(parts) == 4
        assert parts[0] == "APP"
        assert parts[1] == str(year)
        assert parts[2] == ApplicationSequence.get_semester_code(semester)
        assert int(parts[3]) == seq

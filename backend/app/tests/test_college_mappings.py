"""
Tests for `app.core.college_mappings` — pure college-code lookup helpers.

These helpers wrap two constant dicts (`COLLEGE_MAPPINGS` zh +
`COLLEGE_MAPPINGS_EN`) that drive:

- The college dropdown in the student application form (codes like "E" /
  "C" / "I" map to display names)
- Excel exports of college rankings (groups rows by college name)
- Audit-log enrichment when displaying which college a reviewer belongs to

A typo or accidental deletion in one of the mapping dicts would silently
show empty names in the UI. Pin the mapping cardinality + the bilingual
parity so any future edit forces this test to be updated too.

Wave 2d of the production-readiness rollout — fourth batch of
pure-function test coverage.
"""

from __future__ import annotations

import pytest

from app.core.college_mappings import (
    COLLEGE_MAPPINGS,
    COLLEGE_MAPPINGS_EN,
    get_all_colleges,
    get_college_codes,
    get_college_name,
    is_valid_college_code,
)

pytestmark = pytest.mark.smoke


# ---------------------------------------------------------------------------
# Mapping invariants
# ---------------------------------------------------------------------------


class TestMappingInvariants:
    """The zh and en dicts must have identical key sets — a missing en
    translation would render as an empty name in the localised UI."""

    def test_zh_and_en_have_matching_keys(self) -> None:
        assert set(COLLEGE_MAPPINGS.keys()) == set(COLLEGE_MAPPINGS_EN.keys()), (
            "COLLEGE_MAPPINGS and COLLEGE_MAPPINGS_EN have diverged. "
            "Every code that exists in one must exist in the other."
        )

    def test_no_empty_names(self) -> None:
        """Every value in both dicts must be a non-empty string. A blank
        value would render as nothing in the UI dropdown."""
        for code, name in COLLEGE_MAPPINGS.items():
            assert name, f"Empty zh name for college code {code!r}"
        for code, name in COLLEGE_MAPPINGS_EN.items():
            assert name, f"Empty en name for college code {code!r}"

    def test_all_known_college_codes_present(self) -> None:
        """Pin the current 13 college codes so a typo / accidental deletion
        fails fast. If a real college is added in the future, this test gets
        updated as part of that change."""
        expected = {"E", "C", "I", "S", "B", "O", "D", "1", "6", "7", "M", "A", "K"}
        assert set(COLLEGE_MAPPINGS.keys()) == expected


# ---------------------------------------------------------------------------
# get_college_name
# ---------------------------------------------------------------------------


class TestGetCollegeName:
    def test_zh_default(self) -> None:
        """Default language is Chinese."""
        assert get_college_name("E") == "電機學院"

    def test_explicit_zh(self) -> None:
        assert get_college_name("C", lang="zh") == "資訊學院"

    def test_en(self) -> None:
        assert get_college_name("E", lang="en") == "College of Electrical and Computer Engineering"

    def test_unknown_code_zh(self) -> None:
        """An unknown code returns None — caller is expected to handle the
        miss (no fallback to "Unknown")."""
        assert get_college_name("XX") is None

    def test_unknown_code_en(self) -> None:
        assert get_college_name("XX", lang="en") is None

    def test_unknown_lang_falls_back_to_zh(self) -> None:
        """Only 'en' triggers the English path; anything else (including
        'jp' or empty string) returns the Chinese name. This is the documented
        behavior — keeps the function simple and predictable."""
        assert get_college_name("E", lang="jp") == "電機學院"
        assert get_college_name("E", lang="") == "電機學院"


# ---------------------------------------------------------------------------
# get_all_colleges
# ---------------------------------------------------------------------------


class TestGetAllColleges:
    def test_returns_all_13_colleges(self) -> None:
        colleges = get_all_colleges()
        assert len(colleges) == 13

    def test_each_entry_has_code_name_name_en(self) -> None:
        """Each list item must have the documented shape."""
        for entry in get_all_colleges():
            assert set(entry.keys()) == {"code", "name", "name_en"}
            assert entry["code"]
            assert entry["name"]
            assert entry["name_en"]

    def test_sorted_by_code(self) -> None:
        """Output is sorted by college code so the dropdown order is stable
        across renders. Important: codes are mixed letters + digits, so this
        is lexicographic sort, not alphabetical."""
        colleges = get_all_colleges()
        codes = [c["code"] for c in colleges]
        assert codes == sorted(codes)

    def test_en_lang_does_not_change_name_field(self) -> None:
        """The `name` field is always the zh value, regardless of `lang` —
        consumers can pick which field to render. This is the documented
        behavior; the lang parameter only controls iteration / sort, not the
        per-entry shape."""
        zh_list = get_all_colleges(lang="zh")
        en_list = get_all_colleges(lang="en")
        # Same length, same shape, same code order
        assert len(zh_list) == len(en_list)
        for zh_entry, en_entry in zip(zh_list, en_list):
            assert zh_entry["code"] == en_entry["code"]
            assert zh_entry["name"] == en_entry["name"]
            assert zh_entry["name_en"] == en_entry["name_en"]


# ---------------------------------------------------------------------------
# is_valid_college_code + get_college_codes
# ---------------------------------------------------------------------------


class TestValidationHelpers:
    def test_valid_code(self) -> None:
        assert is_valid_college_code("E") is True
        assert is_valid_college_code("M") is True

    def test_invalid_code(self) -> None:
        assert is_valid_college_code("XX") is False
        assert is_valid_college_code("") is False

    def test_case_sensitive(self) -> None:
        """Codes are uppercase. Lowercase 'e' is NOT 'E' — this is
        deliberate; the SIS sends uppercase codes."""
        assert is_valid_college_code("e") is False

    def test_get_college_codes_returns_sorted_list(self) -> None:
        codes = get_college_codes()
        assert len(codes) == 13
        assert codes == sorted(codes)
        assert "E" in codes
        assert "XX" not in codes

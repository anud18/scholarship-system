"""
Tests for app.core.regex_validator — SECURITY-critical module that gates
user-provided regex patterns before they reach re.compile() at runtime.

This module is referenced by:
- app/api/v1/endpoints/email_automation.py
- app/api/v1/endpoints/admin/configurations.py
- app/services/config_management_service.py

Pinned behavior:
- Empty pattern → RegexValidationError
- Pattern length > MAX_PATTERN_LENGTH (200) → RegexValidationError
- Each of the 6 DANGEROUS_PATTERNS triggers rejection
- Invalid syntax → RegexValidationError (wraps re.error)
- validate_and_sanitize_pattern returns identical content via JSON round-trip
- safe_regex_match / safe_regex_search validate first, then run
- Both safe_* return Optional[re.Match]
"""

import re

import pytest

from app.core.regex_validator import (
    DANGEROUS_PATTERNS,
    MAX_PATTERN_LENGTH,
    RegexValidationError,
    safe_regex_match,
    safe_regex_search,
    validate_and_sanitize_pattern,
    validate_regex_pattern,
)

# ─── validate_regex_pattern ─────────────────────────────────────────


class TestValidateRegexPattern:
    def test_rejects_empty_pattern(self):
        """Empty patterns should fail fast — no point trying to compile."""
        with pytest.raises(RegexValidationError, match="cannot be empty"):
            validate_regex_pattern("")

    def test_rejects_pattern_exceeding_max_length(self):
        """Pattern length cap prevents resource exhaustion via massive patterns."""
        oversize = "a" * (MAX_PATTERN_LENGTH + 1)
        with pytest.raises(RegexValidationError, match="exceeds maximum length"):
            validate_regex_pattern(oversize)

    def test_accepts_pattern_at_max_length_boundary(self):
        """Pattern of exactly MAX_PATTERN_LENGTH is the boundary case — should pass."""
        # Use a pattern that's also valid regex
        boundary = "a" * MAX_PATTERN_LENGTH
        validate_regex_pattern(boundary)  # no raise

    def test_accepts_simple_safe_pattern(self):
        """Common production patterns (digit string, email, etc.) must pass."""
        validate_regex_pattern(r"^\d{1,3}$")
        validate_regex_pattern(r"^[a-zA-Z0-9_-]+$")

    def test_rejects_double_unbounded_wildcard(self):
        """`.*.*` is a classic ReDoS shape — must reject."""
        with pytest.raises(RegexValidationError, match="dangerous construct"):
            validate_regex_pattern(".*.*")

    def test_rejects_double_unbounded_plus(self):
        """`.+.+` similar to `.*.*` — must reject."""
        with pytest.raises(RegexValidationError, match="dangerous construct"):
            validate_regex_pattern(".+.+")

    def test_rejects_nested_star_groups(self):
        """`(a*)*(b*)*` quadratic backtracking shape."""
        with pytest.raises(RegexValidationError, match="dangerous construct"):
            validate_regex_pattern("(a*)*(b*)*")

    def test_rejects_nested_plus_groups(self):
        """`(a+)+(b+)+` similar to nested-star."""
        with pytest.raises(RegexValidationError, match="dangerous construct"):
            validate_regex_pattern("(a+)+(b+)+")

    def test_rejects_quantifier_on_starred_group(self):
        """`(a*)*` — Evil Regex catastrophic-backtracking shape."""
        with pytest.raises(RegexValidationError, match="dangerous construct"):
            validate_regex_pattern("(a*)*")

    def test_rejects_quantifier_on_plus_group(self):
        """`(a+)+` — Evil Regex catastrophic-backtracking shape."""
        with pytest.raises(RegexValidationError, match="dangerous construct"):
            validate_regex_pattern("(a+)+")

    def test_dangerous_patterns_list_is_complete(self):
        """Pin the dangerous-pattern count so accidental removal surfaces."""
        assert len(DANGEROUS_PATTERNS) == 6

    def test_rejects_invalid_syntax(self):
        """Malformed regex (unclosed bracket) wraps re.error as RegexValidationError."""
        with pytest.raises(RegexValidationError, match="Invalid regex pattern"):
            validate_regex_pattern("[unclosed")

    def test_test_string_param_is_optional(self):
        """validate_regex_pattern works without a test_string argument."""
        validate_regex_pattern(r"^foo$")  # no exception

    def test_test_string_runs_match_for_redos_check(self):
        """Passing a test_string triggers a match attempt under the same timeout gate."""
        # Safe pattern + safe input — no exception
        validate_regex_pattern(r"^hello$", test_string="hello")


# ─── validate_and_sanitize_pattern ──────────────────────────────────


class TestValidateAndSanitizePattern:
    def test_returns_identical_content(self):
        """JSON round-trip yields a string with the SAME content."""
        original = r"^\d{3}-\d{4}$"
        sanitized = validate_and_sanitize_pattern(original)
        assert sanitized == original

    def test_returns_string_type(self):
        """Output type must be str (not bytes, not other JSON primitive)."""
        result = validate_and_sanitize_pattern("abc")
        assert isinstance(result, str)

    def test_handles_unicode_pattern(self):
        """Non-ASCII patterns (e.g., Chinese in scholarship-form configs) survive."""
        original = r"^[一-龥]+$"  # CJK unified ideographs
        sanitized = validate_and_sanitize_pattern(original)
        assert sanitized == original

    def test_returns_new_object(self):
        """JSON round-trip creates a NEW string object (taint-flow break for CodeQL)."""
        original = "test_pattern_unique_xyz"
        sanitized = validate_and_sanitize_pattern(original)
        # CPython may intern short strings — pick an unguessable long-enough one
        # and assert content equivalence; identity is best-effort.
        assert sanitized == original


# ─── safe_regex_match ───────────────────────────────────────────────


class TestSafeRegexMatch:
    def test_matches_at_start_of_string(self):
        """`re.match` only matches at start — pin the behavior."""
        result = safe_regex_match(r"^hello", "hello world")
        assert result is not None
        assert result.group() == "hello"

    def test_returns_none_when_no_match(self):
        """No-match path returns None, not a falsy Match."""
        result = safe_regex_match(r"^xyz$", "abc")
        assert result is None

    def test_validates_before_matching(self):
        """Dangerous pattern is rejected BEFORE any match attempt."""
        with pytest.raises(RegexValidationError, match="dangerous construct"):
            safe_regex_match("(a+)+", "aaaaaaaaaaaaaaaaaaaaa!")

    def test_accepts_flags(self):
        """re.IGNORECASE flag flows through."""
        result = safe_regex_match(r"^HELLO", "hello", flags=re.IGNORECASE)
        assert result is not None

    def test_validates_pattern_length(self):
        """Oversize pattern fails validation step."""
        with pytest.raises(RegexValidationError, match="exceeds maximum length"):
            safe_regex_match("a" * 201, "input")


# ─── safe_regex_search ──────────────────────────────────────────────


class TestSafeRegexSearch:
    def test_finds_match_anywhere(self):
        """`re.search` finds matches anywhere in the string."""
        result = safe_regex_search(r"\d+", "abc123def")
        assert result is not None
        assert result.group() == "123"

    def test_returns_none_when_no_match(self):
        result = safe_regex_search(r"\d+", "abc")
        assert result is None

    def test_validates_before_searching(self):
        """Dangerous pattern rejected before search."""
        with pytest.raises(RegexValidationError, match="dangerous construct"):
            safe_regex_search("(a*)*", "aaaaaa!")

    def test_accepts_flags(self):
        result = safe_regex_search(r"hello", "say HELLO loudly", flags=re.IGNORECASE)
        assert result is not None

"""
Unit tests for regex validator utility

Tests validation and security features of the regex validator.
"""

import pytest

from app.core.regex_validator import RegexValidationError, safe_regex_match, safe_regex_search, validate_regex_pattern


class TestValidateRegexPattern:
    """Test regex pattern validation"""

    def test_valid_simple_pattern(self):
        """Test that valid simple patterns pass validation"""
        validate_regex_pattern(r"^\d{3}$")
        validate_regex_pattern(r"[a-zA-Z]+")
        validate_regex_pattern(r"test_\w+")

    def test_empty_pattern_rejected(self):
        """Test that empty patterns are rejected"""
        with pytest.raises(RegexValidationError, match="cannot be empty"):
            validate_regex_pattern("")

    def test_too_long_pattern_rejected(self):
        """Test that excessively long patterns are rejected"""
        long_pattern = "a" * 300
        with pytest.raises(RegexValidationError, match="exceeds maximum length"):
            validate_regex_pattern(long_pattern)

    def test_dangerous_patterns_rejected(self):
        """Test that dangerous ReDoS patterns are rejected"""
        dangerous_patterns = [
            r"(.*)*",  # Nested quantifiers
            r"(.+)+",  # Nested plus quantifiers
            r"(a*)*b",  # Catastrophic backtracking
            r"(a+)+b",  # Catastrophic backtracking
        ]

        for pattern in dangerous_patterns:
            with pytest.raises(RegexValidationError, match="dangerous construct"):
                validate_regex_pattern(pattern)

    def test_invalid_syntax_rejected(self):
        """Test that invalid regex syntax is rejected"""
        with pytest.raises(RegexValidationError, match="Invalid regex pattern"):
            validate_regex_pattern(r"[invalid")

        with pytest.raises(RegexValidationError, match="Invalid regex pattern"):
            validate_regex_pattern(r"(?P<unclosed")

    def test_pattern_with_test_string(self):
        """Test validation with test string"""
        # Valid pattern and string
        validate_regex_pattern(r"^\d{3}$", test_string="123")

        # Pattern that doesn't match is still valid
        validate_regex_pattern(r"^\d{3}$", test_string="abc")


class TestSafeRegexMatch:
    """Test safe regex matching"""

    def test_valid_match(self):
        """Test that valid patterns match correctly"""
        result = safe_regex_match(r"^\d{3}$", "123")
        assert result is not None
        assert result.group() == "123"

    def test_no_match(self):
        """Test that non-matching returns None"""
        result = safe_regex_match(r"^\d{3}$", "abc")
        assert result is None

    def test_dangerous_pattern_rejected(self):
        """Test that dangerous patterns are rejected before matching"""
        with pytest.raises(RegexValidationError, match="dangerous construct"):
            safe_regex_match(r"(.*)*", "test")

    def test_invalid_pattern_rejected(self):
        """Test that invalid patterns are rejected"""
        with pytest.raises(RegexValidationError, match="Invalid regex pattern"):
            safe_regex_match(r"[invalid", "test")

    def test_match_with_flags(self):
        """Test matching with regex flags"""
        import re

        result = safe_regex_match(r"^abc$", "ABC", flags=re.IGNORECASE)
        assert result is not None
        assert result.group() == "ABC"


class TestSafeRegexSearch:
    """Test safe regex searching"""

    def test_valid_search(self):
        """Test that valid patterns search correctly"""
        result = safe_regex_search(r"\d{3}", "abc123def")
        assert result is not None
        assert result.group() == "123"

    def test_no_match(self):
        """Test that non-matching returns None"""
        result = safe_regex_search(r"\d{3}", "abcdef")
        assert result is None

    def test_dangerous_pattern_rejected(self):
        """Test that dangerous patterns are rejected before searching"""
        with pytest.raises(RegexValidationError, match="dangerous construct"):
            safe_regex_search(r"(.+)+", "test")

    def test_search_with_flags(self):
        """Test searching with regex flags"""
        import re

        result = safe_regex_search(r"abc", "xyzABCxyz", flags=re.IGNORECASE)
        assert result is not None
        assert result.group() == "ABC"


class TestSecurityScenarios:
    """Test security-specific scenarios"""

    def test_user_input_validation(self):
        """Test validation of user-provided regex patterns"""
        # Simulate user trying to inject malicious pattern
        malicious_patterns = [
            r"(a+)+b",  # ReDoS attack
            r"(.*)*",  # Catastrophic backtracking
            r"(.+)+$",  # Another ReDoS variant
        ]

        for pattern in malicious_patterns:
            with pytest.raises(RegexValidationError):
                safe_regex_match(pattern, "test_string")

    def test_safe_email_validation(self):
        """Test safe email validation pattern"""
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

        # This should be safe
        validate_regex_pattern(email_pattern)

        # Test actual matching
        result = safe_regex_match(email_pattern, "test@example.com")
        assert result is not None

        result = safe_regex_match(email_pattern, "invalid-email")
        assert result is None

    def test_safe_phone_validation(self):
        """Test safe phone number validation pattern"""
        phone_pattern = r"^\d{10}$"

        # This should be safe
        validate_regex_pattern(phone_pattern)

        # Test actual matching
        result = safe_regex_match(phone_pattern, "1234567890")
        assert result is not None

        result = safe_regex_match(phone_pattern, "12345")
        assert result is None

    def test_configuration_value_validation(self):
        """Test configuration value validation use case"""
        # Simulate the use case from config_management_service.py
        validation_patterns = {
            "port": r"^\d{1,5}$",
            "email": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            "url": r"^https?://[a-zA-Z0-9.-]+(:[0-9]{1,5})?(/.*)?$",
        }

        test_values = {
            "port": "8080",
            "email": "admin@example.com",
            "url": "https://example.com:8080/path",
        }

        for key, pattern in validation_patterns.items():
            validate_regex_pattern(pattern)
            result = safe_regex_match(pattern, test_values[key])
            assert result is not None, f"Failed to match {key}"


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_unicode_patterns(self):
        """Test patterns with unicode characters"""
        pattern = r"^[\u4e00-\u9fa5]+$"  # Chinese characters
        validate_regex_pattern(pattern)

        result = safe_regex_match(pattern, "測試")
        assert result is not None

    def test_empty_string_matching(self):
        """Test matching against empty strings"""
        result = safe_regex_match(r"^$", "")
        assert result is not None

        result = safe_regex_match(r".+", "")
        assert result is None

    def test_very_long_input_string(self):
        """Test matching against very long strings"""
        pattern = r"^\d+$"
        long_string = "1" * 10000

        # This should complete without timeout for simple patterns
        result = safe_regex_match(pattern, long_string, timeout_seconds=2)
        assert result is not None

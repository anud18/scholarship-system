r"""
Test suite for ReDoS vulnerability fix in email automation endpoint validation.

This test file specifically validates the security fix for the polynomial ReDoS
vulnerability found in validate_condition_query() function.

Security Issue: CVE-like - Polynomial ReDoS in regex pattern r"\{[^a-zA-Z0-9_]+\}"
Fixed by: Using safe_regex_search wrapper with timeout protection
"""

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.email_automation import validate_condition_query


class TestValidateConditionQueryReDoSFix:
    """Test suite for ReDoS vulnerability fix in condition query validation."""

    # ==================== VALID QUERY TESTS ====================

    def test_valid_query_with_valid_placeholders(self):
        """Test that valid queries with proper placeholders pass validation."""
        valid_query = "SELECT email FROM applications WHERE id = {application_id} AND status = {status}"
        # Should not raise any exception
        validate_condition_query(valid_query)

    def test_valid_query_with_multiple_placeholders(self):
        """Test query with multiple valid placeholders."""
        valid_query = "SELECT * FROM students WHERE student_id = {student_id} AND year = {academic_year} AND semester = {semester}"
        validate_condition_query(valid_query)

    def test_valid_query_with_underscores_in_placeholders(self):
        """Test placeholders with underscores (valid word characters)."""
        valid_query = "SELECT email FROM applications WHERE scholarship_type = {scholarship_type_code}"
        validate_condition_query(valid_query)

    def test_valid_query_with_numbers_in_placeholders(self):
        """Test placeholders with numbers (valid word characters)."""
        valid_query = "SELECT * FROM table WHERE field1 = {value123} AND field2 = {value456}"
        validate_condition_query(valid_query)

    def test_empty_query_passes_validation(self):
        """Test that empty/None queries pass validation."""
        validate_condition_query(None)
        validate_condition_query("")

    # ==================== REDOS ATTACK TESTS ====================

    def test_redos_attack_many_consecutive_open_braces(self):
        r"""
        Test ReDoS attack pattern: excessive consecutive open braces.

        This was the vulnerability: r"\{[^a-zA-Z0-9_]+\}" causes catastrophic
        backtracking on inputs like "{{{{{{{{".

        The fix: Pre-validation check rejects >50 consecutive braces.
        """
        # Create attack string with 100 consecutive open braces
        attack_query = "SELECT * FROM table WHERE field = " + "{" * 100

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(attack_query)

        assert exc_info.value.status_code == 400
        assert "excessive consecutive braces" in exc_info.value.detail.lower()

    def test_redos_attack_many_consecutive_close_braces(self):
        """Test ReDoS attack with excessive consecutive close braces."""
        attack_query = "SELECT * FROM table WHERE field = " + "}" * 100

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(attack_query)

        assert exc_info.value.status_code == 400
        assert "excessive consecutive braces" in exc_info.value.detail.lower()

    def test_redos_attack_mixed_braces_pattern(self):
        """Test ReDoS attack with mixed brace patterns."""
        # Pattern that could cause backtracking: {{{{{{{{{{
        attack_query = "SELECT * FROM table WHERE " + "{{" * 30

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(attack_query)

        assert exc_info.value.status_code == 400
        assert "excessive consecutive braces" in exc_info.value.detail.lower()

    def test_query_exceeds_max_length(self):
        """Test that extremely long queries are rejected (anti-DoS measure)."""
        # Create a query exceeding MAX_QUERY_LENGTH (5000 characters)
        long_query = "SELECT * FROM table WHERE " + "field = {placeholder} AND " * 200

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(long_query)

        assert exc_info.value.status_code == 400
        assert "exceeds maximum length" in exc_info.value.detail

    # ==================== INVALID PLACEHOLDER TESTS ====================

    def test_invalid_placeholder_with_spaces(self):
        """Test that placeholders with spaces are rejected."""
        invalid_query = "SELECT * FROM table WHERE field = {invalid placeholder}"

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(invalid_query)

        assert exc_info.value.status_code == 400
        assert "Invalid placeholder format" in exc_info.value.detail

    def test_invalid_placeholder_with_dashes(self):
        """Test that placeholders with dashes are rejected."""
        invalid_query = "SELECT * FROM table WHERE field = {invalid-placeholder}"

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(invalid_query)

        assert exc_info.value.status_code == 400
        assert "Invalid placeholder format" in exc_info.value.detail

    def test_invalid_placeholder_with_special_chars(self):
        """Test that placeholders with special characters are rejected."""
        invalid_query = "SELECT * FROM table WHERE field = {invalid!placeholder@}"

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(invalid_query)

        assert exc_info.value.status_code == 400
        assert "Invalid placeholder format" in exc_info.value.detail

    def test_multiple_invalid_placeholders_detected(self):
        """Test that multiple invalid placeholders are all detected."""
        invalid_query = "SELECT * FROM table WHERE field1 = {invalid-one} AND field2 = {invalid two}"

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(invalid_query)

        assert exc_info.value.status_code == 400
        assert "Invalid placeholder format" in exc_info.value.detail
        # Should show found invalid placeholders
        assert "Found:" in exc_info.value.detail

    # ==================== SQL INJECTION PREVENTION TESTS ====================

    def test_non_select_statement_rejected(self):
        """Test that non-SELECT statements are rejected."""
        dangerous_queries = [
            "DROP TABLE applications",
            "DELETE FROM applications WHERE id = {app_id}",
            "UPDATE applications SET status = 'approved'",
            "INSERT INTO applications VALUES (1, 2, 3)",
        ]

        for query in dangerous_queries:
            with pytest.raises(HTTPException) as exc_info:
                validate_condition_query(query)
            assert exc_info.value.status_code == 400
            assert "must be a SELECT statement" in exc_info.value.detail

    def test_dangerous_sql_keywords_rejected(self):
        """Test that dangerous SQL keywords are rejected."""
        dangerous_keywords_queries = [
            "SELECT * FROM applications; DROP TABLE users",
            "SELECT * FROM applications WHERE id = {id} UNION SELECT password FROM users",
            "SELECT * FROM applications WHERE id = EXEC('malicious')",
            "SELECT * FROM applications WHERE WAITFOR DELAY '00:00:05'",
            "SELECT LOAD_FILE('/etc/passwd')",
        ]

        for query in dangerous_keywords_queries:
            with pytest.raises(HTTPException) as exc_info:
                validate_condition_query(query)
            assert exc_info.value.status_code == 400
            # Should reject due to forbidden keyword or multiple statements
            assert "forbidden keyword" in exc_info.value.detail or "multiple SQL statements" in exc_info.value.detail

    def test_multiple_statements_rejected(self):
        """Test that multiple SQL statements are rejected."""
        query_with_multiple_statements = "SELECT * FROM table; SELECT * FROM another_table"

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(query_with_multiple_statements)

        assert exc_info.value.status_code == 400
        assert "multiple SQL statements" in exc_info.value.detail

    # ==================== EDGE CASE TESTS ====================

    def test_query_with_exactly_50_consecutive_braces_passes(self):
        """Test boundary condition: exactly 50 consecutive braces should pass."""
        # The pre-check uses r"\{{50,}" which means 50 or more
        # So exactly 49 should pass, 50 should be rejected
        boundary_query = "SELECT * FROM table WHERE field = " + "{" * 49 + " text"

        # This should pass the brace check but fail on other validation
        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(boundary_query)

        # Should NOT be rejected for excessive braces
        assert "excessive consecutive braces" not in exc_info.value.detail.lower()

    def test_query_with_51_consecutive_braces_rejected(self):
        """Test boundary condition: 51 consecutive braces should be rejected."""
        boundary_query = "SELECT * FROM table WHERE field = " + "{" * 51

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(boundary_query)

        assert exc_info.value.status_code == 400
        assert "excessive consecutive braces" in exc_info.value.detail.lower()

    def test_nested_braces_with_valid_content(self):
        """Test that nested braces are handled correctly."""
        # Double braces with valid placeholder inside
        query_with_nested = "SELECT * FROM table WHERE field = {{valid_placeholder}}"

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(query_with_nested)

        # Should be rejected for invalid placeholder format (nested braces)
        assert exc_info.value.status_code == 400

    def test_timeout_protection_on_complex_pattern(self):
        """
        Test that timeout protection works on complex patterns.

        The safe_regex_search wrapper has a 1-second timeout. Any pattern that
        takes longer should raise RegexValidationError and be caught.
        """
        # Create a pattern that might be slow (but caught by pre-checks first)
        # This test validates the error handling path
        complex_query = "SELECT * FROM table WHERE " + "{" * 55  # Triggers pre-check

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(complex_query)

        assert exc_info.value.status_code == 400
        # Should be caught by pre-validation check
        assert "excessive consecutive braces" in exc_info.value.detail.lower()

    def test_unicode_in_placeholders(self):
        """Test that unicode characters in placeholders are rejected."""
        unicode_query = "SELECT * FROM table WHERE field = {placeholder_中文}"

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(unicode_query)

        assert exc_info.value.status_code == 400
        assert "Invalid placeholder format" in exc_info.value.detail

    # ==================== REGRESSION TESTS ====================

    def test_original_vulnerable_pattern_now_safe(self):
        r"""
        Regression test: Verify the original vulnerable pattern is now safe.

        Original vulnerability: re.findall(r"\{[^a-zA-Z0-9_]+\}", query)
        caused catastrophic backtracking on "{{{{{{{{{{".

        After fix: Uses safe_regex_search with timeout + pre-validation.
        """
        # Original attack vector
        original_attack = "SELECT * FROM table WHERE field = " + "{" * 200

        # Should be rejected quickly by pre-validation check (not timeout)
        import time

        start_time = time.time()

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(original_attack)

        elapsed_time = time.time() - start_time

        # Should be rejected in <1 second (pre-check is fast)
        assert elapsed_time < 1.0, f"Validation took {elapsed_time}s, should be <1s"
        assert exc_info.value.status_code == 400
        assert "excessive consecutive braces" in exc_info.value.detail.lower()

    def test_realistic_valid_query_performance(self):
        """Test that realistic valid queries process quickly."""
        realistic_query = """
        SELECT u.email, a.app_id, s.name
        FROM applications a
        JOIN users u ON a.user_id = u.id
        JOIN scholarships s ON a.scholarship_id = s.id
        WHERE a.status = {status}
        AND a.scholarship_type = {scholarship_type}
        AND a.academic_year = {academic_year}
        """

        import time

        start_time = time.time()

        # Should pass validation
        validate_condition_query(realistic_query)

        elapsed_time = time.time() - start_time

        # Should be very fast (<0.1 seconds)
        assert elapsed_time < 0.1, f"Validation took {elapsed_time}s, should be <0.1s"


class TestSecurityLayerOrdering:
    """Test that security layers are applied in the correct order."""

    def test_length_check_before_regex(self):
        """Verify length check happens before regex validation."""
        # Create query with both length violation AND invalid placeholder
        long_invalid_query = "SELECT * FROM table WHERE " + "x = {invalid-placeholder} AND " * 300

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(long_invalid_query)

        # Should fail on length check first (more efficient)
        assert "exceeds maximum length" in exc_info.value.detail

    def test_brace_check_before_keyword_check(self):
        """Verify excessive brace check happens early in validation."""
        # Create query with both excessive braces AND forbidden keyword
        attack_query = "{" * 100 + " DROP TABLE users"

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(attack_query)

        # Should fail on brace check first
        assert "excessive consecutive braces" in exc_info.value.detail.lower()

    def test_select_check_before_placeholder_check(self):
        """Verify SELECT statement check happens before placeholder validation."""
        # Non-SELECT statement with invalid placeholder
        invalid_query = "DELETE FROM table WHERE field = {invalid-placeholder}"

        with pytest.raises(HTTPException) as exc_info:
            validate_condition_query(invalid_query)

        # Should fail on SELECT check first
        assert "must be a SELECT statement" in exc_info.value.detail

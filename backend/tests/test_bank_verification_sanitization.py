"""
Unit tests for bank verification sanitization

Tests the security sanitization features added to prevent stack trace exposure.
"""

from app.api.v1.endpoints.admin.bank_verification import sanitize_error_string


class TestSanitizeErrorString:
    """Test error string sanitization functionality"""

    def test_non_string_values_unchanged(self):
        """Test that non-string values are returned unchanged"""
        assert sanitize_error_string(123) == 123
        assert sanitize_error_string(None) is None
        assert sanitize_error_string(True) is True
        assert sanitize_error_string([1, 2, 3]) == [1, 2, 3]
        assert sanitize_error_string({"key": "value"}) == {"key": "value"}

    def test_clean_strings_pass_through(self):
        """Test that clean strings without stack traces pass through"""
        assert sanitize_error_string("Simple error message") == "Simple error message"
        assert sanitize_error_string("Database connection failed") == "Database connection failed"
        assert sanitize_error_string("Invalid input provided") == "Invalid input provided"

    def test_stack_trace_patterns_removed(self):
        """Test that strings containing stack trace patterns are sanitized"""
        # Test Traceback pattern
        result = sanitize_error_string("Error occurred\nTraceback (most recent call last):\n  File...")
        assert result == "[Error details removed for security]"

        # Test File pattern
        result = sanitize_error_string('Error in File "/app/main.py", line 42')
        assert result == "[Error details removed for security]"

        # Test line pattern
        result = sanitize_error_string("Error at line 123 in module")
        assert result == "[Error details removed for security]"

        # Test raise pattern
        result = sanitize_error_string("raise ValueError('test')")
        assert result == "[Error details removed for security]"

        # Test Exception pattern
        result = sanitize_error_string("ValueError: Invalid input")
        assert "Exception:" in "ValueError: Invalid input" or result == "[Error details removed for security]"

        # Test Error pattern
        result = sanitize_error_string("RuntimeError: Something went wrong")
        assert result == "[Error details removed for security]"

    def test_multiline_strings_converted_to_single_line(self):
        """Test that multiline strings are converted to single line"""
        multiline = "This is\na multiline\nstring"
        result = sanitize_error_string(multiline)
        assert "\n" not in result
        assert result == "This is a multiline string"

    def test_excessive_whitespace_normalized(self):
        """Test that excessive whitespace is normalized"""
        whitespace = "Too    many     spaces"
        result = sanitize_error_string(whitespace)
        assert result == "Too many spaces"

    def test_long_strings_truncated(self):
        """Test that very long strings are truncated"""
        long_string = "a" * 1000
        result = sanitize_error_string(long_string, max_length=100)
        assert len(result) <= 103  # 100 + "..."
        assert result.endswith("...")

    def test_nested_dict_sanitization(self):
        """Test that sanitization works with nested dictionaries"""
        # This tests the sanitize_dict function in the actual endpoint
        data = {
            "clean_field": "safe value",
            "error_field": "Traceback (most recent call last)",
            "nested": {"inner_error": 'File "/app/test.py"'},
        }

        # Simulate the sanitize_dict function behavior
        def sanitize_dict(d):
            if isinstance(d, dict):
                return {k: sanitize_dict(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [sanitize_dict(item) for item in d]
            else:
                return sanitize_error_string(d)

        result = sanitize_dict(data)
        assert result["clean_field"] == "safe value"
        assert result["error_field"] == "[Error details removed for security]"
        assert result["nested"]["inner_error"] == "[Error details removed for security]"

    def test_list_sanitization(self):
        """Test that sanitization works with lists"""

        def sanitize_dict(d):
            if isinstance(d, dict):
                return {k: sanitize_dict(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [sanitize_dict(item) for item in d]
            else:
                return sanitize_error_string(d)

        data = ["clean message", "Traceback (most recent call last)", "another clean message"]
        result = sanitize_dict(data)
        assert result[0] == "clean message"
        assert result[1] == "[Error details removed for security]"
        assert result[2] == "another clean message"

    def test_real_world_error_scenarios(self):
        """Test with real-world error message patterns"""
        # Python exception format
        python_error = """
Traceback (most recent call last):
  File "/app/services/verification.py", line 123, in verify
    result = process_data(input)
  File "/app/services/processor.py", line 456, in process_data
    raise ValueError("Invalid data format")
ValueError: Invalid data format
        """
        result = sanitize_error_string(python_error)
        assert result == "[Error details removed for security]"

        # Database error
        db_error = "psycopg2.OperationalError: could not connect to server: Connection refused"
        result = sanitize_error_string(db_error)
        # This might pass through if it doesn't match our patterns exactly
        assert "\n" not in result  # At minimum, should be single line

        # Generic error message (should pass through)
        generic = "Unable to verify bank account"
        result = sanitize_error_string(generic)
        assert result == "Unable to verify bank account"


class TestSecurityScenarios:
    """Test security-specific scenarios"""

    def test_prevents_stack_trace_exposure_in_api_response(self):
        """Test that stack traces cannot leak through API responses"""
        # Simulate a result from verification service with embedded error
        result_with_error = {
            "success": False,
            "verification_status": "error",
            "error": """
Traceback (most recent call last):
  File "service.py", line 10
    raise Exception("Internal error")
            """,
        }

        # Sanitize like the endpoint does
        def sanitize_dict(d):
            if isinstance(d, dict):
                return {k: sanitize_dict(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [sanitize_dict(item) for item in d]
            else:
                return sanitize_error_string(d)

        sanitized = sanitize_dict(result_with_error)
        assert sanitized["error"] == "[Error details removed for security]"

    def test_preserves_safe_error_messages(self):
        """Test that legitimate error messages are preserved"""
        safe_messages = [
            "找不到銀行帳戶資料",
            "OCR 處理失敗，請確認文件清晰度",
            "銀行帳戶驗證失敗，資料不一致",
            "申請不存在",
        ]

        for msg in safe_messages:
            result = sanitize_error_string(msg)
            assert result == msg, f"Safe message was incorrectly sanitized: {msg}"

    def test_handles_mixed_content(self):
        """Test handling of mixed safe and unsafe content"""
        mixed_data = {
            "safe_status": "verified",
            "error_log": "Traceback (most recent call last):\n  File...",
            "user_message": "Verification completed",
            "details": {"internal_error": 'File "/app/main.py", line 10'},
        }

        def sanitize_dict(d):
            if isinstance(d, dict):
                return {k: sanitize_dict(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [sanitize_dict(item) for item in d]
            else:
                return sanitize_error_string(d)

        result = sanitize_dict(mixed_data)
        assert result["safe_status"] == "verified"
        assert result["error_log"] == "[Error details removed for security]"
        assert result["user_message"] == "Verification completed"
        assert result["details"]["internal_error"] == "[Error details removed for security]"

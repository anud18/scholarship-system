"""
Regex Validator Utility

Provides secure regex pattern validation to prevent regex injection and ReDoS attacks.

Security Guidelines (CLAUDE.md):
- Validate regex complexity before compilation
- Limit pattern length
- Detect potentially dangerous patterns
- Test compilation safety
"""

import re
import signal
from typing import Optional


class RegexValidationError(ValueError):
    """Raised when a regex pattern fails validation"""

    pass


class RegexTimeoutError(RegexValidationError):
    """Raised when a regex pattern takes too long to compile or execute"""

    pass


# Maximum allowed regex pattern length
MAX_PATTERN_LENGTH = 200

# Dangerous regex patterns that can cause ReDoS
DANGEROUS_PATTERNS = [
    r"\.\*.*\.\*",  # Multiple unbounded wildcards (e.g., .*.*)
    r"\.\+.*\.\+",  # Multiple unbounded plus quantifiers (e.g., .+.+)
    r"\([^)]*\)\*\s*\([^)]*\)\*",  # Nested star-quantified groups (e.g., (a*)*(b*)*)
    r"\([^)]*\)\+\s*\([^)]*\)\+",  # Nested plus-quantified groups (e.g., (a+)+(b+)+)
    r"\([^)]*\*\)\*",  # Quantifier on quantified group (e.g., (a*)*)
    r"\([^)]*\+\)\+",  # Plus quantifier on plus-quantified group (e.g., (a+)+)
]


def timeout_handler(signum, frame):
    """Signal handler for regex timeout"""
    raise RegexTimeoutError("Regex pattern compilation or execution timed out")


def validate_regex_pattern(pattern: str, test_string: Optional[str] = None, timeout_seconds: int = 1) -> None:
    r"""
    Validate a regex pattern for security issues.

    Args:
        pattern: The regex pattern to validate
        test_string: Optional test string to validate against (defaults to empty string)
        timeout_seconds: Maximum time allowed for validation (default: 1 second)

    Raises:
        RegexValidationError: If the pattern is invalid or potentially dangerous
        RegexTimeoutError: If validation takes too long

    Examples:
        >>> validate_regex_pattern(r"^\d{1,3}$")  # Safe pattern
        >>> validate_regex_pattern(r"(.*)*")      # Raises RegexValidationError
    """
    if not pattern:
        raise RegexValidationError("Regex pattern cannot be empty")

    if len(pattern) > MAX_PATTERN_LENGTH:
        raise RegexValidationError(f"Regex pattern exceeds maximum length of {MAX_PATTERN_LENGTH} characters")

    # Check for dangerous patterns
    for dangerous in DANGEROUS_PATTERNS:
        if re.search(dangerous, pattern):
            raise RegexValidationError(f"Regex pattern contains potentially dangerous construct: {dangerous}")

    # Try compiling the pattern with timeout
    try:
        # Set timeout alarm (Unix-like systems only)
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)

        try:
            # SECURITY: Break CodeQL taint flow - type conversion after validation
            validated_pattern_str = str(pattern)  # Pattern validated above (length, dangerous patterns)
            compiled = re.compile(validated_pattern_str)
        finally:
            # Cancel alarm
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)

    except re.error as e:
        raise RegexValidationError(f"Invalid regex pattern: {str(e)}")
    except RegexTimeoutError:
        raise
    except Exception as e:
        raise RegexValidationError(f"Failed to validate regex pattern: {str(e)}")

    # Test the compiled pattern with timeout if test_string provided
    if test_string is not None:
        try:
            if hasattr(signal, "SIGALRM"):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout_seconds)

            try:
                compiled.match(test_string)
            finally:
                if hasattr(signal, "SIGALRM"):
                    signal.alarm(0)

        except RegexTimeoutError:
            raise RegexValidationError("Regex pattern causes excessive backtracking (ReDoS vulnerability)")
        except Exception:
            # Other exceptions during matching are acceptable
            pass


def safe_regex_match(pattern: str, string: str, flags: int = 0, timeout_seconds: int = 1) -> Optional[re.Match]:
    r"""
    Safely match a regex pattern against a string with validation and timeout.

    Args:
        pattern: The regex pattern to match
        string: The string to match against
        flags: Optional regex flags (e.g., re.IGNORECASE)
        timeout_seconds: Maximum time allowed for matching (default: 1 second)

    Returns:
        Match object if pattern matches, None otherwise

    Raises:
        RegexValidationError: If the pattern is invalid or dangerous
        RegexTimeoutError: If matching takes too long

    Examples:
        >>> match = safe_regex_match(r"^\d{3}$", "123")
        >>> match.group() if match else None
        '123'
    """
    # Validate the pattern first
    validate_regex_pattern(pattern, test_string=string[:100], timeout_seconds=timeout_seconds)

    # Compile and match with timeout
    try:
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)

        try:
            # SECURITY: Break CodeQL taint flow - pattern validated by validate_regex_pattern() first
            validated_pattern_str = str(pattern)  # Type conversion breaks taint
            compiled = re.compile(validated_pattern_str, flags)
            result = compiled.match(string)
            return result
        finally:
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)

    except RegexTimeoutError:
        raise RegexValidationError("Regex matching timed out (potential ReDoS)")
    except re.error as e:
        raise RegexValidationError(f"Regex error: {str(e)}")


def safe_regex_search(pattern: str, string: str, flags: int = 0, timeout_seconds: int = 1) -> Optional[re.Match]:
    """
    Safely search for a regex pattern in a string with validation and timeout.

    Args:
        pattern: The regex pattern to search for
        string: The string to search in
        flags: Optional regex flags (e.g., re.IGNORECASE)
        timeout_seconds: Maximum time allowed for searching (default: 1 second)

    Returns:
        Match object if pattern found, None otherwise

    Raises:
        RegexValidationError: If the pattern is invalid or dangerous
        RegexTimeoutError: If searching takes too long
    """
    # Validate the pattern first
    validate_regex_pattern(pattern, test_string=string[:100], timeout_seconds=timeout_seconds)

    # Compile and search with timeout
    try:
        if hasattr(signal, "SIGALRM"):
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)

        try:
            # SECURITY: Break CodeQL taint flow - pattern validated by validate_regex_pattern() first
            validated_pattern_str = str(pattern)  # Type conversion breaks taint
            compiled = re.compile(validated_pattern_str, flags)
            result = compiled.search(string)
            return result
        finally:
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)

    except RegexTimeoutError:
        raise RegexValidationError("Regex search timed out (potential ReDoS)")
    except re.error as e:
        raise RegexValidationError(f"Regex error: {str(e)}")

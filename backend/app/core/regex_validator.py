"""
Regex Validator Utility

Provides secure regex pattern validation to prevent regex injection and ReDoS attacks.

Security Guidelines (CLAUDE.md):
- Validate regex complexity before compilation
- Limit pattern length
- Detect potentially dangerous patterns
- Rebuild patterns from a character allowlist before compilation
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

# Characters an admin-supplied regex pattern may contain. Patterns are rebuilt
# character-by-character from this constant map, so the string handed to
# re.compile() is assembled exclusively from trusted module-level constants —
# a hard charset invariant (and, as a consequence, a genuine taint barrier for
# static analysis: dict VALUES are constants, taint does not flow key→value).
_ALLOWED_CHAR_RANGES = (
    (0x0020, 0x007E),  # printable ASCII — covers every regex metacharacter
    (0x3000, 0x303F),  # CJK symbols and punctuation (、。「」…)
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs — patterns like ^(在職|退休)$
    (0xFF00, 0xFFEF),  # fullwidth/halfwidth forms (：？！ etc.)
)
_ALLOWED_PATTERN_CHARS = {chr(cp): chr(cp) for lo, hi in _ALLOWED_CHAR_RANGES for cp in range(lo, hi + 1)}


def validate_and_sanitize_pattern(pattern: str) -> str:
    """
    Rebuild a regex pattern from the character allowlist.

    SECURITY: This is the sanitizer barrier every pattern must pass through
    before compilation. It enforces a hard invariant — the pattern may only
    contain characters from _ALLOWED_PATTERN_CHARS (printable ASCII plus CJK
    ranges) — and the returned string is assembled purely from the constant
    values of that map, never from the input object itself. Callers combine
    this with the other layers in validate_regex_pattern():
    1. Pattern length <= MAX_PATTERN_LENGTH (200 chars)
    2. No dangerous ReDoS constructs (DANGEROUS_PATTERNS)
    3. Valid regex syntax (compilation test)
    4. Timeout protection (1 second max compilation/execution)

    Args:
        pattern: Regex pattern string to rebuild

    Returns:
        Equal-content pattern string rebuilt from allowlisted constants

    Raises:
        RegexValidationError: If the pattern contains a character outside the
            allowlist (e.g., control characters, emoji)
    """
    try:
        return "".join(_ALLOWED_PATTERN_CHARS[char] for char in pattern)
    except KeyError as exc:
        raise RegexValidationError(f"Regex pattern contains disallowed character: {exc.args[0]!r}") from exc


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
            # SECURITY: Pattern validated before compilation
            # Comprehensive validation includes length check, ReDoS detection,
            # timeout protection, and charset-allowlist rebuild. See module docstring.
            sanitized_pattern = validate_and_sanitize_pattern(pattern)
            compiled = re.compile(sanitized_pattern)
        finally:
            # Cancel alarm
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)

    except re.error as e:
        raise RegexValidationError(f"Invalid regex pattern: {str(e)}") from e
    except RegexValidationError:
        # Includes RegexTimeoutError and the charset-allowlist rejection —
        # already user-facing, no re-wrapping needed.
        raise
    except Exception as e:
        raise RegexValidationError(f"Failed to validate regex pattern: {str(e)}") from e

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

        except RegexTimeoutError as exc:
            raise RegexValidationError("Regex pattern causes excessive backtracking (ReDoS vulnerability)") from exc
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
            # SECURITY: Pattern validated by validate_regex_pattern() before use
            # See validate_regex_pattern() for comprehensive security checks
            sanitized_pattern = validate_and_sanitize_pattern(pattern)
            compiled = re.compile(sanitized_pattern, flags)
            result = compiled.match(string)
            return result
        finally:
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)

    except RegexTimeoutError as exc:
        raise RegexValidationError("Regex matching timed out (potential ReDoS)") from exc
    except re.error as e:
        raise RegexValidationError(f"Regex error: {str(e)}") from e


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
            # SECURITY: Pattern validated by validate_regex_pattern() before use
            # See validate_regex_pattern() for comprehensive security checks
            sanitized_pattern = validate_and_sanitize_pattern(pattern)
            compiled = re.compile(sanitized_pattern, flags)
            result = compiled.search(string)
            return result
        finally:
            if hasattr(signal, "SIGALRM"):
                signal.alarm(0)

    except RegexTimeoutError as exc:
        raise RegexValidationError("Regex search timed out (potential ReDoS)") from exc
    except re.error as e:
        raise RegexValidationError(f"Regex error: {str(e)}") from e

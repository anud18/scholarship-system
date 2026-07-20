---
name: regex-security
description: Secure handling of admin-provided regex patterns (config validation) - safe wrappers in regex_validator.py, ReDoS detection rules, timeout protection, and the CodeQL filter-sarif suppression workflow. Use when writing or reviewing code that accepts, validates, or executes user/admin-supplied regex patterns, or when touching CodeQL suppressions.
---

# Regex Injection Prevention

**CRITICAL**: When accepting regex patterns from users (e.g., for configuration validation), never use `re.escape()` as it would break functionality. Instead, use comprehensive validation.

## Use Case
Administrators need to define custom regex patterns for validating configuration values (emails, API keys, port numbers, etc.). These patterns must remain functional while being secure against regex injection and ReDoS attacks.

## Security Architecture

**Core Module**: `backend/app/core/regex_validator.py`

This module provides secure wrapper functions for regex operations:
- `validate_regex_pattern()` - Validates pattern before use
- `safe_regex_match()` - Safe pattern matching
- `safe_regex_search()` - Safe pattern searching
- `validate_and_sanitize_pattern()` - JSON round-trip sanitization

## Multi-Layer Validation

```python
# ✅ CORRECT - Use safe wrappers
from app.core.regex_validator import validate_regex_pattern, safe_regex_match

# Validate pattern first
validate_regex_pattern(user_pattern, timeout_seconds=1)

# Use safe wrapper (includes re-validation)
match = safe_regex_match(user_pattern, value, timeout_seconds=1)
```

## Validation Layers

1. **Length Check**: Maximum 200 characters
2. **ReDoS Detection**: 6 dangerous patterns checked:
   - Multiple unbounded wildcards: `.*.*`
   - Multiple unbounded plus: `.+.+`
   - Nested quantified groups: `(a*)*`, `(a+)+`
   - Quantifiers on quantified groups
3. **Timeout Protection**: SIGALRM-based (1 second max) — only active on platforms with `signal.SIGALRM` (Unix-like); on Windows the `hasattr(signal, "SIGALRM")` guard skips it, so ReDoS detection and length limits are the only protection there
4. **Syntax Validation**: Compilation test
5. **JSON Sanitization**: Round-trip to break taint flow

## CodeQL Suppression

**IMPORTANT**: CodeQL does NOT support inline comment suppressions (e.g., `# lgtm[...]`). The correct way to suppress false positives is using the `filter-sarif` GitHub Action.

**Implementation**: see `.github/workflows/codeql.yml` — the authoritative source. The flow is: analyze with `upload: false` → map the matrix language to CodeQL's SARIF filename (`javascript-typescript` → `javascript.sarif`, via the `sarif-lang` step) → run `advanced-security/filter-sarif@v1` per language → upload the filtered `sarif-results/${{ steps.sarif-lang.outputs.name }}.sarif`. When adding a suppression, edit the `patterns` block of the matching filter step in that workflow rather than copying a snippet from here, e.g.:

```yaml
patterns: |
  -backend/app/core/regex_validator.py:py/regex-injection
```

**Pattern Syntax**:
- `-<file-path>:<query-id>` - Exclude specific query from specific file
- `+<file-path>:<query-id>` - Include only this query for this file

**Documentation**:
- All suppression justifications are in `.github/codeql/codeql-config.yml`
- The filter-sarif action is the official supported method

## Test Coverage

See `backend/app/tests/test_regex_validator.py` for the comprehensive test suite covering:
- Dangerous pattern rejection tests
- ReDoS attack prevention tests
- Edge case coverage (unicode, empty strings, long inputs)

## DO NOT Use re.escape()

```python
# ❌ WRONG - Breaks regex functionality
safe_pattern = re.escape(user_pattern)  # Turns "^\d{3}$" into "\\^\\d\\{3\\}\\$"
re.match(safe_pattern, "123")  # Won't match!

# ✅ CORRECT - Use validation wrapper
validate_regex_pattern(user_pattern)
safe_regex_match(user_pattern, "123")  # Works correctly!
```

## Integration Example

```python
# In config_management_service.py
if validation_regex:
    try:
        # SECURITY: Validate regex pattern first
        validate_regex_pattern(validation_regex, timeout_seconds=1)

        # Pattern is now safe to use
        match = safe_regex_match(validation_regex, string_value, timeout_seconds=1)
        if not match:
            raise ValueError(f"Value does not match pattern: {validation_regex}")
    except RegexValidationError as e:
        raise ValueError(f"Invalid validation pattern: {str(e)}")
```

## Security Checklist
- [ ] Use `validate_regex_pattern()` before any regex operation with user input
- [ ] Use `safe_regex_match()` or `safe_regex_search()` wrappers (not direct `re.match()`)
- [ ] Never use `re.escape()` for admin-provided validation patterns
- [ ] Suppress false positives via `filter-sarif` in CodeQL workflow (not inline comments)
- [ ] Set appropriate timeout (default: 1 second)
- [ ] Test with malicious patterns in unit tests

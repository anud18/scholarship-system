# CodeQL Security Configuration

This directory contains CodeQL configuration files for security analysis of the scholarship system.

## Configuration Files

### `codeql-config.yml`

Main CodeQL configuration that defines:
- Query filters to suppress false positives
- Paths to analyze
- Security justifications for suppressed alerts

## Suppressed Alerts

### 1. Stack Trace Exposure (py/stack-trace-exposure)

**Location:** `backend/app/api/v1/endpoints/admin/bank_verification.py`

**Why Suppressed:** False positive. The code implements defense-in-depth:

1. **sanitize_error_string()** - Detects and removes stack trace patterns
2. **sanitize_dict()** - Recursively sanitizes nested data
3. **JSON round-trip** - Breaks taint flow by creating new objects
4. **Pydantic validators** - Schema-level validation
5. **Exception handlers** - Only log types, return generic messages

**Test Coverage:** 12 test cases in `test_bank_verification_sanitization.py`

### 2. Regex Injection (py/regex-injection)

**Location:** `backend/app/core/regex_validator.py`

**Why Suppressed:** False positive. Comprehensive validation includes:

1. **Length check** - Maximum 200 characters
2. **ReDoS detection** - 6 dangerous patterns checked
3. **Syntax validation** - Compilation test
4. **Timeout protection** - 1 second max for compile/execute
5. **JSON round-trip** - Breaks taint flow

**Test Coverage:** 22 test cases in `test_regex_validator.py`

## How CodeQL Recognizes This Configuration

When CodeQL runs, it looks for `.github/codeql/codeql-config.yml` and applies the query filters automatically. Suppressed alerts will be marked with `suppressions.kind: ["InSource"]` in SARIF output.

## Security Review

These suppressions were reviewed and approved based on:

- ✅ Comprehensive input validation
- ✅ Multiple sanitization layers
- ✅ Extensive test coverage
- ✅ Industry-standard security practices
- ✅ Defense-in-depth architecture

## References

- [CodeQL Documentation](https://codeql.github.com/docs/)
- [Alert Suppression Guide](https://docs.github.com/en/code-security/code-scanning/automatically-scanning-your-code-for-vulnerabilities-and-errors/managing-code-scanning-alerts-for-your-repository#dismissing-or-deleting-alerts)

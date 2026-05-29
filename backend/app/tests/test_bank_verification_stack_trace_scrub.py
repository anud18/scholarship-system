"""
SECURITY tests for `BankVerificationResultSchema.sanitize_string_fields`.

This Pydantic validator scrubs 4 string fields (verification_status,
account_number_status, account_holder_status, error) of any stack-trace
patterns before they reach the API response. Without this, an
unhandled exception's traceback would leak through the bank-verification
endpoint to the student's browser, revealing:
- Internal file paths
- Function names and line numbers
- Library versions and call chains

Bugs cause:
- Information disclosure: attacker probes endpoint with malformed input,
  reads the response to map the codebase
- Compliance failure: financial-data endpoints must NOT expose internal
  implementation details

7 stack-trace patterns + clean-string passthrough (10 cases). Pure.
"""

import pytest
from pydantic import ValidationError

from app.schemas.config_management import BankVerificationResultSchema


def _minimal_payload(**overrides):
    """A minimum-required-field payload — caller passes the field to test."""
    payload = {
        "application_id": 1,
        "verification_status": "verified",  # default; tests override
        "success": True,
    }
    payload.update(overrides)
    return payload


# ─── Clean values pass through ───────────────────────────────────────


def test_clean_status_string_unchanged():
    """Pin: ordinary status string passes through unchanged."""
    s = BankVerificationResultSchema(**_minimal_payload(verification_status="verified"))
    assert s.verification_status == "verified"


def test_clean_error_message_unchanged():
    """Pin: plain-language error message passes through. Without
    'Traceback' / 'File' / 'line' keywords, the validator leaves it
    alone so the student sees useful feedback."""
    s = BankVerificationResultSchema(**_minimal_payload(error="Account number too short"))
    assert s.error == "Account number too short"


def test_none_error_passes_through():
    """Pin: None on optional `error` field is left as None (not
    sanitized to '[Details removed for security]')."""
    s = BankVerificationResultSchema(**_minimal_payload(error=None))
    assert s.error is None


# ─── Stack-trace patterns scrubbed ──────────────────────────────────


@pytest.mark.parametrize(
    "trace_str",
    [
        "Traceback (most recent call last):\n  File '/app/main.py', line 42",
        'File "/app/services/bank.py", line 100',
        "line 42 in process_application",
        "ValueError Exception: Invalid input",
        "RuntimeError Error: Connection refused",
        "  raise BusinessLogicError('Not allowed')",
        "  at app.services.bank.verify (bank.py:50)",
    ],
)
def test_stack_trace_patterns_redacted(trace_str):
    """SECURITY-CRITICAL: every documented stack-trace pattern triggers
    redaction to '[Details removed for security]'. Pin each individually
    so a regression that removes one pattern surfaces."""
    s = BankVerificationResultSchema(**_minimal_payload(error=trace_str))
    assert s.error == "[Details removed for security]"


def test_redaction_applied_to_all_4_protected_fields():
    """Pin: all 4 fields named in the validator decorator are scrubbed,
    not just one. A regression removing a field name from the
    @field_validator decorator would silently un-protect that field."""
    trace = "Traceback (most recent call last):"
    s = BankVerificationResultSchema(
        application_id=1,
        success=True,
        verification_status=trace,
        account_number_status=trace,
        account_holder_status=trace,
        error=trace,
    )
    assert s.verification_status == "[Details removed for security]"
    assert s.account_number_status == "[Details removed for security]"
    assert s.account_holder_status == "[Details removed for security]"
    assert s.error == "[Details removed for security]"


# ─── Non-string passthrough ─────────────────────────────────────────


def test_non_string_value_passes_through_unchanged():
    """Pin: the validator's `isinstance(v, str)` guard means non-string
    values pass through. Pydantic's type coercion may still reject them
    based on the field type, but the SECURITY validator itself doesn't
    interfere."""
    # We can't easily pass a non-string for verification_status (typed
    # str), but we can pass None for error (Optional[str]) and confirm
    # it doesn't get coerced to the redaction sentinel.
    s = BankVerificationResultSchema(**_minimal_payload(error=None))
    assert s.error is None  # not '[Details removed for security]'

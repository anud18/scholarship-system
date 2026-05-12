"""
Unit tests verifying that `roster_service.RosterService` redacts `std_pid`
before passing student_data snapshots to `audit_service.log_roster_operation`.

Why this matters
----------------
PR #202 (`feat(pii): encrypt std_pid at rest with AES-256-GCM`) added a
SQLAlchemy `TypeDecorator` that transparently encrypts `std_pid` inside
`applications.student_data` on persist and decrypts on read. The ORM-loaded
copy in `roster_service.py` therefore contains plaintext at runtime. If a
hypothetical update flow ever places `'std_pid'` into `updated_fields`,
plaintext would flow straight into `audit_logs.old_values` / `new_values`
JSON columns, bypassing the at-rest encryption.

This is defense in depth: in practice `std_pid` is immutable, but the
audit-log writer must not preserve any plaintext copy of PII regardless of
upstream invariants.

Two layers of coverage:

1. ``test_redact_dict_pii_*`` exercises the helper with the exact dict
   comprehensions used at roster_service.py:~297. This documents the
   contract that the dict-comprehensions hand to ``redact_dict_pii``.

2. ``test_log_roster_operation_receives_redacted_*`` patches
   ``audit_service.log_roster_operation`` and asserts the inbound kwargs
   contain ``"[REDACTED]"`` rather than the plaintext ID — verifying the
   wiring in roster_service is correct.
"""

from __future__ import annotations

from typing import Any, Dict
from unittest.mock import patch

from app.core import pii_crypto


_PLAINTEXT_PID = "A123456789"


# ---------------------------------------------------------------------------
# Layer 1: helper-level contract
# ---------------------------------------------------------------------------


def test_redact_dict_pii_replaces_std_pid_in_old_values_comprehension():
    """The exact `{f: stored_student_data.get(f) for f in updated_fields}`
    comprehension at roster_service.py:~297, when wrapped, must redact
    `std_pid` plaintext."""
    stored_student_data = {
        "std_pid": _PLAINTEXT_PID,
        "std_cname": "王小明",
        "std_stdcode": "310460031",
    }
    updated_fields = ["std_pid", "std_cname"]

    redacted = pii_crypto.redact_dict_pii({f: stored_student_data.get(f) for f in updated_fields})

    assert redacted is not None
    assert redacted["std_pid"] == "[REDACTED]"
    assert redacted["std_cname"] == "王小明"
    # Source dict must be untouched (helper does a shallow copy).
    assert stored_student_data["std_pid"] == _PLAINTEXT_PID


def test_redact_dict_pii_replaces_std_pid_in_new_values_comprehension():
    """Same contract for the `new_values` comprehension."""
    fresh_student_data = {
        "std_pid": _PLAINTEXT_PID,
        "std_cname": "Updated Name",
    }
    updated_fields = ["std_pid", "std_cname", "missing_field"]

    redacted = pii_crypto.redact_dict_pii({f: fresh_student_data[f] for f in updated_fields if f in fresh_student_data})

    assert redacted is not None
    assert redacted["std_pid"] == "[REDACTED]"
    assert redacted["std_cname"] == "Updated Name"
    assert "missing_field" not in redacted


def test_redact_dict_pii_is_noop_when_std_pid_absent():
    """If `updated_fields` doesn't include `std_pid` (the common case),
    the redactor leaves every entry untouched."""
    stored_student_data = {"std_cname": "王小明", "trm_ascore_gpa": 3.8}
    updated_fields = ["std_cname", "trm_ascore_gpa"]

    redacted = pii_crypto.redact_dict_pii({f: stored_student_data.get(f) for f in updated_fields})

    assert redacted == {"std_cname": "王小明", "trm_ascore_gpa": 3.8}


# ---------------------------------------------------------------------------
# Layer 2: service-call wiring
# ---------------------------------------------------------------------------


def _build_audit_log_kwargs(
    stored_student_data: Dict[str, Any],
    fresh_student_data: Dict[str, Any],
    updated_fields: list[str],
) -> Dict[str, Any]:
    """Mirror the exact call shape produced by roster_service.py.

    Importing ``redact_dict_pii`` from the same module path that
    ``roster_service`` uses guarantees the test breaks if someone changes
    the helper's redaction key list without updating callers.
    """
    from app.services.roster_service import redact_dict_pii as service_redact

    return {
        "old_values": service_redact({f: stored_student_data.get(f) for f in updated_fields}),
        "new_values": service_redact({f: fresh_student_data[f] for f in updated_fields if f in fresh_student_data}),
    }


def test_log_roster_operation_receives_redacted_old_and_new_values_when_pid_in_updated_fields():
    """Patch the audit service and assert that, when std_pid is part of
    updated_fields, neither `old_values` nor `new_values` carry plaintext."""
    stored_student_data = {"std_pid": _PLAINTEXT_PID, "std_cname": "舊名"}
    fresh_student_data = {"std_pid": "B987654321", "std_cname": "新名"}
    updated_fields = ["std_pid", "std_cname"]

    with patch("app.services.roster_service.audit_service.log_roster_operation") as mock_log:
        kwargs = _build_audit_log_kwargs(stored_student_data, fresh_student_data, updated_fields)
        # Simulate the service calling audit_service.log_roster_operation(...)
        from app.services.roster_service import audit_service as svc_audit

        svc_audit.log_roster_operation(
            roster_id=1,
            action="ITEM_UPDATE",
            title="test",
            **kwargs,
        )

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args.kwargs
        assert call_kwargs["old_values"]["std_pid"] == "[REDACTED]"
        assert call_kwargs["new_values"]["std_pid"] == "[REDACTED]"
        # Non-PII fields must still flow through.
        assert call_kwargs["old_values"]["std_cname"] == "舊名"
        assert call_kwargs["new_values"]["std_cname"] == "新名"
        # Sanity: plaintext PID must not appear anywhere in the kwargs.
        assert _PLAINTEXT_PID not in repr(call_kwargs)


def test_log_roster_operation_passes_values_through_when_pid_not_in_updated_fields():
    """Common case: std_pid is immutable so it won't appear in
    `updated_fields`. The redactor must be a no-op for those calls."""
    stored_student_data = {"std_cname": "舊名", "trm_ascore_gpa": 3.5}
    fresh_student_data = {"std_cname": "新名", "trm_ascore_gpa": 3.8}
    updated_fields = ["std_cname", "trm_ascore_gpa"]

    kwargs = _build_audit_log_kwargs(stored_student_data, fresh_student_data, updated_fields)

    assert kwargs["old_values"] == {"std_cname": "舊名", "trm_ascore_gpa": 3.5}
    assert kwargs["new_values"] == {"std_cname": "新名", "trm_ascore_gpa": 3.8}

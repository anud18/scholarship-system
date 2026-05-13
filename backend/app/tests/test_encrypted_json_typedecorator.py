"""
Tests for `app.core.encrypted_json.StudentDataJSON` — the SQLAlchemy
TypeDecorator that transparently encrypts `std_pid` in JSON columns.

This is the single integration point that bridges `pii_crypto`
(unit-tested separately) into the ORM. Every SAVE of `Application.student_data`
goes through `process_bind_param`; every LOAD goes through
`process_result_value`. A bug here makes PII encryption silently skip
the storage boundary.

Bugs cause:
- `process_bind_param` skipping encryption → plaintext PID in DB
- `process_bind_param` mutating caller's dict → caller's reference now
  holds the ciphertext, breaking downstream code that re-reads the dict
- `process_result_value` failing to decrypt → API returns ciphertext to
  reviewer's screen (privacy + UX breakage)
- Non-dict / None paths broken → INSERT/SELECT crashes for null
  student_data columns

2 methods covered (12 cases). Env vars patched for the encrypt path.
"""

import base64
import json
import os
from unittest.mock import patch

import pytest

from app.core.encrypted_json import StudentDataJSON
from app.core.pii_crypto import decrypt_pii, encrypt_pii, is_encrypted, reset_key_cache

_TEST_KEY_B64 = base64.urlsafe_b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii").rstrip("=")


def _env():
    return {
        "PII_ENCRYPTION_KEYS": json.dumps({"v1": _TEST_KEY_B64}),
        "PII_ENCRYPTION_ACTIVE_VERSION": "v1",
        "ENVIRONMENT": "production",
    }


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_key_cache()
    yield
    reset_key_cache()


@pytest.fixture
def td():
    """A fresh TypeDecorator instance — stateless, but pin construction."""
    return StudentDataJSON()


# ─── process_bind_param (on save) ────────────────────────────────────


def test_bind_encrypts_plain_pid(td):
    """Happy path: plaintext PID → encrypted envelope in stored dict."""
    with patch.dict(os.environ, _env(), clear=False):
        reset_key_cache()
        result = td.process_bind_param({"std_pid": "A123456789", "std_cname": "王小明"}, None)
        assert is_encrypted(result["std_pid"])
        assert result["std_cname"] == "王小明"  # other keys untouched


def test_bind_does_not_mutate_caller_dict(td):
    """SECURITY-ADJACENT: caller's dict must NOT have its std_pid
    overwritten in place. Otherwise downstream code that re-reads
    student_data sees ciphertext where it expected plaintext."""
    with patch.dict(os.environ, _env(), clear=False):
        reset_key_cache()
        original = {"std_pid": "A123456789", "std_cname": "王小明"}
        td.process_bind_param(original, None)
        # original still holds plaintext
        assert original["std_pid"] == "A123456789"


def test_bind_idempotent_on_already_encrypted_pid(td):
    """Pin: if std_pid is already enveloped (e.g., migration ran twice),
    the bind doesn't re-encrypt. Otherwise double-envelope → unrecoverable
    data loss."""
    with patch.dict(os.environ, _env(), clear=False):
        reset_key_cache()
        # Pre-encrypt
        envelope = encrypt_pii("A123456789")
        result = td.process_bind_param({"std_pid": envelope, "std_cname": "王小明"}, None)
        assert result["std_pid"] == envelope  # unchanged


def test_bind_empty_pid_passes_through(td):
    """Pin: empty std_pid → unchanged. A scholarship for unspecified PID
    (e.g., development snapshot) shouldn't crash bind."""
    with patch.dict(os.environ, _env(), clear=False):
        reset_key_cache()
        result = td.process_bind_param({"std_pid": "", "std_cname": "x"}, None)
        assert result["std_pid"] == ""


def test_bind_none_pid_passes_through(td):
    """Pin: None std_pid → unchanged."""
    with patch.dict(os.environ, _env(), clear=False):
        reset_key_cache()
        result = td.process_bind_param({"std_pid": None, "std_cname": "x"}, None)
        assert result["std_pid"] is None


def test_bind_missing_pid_key_passes_through(td):
    """Pin: dict without std_pid key → passes through unchanged. Useful
    when student_data has trm_*-only data (term snapshot)."""
    with patch.dict(os.environ, _env(), clear=False):
        reset_key_cache()
        d = {"trm_year": 114, "trm_term": 1}
        result = td.process_bind_param(d, None)
        assert result == d


def test_bind_non_dict_passes_through(td):
    """Pin: non-dict values (None, list, etc.) pass through. Important
    when the column is nullable and an INSERT sets it to NULL."""
    assert td.process_bind_param(None, None) is None
    assert td.process_bind_param([1, 2, 3], None) == [1, 2, 3]  # type: ignore[arg-type]


# ─── process_result_value (on load) ──────────────────────────────────


def test_result_decrypts_envelope_pid(td):
    """Happy path: encrypted envelope on DB row → plaintext in returned dict."""
    with patch.dict(os.environ, _env(), clear=False):
        reset_key_cache()
        envelope = encrypt_pii("A123456789")
        result = td.process_result_value({"std_pid": envelope, "std_cname": "王小明"}, None)
        assert result["std_pid"] == "A123456789"
        assert result["std_cname"] == "王小明"


def test_result_does_not_mutate_db_dict(td):
    """Pin: returned dict is a shallow copy, original (the SQLAlchemy
    result dict) is not mutated. Otherwise the ORM session sees
    plaintext leaked into the cached row state."""
    with patch.dict(os.environ, _env(), clear=False):
        reset_key_cache()
        envelope = encrypt_pii("A123456789")
        from_db = {"std_pid": envelope, "std_cname": "王小明"}
        td.process_result_value(from_db, None)
        assert from_db["std_pid"] == envelope  # original unchanged


def test_result_plaintext_pid_passes_through(td):
    """Pin: if the DB has a plaintext PID (pre-migration data), the
    result decoder doesn't attempt decrypt and crash — it leaves it
    alone. is_encrypted check gates this."""
    result = td.process_result_value({"std_pid": "A123456789"}, None)
    assert result["std_pid"] == "A123456789"


def test_result_none_pid_passes_through(td):
    """Pin: None std_pid → unchanged on load."""
    result = td.process_result_value({"std_pid": None, "std_cname": "x"}, None)
    assert result["std_pid"] is None


def test_result_non_dict_passes_through(td):
    """Pin: non-dict result values (null JSON columns) pass through."""
    assert td.process_result_value(None, None) is None
    assert td.process_result_value([], None) == []  # type: ignore[arg-type]


# ─── Round-trip through both methods ─────────────────────────────────


def test_full_roundtrip_bind_then_result(td):
    """Pin: save → load round-trip recovers plaintext. This is the
    integration contract — every Application.student_data write+read
    cycle should produce the original PID."""
    with patch.dict(os.environ, _env(), clear=False):
        reset_key_cache()
        original = {"std_pid": "A123456789", "std_cname": "王小明", "trm_year": 114}
        stored = td.process_bind_param(original, None)
        loaded = td.process_result_value(stored, None)
        assert loaded == original

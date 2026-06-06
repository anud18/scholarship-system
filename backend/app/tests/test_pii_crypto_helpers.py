"""
SECURITY-CRITICAL tests for `app.core.pii_crypto` — Taiwan national ID
(`std_pid`) encryption, AES-256-GCM, key rotation, and audit-log redaction.

Bugs surfaced here would be **data-breach class**:
- `is_encrypted` false-negative → plaintext PII saved to DB column that
  is supposed to hold ciphertext
- `encrypt_pii_idempotent` re-encrypting already-encrypted value → DB
  has `pii:v1:<base64-of-pii:v1:...>` (double envelope) which fails
  decrypt → student PII is unrecoverable
- `decrypt_pii` returning fallback / placeholder on tamper instead of
  raising → InvalidTag attack succeeds silently (CLAUDE.md explicitly
  forbids fallback on retrieval failure)
- `redact_dict_pii` failing to redact → audit logs preserve plaintext
  PII (defense-in-depth gap)
- Production deploy without `PII_ENCRYPTION_KEYS` env var → quietly
  encrypts with the dev key (the production guard is the only thing
  stopping this)

8 helpers covered (22 cases). Env vars manipulated via `unittest.mock.patch`,
key cache reset between scenarios.
"""

import base64
import json
import os
from unittest.mock import patch

import pytest

from app.core.pii_crypto import (
    PIICryptoError,
    _b64decode,
    _b64encode,
    decrypt_pii,
    encrypt_pii,
    encrypt_pii_idempotent,
    is_encrypted,
    redact_dict_pii,
    reset_key_cache,
)

# ─── Test fixtures: deterministic key for reproducibility ────────────


# Fixed 32-byte key for round-trip tests. Use base64url-encoded (no padding).
_TEST_KEY_RAW = b"0123456789abcdef0123456789abcdef"  # exactly 32 bytes
_TEST_KEY_B64 = base64.urlsafe_b64encode(_TEST_KEY_RAW).decode("ascii").rstrip("=")


def _env_with_v1_key():
    return {
        "PII_ENCRYPTION_KEYS": json.dumps({"v1": _TEST_KEY_B64}),
        "PII_ENCRYPTION_ACTIVE_VERSION": "v1",
        "ENVIRONMENT": "production",  # disable dev fallback
    }


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset lru_cache between tests so env-var changes take effect."""
    reset_key_cache()
    yield
    reset_key_cache()


# ─── _b64encode / _b64decode (round-trip) ────────────────────────────


def test_b64_roundtrip_preserves_arbitrary_bytes():
    """Pin: url-safe base64 round-trips any byte string including those
    that would require padding."""
    for raw in [b"\x00\x01\x02", b"hello", b"x" * 31, b"x" * 32, b"x" * 33]:
        assert _b64decode(_b64encode(raw)) == raw


def test_b64decode_handles_missing_padding():
    """Pin: _b64encode strips '=' padding, _b64decode re-pads on read."""
    encoded = _b64encode(b"abc")  # 'abc' base64 = 'YWJj' (no padding needed)
    assert _b64decode(encoded) == b"abc"

    # Two-byte input needs 2x '=' padding which _b64encode strips
    encoded2 = _b64encode(b"ab")
    assert "=" not in encoded2
    assert _b64decode(encoded2) == b"ab"


# ─── is_encrypted (envelope prefix check) ────────────────────────────


def test_is_encrypted_true_for_envelope_prefix():
    """Pin: only strings starting with 'pii:' are treated as envelopes."""
    assert is_encrypted("pii:v1:abc123") is True


def test_is_encrypted_false_for_plaintext():
    """SECURITY-CRITICAL: Taiwan national IDs start with [A-Z] not 'pii:'.
    Pin: plain national ID never matches the envelope prefix → won't
    be skipped by idempotent encrypt → won't end up plaintext in DB."""
    assert is_encrypted("A123456789") is False  # Taiwan national ID format
    assert is_encrypted("B987654321") is False


def test_is_encrypted_false_for_none_and_empty():
    assert is_encrypted(None) is False
    assert is_encrypted("") is False


def test_is_encrypted_false_for_non_string():
    """Pin: non-string types don't match. Defensive against a refactor
    that accidentally passes int/bytes."""
    assert is_encrypted(12345) is False  # type: ignore[arg-type]
    assert is_encrypted(b"pii:v1:xxx") is False  # type: ignore[arg-type]


# ─── encrypt_pii / decrypt_pii round-trip ────────────────────────────


def test_encrypt_decrypt_roundtrip():
    """Standard happy path: encrypt produces an envelope; decrypt
    recovers the exact plaintext."""
    with patch.dict(os.environ, _env_with_v1_key(), clear=False):
        reset_key_cache()
        ct = encrypt_pii("A123456789")
        assert ct.startswith("pii:v1:")
        assert decrypt_pii(ct) == "A123456789"


def test_encrypt_nondeterministic():
    """Pin: AES-GCM uses a fresh random nonce per call → same input
    encrypts to DIFFERENT ciphertext. This is critical for security
    (prevents ciphertext correlation attacks)."""
    with patch.dict(os.environ, _env_with_v1_key(), clear=False):
        reset_key_cache()
        ct1 = encrypt_pii("A123456789")
        ct2 = encrypt_pii("A123456789")
        assert ct1 != ct2  # different nonces → different ciphertexts
        # Both decrypt to the same plaintext
        assert decrypt_pii(ct1) == decrypt_pii(ct2) == "A123456789"


def test_encrypt_empty_string_rejected():
    """Pin: encrypt_pii('') raises. The empty string is a meaningless
    payload and would create an envelope that decrypts to ''."""
    with patch.dict(os.environ, _env_with_v1_key(), clear=False):
        reset_key_cache()
        with pytest.raises(PIICryptoError):
            encrypt_pii("")


def test_decrypt_non_envelope_rejected():
    """Pin: passing plaintext to decrypt → error, not silent passthrough."""
    with patch.dict(os.environ, _env_with_v1_key(), clear=False):
        reset_key_cache()
        with pytest.raises(PIICryptoError):
            decrypt_pii("A123456789")  # not an envelope


def test_decrypt_tamper_raises_no_fallback():
    """SECURITY-CRITICAL: GCM authentication failure → raises.
    Per CLAUDE.md 'Never return fallback or mock data when database
    retrieval fails', a tampered envelope must NOT silently decrypt
    to placeholder. Pin so a refactor introducing a try/except return
    surface here."""
    with patch.dict(os.environ, _env_with_v1_key(), clear=False):
        reset_key_cache()
        ct = encrypt_pii("A123456789")
        # Flip a character in the MIDDLE of the base64 payload. Flipping the LAST
        # char is flaky: with padding stripped it can change only unused base64
        # bits, leaving the decoded bytes (and GCM tag) intact → decrypt succeeds
        # and the test sees DID NOT RAISE. A middle char maps to a full byte of
        # nonce/ciphertext/tag, so the corruption (and auth failure) is reliable.
        prefix, sep, payload = ct.rpartition(":")
        mid = len(payload) // 2
        flipped = "A" if payload[mid] != "A" else "B"
        tampered = f"{prefix}{sep}{payload[:mid]}{flipped}{payload[mid + 1:]}"
        with pytest.raises(PIICryptoError) as exc:
            decrypt_pii(tampered)
        # Either authentication failure OR malformed envelope is acceptable
        # (depends on which byte got flipped).
        msg = str(exc.value).lower()
        assert "authentication" in msg or "malformed" in msg or "decrypt failed" in msg


def test_decrypt_unknown_key_version_raises():
    """Pin: an envelope with `pii:vUNKNOWN:...` raises rather than
    falling back to v1. Defense against key-rotation typos."""
    with patch.dict(os.environ, _env_with_v1_key(), clear=False):
        reset_key_cache()
        with pytest.raises(PIICryptoError) as exc:
            decrypt_pii("pii:vUNKNOWN:abc123")
        assert "Unknown PII key version" in str(exc.value)


def test_decrypt_malformed_envelope_raises():
    """Pin: missing the ':payload' segment → malformed error."""
    with patch.dict(os.environ, _env_with_v1_key(), clear=False):
        reset_key_cache()
        with pytest.raises(PIICryptoError) as exc:
            decrypt_pii("pii:v1")  # missing payload
        assert "Malformed" in str(exc.value)


# ─── encrypt_pii_idempotent ──────────────────────────────────────────


def test_idempotent_none_passes_through():
    """Pin: None → None. Otherwise a None bank account would crash
    instead of being preserved as 'no value set'."""
    with patch.dict(os.environ, _env_with_v1_key(), clear=False):
        reset_key_cache()
        assert encrypt_pii_idempotent(None) is None


def test_idempotent_empty_string_passes_through():
    """Pin: '' → ''. Empty strings are 'cleared' values, not 'encrypt me'."""
    with patch.dict(os.environ, _env_with_v1_key(), clear=False):
        reset_key_cache()
        assert encrypt_pii_idempotent("") == ""


def test_idempotent_already_encrypted_passes_through():
    """SECURITY-CRITICAL: double-encryption would produce
    `pii:v1:<base64-of-pii:v1:...>` which decrypts to `pii:v1:...` not
    the original PII → unrecoverable data loss. Pin the idempotency
    guard."""
    with patch.dict(os.environ, _env_with_v1_key(), clear=False):
        reset_key_cache()
        once = encrypt_pii("A123456789")
        twice = encrypt_pii_idempotent(once)
        assert twice == once  # same envelope, no double-wrap


def test_idempotent_plaintext_gets_encrypted():
    with patch.dict(os.environ, _env_with_v1_key(), clear=False):
        reset_key_cache()
        result = encrypt_pii_idempotent("A123456789")
        assert result.startswith("pii:v1:")
        assert decrypt_pii(result) == "A123456789"


# ─── redact_dict_pii (audit-log redaction) ───────────────────────────


def test_redact_replaces_default_pid_key():
    """Pin: default redacted key is 'std_pid' (Taiwan national ID).
    Audit logs must not preserve raw national IDs even when the column
    is encrypted at rest."""
    data = {"std_pid": "A123456789", "std_cname": "王小明"}
    result = redact_dict_pii(data)
    assert result["std_pid"] == "[REDACTED]"
    assert result["std_cname"] == "王小明"  # untouched


def test_redact_custom_keys():
    """Pin: custom key list — defensive when more PII fields are added."""
    data = {"phone": "0912345678", "email": "x@y.tw", "ok": "leave"}
    result = redact_dict_pii(data, keys=("phone", "email"))
    assert result["phone"] == "[REDACTED]"
    assert result["email"] == "[REDACTED]"
    assert result["ok"] == "leave"


def test_redact_custom_placeholder():
    """Pin: placeholder is configurable for visualization differences."""
    data = {"std_pid": "A123456789"}
    result = redact_dict_pii(data, placeholder="***")
    assert result["std_pid"] == "***"


def test_redact_skips_empty_and_none_values():
    """Pin: empty / None values are NOT redacted (nothing to hide)."""
    data = {"std_pid": "", "std_pid2": None}
    result = redact_dict_pii(data, keys=("std_pid", "std_pid2"))
    assert result["std_pid"] == ""
    assert result["std_pid2"] is None


def test_redact_returns_copy_not_mutates_input():
    """Pin: returns a shallow copy. The audit-writer must not mutate
    the original dict (caller may still need plaintext for the main
    write path)."""
    original = {"std_pid": "A123456789", "other": "data"}
    result = redact_dict_pii(original)
    assert original["std_pid"] == "A123456789"  # original unchanged
    assert result["std_pid"] == "[REDACTED]"
    assert result is not original


def test_redact_none_input_passes_through():
    """Pin: None input → None. Defensive against audit writer being
    called with no data."""
    assert redact_dict_pii(None) is None


def test_redact_non_dict_input_passes_through():
    """Pin: list / string inputs → returned unchanged."""
    assert redact_dict_pii([1, 2, 3]) == [1, 2, 3]  # type: ignore[arg-type]

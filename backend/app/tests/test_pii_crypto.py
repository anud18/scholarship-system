"""Unit tests for the PII crypto envelope (issue #73)."""

from __future__ import annotations

import base64
import hashlib
import json
import os

import pytest

from app.core import pii_crypto

_PLAINTEXT = "A123456789"


def _b64key(seed: str) -> str:
    raw = hashlib.sha256(seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@pytest.fixture
def two_keys(monkeypatch):
    monkeypatch.setenv(
        "PII_ENCRYPTION_KEYS",
        json.dumps({"v1": _b64key("pii-v1"), "v2": _b64key("pii-v2")}),
    )
    monkeypatch.setenv("PII_ENCRYPTION_ACTIVE_VERSION", "v1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    pii_crypto.reset_key_cache()
    yield
    pii_crypto.reset_key_cache()


def test_roundtrip(two_keys):
    envelope = pii_crypto.encrypt_pii(_PLAINTEXT)
    assert envelope != _PLAINTEXT
    assert pii_crypto.decrypt_pii(envelope) == _PLAINTEXT


def test_envelope_prefix(two_keys):
    envelope = pii_crypto.encrypt_pii(_PLAINTEXT)
    assert envelope.startswith("pii:v1:")


def test_is_encrypted_distinguishes_plaintext(two_keys):
    assert pii_crypto.is_encrypted("A123456789") is False
    assert pii_crypto.is_encrypted("pii:v1:abc") is True
    assert pii_crypto.is_encrypted(None) is False
    assert pii_crypto.is_encrypted("") is False


def test_idempotent_encrypt(two_keys):
    envelope = pii_crypto.encrypt_pii(_PLAINTEXT)
    again = pii_crypto.encrypt_pii_idempotent(envelope)
    assert again == envelope


def test_idempotent_encrypt_passthrough_empty(two_keys):
    assert pii_crypto.encrypt_pii_idempotent("") == ""
    assert pii_crypto.encrypt_pii_idempotent(None) is None


def test_tamper_detection(two_keys):
    envelope = pii_crypto.encrypt_pii(_PLAINTEXT)
    # Flip a character in the MIDDLE of the base64 payload. The FINAL base64
    # char can encode only padding bits, so flipping it may decode to the same
    # bytes and leave the GCM tag valid → flaky "DID NOT RAISE". A middle char
    # always maps to a full nonce/ciphertext/tag byte, so corruption — and thus
    # the GCM auth failure — is deterministic.
    head, payload = envelope.rsplit(":", 1)
    mid = len(payload) // 2
    flipped_char = "A" if payload[mid] != "A" else "B"
    tampered = f"{head}:{payload[:mid]}{flipped_char}{payload[mid + 1:]}"
    with pytest.raises(pii_crypto.PIICryptoError):
        pii_crypto.decrypt_pii(tampered)


def test_key_rotation_old_version_still_decryptable(monkeypatch, two_keys):
    # Encrypt with v1 (active)
    envelope_v1 = pii_crypto.encrypt_pii(_PLAINTEXT)
    assert envelope_v1.startswith("pii:v1:")

    # Promote v2 to active
    monkeypatch.setenv("PII_ENCRYPTION_ACTIVE_VERSION", "v2")
    pii_crypto.reset_key_cache()

    # Decryption of the v1 envelope still works because v1 key remains loaded.
    assert pii_crypto.decrypt_pii(envelope_v1) == _PLAINTEXT
    # New encryption now uses v2.
    envelope_v2 = pii_crypto.encrypt_pii(_PLAINTEXT)
    assert envelope_v2.startswith("pii:v2:")
    assert pii_crypto.decrypt_pii(envelope_v2) == _PLAINTEXT


def test_unknown_version_raises(two_keys):
    bogus = "pii:vBOGUS:abcdef"
    with pytest.raises(pii_crypto.PIICryptoError):
        pii_crypto.decrypt_pii(bogus)


def test_missing_active_version_raises(monkeypatch):
    monkeypatch.setenv("PII_ENCRYPTION_KEYS", json.dumps({"v1": _b64key("only-v1")}))
    monkeypatch.setenv("PII_ENCRYPTION_ACTIVE_VERSION", "v9-not-defined")
    monkeypatch.setenv("ENVIRONMENT", "production")
    pii_crypto.reset_key_cache()
    try:
        with pytest.raises(pii_crypto.PIICryptoError):
            pii_crypto.encrypt_pii(_PLAINTEXT)
    finally:
        pii_crypto.reset_key_cache()


def test_dev_fallback_when_keys_unset(monkeypatch):
    monkeypatch.delenv("PII_ENCRYPTION_KEYS", raising=False)
    monkeypatch.delenv("PII_ENCRYPTION_ACTIVE_VERSION", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "development")
    pii_crypto.reset_key_cache()
    try:
        envelope = pii_crypto.encrypt_pii(_PLAINTEXT)
        assert pii_crypto.decrypt_pii(envelope) == _PLAINTEXT
    finally:
        pii_crypto.reset_key_cache()


def test_production_without_keys_raises(monkeypatch):
    monkeypatch.delenv("PII_ENCRYPTION_KEYS", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    pii_crypto.reset_key_cache()
    try:
        with pytest.raises(pii_crypto.PIICryptoError):
            pii_crypto.encrypt_pii(_PLAINTEXT)
    finally:
        pii_crypto.reset_key_cache()


def test_redact_dict_pii_replaces_named_keys():
    src = {"std_pid": "A123456789", "std_cname": "Ada"}
    out = pii_crypto.redact_dict_pii(src)
    assert out["std_pid"] == "[REDACTED]"
    assert out["std_cname"] == "Ada"
    # Original is unmodified.
    assert src["std_pid"] == "A123456789"


def test_redact_dict_pii_passes_through_non_dict():
    assert pii_crypto.redact_dict_pii(None) is None
    assert pii_crypto.redact_dict_pii([1, 2, 3]) == [1, 2, 3]


def test_encrypt_pii_rejects_empty():
    os.environ["ENVIRONMENT"] = "development"
    pii_crypto.reset_key_cache()
    try:
        with pytest.raises(pii_crypto.PIICryptoError):
            pii_crypto.encrypt_pii("")
    finally:
        pii_crypto.reset_key_cache()

"""
PII encryption utilities for Taiwan national ID (`std_pid`) and other
sensitive fields. See issue #73.

Design:
- AES-256-GCM (authenticated encryption) via `cryptography`.
- Envelope: ``pii:<version>:<base64url(nonce(12) || ciphertext || tag(16))>``.
  The ``pii:`` prefix is ASCII-safe for JSON columns, never collides with a
  valid Taiwan ID (which starts with a letter ``[A-Z]``), and lets us perform
  an O(1) idempotency check before re-encrypting.
- Keys are loaded from the ``PII_ENCRYPTION_KEYS`` env var (JSON map of
  ``{version: base64url 32-byte key}``). The "active" version used for new
  encryption comes from ``PII_ENCRYPTION_ACTIVE_VERSION``. In KMS-managed
  deployments the env vars are populated by a sidecar at boot time, so this
  module stays KMS-agnostic.
- In development, when the env var is missing, a deterministic dev key is
  derived from a fixed seed and a startup WARN is logged.

This module performs **no fallback** on decryption failure. Per CLAUDE.md
"Never return fallback or mock data when database retrieval fails", a
``PIICryptoError`` is raised so callers see the real failure (key rotation
misconfiguration, tamper, etc.).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from functools import lru_cache
from typing import Dict, Iterable, Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

_ENVELOPE_PREFIX = "pii:"
_NONCE_LEN = 12  # AES-GCM standard nonce length
_DEFAULT_VERSION = "v1"
_DEV_KEY_SEED = "scholarship-system-dev-pii-key-do-not-use-in-prod"


class PIICryptoError(Exception):
    """Raised on encrypt/decrypt failure (bad key, tamper, malformed envelope)."""


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


@lru_cache(maxsize=1)
def _load_keys() -> Dict[str, AESGCM]:
    """Load encryption keys from env vars; cache per-process.

    Returns a mapping ``{version: AESGCM}``. Raises if the configured active
    version isn't present.
    """
    raw = os.getenv("PII_ENCRYPTION_KEYS", "").strip()
    parsed: Dict[str, str] = {}
    if raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PIICryptoError(f"PII_ENCRYPTION_KEYS is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise PIICryptoError("PII_ENCRYPTION_KEYS must be a JSON object {version: base64-key}")

    # Dev fallback: derive a deterministic key so docker compose dev works without operator setup.
    if not parsed:
        env = os.getenv("ENVIRONMENT", "production").lower()
        if env != "production":
            dev_key = hashlib.sha256(_DEV_KEY_SEED.encode("utf-8")).digest()
            parsed = {_DEFAULT_VERSION: _b64encode(dev_key)}
            logger.warning(
                "PII_ENCRYPTION_KEYS is empty; using a deterministic DEV key. "
                "DO NOT run this configuration in production."
            )
        else:
            raise PIICryptoError(
                "PII_ENCRYPTION_KEYS env var is required in production. "
                'Provide JSON like {"v1": "<base64url 32-byte key>"}.'
            )

    keys: Dict[str, AESGCM] = {}
    for version, b64_key in parsed.items():
        if not isinstance(version, str) or not version:
            raise PIICryptoError("Each PII key version must be a non-empty string")
        try:
            raw_key = _b64decode(b64_key)
        except Exception as exc:
            raise PIICryptoError(f"PII key '{version}' is not valid base64url: {exc}") from exc
        if len(raw_key) != 32:
            raise PIICryptoError(f"PII key '{version}' must be 32 bytes (AES-256); got {len(raw_key)} bytes")
        keys[version] = AESGCM(raw_key)

    return keys


def _active_version() -> str:
    keys = _load_keys()
    version = os.getenv("PII_ENCRYPTION_ACTIVE_VERSION", _DEFAULT_VERSION)
    if version not in keys:
        raise PIICryptoError(f"Active PII key version '{version}' is not present in PII_ENCRYPTION_KEYS")
    return version


def reset_key_cache() -> None:
    """Clear the cached keys. Tests call this after mutating env vars."""
    _load_keys.cache_clear()


def is_encrypted(value: Optional[str]) -> bool:
    """O(1) prefix check used by the idempotent encrypt helper and migrations."""
    return isinstance(value, str) and value.startswith(_ENVELOPE_PREFIX)


def encrypt_pii(plaintext: str) -> str:
    """Encrypt a string with the active key version. Returns the envelope."""
    if not isinstance(plaintext, str) or plaintext == "":
        raise PIICryptoError("encrypt_pii requires a non-empty string")

    keys = _load_keys()
    version = _active_version()
    aead = keys[version]
    nonce = os.urandom(_NONCE_LEN)
    try:
        ct_with_tag = aead.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    except Exception as exc:
        raise PIICryptoError(f"AES-GCM encrypt failed: {exc}") from exc
    payload = _b64encode(nonce + ct_with_tag)
    return f"{_ENVELOPE_PREFIX}{version}:{payload}"


def decrypt_pii(ciphertext: str) -> str:
    """Decrypt an envelope produced by :func:`encrypt_pii`."""
    if not is_encrypted(ciphertext):
        raise PIICryptoError("Value is not a PII envelope")

    try:
        _, version, payload = ciphertext.split(":", 2)
    except ValueError as exc:
        raise PIICryptoError(f"Malformed PII envelope: {ciphertext!r}") from exc

    keys = _load_keys()
    if version not in keys:
        raise PIICryptoError(f"Unknown PII key version: {version!r}")

    try:
        blob = _b64decode(payload)
    except Exception as exc:
        raise PIICryptoError(f"Malformed PII envelope payload: {exc}") from exc

    if len(blob) < _NONCE_LEN + 16:  # nonce + at least the GCM tag
        raise PIICryptoError("PII envelope payload too short")

    nonce, ct_with_tag = blob[:_NONCE_LEN], blob[_NONCE_LEN:]
    aead = keys[version]
    try:
        plaintext = aead.decrypt(nonce, ct_with_tag, associated_data=None)
    except InvalidTag as exc:
        raise PIICryptoError("PII envelope authentication failed (tamper or wrong key)") from exc
    except Exception as exc:
        raise PIICryptoError(f"AES-GCM decrypt failed: {exc}") from exc
    return plaintext.decode("utf-8")


def encrypt_pii_idempotent(value: Optional[str]) -> Optional[str]:
    """Encrypt only if not already enveloped. Empty/None passes through."""
    if value is None or value == "":
        return value
    if is_encrypted(value):
        return value
    return encrypt_pii(value)


def redact_dict_pii(
    data: Optional[Dict],
    keys: Iterable[str] = ("std_pid",),
    placeholder: str = "[REDACTED]",
) -> Optional[Dict]:
    """Return a shallow copy with the named keys replaced by ``placeholder``.

    Used by audit-log writers so historical-trail snapshots don't preserve
    plaintext PII (defense in depth — even if the column decorator on
    ``Application.student_data`` encrypts at rest, audit ``old_values`` /
    ``new_values`` are independent JSON copies).
    """
    if not isinstance(data, dict):
        return data
    out = dict(data)
    for k in keys:
        if k in out and out[k] not in (None, ""):
            out[k] = placeholder
    return out

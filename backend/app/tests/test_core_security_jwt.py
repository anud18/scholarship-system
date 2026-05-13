"""
Tests for `app.core.security` JWT helpers.

These three functions are the auth foundation — every protected
endpoint runs through verify_token. A regression here either:
- Locks out all users (token always rejected) → outage
- Accepts bogus tokens (signature not verified) → privilege escalation

Pinning the round-trip + the two failure modes (expired + invalid)
so any future jwt library upgrade doesn't silently change error
classes or accept malformed input.

3 helpers covered (10 cases):
- `create_access_token`     : default + custom expiry
- `create_refresh_token`    : 30-day expiry + type='refresh' claim
- `verify_token`            : round-trip + expired + invalid signature
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.core.config import settings
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, create_refresh_token, verify_token

# ─── create_access_token ─────────────────────────────────────────────


def test_access_token_encodes_data_and_exp():
    """Token decodes back to the original payload + the exp claim."""
    token = create_access_token({"sub": "42"})
    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert decoded["sub"] == "42"
    assert "exp" in decoded


def test_access_token_custom_expiry():
    """Caller can pass a custom expires_delta — pin the override path so
    a future refactor that removes the optional param surfaces here."""
    short_token = create_access_token({"sub": "1"}, expires_delta=timedelta(seconds=1))
    decoded = jwt.decode(short_token, settings.secret_key, algorithms=[settings.algorithm])
    # exp should be roughly now+1s (allow 5s slack for slow CI).
    delta = decoded["exp"] - datetime.now(timezone.utc).timestamp()
    assert -1 <= delta <= 5


def test_access_token_default_expiry_uses_settings():
    """Without expires_delta, uses settings.access_token_expire_minutes
    — pin so config drift is caught."""
    token = create_access_token({"sub": "1"})
    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    # exp should be roughly now + access_token_expire_minutes.
    expected = settings.access_token_expire_minutes * 60
    delta = decoded["exp"] - datetime.now(timezone.utc).timestamp()
    # Allow ±60s slack.
    assert expected - 60 <= delta <= expected + 60


# ─── create_refresh_token ────────────────────────────────────────────


def test_refresh_token_has_type_claim():
    """Refresh tokens carry type='refresh' so the refresh endpoint can
    reject access tokens. Critical invariant for the auth flow."""
    token = create_refresh_token({"sub": "42"})
    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    assert decoded["type"] == "refresh"
    assert decoded["sub"] == "42"


def test_refresh_token_expiry_is_days():
    """Refresh tokens last days (not minutes). Pin so an accidental
    timedelta() swap doesn't make refresh tokens expire too fast."""
    token = create_refresh_token({"sub": "1"})
    decoded = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    expected = settings.refresh_token_expire_days * 24 * 60 * 60
    delta = decoded["exp"] - datetime.now(timezone.utc).timestamp()
    # Within ±5min of expected.
    assert expected - 300 <= delta <= expected + 300


# ─── verify_token ────────────────────────────────────────────────────


def test_verify_token_round_trip():
    """Token created → verified → payload preserved."""
    token = create_access_token({"sub": "42", "role": "admin"})
    payload = verify_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "admin"


def test_verify_expired_token_raises_auth_error():
    """Expired token (exp in the past) raises AuthenticationError.
    Production safety: don't silently accept expired tokens."""
    expired = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    with pytest.raises(AuthenticationError, match="expired"):
        verify_token(expired)


def test_verify_invalid_signature_raises_auth_error():
    """Token signed with a different key → AuthenticationError. This is
    the gate that prevents token forgery."""
    forged = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "WRONG_SECRET_KEY",  # Different secret
        algorithm=settings.algorithm,
    )
    with pytest.raises(AuthenticationError, match="Invalid"):
        verify_token(forged)


def test_verify_malformed_token_raises_auth_error():
    """Random non-JWT string → AuthenticationError. Pin so a future
    refactor doesn't return generic dict for unparseable input
    (which could leak through downstream code)."""
    with pytest.raises(AuthenticationError):
        verify_token("this-is-not-a-jwt")


def test_verify_token_with_no_payload():
    """Empty token string → AuthenticationError."""
    with pytest.raises(AuthenticationError):
        verify_token("")

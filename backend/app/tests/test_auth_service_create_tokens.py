"""
Deep async-DB tests for `AuthService.create_tokens`.

Critical security boundary: every authenticated request rides on a JWT
issued here. Regression risks pinned:
- Wrong user identity claims (sub/nycu_id/role) → wrong permissions.
- portal/student data leaking into production tokens (debug-only).
- TokenResponse omitting fields the frontend depends on.

7 cases pinning:
- Required claims (sub, nycu_id, role) present in production access token.
- Production mode (env=production, debug=False, no test indicators)
  DOES NOT embed portal_data or student_data.
- Development mode embeds portal_data + student_data when provided +
  sets debug_mode=True.
- Test mode (portal_test_mode=True) embeds debug data even with
  env=production.
- Debug mode without portal/student data still sets debug_mode=True
  (the flag indicates capability, not presence).
- Both access_token AND refresh_token are non-empty distinct strings.
- expires_in=3600 (1 hour) — the contract the frontend relies on.
"""

from datetime import datetime, timezone

import jwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User, UserRole, UserType
from app.services.auth_service import AuthService


async def _seed_user(db: AsyncSession, *, nycu_id: str, role: UserRole = UserRole.student) -> User:
    u = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _decode(token: str) -> dict:
    """Decode without verification — we just want to inspect claims in tests."""
    return jwt.decode(token, options={"verify_signature": False, "verify_aud": False})


@pytest.mark.asyncio
async def test_required_claims_present(db: AsyncSession):
    user = await _seed_user(db, nycu_id="auth_claims", role=UserRole.admin)
    service = AuthService(db)
    result = await service.create_tokens(user)

    claims = _decode(result.access_token)
    assert claims["sub"] == str(user.id)
    assert claims["nycu_id"] == "auth_claims"
    assert claims["role"] == UserRole.admin.value


@pytest.mark.asyncio
async def test_production_mode_does_not_embed_portal_or_student_data(db: AsyncSession, monkeypatch):
    """Switch off every debug-data signal: env=production, no portal_test_mode,
    debug=False, base_url with no test indicators. Then portal/student data
    must NOT appear in the token even when passed."""
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "portal_test_mode", False)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "base_url", "https://scholarship.nycu.edu.tw")

    user = await _seed_user(db, nycu_id="auth_prod_no_debug")
    service = AuthService(db)
    result = await service.create_tokens(
        user,
        portal_data={"some": "portal-secret"},
        student_data={"some": "student-secret"},
    )

    claims = _decode(result.access_token)
    assert "portal_data" not in claims
    assert "student_data" not in claims
    assert claims.get("debug_mode") is not True


@pytest.mark.asyncio
async def test_development_mode_embeds_portal_and_student_data(db: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "portal_test_mode", False)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "base_url", "https://scholarship.nycu.edu.tw")

    user = await _seed_user(db, nycu_id="auth_dev_with_debug")
    service = AuthService(db)
    result = await service.create_tokens(
        user,
        portal_data={"institution": "NYCU"},
        student_data={"std_cname": "王小明"},
    )

    claims = _decode(result.access_token)
    assert claims["debug_mode"] is True
    assert claims["portal_data"] == {"institution": "NYCU"}
    assert claims["student_data"] == {"std_cname": "王小明"}


@pytest.mark.asyncio
async def test_portal_test_mode_overrides_production_environment(db: AsyncSession, monkeypatch):
    """portal_test_mode=True alone is enough to enable debug data,
    even if environment=production."""
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "portal_test_mode", True)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "base_url", "https://scholarship.nycu.edu.tw")

    user = await _seed_user(db, nycu_id="auth_test_mode")
    service = AuthService(db)
    result = await service.create_tokens(user, portal_data={"x": "y"})

    claims = _decode(result.access_token)
    assert claims["debug_mode"] is True
    assert claims["portal_data"] == {"x": "y"}


@pytest.mark.asyncio
async def test_debug_mode_flag_set_even_without_extra_data(db: AsyncSession, monkeypatch):
    """The debug_mode flag is set whenever we're in a debug-eligible
    environment — independent of whether portal/student data was passed.
    Pins that the flag indicates capability, not presence."""
    monkeypatch.setattr(settings, "environment", "testing")
    monkeypatch.setattr(settings, "portal_test_mode", False)
    monkeypatch.setattr(settings, "debug", False)
    monkeypatch.setattr(settings, "base_url", "https://scholarship.nycu.edu.tw")

    user = await _seed_user(db, nycu_id="auth_debug_flag_only")
    service = AuthService(db)
    # No portal_data or student_data passed.
    result = await service.create_tokens(user)

    claims = _decode(result.access_token)
    assert claims["debug_mode"] is True
    assert "portal_data" not in claims
    assert "student_data" not in claims


@pytest.mark.asyncio
async def test_access_and_refresh_tokens_are_distinct_non_empty(db: AsyncSession):
    user = await _seed_user(db, nycu_id="auth_token_pair")
    service = AuthService(db)
    result = await service.create_tokens(user)

    assert result.access_token
    assert result.refresh_token
    assert result.access_token != result.refresh_token


@pytest.mark.asyncio
async def test_expires_in_is_3600(db: AsyncSession):
    """The frontend assumes 1-hour access-token lifetime — pin it."""
    user = await _seed_user(db, nycu_id="auth_expires_in")
    service = AuthService(db)
    result = await service.create_tokens(user)
    assert result.expires_in == 3600

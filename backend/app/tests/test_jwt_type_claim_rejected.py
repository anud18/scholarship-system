"""Regression tests for the JWT `type`-claim hardening from #1079.

`verify_token` / `get_current_user` never checked the token `type`, so a refresh
token (7-day expiry) would be accepted anywhere an access token is expected. Both
`get_current_user` implementations (`app.core.security` and `app.core.deps`) now
reject a token whose `type` claim is `refresh`.
"""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user as deps_get_current_user
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, create_refresh_token
from app.core.security import get_current_user as security_get_current_user
from app.models.user import User, UserRole, UserType


async def _seed_user(db: AsyncSession) -> User:
    user = User(
        nycu_id="jwt_type_user",
        name="JWT Type User",
        email="jwt_type_user@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def test_security_get_current_user_rejects_refresh_token(db: AsyncSession):
    user = await _seed_user(db)
    refresh = create_refresh_token({"sub": str(user.id)})
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=refresh)
    with pytest.raises(AuthenticationError):
        await security_get_current_user(credentials=creds, db=db)


async def test_security_get_current_user_accepts_access_token(db: AsyncSession):
    user = await _seed_user(db)
    access = create_access_token({"sub": str(user.id)})
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=access)
    resolved = await security_get_current_user(credentials=creds, db=db)
    assert resolved.id == user.id


async def test_deps_get_current_user_rejects_refresh_token(db: AsyncSession):
    user = await _seed_user(db)
    refresh = create_refresh_token({"sub": str(user.id)})
    with pytest.raises(HTTPException):
        await deps_get_current_user(token=refresh, db=db)


async def test_deps_get_current_user_accepts_access_token(db: AsyncSession):
    user = await _seed_user(db)
    access = create_access_token({"sub": str(user.id)})
    resolved = await deps_get_current_user(token=access, db=db)
    assert resolved.id == user.id

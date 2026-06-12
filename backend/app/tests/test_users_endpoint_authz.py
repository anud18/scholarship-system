"""
Endpoint-level authorization tests for the user management routes.

Security-critical regressions pinned (PR: fix security vulnerabilities):
- PUT /users/me must IGNORE privilege fields (role/user_type/status/
  college_code) — a student cannot escalate to super_admin via self-update.
- PUT /users/{id}:
    * a plain admin cannot change anyone's role (incl. self),
    * nobody (even super_admin) can change their OWN role,
    * a super_admin CAN change another user's role.
"""

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin
from app.db.deps import get_db
from app.main import app
from app.models.user import User, UserRole, UserType


async def _seed_user(
    db: AsyncSession,
    *,
    nycu_id: str,
    role: UserRole = UserRole.student,
    college_code: str = "A",
) -> User:
    u = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
        college_code=college_code,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _client_as(actor: User, db: AsyncSession) -> AsyncClient:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    async def override_current_user():
        return actor

    async def override_require_admin():
        return actor

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[require_admin] = override_require_admin
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture(autouse=True)
async def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_self_update_ignores_role_escalation(db: AsyncSession):
    """A student PUT /users/me with role=super_admin must NOT change the role."""
    student = await _seed_user(db, nycu_id="self_escalate", role=UserRole.student)

    async with _client_as(student, db) as ac:
        resp = await ac.put("/api/v1/users/me", json={"role": "super_admin", "name": "New Name"})

    assert resp.status_code == 200
    # Non-privileged field is applied...
    assert resp.json()["data"]["name"] == "New Name"
    # ...but the role is unchanged.
    await db.refresh(student)
    assert student.role == UserRole.student


@pytest.mark.asyncio
async def test_self_update_ignores_user_type_and_college(db: AsyncSession):
    student = await _seed_user(db, nycu_id="self_fields", role=UserRole.student, college_code="A")

    async with _client_as(student, db) as ac:
        resp = await ac.put(
            "/api/v1/users/me",
            json={"user_type": "employee", "college_code": "ZZ"},
        )

    assert resp.status_code == 200
    await db.refresh(student)
    assert student.user_type == UserType.student
    assert student.college_code == "A"


@pytest.mark.asyncio
async def test_admin_cannot_change_other_user_role(db: AsyncSession):
    admin = await _seed_user(db, nycu_id="plain_admin", role=UserRole.admin)
    target = await _seed_user(db, nycu_id="victim", role=UserRole.student)

    async with _client_as(admin, db) as ac:
        resp = await ac.put(f"/api/v1/users/{target.id}", json={"role": "super_admin"})

    assert resp.status_code == 403
    await db.refresh(target)
    assert target.role == UserRole.student


@pytest.mark.asyncio
async def test_admin_cannot_change_own_role(db: AsyncSession):
    admin = await _seed_user(db, nycu_id="self_admin", role=UserRole.admin)

    async with _client_as(admin, db) as ac:
        resp = await ac.put(f"/api/v1/users/{admin.id}", json={"role": "super_admin"})

    assert resp.status_code == 403
    await db.refresh(admin)
    assert admin.role == UserRole.admin


@pytest.mark.asyncio
async def test_super_admin_cannot_change_own_role(db: AsyncSession):
    sa = await _seed_user(db, nycu_id="self_super", role=UserRole.super_admin)

    async with _client_as(sa, db) as ac:
        resp = await ac.put(f"/api/v1/users/{sa.id}", json={"role": "admin"})

    assert resp.status_code == 403
    await db.refresh(sa)
    assert sa.role == UserRole.super_admin


@pytest.mark.asyncio
async def test_super_admin_can_change_other_user_role(db: AsyncSession):
    sa = await _seed_user(db, nycu_id="grantor", role=UserRole.super_admin)
    target = await _seed_user(db, nycu_id="promotee", role=UserRole.student)

    async with _client_as(sa, db) as ac:
        resp = await ac.put(f"/api/v1/users/{target.id}", json={"role": "professor"})

    assert resp.status_code == 200
    await db.refresh(target)
    assert target.role == UserRole.professor


@pytest.mark.asyncio
async def test_admin_can_update_non_role_fields_of_other_user(db: AsyncSession):
    """Non-role updates by a plain admin still work (no over-restriction)."""
    admin = await _seed_user(db, nycu_id="editor_admin", role=UserRole.admin)
    target = await _seed_user(db, nycu_id="editable", role=UserRole.student)

    async with _client_as(admin, db) as ac:
        resp = await ac.put(f"/api/v1/users/{target.id}", json={"name": "Renamed", "role": "student"})

    assert resp.status_code == 200
    await db.refresh(target)
    assert target.name == "Renamed"
    assert target.role == UserRole.student

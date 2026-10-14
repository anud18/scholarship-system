"""
college_code must be an academies.code on every admin write path.

ZAP's active scan (Path Traversal, plugin 6) showed PATCH /users/{id}/college
storing any string it was sent. college_code scopes a college reviewer's
view, so an unknown value silently strands the account with nothing to
review. Pinned here for every admin writer: POST /users, PUT /users/{id},
PATCH /users/{id}/college and POST /auth/register.
"""

from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin
from app.db.deps import get_db
from app.main import app
from app.models.student import Academy
from app.models.user import User, UserRole, UserType

UNKNOWN_CODES = ["ZZ", "../../etc/passwd", "college"]


async def _seed_plain_admin(db: AsyncSession) -> User:
    return await _seed_user(db, nycu_id="plain_admin", role=UserRole.admin, college_code=None)


async def _seed_user(db: AsyncSession, *, nycu_id: str, role: UserRole, college_code: str | None = "E") -> User:
    user = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.employee,
        role=role,
        college_code=college_code,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def academies(db: AsyncSession):
    db.add_all([Academy(code="E", name="電機學院"), Academy(code="C", name="資訊學院")])
    await db.commit()


@pytest_asyncio.fixture
async def super_admin(db: AsyncSession, academies) -> User:
    return await _seed_user(db, nycu_id="sa_college", role=UserRole.super_admin, college_code=None)


@pytest_asyncio.fixture
async def client(db: AsyncSession, super_admin: User) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    async def override_user():
        return super_admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[require_admin] = override_user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_patch_college_accepts_known_code(client: AsyncClient, db: AsyncSession):
    target = await _seed_user(db, nycu_id="col_ok", role=UserRole.college)
    resp = await client.patch(f"/api/v1/users/{target.id}/college", params={"college_code": "C"})
    assert resp.status_code == 200
    await db.refresh(target)
    assert target.college_code == "C"


@pytest.mark.asyncio
@pytest.mark.parametrize("code", UNKNOWN_CODES)
async def test_patch_college_rejects_unknown_code_without_echo(client: AsyncClient, db: AsyncSession, code: str):
    target = await _seed_user(db, nycu_id=f"col_bad_{UNKNOWN_CODES.index(code)}", role=UserRole.college)
    resp = await client.patch(f"/api/v1/users/{target.id}/college", params={"college_code": code})
    assert resp.status_code == 422
    assert resp.json()["message"] == "學院代碼不存在"  # generic; never echoes the probe
    await db.refresh(target)
    assert target.college_code == "E"


@pytest.mark.asyncio
async def test_patch_college_blank_clears_assignment(client: AsyncClient, db: AsyncSession):
    target = await _seed_user(db, nycu_id="col_clear", role=UserRole.college)
    resp = await client.patch(f"/api/v1/users/{target.id}/college", params={"college_code": "  "})
    assert resp.status_code == 200
    await db.refresh(target)
    assert target.college_code is None


@pytest.mark.asyncio
async def test_put_user_rejects_unknown_college_code(client: AsyncClient, db: AsyncSession):
    target = await _seed_user(db, nycu_id="put_bad", role=UserRole.college)
    resp = await client.put(f"/api/v1/users/{target.id}", json={"college_code": "ZZ", "name": "Renamed"})
    assert resp.status_code == 422
    await db.refresh(target)
    assert (target.college_code, target.name) == ("E", "User put_bad")


@pytest.mark.asyncio
async def test_put_user_resending_unchanged_legacy_code_still_saves(client: AsyncClient, db: AsyncSession):
    """The edit form re-sends college_code; an unchanged legacy value must not block other edits."""
    target = await _seed_user(db, nycu_id="put_legacy", role=UserRole.college, college_code="OLD")
    resp = await client.put(f"/api/v1/users/{target.id}", json={"college_code": "OLD", "name": "Renamed"})
    assert resp.status_code == 200
    await db.refresh(target)
    assert (target.college_code, target.name) == ("OLD", "Renamed")


@pytest.mark.asyncio
async def test_put_user_without_college_code_is_unaffected(client: AsyncClient, db: AsyncSession):
    target = await _seed_user(db, nycu_id="put_other", role=UserRole.college)
    resp = await client.put(f"/api/v1/users/{target.id}", json={"name": "Renamed"})
    assert resp.status_code == 200
    await db.refresh(target)
    assert (target.college_code, target.name) == ("E", "Renamed")


@pytest.mark.asyncio
async def test_create_user_validates_college_code(client: AsyncClient):
    base = {"email": "new.college@u.edu", "name": "New College", "user_type": "employee", "role": "college"}
    bad = await client.post("/api/v1/users", json={**base, "nycu_id": "new_bad", "college_code": "ZZ"})
    assert bad.status_code == 422

    ok = await client.post("/api/v1/users", json={**base, "nycu_id": "new_ok", "college_code": "C"})
    assert ok.status_code == 201
    assert ok.json()["data"]["college_code"] == "C"


@pytest.mark.asyncio
@pytest.mark.parametrize(("sent", "stored"), [("c", "C"), (" E ", "E"), ("Y", "E")])
async def test_patch_college_normalizes_case_and_retired_codes(
    client: AsyncClient, db: AsyncSession, sent: str, stored: str
):
    target = await _seed_user(db, nycu_id=f"col_norm_{stored}_{len(sent)}", role=UserRole.college, college_code=None)
    resp = await client.patch(f"/api/v1/users/{target.id}/college", params={"college_code": sent})
    assert resp.status_code == 200
    await db.refresh(target)
    assert target.college_code == stored


@pytest.mark.asyncio
async def test_put_user_unchanged_legacy_code_with_whitespace_still_saves(client: AsyncClient, db: AsyncSession):
    target = await _seed_user(db, nycu_id="put_legacy_ws", role=UserRole.college, college_code="OLD")
    resp = await client.put(f"/api/v1/users/{target.id}", json={"college_code": "OLD ", "name": "Renamed"})
    assert resp.status_code == 200
    await db.refresh(target)
    assert (target.college_code, target.name) == ("OLD", "Renamed")


@pytest.mark.asyncio
async def test_put_user_authorization_runs_before_college_validation(db: AsyncSession, academies):
    """A plain admin attempting a role grant gets 403, not a 422 that reveals which codes exist."""
    admin = await _seed_plain_admin(db)
    target = await _seed_user(db, nycu_id="authz_first", role=UserRole.student)

    async def override_get_db():
        yield db

    async def override_user():
        return admin

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[require_admin] = override_user
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.put(f"/api/v1/users/{target.id}", json={"role": "super_admin", "college_code": "ZZ"})
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_auth_register_validates_college_code(client: AsyncClient):
    base = {"email": "reg.college@u.edu", "name": "Reg College", "user_type": "employee", "role": "college"}
    bad = await client.post("/api/v1/auth/register", json={**base, "nycu_id": "reg_bad", "college_code": "ZZ"})
    assert bad.status_code == 422

    ok = await client.post("/api/v1/auth/register", json={**base, "nycu_id": "reg_ok", "college_code": "e"})
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_put_user_unchanged_lowercase_legacy_code_still_saves(client: AsyncClient, db: AsyncSession):
    """A legacy code stored in lowercase is unchanged when re-sent, even though normalization uppercases."""
    target = await _seed_user(db, nycu_id="put_legacy_lc", role=UserRole.college, college_code="old")
    resp = await client.put(f"/api/v1/users/{target.id}", json={"college_code": "old", "name": "Renamed"})
    assert resp.status_code == 200
    await db.refresh(target)
    assert (target.college_code, target.name) == ("old", "Renamed")

"""Admin config endpoints accept and return 本次開放申請類別 (open_sub_types)."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.main import app
from app.models.scholarship import ScholarshipConfiguration, ScholarshipStatus, ScholarshipType
from app.models.user import AdminScholarship, User, UserRole, UserType

BASE = "/api/v1/scholarship-configurations/configurations"


@pytest_asyncio.fixture
async def phd_type(db: AsyncSession) -> ScholarshipType:
    scholarship_type = ScholarshipType(
        code="open_sub_types_phd",
        name="Open Sub-types PhD",
        status=ScholarshipStatus.active.value,
        sub_type_list=["general", "nstc", "moe_1w", "moe_2w"],
    )
    db.add(scholarship_type)
    await db.commit()
    await db.refresh(scholarship_type)
    return scholarship_type


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, db: AsyncSession, phd_type) -> AsyncClient:
    admin = User(
        nycu_id="open_sub_admin",
        email="open_sub_admin@u.edu",
        name="Open Sub Admin",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    db.add(AdminScholarship(admin_id=admin.id, scholarship_id=phd_type.id))
    await db.commit()

    async def override_admin():
        return admin

    app.dependency_overrides[require_admin] = override_admin
    try:
        yield client
    finally:
        app.dependency_overrides.pop(require_admin, None)


def _payload(phd_type, **extra):
    return {
        "scholarship_type_id": phd_type.id,
        "config_name": "Open sub-types config",
        "config_code": "OPEN-SUB-114",
        "academic_year": 114,
        "amount": 40000,
        **extra,
    }


async def _read_open_sub_types(client: AsyncClient, config_id: int):
    response = await client.get(f"{BASE}/{config_id}")
    assert response.status_code == 200
    return response.json()["data"]["open_sub_types"]


@pytest.mark.asyncio
async def test_create_round_trips_normalized_open_sub_types(admin_client: AsyncClient, phd_type):
    response = await admin_client.post(BASE, json=_payload(phd_type, open_sub_types=[" MOE_1W", "moe_2w", "moe_1w"]))

    assert response.status_code == 200
    config_id = response.json()["data"]["id"]
    assert await _read_open_sub_types(admin_client, config_id) == ["moe_1w", "moe_2w"]

    listed = await admin_client.get(BASE, params={"scholarship_type_id": phd_type.id})
    assert [c["open_sub_types"] for c in listed.json()["data"]] == [["moe_1w", "moe_2w"]]


@pytest.mark.asyncio
async def test_create_without_open_sub_types_keeps_all_open(admin_client: AsyncClient, phd_type):
    response = await admin_client.post(BASE, json=_payload(phd_type))

    assert response.status_code == 200
    assert await _read_open_sub_types(admin_client, response.json()["data"]["id"]) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_value", [[], ["general"], ["nstc", "unknown_type"], "nstc"])
async def test_create_rejects_invalid_open_sub_types(admin_client: AsyncClient, db: AsyncSession, phd_type, bad_value):
    response = await admin_client.post(BASE, json=_payload(phd_type, open_sub_types=bad_value))

    assert response.status_code == 422
    assert response.json()["success"] is False
    assert await db.scalar(select(func.count(ScholarshipConfiguration.id))) == 0


@pytest.mark.asyncio
async def test_update_sets_restricts_and_reopens(admin_client: AsyncClient, phd_type):
    config_id = (await admin_client.post(BASE, json=_payload(phd_type))).json()["data"]["id"]

    restricted = await admin_client.put(f"{BASE}/{config_id}", json={"open_sub_types": ["nstc"]})
    assert restricted.status_code == 200
    assert await _read_open_sub_types(admin_client, config_id) == ["nstc"]

    rejected = await admin_client.put(f"{BASE}/{config_id}", json={"open_sub_types": []})
    assert rejected.status_code == 422
    assert await _read_open_sub_types(admin_client, config_id) == ["nstc"]

    untouched = await admin_client.put(f"{BASE}/{config_id}", json={"config_name": "renamed"})
    assert untouched.status_code == 200
    assert await _read_open_sub_types(admin_client, config_id) == ["nstc"]

    reopened = await admin_client.put(f"{BASE}/{config_id}", json={"open_sub_types": None})
    assert reopened.status_code == 200
    assert await _read_open_sub_types(admin_client, config_id) is None

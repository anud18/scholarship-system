"""GET /scholarships/eligible offers only the sub-types the current opening accepts."""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.main import app
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipRule,
    ScholarshipStatus,
    ScholarshipSubTypeConfig,
    ScholarshipType,
)
from app.models.user import User, UserRole, UserType
from app.services import application_service

STUDENT_DATA = {"std_stdcode": "311000001", "std_degree": "1"}


@pytest_asyncio.fixture
async def student_client(client: AsyncClient, db: AsyncSession, monkeypatch) -> AsyncClient:
    student = User(
        nycu_id="311000001",
        name="Open Sub Student",
        email="311000001@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    await db.commit()
    await db.refresh(student)

    async def fake_student_data(user):
        return dict(STUDENT_DATA)

    async def override_user():
        return student

    monkeypatch.setattr(application_service, "get_student_data_from_user", fake_student_data)
    app.dependency_overrides[get_current_user] = override_user
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


async def _seed_phd(db: AsyncSession, *, open_sub_types, ineligible_sub_types=()) -> ScholarshipType:
    scholarship_type = ScholarshipType(
        code="open_sub_phd",
        name="Open Sub PhD",
        status=ScholarshipStatus.active.value,
        sub_type_list=["nstc", "moe_1w"],
    )
    db.add(scholarship_type)
    await db.commit()
    await db.refresh(scholarship_type)

    now = datetime.now(timezone.utc)
    db.add_all(
        [
            ScholarshipSubTypeConfig(scholarship_type_id=scholarship_type.id, sub_type_code="nstc", name="國科會"),
            ScholarshipSubTypeConfig(scholarship_type_id=scholarship_type.id, sub_type_code="moe_1w", name="教育部"),
            ScholarshipConfiguration(
                scholarship_type_id=scholarship_type.id,
                academic_year=114,
                config_name="114 PhD",
                config_code="open_sub_phd_114",
                amount=40000,
                is_active=True,
                application_start_date=now - timedelta(days=1),
                application_end_date=now + timedelta(days=30),
                open_sub_types=open_sub_types,
            ),
            *[
                ScholarshipRule(
                    scholarship_type_id=scholarship_type.id,
                    sub_type=sub_type,
                    rule_name=f"{sub_type} 博士生",
                    rule_type="student",
                    tag="博士生",
                    condition_field="std_degree",
                    operator="==",
                    expected_value="3" if sub_type in ineligible_sub_types else STUDENT_DATA["std_degree"],
                    message="需為博士生",
                    is_hard_rule=False,
                )
                for sub_type in scholarship_type.sub_type_list
            ],
        ]
    )
    await db.commit()
    return scholarship_type


async def _eligible(client: AsyncClient):
    response = await client.get("/api/v1/scholarships/eligible")
    assert response.status_code == 200
    [scholarship] = response.json()["data"]
    return scholarship


def _offered(scholarship):
    return [st["value"] for st in scholarship["eligible_sub_types"]]


def _common_error_messages(scholarship):
    return [e["message"] for e in scholarship["errors"] if not e.get("sub_type")]


@pytest.mark.asyncio
async def test_all_open_when_unrestricted(student_client: AsyncClient, db: AsyncSession):
    await _seed_phd(db, open_sub_types=None)

    scholarship = await _eligible(student_client)

    assert _offered(scholarship) == ["nstc", "moe_1w"]
    assert scholarship["closed_sub_types"] == []
    assert _common_error_messages(scholarship) == []


@pytest.mark.asyncio
async def test_closed_sub_type_is_not_offered(student_client: AsyncClient, db: AsyncSession):
    await _seed_phd(db, open_sub_types=["moe_1w"])

    scholarship = await _eligible(student_client)

    assert _offered(scholarship) == ["moe_1w"]
    assert [(st["value"], st["label"]) for st in scholarship["closed_sub_types"]] == [("nstc", "國科會")]
    assert _common_error_messages(scholarship) == []


@pytest.mark.asyncio
async def test_only_closed_sub_types_qualify_gives_not_applyable_reason(student_client: AsyncClient, db: AsyncSession):
    await _seed_phd(db, open_sub_types=["moe_1w"], ineligible_sub_types=["moe_1w"])

    scholarship = await _eligible(student_client)

    assert "nstc" not in _offered(scholarship)
    assert "moe_1w" not in _offered(scholarship)
    assert _common_error_messages(scholarship) == ["本次未開放您符合資格的申請類別"]

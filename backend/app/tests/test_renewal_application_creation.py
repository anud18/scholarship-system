"""Tests for renewal & challenge application creation endpoints.

Covers:
- POST /api/v1/renewals/                 → create renewal from prior approved app
- POST /api/v1/renewals/challenge        → create challenge from approved renewal

The endpoints validate against `ScholarshipConfiguration` (not `ScholarshipType`)
for renewal_application_* and application_* date windows, matching the actual
schema.

Auth is mocked via `app.dependency_overrides[get_current_user]` so tests don't
need real JWT tokens.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.main import app
from app.models.application import Application
from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User

CURRENT_ACADEMIC_YEAR = 114
PRIOR_ACADEMIC_YEAR = 113


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_renewal_config(
    scholarship_type_id: int,
    *,
    config_code: str,
    academic_year: int = CURRENT_ACADEMIC_YEAR,
    in_renewal_period: bool = True,
    quotas: dict | None = None,
) -> ScholarshipConfiguration:
    """ScholarshipConfiguration with renewal window either open or closed."""
    now = datetime.now(timezone.utc)
    if in_renewal_period:
        start = now - timedelta(days=1)
        end = now + timedelta(days=7)
    else:
        start = now + timedelta(days=7)
        end = now + timedelta(days=14)

    return ScholarshipConfiguration(
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=None,
        config_name=f"Config {config_code}",
        config_code=config_code,
        amount=30000,
        currency="TWD",
        is_active=True,
        renewal_application_start_date=start,
        renewal_application_end_date=end,
        quotas=quotas,
    )


def _make_general_config(
    scholarship_type_id: int,
    *,
    config_code: str,
    academic_year: int = CURRENT_ACADEMIC_YEAR,
    in_general_period: bool = True,
    quotas: dict | None = None,
) -> ScholarshipConfiguration:
    """ScholarshipConfiguration with general application window either open or closed."""
    now = datetime.now(timezone.utc)
    if in_general_period:
        start = now - timedelta(days=1)
        end = now + timedelta(days=7)
    else:
        start = now + timedelta(days=7)
        end = now + timedelta(days=14)

    return ScholarshipConfiguration(
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=None,
        config_name=f"GenConfig {config_code}",
        config_code=config_code,
        amount=30000,
        currency="TWD",
        is_active=True,
        application_start_date=start,
        application_end_date=end,
        quotas=quotas,
    )


async def _insert_prior_application(
    db: AsyncSession,
    *,
    user: User,
    scholarship_type: ScholarshipType,
    configuration_id: int | None = None,
    academic_year: int = PRIOR_ACADEMIC_YEAR,
    status: ApplicationStatus = ApplicationStatus.approved,
    sub_scholarship_type: str = "nstc",
    is_renewal: bool = False,
    renewal_year: int | None = None,
    app_id_suffix: str = "00001",
) -> Application:
    app = Application(
        app_id=f"APP-{academic_year}-0-{app_id_suffix}",
        user_id=user.id,
        scholarship_type_id=scholarship_type.id,
        scholarship_configuration_id=configuration_id,
        scholarship_subtype_list=[sub_scholarship_type],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type=sub_scholarship_type,
        academic_year=academic_year,
        semester=None,
        status=status,
        is_renewal=is_renewal,
        renewal_year=renewal_year,
        agree_terms=True,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest_asyncio.fixture
async def authed_client(client: AsyncClient, test_user: User):
    """Yield a client whose `get_current_user` always returns `test_user`.

    Avoids the need for real JWT tokens in unit tests.
    """

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def freeze_current_academic_year(monkeypatch):
    """Force `get_current_academic_period()` to return AY114 so tests are stable."""
    from app.utils import academic_period

    def _fake_current_period():
        return {"academic_year": CURRENT_ACADEMIC_YEAR, "semester": "first", "western_year": 2025}

    monkeypatch.setattr(academic_period, "get_current_academic_period", _fake_current_period)


# --------------------------------------------------------------------------- #
# Renewal creation tests (Task 3.2)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_renewal_application_success(
    db: AsyncSession,
    authed_client: AsyncClient,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Approved prior app + open renewal window → 201 with renewal fields set."""
    config = _make_renewal_config(test_scholarship.id, config_code="RE-114-OK")
    db.add(config)
    await db.commit()
    await db.refresh(config)

    prior = await _insert_prior_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        sub_scholarship_type="nstc",
    )

    resp = await authed_client.post(
        "/api/v1/renewals/",
        json={"previous_application_id": prior.id},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["success"] is True
    new_app = body["data"]
    assert new_app["is_renewal"] is True
    assert new_app["sub_scholarship_type"] == "nstc"
    assert new_app["previous_application_id"] == prior.id
    assert new_app["academic_year"] == CURRENT_ACADEMIC_YEAR
    assert new_app["renewal_year"] == PRIOR_ACADEMIC_YEAR


@pytest.mark.asyncio
async def test_create_renewal_rejects_when_prior_not_approved(
    db: AsyncSession,
    authed_client: AsyncClient,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Prior application status=rejected → 400."""
    config = _make_renewal_config(test_scholarship.id, config_code="RE-114-REJ")
    db.add(config)
    await db.commit()
    await db.refresh(config)

    prior = await _insert_prior_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        status=ApplicationStatus.rejected,
    )

    resp = await authed_client.post(
        "/api/v1/renewals/",
        json={"previous_application_id": prior.id},
    )
    assert resp.status_code == 400
    # The app's exception handler maps HTTPException.detail → "message"
    detail = resp.json().get("message") or resp.json().get("detail", "")
    assert "未核可" in detail or "approved" in detail.lower()


@pytest.mark.asyncio
async def test_create_renewal_rejects_outside_period(
    db: AsyncSession,
    authed_client: AsyncClient,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """No active renewal window in current-year config → 400."""
    config = _make_renewal_config(
        test_scholarship.id,
        config_code="RE-114-CLOSED",
        in_renewal_period=False,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    prior = await _insert_prior_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
    )

    resp = await authed_client.post(
        "/api/v1/renewals/",
        json={"previous_application_id": prior.id},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_renewal_rejects_duplicate(
    db: AsyncSession,
    authed_client: AsyncClient,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Second attempt against the same prior application → 409."""
    config = _make_renewal_config(test_scholarship.id, config_code="RE-114-DUP")
    db.add(config)
    await db.commit()
    await db.refresh(config)

    prior = await _insert_prior_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
    )

    r1 = await authed_client.post(
        "/api/v1/renewals/",
        json={"previous_application_id": prior.id},
    )
    assert r1.status_code == 201, r1.text

    r2 = await authed_client.post(
        "/api/v1/renewals/",
        json={"previous_application_id": prior.id},
    )
    assert r2.status_code == 409


# --------------------------------------------------------------------------- #
# Challenge creation tests (Task 3.4)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_challenge_success(
    db: AsyncSession,
    authed_client: AsyncClient,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Approved renewal + open general window → challenge created for different sub_type."""
    config = _make_general_config(
        test_scholarship.id,
        config_code="GEN-114-OK",
        quotas={"nstc": {"114": 8}, "moe_1w": {"114": 6}},
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    renewal = await _insert_prior_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
        sub_scholarship_type="nstc",
        is_renewal=True,
        renewal_year=PRIOR_ACADEMIC_YEAR,
        app_id_suffix="99001",  # Prevent collision with generated app_id (sequence starts at 1)
    )

    resp = await authed_client.post(
        "/api/v1/renewals/challenge",
        json={"renewal_application_id": renewal.id, "target_sub_type": "moe_1w"},
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["is_renewal"] is False
    assert data["sub_scholarship_type"] == "moe_1w"
    assert data["challenges_application_id"] == renewal.id


@pytest.mark.asyncio
async def test_create_challenge_rejects_same_sub_type(
    db: AsyncSession,
    authed_client: AsyncClient,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """target_sub_type equal to renewal's sub_type → 400."""
    config = _make_general_config(
        test_scholarship.id,
        config_code="GEN-114-SAME",
        quotas={"nstc": {"114": 8}},
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    renewal = await _insert_prior_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
        sub_scholarship_type="nstc",
        is_renewal=True,
    )

    resp = await authed_client.post(
        "/api/v1/renewals/challenge",
        json={"renewal_application_id": renewal.id, "target_sub_type": "nstc"},
    )
    assert resp.status_code == 400
    detail = resp.json().get("message") or resp.json().get("detail", "")
    assert "sub_type" in detail


@pytest.mark.asyncio
async def test_create_challenge_rejects_when_renewal_not_approved(
    db: AsyncSession,
    authed_client: AsyncClient,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Renewal application status != approved → 400."""
    config = _make_general_config(
        test_scholarship.id,
        config_code="GEN-114-NOT-APPR",
        quotas={"nstc": {"114": 8}, "moe_1w": {"114": 6}},
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    renewal = await _insert_prior_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
        sub_scholarship_type="nstc",
        is_renewal=True,
        status=ApplicationStatus.rejected,
    )

    resp = await authed_client.post(
        "/api/v1/renewals/challenge",
        json={"renewal_application_id": renewal.id, "target_sub_type": "moe_1w"},
    )
    assert resp.status_code == 400


# Mark ReviewStage as imported (used in helper assertion in future)
_ = ReviewStage

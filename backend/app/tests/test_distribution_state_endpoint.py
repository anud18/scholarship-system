"""Tests for the manual distribution state endpoint (Phase 8.1).

Covers:
- GET /api/v1/manual-distribution/state?scholarship_type_id=X&academic_year=Y

The endpoint aggregates three views the admin Manual Distribution panel needs:
  * ``renewal_allocations`` — approved renewals grouped by
    ``(sub_type, renewal_year)`` with a ``has_challenge`` flag per renewal.
  * ``available_quotas`` — per ``(sub_type, allocation_year)``: total / used /
    remaining where ``used`` is approved renewals consumed from that pool.
  * ``candidates`` — non-renewal applicants ordered by
    ``CollegeRankingItem.rank_position`` with ``is_challenge`` and a
    ``challenged_renewal`` payload.

Auth is mocked via ``app.dependency_overrides[get_current_admin_user]`` so
tests don't need real JWT tokens — same pattern as
``test_renewal_distribution_result.py``.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin_user
from app.main import app
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType

CURRENT_ACADEMIC_YEAR = 114
PRIOR_ACADEMIC_YEAR = 113


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(
        nycu_id="admin_state",
        name="State Admin",
        email="state_admin@university.edu",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, admin_user: User, db: AsyncSession):
    """Yield a client with admin auth + a second get_db override.

    NOTE: conftest's ``client`` fixture overrides ``app.db.deps.get_db``,
    but ``manual_distribution.py`` imports ``get_db`` from
    ``app.core.deps`` (a separate function object). Without overriding
    *both*, the endpoint creates a fresh ``AsyncSessionLocal`` session
    that points at the production database URL, bypassing our in-memory
    SQLite — yielding "no such table" errors.
    """
    from app.core.deps import get_db as core_get_db

    async def override_admin():
        return admin_user

    async def override_db():
        yield db

    app.dependency_overrides[get_current_admin_user] = override_admin
    app.dependency_overrides[core_get_db] = override_db
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_admin_user, None)
        app.dependency_overrides.pop(core_get_db, None)


@pytest_asyncio.fixture
async def scholarship_with_config(db: AsyncSession) -> ScholarshipType:
    """Scholarship type + an active configuration with year-keyed quotas."""
    sch = ScholarshipType(
        code="phase8_sch",
        name="Phase 8 Test Scholarship",
        description="Fixture for distribution state endpoint",
    )
    db.add(sch)
    await db.commit()
    await db.refresh(sch)

    config = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
        semester=None,
        config_name="Phase 8 Config",
        config_code="phase8-config",
        amount=30000,
        currency="TWD",
        is_active=True,
        quotas={
            "nstc": {"114": 8, "113": 2},
            "moe_1w": {"114": 5},
        },
        prior_quota_years={"nstc": [PRIOR_ACADEMIC_YEAR], "moe_1w": []},
    )
    db.add(config)
    await db.commit()
    return sch


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _make_student(db: AsyncSession, *, suffix: str, name: str) -> User:
    user = User(
        nycu_id=f"stu_{suffix}",
        name=name,
        email=f"stu_{suffix}@university.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_renewal_app(
    db: AsyncSession,
    *,
    user: User,
    scholarship_type: ScholarshipType,
    sub_type: str,
    renewal_year: int,
    status_value: ApplicationStatus = ApplicationStatus.approved,
    app_id_suffix: str,
) -> Application:
    app_row = Application(
        app_id=f"APP-{CURRENT_ACADEMIC_YEAR}-0-{app_id_suffix}",
        user_id=user.id,
        scholarship_type_id=scholarship_type.id,
        scholarship_subtype_list=[sub_type],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type=sub_type,
        academic_year=CURRENT_ACADEMIC_YEAR,
        semester=None,
        status=status_value,
        review_stage=ReviewStage.quota_distributed,
        is_renewal=True,
        renewal_year=renewal_year,
        agree_terms=True,
    )
    db.add(app_row)
    await db.commit()
    await db.refresh(app_row)
    return app_row


async def _make_new_app(
    db: AsyncSession,
    *,
    user: User,
    scholarship_type: ScholarshipType,
    sub_type: str,
    app_id_suffix: str,
    challenges_application_id: int | None = None,
) -> Application:
    app_row = Application(
        app_id=f"APP-{CURRENT_ACADEMIC_YEAR}-0-{app_id_suffix}",
        user_id=user.id,
        scholarship_type_id=scholarship_type.id,
        scholarship_subtype_list=[sub_type],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type=sub_type,
        academic_year=CURRENT_ACADEMIC_YEAR,
        semester=None,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.college_ranked,
        is_renewal=False,
        challenges_application_id=challenges_application_id,
        agree_terms=True,
    )
    db.add(app_row)
    await db.commit()
    await db.refresh(app_row)
    return app_row


async def _attach_ranking_item(
    db: AsyncSession,
    *,
    scholarship_type: ScholarshipType,
    sub_type_code: str,
    application_id: int,
    rank_position: int,
) -> CollegeRankingItem:
    """Create (or reuse) a CollegeRanking row for the sub_type and add an item."""
    from sqlalchemy import select

    existing = (
        (
            await db.execute(
                select(CollegeRanking).where(
                    CollegeRanking.scholarship_type_id == scholarship_type.id,
                    CollegeRanking.sub_type_code == sub_type_code,
                    CollegeRanking.academic_year == CURRENT_ACADEMIC_YEAR,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is None:
        ranking = CollegeRanking(
            scholarship_type_id=scholarship_type.id,
            sub_type_code=sub_type_code,
            academic_year=CURRENT_ACADEMIC_YEAR,
            semester=None,
            is_finalized=True,
            ranking_status="finalized",
        )
        db.add(ranking)
        await db.commit()
        await db.refresh(ranking)
    else:
        ranking = existing

    item = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=application_id,
        rank_position=rank_position,
        is_allocated=False,
        status="ranked",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_returns_empty_state_when_no_data(
    db: AsyncSession,
    admin_client: AsyncClient,
    scholarship_with_config: ScholarshipType,
):
    """No applications → empty groups & candidates; available_quotas reflects config."""
    resp = await admin_client.get(
        "/api/v1/manual-distribution/state",
        params={
            "scholarship_type_id": scholarship_with_config.id,
            "academic_year": CURRENT_ACADEMIC_YEAR,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True

    data = body["data"]
    assert data["renewal_allocations"] == []
    assert data["candidates"] == []

    # available_quotas should mirror the config's year-keyed quotas with used=0
    # and remaining=total since no approved renewals exist yet.
    by_key = {(q["sub_type"], q["allocation_year"]): q for q in data["available_quotas"]}
    assert ("nstc", 114) in by_key
    assert by_key[("nstc", 114)] == {
        "sub_type": "nstc",
        "allocation_year": 114,
        "total": 8,
        "used": 0,
        "remaining": 8,
    }
    assert by_key[("nstc", 113)]["remaining"] == 2
    assert by_key[("moe_1w", 114)]["remaining"] == 5
    assert len(data["available_quotas"]) == 3


@pytest.mark.asyncio
async def test_groups_renewal_allocations_correctly(
    db: AsyncSession,
    admin_client: AsyncClient,
    scholarship_with_config: ScholarshipType,
):
    """Renewals across multiple (sub_type, renewal_year) keys form separate groups."""
    s1 = await _make_student(db, suffix="r1", name="Renewal One")
    s2 = await _make_student(db, suffix="r2", name="Renewal Two")
    s3 = await _make_student(db, suffix="r3", name="Renewal Three")
    s4 = await _make_student(db, suffix="r4", name="Renewal Four")

    # Group A: nstc / 113
    await _make_renewal_app(
        db,
        user=s1,
        scholarship_type=scholarship_with_config,
        sub_type="nstc",
        renewal_year=PRIOR_ACADEMIC_YEAR,
        app_id_suffix="10001",
    )
    # Group A (second member): nstc / 113
    await _make_renewal_app(
        db,
        user=s2,
        scholarship_type=scholarship_with_config,
        sub_type="nstc",
        renewal_year=PRIOR_ACADEMIC_YEAR,
        app_id_suffix="10002",
    )
    # Group B: nstc / 114 (same sub_type, different year)
    await _make_renewal_app(
        db,
        user=s3,
        scholarship_type=scholarship_with_config,
        sub_type="nstc",
        renewal_year=CURRENT_ACADEMIC_YEAR,
        app_id_suffix="10003",
    )
    # Group C: moe_1w / 114 (different sub_type)
    await _make_renewal_app(
        db,
        user=s4,
        scholarship_type=scholarship_with_config,
        sub_type="moe_1w",
        renewal_year=CURRENT_ACADEMIC_YEAR,
        app_id_suffix="10004",
    )

    resp = await admin_client.get(
        "/api/v1/manual-distribution/state",
        params={
            "scholarship_type_id": scholarship_with_config.id,
            "academic_year": CURRENT_ACADEMIC_YEAR,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    groups = data["renewal_allocations"]
    assert len(groups) == 3
    by_key = {(g["sub_type"], g["renewal_year"]): g for g in groups}

    nstc_113 = by_key[("nstc", PRIOR_ACADEMIC_YEAR)]
    assert len(nstc_113["applications"]) == 2
    nstc_113_names = {a["student_name"] for a in nstc_113["applications"]}
    assert nstc_113_names == {"Renewal One", "Renewal Two"}

    assert len(by_key[("nstc", CURRENT_ACADEMIC_YEAR)]["applications"]) == 1
    assert len(by_key[("moe_1w", CURRENT_ACADEMIC_YEAR)]["applications"]) == 1

    # available_quotas should reflect approved renewals subtracted from pool.
    quotas_by_key = {(q["sub_type"], q["allocation_year"]): q for q in data["available_quotas"]}
    assert quotas_by_key[("nstc", PRIOR_ACADEMIC_YEAR)] == {
        "sub_type": "nstc",
        "allocation_year": PRIOR_ACADEMIC_YEAR,
        "total": 2,
        "used": 2,
        "remaining": 0,
    }
    assert quotas_by_key[("nstc", CURRENT_ACADEMIC_YEAR)]["used"] == 1
    assert quotas_by_key[("nstc", CURRENT_ACADEMIC_YEAR)]["remaining"] == 7
    assert quotas_by_key[("moe_1w", CURRENT_ACADEMIC_YEAR)]["used"] == 1
    assert quotas_by_key[("moe_1w", CURRENT_ACADEMIC_YEAR)]["remaining"] == 4


@pytest.mark.asyncio
async def test_marks_has_challenge_on_renewals_with_challenge(
    db: AsyncSession,
    admin_client: AsyncClient,
    scholarship_with_config: ScholarshipType,
):
    """A renewal with a downstream challenge app → has_challenge=True; others False."""
    stu_challenged = await _make_student(db, suffix="rc", name="Renewal Challenged")
    stu_calm = await _make_student(db, suffix="rq", name="Renewal Quiet")

    renewal_a = await _make_renewal_app(
        db,
        user=stu_challenged,
        scholarship_type=scholarship_with_config,
        sub_type="nstc",
        renewal_year=PRIOR_ACADEMIC_YEAR,
        app_id_suffix="20001",
    )
    renewal_b = await _make_renewal_app(
        db,
        user=stu_calm,
        scholarship_type=scholarship_with_config,
        sub_type="nstc",
        renewal_year=PRIOR_ACADEMIC_YEAR,
        app_id_suffix="20002",
    )

    # Challenge app targets renewal_a (with a different sub_type, per spec)
    await _make_new_app(
        db,
        user=stu_challenged,
        scholarship_type=scholarship_with_config,
        sub_type="moe_1w",
        app_id_suffix="29001",
        challenges_application_id=renewal_a.id,
    )

    resp = await admin_client.get(
        "/api/v1/manual-distribution/state",
        params={
            "scholarship_type_id": scholarship_with_config.id,
            "academic_year": CURRENT_ACADEMIC_YEAR,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    groups = data["renewal_allocations"]
    assert len(groups) == 1
    apps = groups[0]["applications"]
    by_id = {a["application_id"]: a for a in apps}
    assert by_id[renewal_a.id]["has_challenge"] is True
    assert by_id[renewal_b.id]["has_challenge"] is False


@pytest.mark.asyncio
async def test_candidate_list_includes_challenges(
    db: AsyncSession,
    admin_client: AsyncClient,
    scholarship_with_config: ScholarshipType,
):
    """Challenge applications appear in candidates with is_challenge=True and a populated challenged_renewal."""
    stu_renewal = await _make_student(db, suffix="ren", name="The Renewer")
    stu_challenger = await _make_student(db, suffix="ch", name="The Challenger")
    stu_pure = await _make_student(db, suffix="p", name="Pure New")

    renewal = await _make_renewal_app(
        db,
        user=stu_renewal,
        scholarship_type=scholarship_with_config,
        sub_type="nstc",
        renewal_year=PRIOR_ACADEMIC_YEAR,
        app_id_suffix="30001",
    )

    challenge_app = await _make_new_app(
        db,
        user=stu_challenger,
        scholarship_type=scholarship_with_config,
        sub_type="moe_1w",
        app_id_suffix="39001",
        challenges_application_id=renewal.id,
    )
    pure_app = await _make_new_app(
        db,
        user=stu_pure,
        scholarship_type=scholarship_with_config,
        sub_type="moe_1w",
        app_id_suffix="39002",
    )

    # Rank challenger #1, pure-new #2 in moe_1w
    await _attach_ranking_item(
        db,
        scholarship_type=scholarship_with_config,
        sub_type_code="moe_1w",
        application_id=challenge_app.id,
        rank_position=1,
    )
    await _attach_ranking_item(
        db,
        scholarship_type=scholarship_with_config,
        sub_type_code="moe_1w",
        application_id=pure_app.id,
        rank_position=2,
    )

    resp = await admin_client.get(
        "/api/v1/manual-distribution/state",
        params={
            "scholarship_type_id": scholarship_with_config.id,
            "academic_year": CURRENT_ACADEMIC_YEAR,
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    cands = data["candidates"]
    assert len(cands) == 2

    by_app = {c["application_id"]: c for c in cands}

    chal = by_app[challenge_app.id]
    assert chal["is_challenge"] is True
    assert chal["applying_sub_type"] == "moe_1w"
    assert chal["rank"] == 1
    assert chal["challenged_renewal"] == {
        "renewal_application_id": renewal.id,
        "sub_type": "nstc",
        "renewal_year": PRIOR_ACADEMIC_YEAR,
    }
    assert chal["student_name"] == "The Challenger"

    pure = by_app[pure_app.id]
    assert pure["is_challenge"] is False
    assert pure["challenged_renewal"] is None
    assert pure["rank"] == 2

    # Candidates ordered by rank_position
    assert [c["rank"] for c in cands] == [1, 2]

"""Integration test for Phase 6: challenge release + waitlist fill-in.

Mirrors the spec Section 9.3 scenario (updated for per-config pool, §6.3):

Scholarship configuration::

    quotas = {"nstc": {"A": 8}, "moe_1w": {"A": 6}}, has_college_quota = True
    pool_total("nstc") = 8, pool_total("moe_1w") = 6

  - 1 renewal application for student A: is_renewal=True,
    sub_scholarship_type=nstc, status=approved,
    allocation_config_id=config.id  ← consumes 1 of the 8 nstc slots.
    remaining before first-round = 8 - 1 = 7.
  - 1 challenge application from A: is_renewal=False,
    challenges_application_id=renewal_A.id, sub_scholarship_type=moe_1w,
    academic_year=114, status=under_review. Ranked #1 in moe_1w.
  - 10 pure-new nstc candidates ranked 1..10, status=under_review.
  - 5 pure-new moe_1w candidates ranked 2..6, status=under_review.

After ``execute_general_distribution``:

  - challenge_A.status == approved
  - renewal_A.status == cancelled_by_challenge
  - renewal_A.cancelled_due_to_application_id == challenge_A.id
  - nstc ranks 1..7 approved in first round (7 remaining = 8 total - 1 renewal).
  - nstc rank #8 filled in from waitlist after renewal_A's slot is freed.
    CollegeRankingItem.allocation_config_id = config.id (same config, freed slot).
  - nstc ranks #9 and #10 still under_review.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.manual_distribution_service import ManualDistributionService

CURRENT_ACADEMIC_YEAR = 114
RENEWAL_YEAR = 113


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_user(suffix: str) -> User:
    return User(
        nycu_id=f"phase6_{suffix}",
        name=f"Phase6 Test {suffix}",
        email=f"phase6_{suffix}@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )


def _make_application(
    *,
    user_id: int,
    scholarship_type_id: int,
    app_id: str,
    sub_scholarship_type: str,
    status: ApplicationStatus,
    review_stage: ReviewStage,
    is_renewal: bool = False,
    renewal_year: int | None = None,
    challenges_application_id: int | None = None,
    allocation_config_id: int | None = None,
    academic_year: int = CURRENT_ACADEMIC_YEAR,
) -> Application:
    return Application(
        app_id=app_id,
        user_id=user_id,
        scholarship_type_id=scholarship_type_id,
        scholarship_subtype_list=[sub_scholarship_type],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type=sub_scholarship_type,
        academic_year=academic_year,
        semester=None,
        status=status,
        review_stage=review_stage,
        is_renewal=is_renewal,
        renewal_year=renewal_year,
        challenges_application_id=challenges_application_id,
        allocation_config_id=allocation_config_id,
        agree_terms=True,
    )


async def _make_ranking_with_item(
    db: AsyncSession,
    *,
    scholarship_type_id: int,
    sub_type_code: str,
    application_id: int,
    rank_position: int,
) -> CollegeRankingItem:
    """Create (or reuse) a CollegeRanking row for (sub_type, year) and attach an item."""
    existing = (
        (
            await db.execute(
                select(CollegeRanking).where(
                    CollegeRanking.scholarship_type_id == scholarship_type_id,
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
            scholarship_type_id=scholarship_type_id,
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
# Test
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_challenge_success_releases_renewal_and_fills_waitlist(
    db: AsyncSession,
):
    # ------------------------------------------------------------------- #
    # Scholarship type + configuration
    # ------------------------------------------------------------------- #
    sch = ScholarshipType(
        code="phase6_sch",
        name="Phase 6 Test Scholarship",
        description="Fixture for challenge-release distribution",
    )
    db.add(sch)
    await db.commit()
    await db.refresh(sch)

    config = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
        semester=None,
        config_name="Phase 6 Config",
        config_code="phase6-config",
        amount=30000,
        currency="TWD",
        is_active=True,
        has_college_quota=True,
        quotas={"nstc": {"A": 8}, "moe_1w": {"A": 6}},
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    # ------------------------------------------------------------------- #
    # Users
    # ------------------------------------------------------------------- #
    user_A = _make_user("A")
    db.add(user_A)

    nstc_users: list[User] = [_make_user(f"nstc{i}") for i in range(1, 11)]
    db.add_all(nstc_users)

    moe_users: list[User] = [_make_user(f"moe{i}") for i in range(2, 7)]
    db.add_all(moe_users)
    await db.commit()
    await db.refresh(user_A)
    for u in nstc_users + moe_users:
        await db.refresh(u)

    # ------------------------------------------------------------------- #
    # A's renewal (already approved, consumes 1 nstc slot on config)
    # ------------------------------------------------------------------- #
    renewal_A = _make_application(
        user_id=user_A.id,
        scholarship_type_id=sch.id,
        app_id="APP-114-0-A0R01",
        sub_scholarship_type="nstc",
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.quota_distributed,
        is_renewal=True,
        renewal_year=RENEWAL_YEAR,
        allocation_config_id=config.id,
    )
    db.add(renewal_A)
    await db.commit()
    await db.refresh(renewal_A)

    # A's challenge on moe_1w (under_review, ranked #1 in moe_1w)
    challenge_A = _make_application(
        user_id=user_A.id,
        scholarship_type_id=sch.id,
        app_id="APP-114-0-A0C01",
        sub_scholarship_type="moe_1w",
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.college_ranked,
        is_renewal=False,
        challenges_application_id=renewal_A.id,
    )
    db.add(challenge_A)
    await db.commit()
    await db.refresh(challenge_A)

    # ------------------------------------------------------------------- #
    # Pure-new nstc candidates (ranks 1..10)
    # ------------------------------------------------------------------- #
    nstc_apps: list[Application] = []
    for idx, u in enumerate(nstc_users, start=1):
        app = _make_application(
            user_id=u.id,
            scholarship_type_id=sch.id,
            app_id=f"APP-114-0-NSTC{idx:03d}",
            sub_scholarship_type="nstc",
            status=ApplicationStatus.under_review,
            review_stage=ReviewStage.college_ranked,
        )
        db.add(app)
        nstc_apps.append(app)
    await db.commit()
    for app in nstc_apps:
        await db.refresh(app)
    for idx, app in enumerate(nstc_apps, start=1):
        await _make_ranking_with_item(
            db,
            scholarship_type_id=sch.id,
            sub_type_code="nstc",
            application_id=app.id,
            rank_position=idx,
        )

    # ------------------------------------------------------------------- #
    # moe_1w candidates — A's challenge at rank 1, plus pure-new at ranks 2..6
    # ------------------------------------------------------------------- #
    await _make_ranking_with_item(
        db,
        scholarship_type_id=sch.id,
        sub_type_code="moe_1w",
        application_id=challenge_A.id,
        rank_position=1,
    )
    moe_apps: list[Application] = []
    for idx, u in enumerate(moe_users, start=2):
        app = _make_application(
            user_id=u.id,
            scholarship_type_id=sch.id,
            app_id=f"APP-114-0-MOE{idx:03d}",
            sub_scholarship_type="moe_1w",
            status=ApplicationStatus.under_review,
            review_stage=ReviewStage.college_ranked,
        )
        db.add(app)
        moe_apps.append(app)
    await db.commit()
    for app in moe_apps:
        await db.refresh(app)
    for app in moe_apps:
        await _make_ranking_with_item(
            db,
            scholarship_type_id=sch.id,
            sub_type_code="moe_1w",
            application_id=app.id,
            rank_position=int(app.app_id[-3:]),
        )

    # ------------------------------------------------------------------- #
    # Act
    # ------------------------------------------------------------------- #
    service = ManualDistributionService(db)
    result = await service.execute_general_distribution(
        scholarship_type_id=sch.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
    )

    # ------------------------------------------------------------------- #
    # Assert — summary stats
    # ------------------------------------------------------------------- #
    # approved_renewals key is removed; only approved_challenges remains.
    assert result["approved_challenges"] == 1
    # released: A's renewal freed up 1 nstc slot on config (keyed "nstc:{config.id}")
    assert result["released_slots"] == {f"nstc:{config.id}": 1}
    assert result["filled_in"] == 1
    assert result["unfilled"] == 0

    # Invariant (spec §10): every released slot is accounted for as either
    # filled in or left unfilled. This guards against silent drift in the
    # distribution summary stats.
    assert sum(result["released_slots"].values()) == result["filled_in"] + result["unfilled"]

    # ------------------------------------------------------------------- #
    # Assert — challenge approved, renewal cancelled by challenge
    # ------------------------------------------------------------------- #
    await db.refresh(challenge_A)
    await db.refresh(renewal_A)
    assert challenge_A.status == ApplicationStatus.approved
    assert renewal_A.status == ApplicationStatus.cancelled_by_challenge
    assert renewal_A.cancelled_due_to_application_id == challenge_A.id

    # ------------------------------------------------------------------- #
    # Assert — first-round nstc winners are ranks 1..7 (7 = 8 total - 1 renewal)
    # ------------------------------------------------------------------- #
    for idx in range(7):
        await db.refresh(nstc_apps[idx])
        assert (
            nstc_apps[idx].status == ApplicationStatus.approved
        ), f"nstc rank {idx + 1} should be approved (first-round winner)"

    # Rank #8 (index 7) was filled-in from waitlist on the freed config slot.
    await db.refresh(nstc_apps[7])
    assert (
        nstc_apps[7].status == ApplicationStatus.approved
    ), "nstc rank #8 should be promoted from waitlist after challenge release"

    # Verify rank #8's CollegeRankingItem.allocation_config_id points to the config.
    rank8_item = (
        (await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.application_id == nstc_apps[7].id)))
        .scalars()
        .first()
    )
    assert rank8_item is not None
    assert rank8_item.allocation_config_id == config.id

    # Ranks #9 and #10 should still be under_review (no more slots to fill)
    for idx in range(8, 10):
        await db.refresh(nstc_apps[idx])
        assert nstc_apps[idx].status == ApplicationStatus.under_review

    # Student academic_year unchanged for the filled-in candidate
    assert nstc_apps[7].academic_year == CURRENT_ACADEMIC_YEAR

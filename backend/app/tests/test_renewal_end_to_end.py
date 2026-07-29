"""End-to-end test for the full renewal + challenge distribution flow.

Spec Section 9.3 scenario:

Doctoral scholarship, academic_year=114, quota pool::

    prior sibling config e2e-phd-config-113 (academic_year=113):
        nstc: 10 slots  (linked as shared_quota_sources into e2e-phd-config)
    current config e2e-phd-config (academic_year=114):
        nstc: 8 slots (own-year)
        moe_1w: 6 slots (own-year)

    The two configs are linked via shared_quota_sources so nstc consumers can
    draw from e2e-phd-config-113 after exhausting e2e-phd-config's 8 own slots.

Renewal phase:
  10 prior year (113) winners renew under nstc; all approved.
  Their allocation_config_id is set to prior_config (e2e-phd-config-113).
  Two of them (A and B) will challenge moe_1w in the general phase.

General phase candidates (academic_year=114):
  nstc pure-new candidates ranked 1..10  (M, N, O, P, Q, R, S, T, U, V)
  moe_1w candidates: A (rank 1, challenge), B (rank 2, challenge),
                     plus pure-new X, Y, Z, AA, BB, CC (ranks 3..8).

Expected outcome:
  - A and B approved on moe_1w[114]; their renewals flip to
    cancelled_by_challenge with cancelled_due_to_application_id set.
  - The other 4 moe_1w pure-new (X..AA, ranks 3..6) approved on moe_1w[114].
  - nstc ranks 1..8 (M..T) approved on nstc[114] first-round
    (allocation_config_id == e2e-phd-config / config.id).
  - nstc ranks 9, 10 (U, V) fill in on the two slots freed by A and B's
    cancelled renewals — both promoted with
    allocation_config_id == e2e-phd-config-113 / prior_config.id.
  - released_slots == {"nstc:{prior_config.id}": 2}
  - filled_in == 2, unfilled == 0

This test wires up every service touched by the feature:
  - ApplicationService.create_renewal_from_previous  (Phase 3)
  - RenewalDistributionService.auto_approve_passed_reviews (Phase 5)
  - ApplicationService.create_challenge_from_renewal  (Phase 3)
  - ManualDistributionService.execute_general_distribution (Phase 6)

If any one of them drifts, this scenario will break.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService
from app.services.manual_distribution_service import ManualDistributionService
from app.services.renewal_distribution_service import RenewalDistributionService

CURRENT_ACADEMIC_YEAR = 114
RENEWAL_YEAR = 113


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_user(suffix: str) -> User:
    return User(
        nycu_id=f"e2e_{suffix}",
        name=f"E2E {suffix}",
        email=f"e2e_{suffix}@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )


def _make_prior_approved(
    *,
    user_id: int,
    scholarship_type_id: int,
    app_id: str,
    sub_scholarship_type: str = "nstc",
    academic_year: int = RENEWAL_YEAR,
) -> Application:
    """An approved application from a prior academic year — used as the
    `previous` argument to `ApplicationService.create_renewal_from_previous`.
    """
    return Application(
        app_id=app_id,
        user_id=user_id,
        scholarship_type_id=scholarship_type_id,
        scholarship_subtype_list=[sub_scholarship_type],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type=sub_scholarship_type,
        academic_year=academic_year,
        semester=None,
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.quota_distributed,
        is_renewal=False,
        agree_terms=True,
    )


def _make_pure_new_application(
    *,
    user_id: int,
    scholarship_type_id: int,
    app_id: str,
    sub_scholarship_type: str,
    review_stage: ReviewStage = ReviewStage.college_ranked,
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
        status=ApplicationStatus.under_review,
        review_stage=review_stage,
        is_renewal=False,
        agree_terms=True,
    )


async def _attach_ranking_item(
    db: AsyncSession,
    *,
    scholarship_type_id: int,
    sub_type_code: str,
    application_id: int,
    rank_position: int,
) -> CollegeRankingItem:
    """Get-or-create a CollegeRanking row for (sub_type, year) and attach an item."""
    ranking = (
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
    if ranking is None:
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
async def test_full_renewal_challenge_e2e(db: AsyncSession):
    """End-to-end exercise of the renewal/challenge/general distribution flow.

    See module docstring for the spec Section 9.3 scenario and expected outcome.
    """
    # ------------------------------------------------------------------- #
    # 1. Scholarship type + two configs: prior sibling (113, 10 nstc) linked
    #    to current (114, 8 nstc + 6 moe_1w) via shared_quota_sources.
    # ------------------------------------------------------------------- #
    scholarship = ScholarshipType(
        code="e2e_phd",
        name="E2E PhD Scholarship",
        description="Spec Section 9.3 end-to-end fixture",
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)

    prior_config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=RENEWAL_YEAR,
        semester=None,
        config_name="E2E PhD Prior Config",
        config_code="e2e-phd-config-113",
        amount=40000,
        currency="TWD",
        is_active=True,
        has_college_quota=True,
        quotas={"nstc": {"EE": 10}},  # 10 nstc[113] slots — renewal pool
    )
    db.add(prior_config)
    await db.commit()
    await db.refresh(prior_config)

    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
        semester=None,
        config_name="E2E PhD Config",
        config_code="e2e-phd-config",
        amount=40000,
        currency="TWD",
        is_active=True,
        has_college_quota=True,
        requires_professor_recommendation=True,
        requires_college_review=True,
        renewal_requires_professor_review=True,
        renewal_requires_college_review=True,
        quotas={"nstc": {"EE": 8}, "moe_1w": {"EE": 6}},
        shared_quota_sources=[{"source_config_code": "e2e-phd-config-113", "sub_types": ["nstc"]}],
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    # ------------------------------------------------------------------- #
    # 2. Users — 10 renewal candidates (A..J) plus pure-new pools
    # ------------------------------------------------------------------- #
    renewal_user_letters = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    renewal_users = [_make_user(f"renew_{l}") for l in renewal_user_letters]
    db.add_all(renewal_users)

    # 10 pure-new nstc candidates M..V (ranks 1..10)
    nstc_pure_letters = ["M", "N", "O", "P", "Q", "R", "S", "T", "U", "V"]
    nstc_pure_users = [_make_user(f"nstc_{l}") for l in nstc_pure_letters]
    db.add_all(nstc_pure_users)

    # 6 pure-new moe_1w candidates X..CC (ranks 3..8 — A & B challenges take 1, 2)
    moe_pure_letters = ["X", "Y", "Z", "AA", "BB", "CC"]
    moe_pure_users = [_make_user(f"moe_{l}") for l in moe_pure_letters]
    db.add_all(moe_pure_users)

    await db.commit()
    for u in renewal_users + nstc_pure_users + moe_pure_users:
        await db.refresh(u)

    # ------------------------------------------------------------------- #
    # 3. Create 10 prior-year approved nstc applications (the "previous"
    #    applications that 113-year winners hold).
    # ------------------------------------------------------------------- #
    prior_apps: list[Application] = []
    for idx, user in enumerate(renewal_users, start=1):
        prior = _make_prior_approved(
            user_id=user.id,
            scholarship_type_id=scholarship.id,
            app_id=f"APP-113-0-PRIOR{idx:02d}",
        )
        db.add(prior)
        prior_apps.append(prior)
    await db.commit()
    for p in prior_apps:
        await db.refresh(p)

    # ------------------------------------------------------------------- #
    # 4. For each prior app, create a renewal application for AY 114
    #    via ApplicationService.create_renewal_from_previous (Phase 3).
    #    Then promote them to under_review + college_reviewed so that
    #    RenewalDistributionService.auto_approve_passed_reviews can
    #    auto-approve them (Phase 5).
    # ------------------------------------------------------------------- #
    app_service = ApplicationService(db)
    renewal_apps: list[Application] = []
    for prior, user in zip(prior_apps, renewal_users):
        renewal = await app_service.create_renewal_from_previous(
            previous=prior,
            current_user=user,
            target_academic_year=CURRENT_ACADEMIC_YEAR,
            renewal_year=RENEWAL_YEAR,
        )
        # These renewals consume the prior-year (113) shared pool.
        renewal.allocation_config_id = prior_config.id
        # Promote past student_draft so the renewal distribution service can pick it up.
        renewal.status = ApplicationStatus.under_review
        renewal.review_stage = ReviewStage.college_reviewed
        renewal.agree_terms = True
        renewal_apps.append(renewal)
    await db.commit()
    for r in renewal_apps:
        await db.refresh(r)

    # Sanity: all 10 are renewals in under_review @ college_reviewed.
    assert all(r.is_renewal for r in renewal_apps)
    assert all(r.status == ApplicationStatus.under_review for r in renewal_apps)
    assert all(r.review_stage == ReviewStage.college_reviewed for r in renewal_apps)
    assert all(r.renewal_year == RENEWAL_YEAR for r in renewal_apps)
    assert all(r.sub_scholarship_type == "nstc" for r in renewal_apps)

    # ------------------------------------------------------------------- #
    # 5. Run renewal distribution — all 10 should be approved.
    # ------------------------------------------------------------------- #
    renewal_service = RenewalDistributionService(db)
    renewal_result = await renewal_service.auto_approve_passed_reviews(
        scholarship_type_id=scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
    )
    assert renewal_result["approved_count"] == 10
    for r in renewal_apps:
        await db.refresh(r)
        assert r.status == ApplicationStatus.approved
        assert r.review_stage == ReviewStage.quota_distributed

    # ------------------------------------------------------------------- #
    # 6. Renewals A and B challenge moe_1w (Phase 3 factory).
    # ------------------------------------------------------------------- #
    renewal_A = renewal_apps[0]
    renewal_B = renewal_apps[1]
    user_A = renewal_users[0]
    user_B = renewal_users[1]

    challenge_A = await app_service.create_challenge_from_renewal(
        renewal=renewal_A,
        current_user=user_A,
        target_sub_type="moe_1w",
    )
    challenge_B = await app_service.create_challenge_from_renewal(
        renewal=renewal_B,
        current_user=user_B,
        target_sub_type="moe_1w",
    )
    # Promote challenges past student_draft so they show up in the
    # general-phase candidates query.
    for challenge in (challenge_A, challenge_B):
        challenge.status = ApplicationStatus.under_review
        challenge.review_stage = ReviewStage.college_ranked
        challenge.agree_terms = True
    await db.commit()
    await db.refresh(challenge_A)
    await db.refresh(challenge_B)
    assert challenge_A.challenges_application_id == renewal_A.id
    assert challenge_B.challenges_application_id == renewal_B.id
    assert challenge_A.sub_scholarship_type == "moe_1w"

    # ------------------------------------------------------------------- #
    # 7. Pure-new nstc candidates M..V at ranks 1..10.
    # ------------------------------------------------------------------- #
    nstc_pure_apps: list[Application] = []
    for idx, (letter, user) in enumerate(zip(nstc_pure_letters, nstc_pure_users), start=1):
        app = _make_pure_new_application(
            user_id=user.id,
            scholarship_type_id=scholarship.id,
            app_id=f"APP-114-0-NSTCP{idx:02d}",
            sub_scholarship_type="nstc",
        )
        db.add(app)
        nstc_pure_apps.append(app)
    await db.commit()
    for app in nstc_pure_apps:
        await db.refresh(app)
    for idx, app in enumerate(nstc_pure_apps, start=1):
        await _attach_ranking_item(
            db,
            scholarship_type_id=scholarship.id,
            sub_type_code="nstc",
            application_id=app.id,
            rank_position=idx,
        )

    # ------------------------------------------------------------------- #
    # 8. moe_1w ranking: A (#1), B (#2), then 6 pure-new at ranks 3..8.
    # ------------------------------------------------------------------- #
    await _attach_ranking_item(
        db,
        scholarship_type_id=scholarship.id,
        sub_type_code="moe_1w",
        application_id=challenge_A.id,
        rank_position=1,
    )
    await _attach_ranking_item(
        db,
        scholarship_type_id=scholarship.id,
        sub_type_code="moe_1w",
        application_id=challenge_B.id,
        rank_position=2,
    )

    moe_pure_apps: list[Application] = []
    for idx, (letter, user) in enumerate(zip(moe_pure_letters, moe_pure_users), start=1):
        app = _make_pure_new_application(
            user_id=user.id,
            scholarship_type_id=scholarship.id,
            app_id=f"APP-114-0-MOEP{idx:02d}",
            sub_scholarship_type="moe_1w",
        )
        db.add(app)
        moe_pure_apps.append(app)
    await db.commit()
    for app in moe_pure_apps:
        await db.refresh(app)
    for idx, app in enumerate(moe_pure_apps, start=3):  # ranks 3..8
        await _attach_ranking_item(
            db,
            scholarship_type_id=scholarship.id,
            sub_type_code="moe_1w",
            application_id=app.id,
            rank_position=idx,
        )

    # ------------------------------------------------------------------- #
    # 9. Execute general distribution.
    # ------------------------------------------------------------------- #
    manual_service = ManualDistributionService(db)
    result = await manual_service.execute_general_distribution(
        scholarship_type_id=scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
    )

    # ------------------------------------------------------------------- #
    # 10. Assertions — summary stats.
    # ------------------------------------------------------------------- #
    assert renewal_result["approved_count"] == 10
    assert result["approved_challenges"] == 2
    assert result["released_slots"] == {f"nstc:{prior_config.id}": 2}
    assert result["filled_in"] == 2
    assert result["unfilled"] == 0
    # Spec §10 invariant: released == filled_in + unfilled
    assert sum(result["released_slots"].values()) == result["filled_in"] + result["unfilled"]

    # ------------------------------------------------------------------- #
    # 11. Assertions — challenge winners approved, renewals cancelled.
    # ------------------------------------------------------------------- #
    for challenge, renewal in ((challenge_A, renewal_A), (challenge_B, renewal_B)):
        await db.refresh(challenge)
        await db.refresh(renewal)
        assert challenge.status == ApplicationStatus.approved
        assert renewal.status == ApplicationStatus.cancelled_by_challenge
        assert renewal.cancelled_due_to_application_id == challenge.id

    # The other 8 renewals stay approved.
    for renewal in renewal_apps[2:]:
        await db.refresh(renewal)
        assert renewal.status == ApplicationStatus.approved

    # ------------------------------------------------------------------- #
    # 12. Assertions — nstc ranks 1..8 (M..T) approved on nstc[114].
    # ------------------------------------------------------------------- #
    for idx in range(8):
        await db.refresh(nstc_pure_apps[idx])
        assert (
            nstc_pure_apps[idx].status == ApplicationStatus.approved
        ), f"nstc rank {idx + 1} ({nstc_pure_letters[idx]}) should be approved on nstc[114]"
        item = (
            (
                await db.execute(
                    select(CollegeRankingItem).where(CollegeRankingItem.application_id == nstc_pure_apps[idx].id)
                )
            )
            .scalars()
            .first()
        )
        assert item is not None
        assert (
            item.allocation_config_id == config.id
        ), f"nstc rank {idx + 1} should occupy current config nstc[{CURRENT_ACADEMIC_YEAR}]"

    # ------------------------------------------------------------------- #
    # 13. Assertions — nstc ranks 9, 10 (U, V) filled in on nstc[113].
    # ------------------------------------------------------------------- #
    for idx in (8, 9):
        await db.refresh(nstc_pure_apps[idx])
        assert (
            nstc_pure_apps[idx].status == ApplicationStatus.approved
        ), f"nstc rank {idx + 1} ({nstc_pure_letters[idx]}) should be filled in from waitlist"
        item = (
            (
                await db.execute(
                    select(CollegeRankingItem).where(CollegeRankingItem.application_id == nstc_pure_apps[idx].id)
                )
            )
            .scalars()
            .first()
        )
        assert item is not None
        assert (
            item.allocation_config_id == prior_config.id
        ), f"nstc rank {idx + 1} should be promoted to prior config (slot freed by cancelled renewal)"

    # ------------------------------------------------------------------- #
    # 14. Assertions — moe_1w pure-new winners (ranks 3..6) approved.
    # ------------------------------------------------------------------- #
    # 6 moe_1w slots total, minus 2 taken by challenges = 4 left for pure-new.
    for idx in range(4):
        await db.refresh(moe_pure_apps[idx])
        assert (
            moe_pure_apps[idx].status == ApplicationStatus.approved
        ), f"moe_1w rank {idx + 3} ({moe_pure_letters[idx]}) should be approved"
    # The last 2 moe_1w pure-new (ranks 7, 8) stay under_review.
    for idx in range(4, 6):
        await db.refresh(moe_pure_apps[idx])
        assert moe_pure_apps[idx].status == ApplicationStatus.under_review

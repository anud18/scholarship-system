"""Tests for the 教授推薦/學院推薦 display fields on manual-distribution rows.

get_students_for_distribution must expose, per student row:
  - professor_review_items / college_review_items: per-sub-type verdicts
    ({sub_type_code, recommendation, comments}) split by reviewer role, with
    admin reviews excluded (the grid IS the admin decision surface);
  - requires_professor_recommendation: renewal-aware config flag so the UI can
    distinguish 未推薦 chips (professor step required, no verdict yet) from —
    (no professor step at all).

The college's PRIMARY verdict is the finalized ranking itself (the existing
college_rejected field) — college review items only supplement it, so there is
no requires_college_review flag.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus, ReviewStage, Semester
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.manual_distribution_service import ManualDistributionService

YEAR = 114
SEM = Semester.first.value


async def _make_user(db: AsyncSession, *, suffix: str, role: UserRole) -> User:
    user = User(
        nycu_id=f"rvd_{role.value}_{suffix}",
        name=f"Rvd {role.value} {suffix}",
        email=f"rvd_{role.value}_{suffix}@u.edu",
        user_type=UserType.student if role == UserRole.student else UserType.employee,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _add_review(
    db: AsyncSession,
    *,
    application_id: int,
    reviewer: User,
    items: list[tuple[str, str, str | None]],
) -> None:
    """Add one ApplicationReview with (sub_type_code, recommendation, comments) items."""
    review = ApplicationReview(
        application_id=application_id,
        reviewer_id=reviewer.id,
        recommendation="approve" if all(rec == "approve" for _, rec, _ in items) else "partial_approve",
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    for sub_type_code, recommendation, comments in items:
        db.add(
            ApplicationReviewItem(
                review_id=review.id,
                sub_type_code=sub_type_code,
                recommendation=recommendation,
                comments=comments,
            )
        )
    await db.commit()


async def _setup(
    db: AsyncSession,
    *,
    suffix: str,
    requires_prof: bool = True,
    renewal_requires_prof: bool = False,
    is_renewal: bool = False,
) -> tuple[ManualDistributionService, Application, int]:
    """Student + config + application + finalized ranking item.

    Returns (service, application, scholarship_type_id).
    """
    student = await _make_user(db, suffix=suffix, role=UserRole.student)

    sch = ScholarshipType(code=f"rvd_sch_{suffix}", name=f"Rvd Sch {suffix}", status="active")
    db.add(sch)
    await db.commit()
    await db.refresh(sch)

    cfg = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code=f"rvd_cfg_{suffix}",
        config_name=f"Rvd cfg {suffix}",
        academic_year=YEAR,
        semester=SEM,
        amount=30000,
        currency="TWD",
        is_active=True,
        requires_professor_recommendation=requires_prof,
        renewal_requires_professor_review=renewal_requires_prof,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)

    app = Application(
        app_id=f"APP-RVD-{suffix}",
        user_id=student.id,
        scholarship_type_id=sch.id,
        scholarship_configuration_id=cfg.id,
        sub_type_selection_mode="multiple",
        is_renewal=is_renewal,
        academic_year=YEAR,
        semester=Semester.first.value,
        review_stage=ReviewStage.college_ranked.value,
        status=ApplicationStatus.submitted.value,
        scholarship_subtype_list=["nstc", "moe_1w"],
        agree_terms=True,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)

    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="default",
        academic_year=YEAR,
        semester=SEM,
        total_applications=1,
        total_quota=5,
        is_finalized=True,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)

    item = CollegeRankingItem(ranking_id=ranking.id, application_id=app.id, rank_position=1)
    db.add(item)
    await db.commit()

    return ManualDistributionService(db), app, sch.id


@pytest.mark.asyncio
async def test_rows_split_review_items_by_role_and_exclude_admin(db: AsyncSession):
    service, app, sch_id = await _setup(db, suffix="split")
    professor = await _make_user(db, suffix="split", role=UserRole.professor)
    college = await _make_user(db, suffix="split", role=UserRole.college)
    admin = await _make_user(db, suffix="split", role=UserRole.admin)

    await _add_review(
        db,
        application_id=app.id,
        reviewer=professor,
        items=[("nstc", "approve", None), ("moe_1w", "reject", "名額有限")],
    )
    await _add_review(db, application_id=app.id, reviewer=college, items=[("nstc", "approve", "同意")])
    await _add_review(db, application_id=app.id, reviewer=admin, items=[("nstc", "reject", "admin 不算")])

    rows = await service.get_students_for_distribution(sch_id, YEAR, SEM)

    assert len(rows) == 1
    row = rows[0]
    assert row["professor_review_items"] == [
        {"sub_type_code": "nstc", "recommendation": "approve", "comments": None},
        {"sub_type_code": "moe_1w", "recommendation": "reject", "comments": "名額有限"},
    ]
    assert row["college_review_items"] == [{"sub_type_code": "nstc", "recommendation": "approve", "comments": "同意"}]
    assert row["requires_professor_recommendation"] is True


@pytest.mark.asyncio
async def test_rows_without_reviews_expose_empty_lists_and_config_flag(db: AsyncSession):
    service, _app, sch_id = await _setup(db, suffix="empty", requires_prof=False)

    rows = await service.get_students_for_distribution(sch_id, YEAR, SEM)

    assert len(rows) == 1
    row = rows[0]
    assert row["professor_review_items"] == []
    assert row["college_review_items"] == []
    assert row["requires_professor_recommendation"] is False


@pytest.mark.asyncio
async def test_review_item_sub_type_codes_are_normalized(db: AsyncSession):
    """Codes are admin-defined free-form strings — the display fields must be
    normalized (lowercase/stripped) exactly like rejected_sub_types so the
    frontend can match them against config column keys."""
    service, app, sch_id = await _setup(db, suffix="norm")
    professor = await _make_user(db, suffix="norm", role=UserRole.professor)

    await _add_review(db, application_id=app.id, reviewer=professor, items=[(" NSTC ", "approve", None)])

    rows = await service.get_students_for_distribution(sch_id, YEAR, SEM)

    assert rows[0]["professor_review_items"] == [
        {"sub_type_code": "nstc", "recommendation": "approve", "comments": None}
    ]


@pytest.mark.asyncio
async def test_renewal_rows_ignore_general_professor_flag(db: AsyncSession):
    """Renewals read renewal_requires_professor_review, NOT the general flag —
    a renewal of a scholarship whose new-application flow needs a professor
    step must not show 教授未推薦 chips when the renewal flow skips that step."""
    service, _app, sch_id = await _setup(
        db, suffix="renew", requires_prof=True, renewal_requires_prof=False, is_renewal=True
    )

    rows = await service.get_students_for_distribution(sch_id, YEAR, SEM)

    assert rows[0]["requires_professor_recommendation"] is False


@pytest.mark.asyncio
async def test_renewal_rows_use_renewal_professor_flag(db: AsyncSession):
    service, _app, sch_id = await _setup(
        db, suffix="renew2", requires_prof=False, renewal_requires_prof=True, is_renewal=True
    )

    rows = await service.get_students_for_distribution(sch_id, YEAR, SEM)

    assert rows[0]["requires_professor_recommendation"] is True

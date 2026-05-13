"""
Unit tests for the new college-review statistics endpoint (issue #216).

Pins the aggregation contract for
`GET /api/v1/college-review/statistics`:

- Permission-scoping: only scholarship_types in AdminScholarship for the
  caller appear in the response. Empty perms ⇒ empty data, success=True.
- Counts: applications, reviews-by-recommendation, items-by-sub-type-and-
  recommendation roll up correctly.
- Response shape: `{success, message, data}` per CLAUDE.md §5.
- Recommendation values stay strings ('approve' | 'partial_approve' |
  'reject' for reviews; 'approve' | 'reject' for items) so the frontend
  doesn't have to special-case enums.

We invoke the endpoint coroutine directly with a seeded async DB,
bypassing FastAPI's dependency injection — this keeps the test below
a second and avoids the SSO auth round trip.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.college_review.utilities import get_review_statistics
from app.models.application import Application, ApplicationStatus
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import AdminScholarship, User, UserRole, UserType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _seed_user(db: AsyncSession, *, role: UserRole, suffix: str) -> User:
    user = User(
        nycu_id=f"stats_{role.value}_{suffix}",
        name=f"Stats {role.value} {suffix}",
        email=f"stats_{role.value}_{suffix}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seed_scholarship(db: AsyncSession, *, code: str, name: str) -> ScholarshipType:
    stype = ScholarshipType(code=code, name=name, status="active")
    db.add(stype)
    await db.commit()
    await db.refresh(stype)
    return stype


async def _seed_config(db: AsyncSession, *, scholarship_type_id: int, suffix: str) -> ScholarshipConfiguration:
    cfg = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type_id,
        config_code=f"stats_cfg_{suffix}",
        config_name=f"Stats config {suffix}",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=True,
        requires_college_review=True,
        amount=0,
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def _seed_app(
    db: AsyncSession, *, student: User, scholarship_type_id: int, config_id: int, suffix: str
) -> Application:
    app = Application(
        app_id=f"APP-STATS-{suffix}",
        user_id=student.id,
        scholarship_type_id=scholarship_type_id,
        scholarship_configuration_id=config_id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=ApplicationStatus.submitted.value,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def _seed_review(
    db: AsyncSession,
    *,
    application: Application,
    reviewer: User,
    recommendation: str,
    items: list[tuple[str, str]],  # [(sub_type_code, recommendation)]
) -> ApplicationReview:
    review = ApplicationReview(
        application_id=application.id,
        reviewer_id=reviewer.id,
        recommendation=recommendation,
        comments="seed",
        reviewed_at=_utcnow(),
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    for sub_type, item_rec in items:
        db.add(
            ApplicationReviewItem(
                review_id=review.id,
                sub_type_code=sub_type,
                recommendation=item_rec,
                comments="seed item",
            )
        )
    await db.commit()
    return review


@pytest.mark.asyncio
async def test_statistics_empty_when_user_has_no_permissions(db: AsyncSession):
    """College user with no AdminScholarship rows ⇒ empty data, still success."""
    college_user = await _seed_user(db, role=UserRole.college, suffix="noperm")

    result = await get_review_statistics(current_user=college_user, db=db)

    assert result["success"] is True
    assert result["data"]["per_scholarship"] == []
    assert result["data"]["totals"]["applications"] == 0
    assert result["data"]["totals"]["reviews"] == 0
    assert result["data"]["totals"]["reviews_by_recommendation"] == {}
    assert result["data"]["totals"]["items_by_recommendation"] == {}


@pytest.mark.asyncio
async def test_statistics_aggregates_per_scholarship_and_total(db: AsyncSession):
    """Counts roll up correctly per scholarship + system-wide."""
    college_user = await _seed_user(db, role=UserRole.college, suffix="agg")
    professor = await _seed_user(db, role=UserRole.professor, suffix="agg")
    student = await _seed_user(db, role=UserRole.student, suffix="agg")

    phd_type = await _seed_scholarship(db, code="phd_agg", name="PhD agg")
    undergrad_type = await _seed_scholarship(db, code="ug_agg", name="UG agg")

    # User can see both scholarships.
    db.add(AdminScholarship(admin_id=college_user.id, scholarship_id=phd_type.id))
    db.add(AdminScholarship(admin_id=college_user.id, scholarship_id=undergrad_type.id))
    await db.commit()

    phd_cfg = await _seed_config(db, scholarship_type_id=phd_type.id, suffix="phd")
    ug_cfg = await _seed_config(db, scholarship_type_id=undergrad_type.id, suffix="ug")

    # 2 PhD apps, 1 UG app.
    phd_app1 = await _seed_app(
        db, student=student, scholarship_type_id=phd_type.id, config_id=phd_cfg.id, suffix="phd1"
    )
    phd_app2 = await _seed_app(
        db, student=student, scholarship_type_id=phd_type.id, config_id=phd_cfg.id, suffix="phd2"
    )
    ug_app1 = await _seed_app(
        db, student=student, scholarship_type_id=undergrad_type.id, config_id=ug_cfg.id, suffix="ug1"
    )

    # 1 PhD review (approve) with 2 items (nstc=approve, moe_1w=reject).
    await _seed_review(
        db,
        application=phd_app1,
        reviewer=professor,
        recommendation="partial_approve",
        items=[("nstc", "approve"), ("moe_1w", "reject")],
    )
    # 1 PhD review (reject) with 1 item.
    await _seed_review(
        db,
        application=phd_app2,
        reviewer=professor,
        recommendation="reject",
        items=[("nstc", "reject")],
    )
    # 1 UG review (approve) with 1 item.
    await _seed_review(
        db,
        application=ug_app1,
        reviewer=professor,
        recommendation="approve",
        items=[("default", "approve")],
    )

    result = await get_review_statistics(current_user=college_user, db=db)

    assert result["success"] is True
    assert result["message"] == "查詢成功"

    data = result["data"]
    per = {row["scholarship_type_id"]: row for row in data["per_scholarship"]}
    assert set(per.keys()) == {phd_type.id, undergrad_type.id}

    # PhD: 2 apps, 1 partial_approve + 1 reject review.
    assert per[phd_type.id]["applications"] == 2
    assert per[phd_type.id]["reviews_by_recommendation"] == {"partial_approve": 1, "reject": 1}
    phd_items = per[phd_type.id]["items_by_sub_type_and_recommendation"]
    assert phd_items["nstc"] == {"approve": 1, "reject": 1}
    assert phd_items["moe_1w"] == {"reject": 1}

    # UG: 1 app, 1 approve review.
    assert per[undergrad_type.id]["applications"] == 1
    assert per[undergrad_type.id]["reviews_by_recommendation"] == {"approve": 1}
    assert per[undergrad_type.id]["items_by_sub_type_and_recommendation"] == {"default": {"approve": 1}}

    # System-wide totals.
    totals = data["totals"]
    assert totals["applications"] == 3
    assert totals["reviews"] == 3
    assert totals["reviews_by_recommendation"] == {"partial_approve": 1, "reject": 1, "approve": 1}
    assert totals["items_by_recommendation"] == {"approve": 2, "reject": 2}


@pytest.mark.asyncio
async def test_statistics_excludes_unpermitted_scholarships(db: AsyncSession):
    """Scholarships the user has no AdminScholarship for must not appear."""
    college_user = await _seed_user(db, role=UserRole.college, suffix="scoped")
    professor = await _seed_user(db, role=UserRole.professor, suffix="scoped")
    student = await _seed_user(db, role=UserRole.student, suffix="scoped")

    allowed_type = await _seed_scholarship(db, code="allowed", name="Allowed scholarship")
    forbidden_type = await _seed_scholarship(db, code="forbidden", name="Forbidden scholarship")

    # Only the allowed type is granted.
    db.add(AdminScholarship(admin_id=college_user.id, scholarship_id=allowed_type.id))
    await db.commit()

    allowed_cfg = await _seed_config(db, scholarship_type_id=allowed_type.id, suffix="allowed")
    forbidden_cfg = await _seed_config(db, scholarship_type_id=forbidden_type.id, suffix="forbidden")

    allowed_app = await _seed_app(
        db, student=student, scholarship_type_id=allowed_type.id, config_id=allowed_cfg.id, suffix="allowed"
    )
    forbidden_app = await _seed_app(
        db,
        student=student,
        scholarship_type_id=forbidden_type.id,
        config_id=forbidden_cfg.id,
        suffix="forbidden",
    )

    await _seed_review(
        db,
        application=allowed_app,
        reviewer=professor,
        recommendation="approve",
        items=[("nstc", "approve")],
    )
    await _seed_review(
        db,
        application=forbidden_app,
        reviewer=professor,
        recommendation="reject",
        items=[("nstc", "reject")],
    )

    result = await get_review_statistics(current_user=college_user, db=db)

    per = {row["scholarship_type_id"]: row for row in result["data"]["per_scholarship"]}
    assert set(per.keys()) == {allowed_type.id}, "forbidden scholarship leaked into response"

    # Totals reflect only the allowed scope.
    totals = result["data"]["totals"]
    assert totals["applications"] == 1
    assert totals["reviews"] == 1
    assert totals["reviews_by_recommendation"] == {"approve": 1}
    assert totals["items_by_recommendation"] == {"approve": 1}

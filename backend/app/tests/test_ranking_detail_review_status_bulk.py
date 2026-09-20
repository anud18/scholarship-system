"""
Regression tests for the 學院 學生排序 ranking-detail load path.

Opening a ranking (GET /college-review/rankings/{id}) used to call
``ReviewService.get_subtype_cumulative_status`` once per ranking item — one
DB round-trip per student — so large rankings took seconds to render after
the card was clicked. The endpoint now loads every application's review
status in a single query via ``get_subtype_cumulative_status_bulk``.

These tests pin both halves: the bulk loader must agree with the per-id
loader, and the endpoint must hit ``application_reviews`` exactly once no
matter how many items the ranking has.
"""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_college
from app.main import app
from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.review_service import ReviewService

RANKING_ITEM_COUNT = 8
REVIEW_TABLE = "application_reviews"


def _user(role: UserRole, suffix: str) -> User:
    return User(
        nycu_id=f"bulk_{role.value}_{suffix}",
        name=f"Bulk {role.value} {suffix}",
        email=f"bulk_{role.value}_{suffix}@u.edu",
        user_type=UserType.student if role == UserRole.student else UserType.employee,
        role=role,
    )


async def _seed_review(
    db: AsyncSession,
    *,
    application: Application,
    reviewer: User,
    items: list[tuple[str, str]],
    reviewed_at: datetime,
) -> None:
    review = ApplicationReview(
        application_id=application.id,
        reviewer_id=reviewer.id,
        recommendation=items[0][1],
        reviewed_at=reviewed_at,
        created_at=reviewed_at,
    )
    db.add(review)
    await db.flush()
    db.add_all(
        [
            ApplicationReviewItem(
                review_id=review.id,
                sub_type_code=code,
                recommendation=recommendation,
                comments=f"{code}-{recommendation}",
            )
            for code, recommendation in items
        ]
    )
    await db.flush()


async def _seed_ranking(db: AsyncSession, item_count: int) -> tuple[CollegeRanking, list[Application], User]:
    """A ranking whose items cover every review-status shape: no review, approve only,
    reject only, approve-then-reject, reject-then-approve."""
    admin = _user(UserRole.admin, "a1")
    professor = _user(UserRole.professor, "p1")
    college = _user(UserRole.college, "c1")
    db.add_all([admin, professor, college])
    await db.flush()

    stype = ScholarshipType(
        code="phd_bulk_status",
        name="PhD bulk status",
        sub_type_selection_mode=SubTypeSelectionMode.multiple,
        status="active",
    )
    db.add(stype)
    await db.flush()
    db.add(
        ScholarshipConfiguration(
            scholarship_type_id=stype.id,
            academic_year=114,
            semester=None,
            config_name="PhD bulk 114",
            config_code="phd-bulk-114",
            amount=40000,
            is_active=True,
        )
    )

    ranking = CollegeRanking(
        scholarship_type_id=stype.id,
        sub_type_code="default",
        academic_year=114,
        ranking_name="bulk",
        created_by=admin.id,
        is_finalized=False,
    )
    db.add(ranking)
    await db.flush()

    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    applications: list[Application] = []
    for index in range(item_count):
        student = _user(UserRole.student, f"s{index}")
        db.add(student)
        await db.flush()
        application = Application(
            app_id=f"APP-114-0-{index:05d}",
            user_id=student.id,
            scholarship_type_id=stype.id,
            academic_year=114,
            semester=None,
            status=ApplicationStatus.under_review,
            sub_type_selection_mode=SubTypeSelectionMode.multiple,
            student_data={"std_stdcode": f"3104600{index:02d}", "std_cname": f"學生{index}"},
            scholarship_subtype_list=["nstc", "moe_1w"],
            submitted_form_data={"fields": {}},
        )
        db.add(application)
        await db.flush()
        applications.append(application)

        shape = index % 5
        if shape == 1:
            await _seed_review(
                db, application=application, reviewer=professor, items=[("nstc", "approve")], reviewed_at=base_time
            )
        elif shape == 2:
            await _seed_review(
                db, application=application, reviewer=professor, items=[("NSTC ", "reject")], reviewed_at=base_time
            )
        elif shape == 3:
            await _seed_review(
                db, application=application, reviewer=professor, items=[("nstc", "approve")], reviewed_at=base_time
            )
            await _seed_review(
                db,
                application=application,
                reviewer=college,
                items=[("nstc", "reject"), ("moe_1w", "approve")],
                reviewed_at=base_time + timedelta(days=1),
            )
        elif shape == 4:
            await _seed_review(
                db, application=application, reviewer=professor, items=[("moe_1w", "reject")], reviewed_at=base_time
            )
            await _seed_review(
                db,
                application=application,
                reviewer=college,
                items=[("moe_1w", "approve")],
                reviewed_at=base_time + timedelta(days=1),
            )

        db.add(
            CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=application.id,
                rank_position=index + 1,
                status="ranked",
                college_rejected=False,
                is_allocated=False,
            )
        )
    await db.commit()
    return ranking, applications, admin


@pytest.mark.asyncio
async def test_bulk_status_matches_per_application_status(db: AsyncSession):
    _, applications, _ = await _seed_ranking(db, RANKING_ITEM_COUNT)
    service = ReviewService(db)

    bulk = await service.get_subtype_cumulative_status_bulk([application.id for application in applications])

    assert set(bulk) == {application.id for application in applications}
    for application in applications:
        assert bulk[application.id] == await service.get_subtype_cumulative_status(application.id)

    # Spot-check the shapes so a regression that returns {} everywhere cannot pass.
    assert bulk[applications[0].id] == {}
    assert bulk[applications[1].id]["nstc"]["status"] == "approved"
    assert bulk[applications[2].id]["nstc"]["status"] == "rejected"
    assert bulk[applications[2].id]["nstc"]["rejected_by"]["role"] == "professor"
    assert bulk[applications[3].id]["nstc"]["rejected_by"]["role"] == "college"
    assert bulk[applications[3].id]["moe_1w"]["status"] == "approved"
    # An earlier reject is never overturned by a later approve.
    assert bulk[applications[4].id]["moe_1w"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_bulk_status_ignores_empty_and_duplicate_ids(db: AsyncSession):
    _, applications, _ = await _seed_ranking(db, 2)
    service = ReviewService(db)

    assert await service.get_subtype_cumulative_status_bulk([]) == {}
    duplicated = await service.get_subtype_cumulative_status_bulk([applications[1].id, applications[1].id, None])
    assert list(duplicated) == [applications[1].id]


@pytest.mark.asyncio
async def test_ranking_detail_queries_reviews_once(client: AsyncClient, db: AsyncSession):
    ranking, applications, admin = await _seed_ranking(db, RANKING_ITEM_COUNT)

    review_selects: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        if statement.lstrip().upper().startswith("SELECT") and REVIEW_TABLE in statement:
            review_selects.append(statement)

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", _record)
    app.dependency_overrides[require_college] = lambda: admin
    try:
        response = await client.get(f"/api/v1/college-review/rankings/{ranking.id}")
    finally:
        app.dependency_overrides.pop(require_college, None)
        event.remove(engine, "before_cursor_execute", _record)

    assert response.status_code == 200, response.text
    items = response.json()["data"]["items"]
    assert len(items) == RANKING_ITEM_COUNT
    assert len(review_selects) == 1, f"expected one review-status query, got {len(review_selects)}"

    by_app_id = {item["application"]["id"]: item for item in items}
    rejected = {entry["code"]: entry for entry in by_app_id[applications[2].id]["application"]["eligible_subtypes"]}
    assert rejected["nstc"]["is_rejected"] is True
    assert rejected["nstc"]["rejection_reason"] == "NSTC -reject"
    assert rejected["moe_1w"]["is_rejected"] is False

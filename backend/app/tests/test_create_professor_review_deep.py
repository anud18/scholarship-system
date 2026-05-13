"""
Deep async-DB tests for `ApplicationService.create_professor_review`.

Pins the professor review submission contract — the workhorse of the
review pipeline. Critical pieces:
- Assignment guard (only the assigned professor can submit).
- Overall-recommendation derivation: all approve→approve, all
  reject→reject, mixed→partial_approve.
- Upsert semantics: re-submitting replaces the previous review's items
  (no duplicate item rows accumulating).
- review_stage advancement to professor_reviewed.

Contract pinned (5 cases):
- 404 when application_id not found.
- Wrong professor (assignment guard) raises AuthorizationError.
- All-approve items → recommendation='approve', review row + items
  persisted, review_stage advanced.
- Mixed-approve-reject items → recommendation='partial_approve'.
- Re-submit replaces items (upsert; no duplicates).
"""

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError
from app.models.application import Application, ApplicationStatus
from app.models.enums import ReviewStage
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.schemas.review import ReviewCreate, ReviewItemCreate
from app.services.application_service import ApplicationService


def _val(x):
    return x.value if hasattr(x, "value") else x


async def _seed_user(db: AsyncSession, *, role: UserRole, nycu_id: str) -> User:
    u = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _seed_config(db: AsyncSession, *, suffix: str) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"profrev_{suffix}", name=f"ProfRev type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"profrev_cfg_{suffix}",
        config_name=f"ProfRev cfg {suffix}",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=True,
        requires_college_review=False,
        amount=0,
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def _seed_app(
    db: AsyncSession,
    *,
    student: User,
    config: ScholarshipConfiguration,
    status: str,
    professor_id: int | None,
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-PROFREV-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
        professor_id=professor_id,
        submitted_form_data={"fields": {}, "documents": []},
        student_data={"std_cname": student.name},
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.fixture
def silence_email_automation(monkeypatch):
    """email_automation_service.trigger_professor_review_submitted runs at the
    end; stub it out (test-irrelevant + needs SMTP config)."""
    from app.services import application_service as svc_module

    monkeypatch.setattr(
        svc_module.email_automation_service,
        "trigger_professor_review_submitted",
        AsyncMock(return_value=None),
    )


@pytest.mark.asyncio
async def test_not_found_raises(db: AsyncSession, silence_email_automation):
    professor = await _seed_user(db, role=UserRole.professor, nycu_id="profrev_prof_404")
    service = ApplicationService(db)
    review_data = ReviewCreate(
        application_id=999_999,
        items=[ReviewItemCreate(sub_type_code="nstc", recommendation="approve")],
    )
    with pytest.raises(NotFoundError):
        await service.create_professor_review(999_999, professor, review_data)


@pytest.mark.asyncio
async def test_wrong_professor_raises_authorization_error(db: AsyncSession, silence_email_automation):
    student = await _seed_user(db, role=UserRole.student, nycu_id="profrev_stu_xpr")
    prof_a = await _seed_user(db, role=UserRole.professor, nycu_id="profrev_a")
    prof_b = await _seed_user(db, role=UserRole.professor, nycu_id="profrev_b")
    cfg = await _seed_config(db, suffix="xpr")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=prof_a.id,
        suffix="xpr",
    )
    service = ApplicationService(db)
    review_data = ReviewCreate(
        application_id=app.id,
        items=[ReviewItemCreate(sub_type_code="nstc", recommendation="approve")],
    )
    with pytest.raises(AuthorizationError):
        await service.create_professor_review(app.id, prof_b, review_data)


@pytest.mark.asyncio
async def test_all_approve_results_in_approve_recommendation(db: AsyncSession, silence_email_automation):
    student = await _seed_user(db, role=UserRole.student, nycu_id="profrev_stu_allappr")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="profrev_prof_allappr")
    cfg = await _seed_config(db, suffix="allappr")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=prof.id,
        suffix="allappr",
    )
    service = ApplicationService(db)
    review_data = ReviewCreate(
        application_id=app.id,
        items=[
            ReviewItemCreate(sub_type_code="nstc", recommendation="approve"),
            ReviewItemCreate(sub_type_code="moe_1w", recommendation="approve"),
        ],
    )

    await service.create_professor_review(app.id, prof, review_data)

    # One ApplicationReview with recommendation='approve' + 2 items.
    reviews = (
        (
            await db.execute(
                select(ApplicationReview).where(
                    ApplicationReview.application_id == app.id,
                    ApplicationReview.reviewer_id == prof.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(reviews) == 1
    assert reviews[0].recommendation == "approve"

    items = (
        (await db.execute(select(ApplicationReviewItem).where(ApplicationReviewItem.review_id == reviews[0].id)))
        .scalars()
        .all()
    )
    assert len(items) == 2
    assert {i.sub_type_code for i in items} == {"nstc", "moe_1w"}

    # review_stage advanced to professor_reviewed.
    await db.refresh(app)
    assert _val(app.review_stage) == ReviewStage.professor_reviewed.value


@pytest.mark.asyncio
async def test_mixed_approve_reject_produces_partial_approve(db: AsyncSession, silence_email_automation):
    student = await _seed_user(db, role=UserRole.student, nycu_id="profrev_stu_mix")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="profrev_prof_mix")
    cfg = await _seed_config(db, suffix="mix")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=prof.id,
        suffix="mix",
    )
    service = ApplicationService(db)
    review_data = ReviewCreate(
        application_id=app.id,
        items=[
            ReviewItemCreate(sub_type_code="nstc", recommendation="approve"),
            ReviewItemCreate(sub_type_code="moe_1w", recommendation="reject", comments="GPA too low"),
        ],
    )

    await service.create_professor_review(app.id, prof, review_data)

    reviews = (
        (
            await db.execute(
                select(ApplicationReview).where(
                    ApplicationReview.application_id == app.id,
                    ApplicationReview.reviewer_id == prof.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(reviews) == 1
    assert reviews[0].recommendation == "partial_approve"


@pytest.mark.asyncio
async def test_resubmit_replaces_items_no_duplicates(db: AsyncSession, silence_email_automation):
    """Re-submitting upserts: previous items are deleted, new ones inserted."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="profrev_stu_resub")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="profrev_prof_resub")
    cfg = await _seed_config(db, suffix="resub")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=prof.id,
        suffix="resub",
    )
    service = ApplicationService(db)

    # First submission: 2 items.
    await service.create_professor_review(
        app.id,
        prof,
        ReviewCreate(
            application_id=app.id,
            items=[
                ReviewItemCreate(sub_type_code="nstc", recommendation="approve"),
                ReviewItemCreate(sub_type_code="moe_1w", recommendation="approve"),
            ],
        ),
    )

    # Second submission with different sub_type and recommendation.
    await service.create_professor_review(
        app.id,
        prof,
        ReviewCreate(
            application_id=app.id,
            items=[ReviewItemCreate(sub_type_code="nstc", recommendation="reject")],
        ),
    )

    # Still exactly one ApplicationReview row (upsert by professor).
    reviews = (
        (
            await db.execute(
                select(ApplicationReview).where(
                    ApplicationReview.application_id == app.id,
                    ApplicationReview.reviewer_id == prof.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(reviews) == 1
    assert reviews[0].recommendation == "reject"

    # Items are replaced: now 1 item, not 3 accumulated.
    items = (
        (await db.execute(select(ApplicationReviewItem).where(ApplicationReviewItem.review_id == reviews[0].id)))
        .scalars()
        .all()
    )
    assert len(items) == 1
    assert items[0].sub_type_code == "nstc"
    assert items[0].recommendation == "reject"

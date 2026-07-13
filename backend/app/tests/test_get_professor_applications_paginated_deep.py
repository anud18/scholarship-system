"""
Deep async-DB tests for `ApplicationService.get_professor_applications_paginated`.

Drives the professor dashboard's review queue (paginated). Three filter
rules + pagination + ordering — any of them silently misbehaving would
show the wrong applications to the wrong professor.

Contract pinned (6 cases):
- Base filter: only applications with requires_professor_recommendation=True.
- Base filter: only applications assigned to the calling professor.
- Base filter: only statuses in {submitted, under_review, approved,
  partial_approved, rejected}; drafts are excluded.
- status_filter='pending' → applications this professor has NOT reviewed yet
  (no ApplicationReview row authored by them), regardless of Application.status.
- status_filter='completed' → applications this professor HAS reviewed.
- Pagination: page=2, size=2 returns rows 3-4 of an ordered set; total
  count reflects the full filtered set, not the page.
- No implicit cap: the default call (size omitted) returns EVERY assigned
  application — professors must see all of them (the old default silently
  truncated the list to 20).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.review import ApplicationReview
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService


async def _seed_review(db: AsyncSession, *, application: Application, reviewer_id: int) -> ApplicationReview:
    """Record a professor review for ``application`` — the signal that moves it
    from 待審核 (pending) to 已完成 (completed)."""
    review = ApplicationReview(
        application_id=application.id,
        reviewer_id=reviewer_id,
        recommendation="approve",
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(review)
    await db.commit()
    return review


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


async def _seed_config(db: AsyncSession, *, requires_prof: bool, suffix: str) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"profpag_{suffix}", name=f"ProfPag type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"profpag_cfg_{suffix}",
        config_name=f"ProfPag cfg {suffix}",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        # Review windows are retained for realism, but the professor queue no
        # longer phase-gates — it buckets by whether the professor has reviewed.
        professor_review_start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        professor_review_end=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=requires_prof,
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
    created_at: datetime | None = None,
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-PROFPAG-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
        professor_id=professor_id,
    )
    if created_at:
        app.created_at = created_at
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.mark.asyncio
async def test_excludes_apps_where_scholarship_does_not_require_professor(db: AsyncSession):
    student = await _seed_user(db, role=UserRole.student, nycu_id="profpag_stu_noprof")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="profpag_prof_noprof")
    cfg_yes = await _seed_config(db, requires_prof=True, suffix="yes")
    cfg_no = await _seed_config(db, requires_prof=False, suffix="no")

    await _seed_app(
        db,
        student=student,
        config=cfg_yes,
        status=ApplicationStatus.submitted.value,
        professor_id=prof.id,
        suffix="yes",
    )
    await _seed_app(
        db, student=student, config=cfg_no, status=ApplicationStatus.submitted.value, professor_id=prof.id, suffix="no"
    )

    service = ApplicationService(db)
    apps, total = await service.get_professor_applications_paginated(professor_id=prof.id)
    assert total == 1
    assert len(apps) == 1


@pytest.mark.asyncio
async def test_excludes_apps_assigned_to_other_professors(db: AsyncSession):
    student = await _seed_user(db, role=UserRole.student, nycu_id="profpag_stu_assign")
    me = await _seed_user(db, role=UserRole.professor, nycu_id="profpag_me")
    other = await _seed_user(db, role=UserRole.professor, nycu_id="profpag_other")
    cfg = await _seed_config(db, requires_prof=True, suffix="assign")

    await _seed_app(
        db, student=student, config=cfg, status=ApplicationStatus.submitted.value, professor_id=me.id, suffix="mine"
    )
    await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=other.id,
        suffix="theirs1",
    )
    await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.under_review.value,
        professor_id=other.id,
        suffix="theirs2",
    )

    service = ApplicationService(db)
    apps, total = await service.get_professor_applications_paginated(professor_id=me.id)
    assert total == 1


@pytest.mark.asyncio
async def test_excludes_drafts(db: AsyncSession):
    student = await _seed_user(db, role=UserRole.student, nycu_id="profpag_stu_draft")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="profpag_prof_draft")
    cfg = await _seed_config(db, requires_prof=True, suffix="draft")

    await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=prof.id,
        suffix="submitted",
    )
    await _seed_app(
        db, student=student, config=cfg, status=ApplicationStatus.draft.value, professor_id=prof.id, suffix="draft"
    )

    service = ApplicationService(db)
    apps, total = await service.get_professor_applications_paginated(professor_id=prof.id)
    assert total == 1


@pytest.mark.asyncio
async def test_status_filter_pending_is_apps_without_professor_review(db: AsyncSession):
    """pending = assigned apps this professor has NOT reviewed yet — independent
    of Application.status. A professor-approved app whose scholarship requires
    college review stays at under_review (issue #182) but must NOT appear in
    pending once the review row exists."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="profpag_stu_pending")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="profpag_prof_pending")
    cfg = await _seed_config(db, requires_prof=True, suffix="pending")

    # Two apps left un-reviewed → pending.
    await _seed_app(
        db, student=student, config=cfg, status=ApplicationStatus.submitted.value, professor_id=prof.id, suffix="p1"
    )
    await _seed_app(
        db, student=student, config=cfg, status=ApplicationStatus.under_review.value, professor_id=prof.id, suffix="p2"
    )
    # Two apps the professor already reviewed (still under_review) → NOT pending.
    reviewed_a = await _seed_app(
        db, student=student, config=cfg, status=ApplicationStatus.under_review.value, professor_id=prof.id, suffix="p3"
    )
    reviewed_b = await _seed_app(
        db, student=student, config=cfg, status=ApplicationStatus.approved.value, professor_id=prof.id, suffix="p4"
    )
    await _seed_review(db, application=reviewed_a, reviewer_id=prof.id)
    await _seed_review(db, application=reviewed_b, reviewer_id=prof.id)

    service = ApplicationService(db)
    apps, total = await service.get_professor_applications_paginated(professor_id=prof.id, status_filter="pending")
    assert total == 2
    returned = {a.id for a in apps}
    assert reviewed_a.id not in returned
    assert reviewed_b.id not in returned


@pytest.mark.asyncio
async def test_status_filter_completed_is_apps_with_professor_review(db: AsyncSession):
    """completed = assigned apps this professor HAS reviewed — independent of
    Application.status."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="profpag_stu_done")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="profpag_prof_done")
    cfg = await _seed_config(db, requires_prof=True, suffix="done")

    # Un-reviewed → NOT completed.
    await _seed_app(
        db, student=student, config=cfg, status=ApplicationStatus.submitted.value, professor_id=prof.id, suffix="d1"
    )
    # Three reviewed apps spanning different statuses → all completed.
    r1 = await _seed_app(
        db, student=student, config=cfg, status=ApplicationStatus.under_review.value, professor_id=prof.id, suffix="d2"
    )
    r2 = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.partial_approved.value,
        professor_id=prof.id,
        suffix="d3",
    )
    r3 = await _seed_app(
        db, student=student, config=cfg, status=ApplicationStatus.rejected.value, professor_id=prof.id, suffix="d4"
    )
    for app in (r1, r2, r3):
        await _seed_review(db, application=app, reviewer_id=prof.id)

    service = ApplicationService(db)
    apps, total = await service.get_professor_applications_paginated(professor_id=prof.id, status_filter="completed")
    assert total == 3
    assert {a.id for a in apps} == {r1.id, r2.id, r3.id}


@pytest.mark.asyncio
async def test_pagination_returns_correct_slice_and_total(db: AsyncSession):
    """page=2, size=2 returns rows 3-4. total_count reflects the full filtered set."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="profpag_stu_page")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="profpag_prof_page")
    cfg = await _seed_config(db, requires_prof=True, suffix="page")

    now = datetime.now(timezone.utc)
    # Seed 5 apps with descending created_at so the order is deterministic.
    for i in range(5):
        await _seed_app(
            db,
            student=student,
            config=cfg,
            status=ApplicationStatus.submitted.value,
            professor_id=prof.id,
            created_at=now - timedelta(days=i),
            suffix=f"page_{i}",
        )

    service = ApplicationService(db)
    page2, total = await service.get_professor_applications_paginated(professor_id=prof.id, page=2, size=2)
    # Total reflects the full set, not just this page.
    assert total == 5
    # The page has 2 rows.
    assert len(page2) == 2


@pytest.mark.asyncio
async def test_default_call_returns_all_applications_without_cap(db: AsyncSession):
    """size omitted → every assigned application is returned (no implicit 20-row cap)."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="profpag_stu_nocap")
    prof = await _seed_user(db, role=UserRole.professor, nycu_id="profpag_prof_nocap")
    cfg = await _seed_config(db, requires_prof=True, suffix="nocap")

    # 25 apps > the old default page size of 20.
    for i in range(25):
        await _seed_app(
            db,
            student=student,
            config=cfg,
            status=ApplicationStatus.submitted.value,
            professor_id=prof.id,
            suffix=f"nocap_{i}",
        )

    service = ApplicationService(db)
    apps, total = await service.get_professor_applications_paginated(professor_id=prof.id)
    assert total == 25
    assert len(apps) == 25

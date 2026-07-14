"""Tests for Phase 4 review-routing filter (renewal vs general phase).

Verifies ``apply_renewal_phase_filter`` correctly restricts pending-review
listings so educators see only the applications appropriate for the current
review window:

  - During the renewal review window: only ``is_renewal=True`` applications
    whose configuration has a currently-open renewal window.
  - During the general review window: only ``is_renewal=False`` applications
    whose configuration has a currently-open general window.

These tests intentionally exercise the SQL filter against real rows via the
in-memory SQLite test fixtures rather than mocking the query, so we catch
join / column-name regressions early.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.services.review_phase_filter import apply_renewal_phase_filter

CURRENT_ACADEMIC_YEAR = 114


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_config_in_renewal_phase(
    scholarship_type_id: int,
    *,
    role: str,
    config_code: str,
    academic_year: int = CURRENT_ACADEMIC_YEAR,
) -> ScholarshipConfiguration:
    """ScholarshipConfiguration with the renewal-{role}-review window open NOW
    and the general-{role}-review window closed (in the future).
    """
    now = datetime.now(timezone.utc)
    open_start = now - timedelta(days=1)
    open_end = now + timedelta(days=7)
    closed_start = now + timedelta(days=14)
    closed_end = now + timedelta(days=21)

    kwargs = dict(
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=None,
        config_name=f"Config {config_code}",
        config_code=config_code,
        amount=30000,
        currency="TWD",
        is_active=True,
    )
    if role == "professor":
        kwargs.update(
            renewal_requires_professor_review=True,
            renewal_professor_review_start=open_start,
            renewal_professor_review_end=open_end,
            professor_review_start=closed_start,
            professor_review_end=closed_end,
        )
    elif role == "college":
        kwargs.update(
            renewal_requires_college_review=True,
            renewal_college_review_start=open_start,
            renewal_college_review_end=open_end,
            college_review_start=closed_start,
            college_review_end=closed_end,
        )
    else:  # pragma: no cover
        raise ValueError(role)

    return ScholarshipConfiguration(**kwargs)


def _make_config_in_general_phase(
    scholarship_type_id: int,
    *,
    role: str,
    config_code: str,
    academic_year: int = CURRENT_ACADEMIC_YEAR,
) -> ScholarshipConfiguration:
    """ScholarshipConfiguration with the general-{role}-review window open NOW
    and the renewal-{role}-review window already closed (in the past).
    """
    now = datetime.now(timezone.utc)
    closed_start = now - timedelta(days=21)
    closed_end = now - timedelta(days=14)
    open_start = now - timedelta(days=1)
    open_end = now + timedelta(days=7)

    kwargs = dict(
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=None,
        config_name=f"Config {config_code}",
        config_code=config_code,
        amount=30000,
        currency="TWD",
        is_active=True,
    )
    if role == "professor":
        kwargs.update(
            renewal_requires_professor_review=True,
            renewal_professor_review_start=closed_start,
            renewal_professor_review_end=closed_end,
            professor_review_start=open_start,
            professor_review_end=open_end,
        )
    elif role == "college":
        kwargs.update(
            renewal_requires_college_review=True,
            renewal_college_review_start=closed_start,
            renewal_college_review_end=closed_end,
            college_review_start=open_start,
            college_review_end=open_end,
        )
    else:  # pragma: no cover
        raise ValueError(role)

    return ScholarshipConfiguration(**kwargs)


async def _make_pending_application(
    db: AsyncSession,
    *,
    user: User,
    scholarship_type: ScholarshipType,
    configuration_id: Optional[int],
    is_renewal: bool,
    app_id_suffix: str,
    academic_year: int = CURRENT_ACADEMIC_YEAR,
) -> Application:
    app = Application(
        app_id=f"APP-{academic_year}-0-{app_id_suffix}",
        user_id=user.id,
        scholarship_type_id=scholarship_type.id,
        scholarship_configuration_id=configuration_id,
        scholarship_subtype_list=["nstc"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
        academic_year=academic_year,
        semester=None,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.professor_review,
        is_renewal=is_renewal,
        agree_terms=True,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


# --------------------------------------------------------------------------- #
# Professor-role tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_professor_sees_only_renewal_during_renewal_period(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Configuration is in its renewal_professor_review window NOW.

    Only the renewal application should pass the filter; the general one
    should be filtered out.
    """
    config = _make_config_in_renewal_phase(test_scholarship.id, role="professor", config_code="PROF-RENEW")
    db.add(config)
    await db.commit()
    await db.refresh(config)

    renewal_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=True,
        app_id_suffix="00001",
    )
    general_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=False,
        app_id_suffix="00002",
    )

    stmt = select(Application).where(Application.status == ApplicationStatus.under_review.value)
    stmt = apply_renewal_phase_filter(stmt, role="professor")

    result = await db.execute(stmt)
    visible_ids = {row.id for row in result.scalars().all()}

    assert renewal_app.id in visible_ids, "renewal application should be visible during renewal phase"
    assert general_app.id not in visible_ids, "general application should NOT be visible during renewal phase"


@pytest.mark.asyncio
async def test_renewal_hidden_when_admin_disabled_renewal_professor_review(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Renewal window is open NOW, but the admin turned OFF
    renewal_requires_professor_review — the renewal application must be
    hidden from the professor's pending list despite the open window.
    """
    config = _make_config_in_renewal_phase(test_scholarship.id, role="professor", config_code="PROF-RENEW-OFF")
    config.renewal_requires_professor_review = False
    db.add(config)
    await db.commit()
    await db.refresh(config)

    renewal_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=True,
        app_id_suffix="00021",
    )

    stmt = select(Application).where(Application.status == ApplicationStatus.under_review.value)
    stmt = apply_renewal_phase_filter(stmt, role="professor")

    result = await db.execute(stmt)
    visible_ids = {row.id for row in result.scalars().all()}

    assert (
        renewal_app.id not in visible_ids
    ), "renewal application must be hidden when the admin disabled renewal professor review"


@pytest.mark.asyncio
async def test_professor_sees_only_general_during_general_period(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Configuration is in its general professor_review window NOW.

    Only the non-renewal application should pass the filter; the renewal
    one should be filtered out.
    """
    config = _make_config_in_general_phase(test_scholarship.id, role="professor", config_code="PROF-GEN")
    db.add(config)
    await db.commit()
    await db.refresh(config)

    renewal_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=True,
        app_id_suffix="00011",
    )
    general_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=False,
        app_id_suffix="00012",
    )

    stmt = select(Application).where(Application.status == ApplicationStatus.under_review.value)
    stmt = apply_renewal_phase_filter(stmt, role="professor")

    result = await db.execute(stmt)
    visible_ids = {row.id for row in result.scalars().all()}

    assert general_app.id in visible_ids, "general application should be visible during general phase"
    assert renewal_app.id not in visible_ids, "renewal application should NOT be visible during general phase"


# --------------------------------------------------------------------------- #
# College-role tests (mirror of the professor pair)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_college_sees_only_renewal_during_renewal_period(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    config = _make_config_in_renewal_phase(test_scholarship.id, role="college", config_code="COL-RENEW")
    db.add(config)
    await db.commit()
    await db.refresh(config)

    renewal_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=True,
        app_id_suffix="00021",
    )
    general_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=False,
        app_id_suffix="00022",
    )

    stmt = select(Application).where(Application.status == ApplicationStatus.under_review.value)
    stmt = apply_renewal_phase_filter(stmt, role="college")

    result = await db.execute(stmt)
    visible_ids = {row.id for row in result.scalars().all()}

    assert renewal_app.id in visible_ids
    assert general_app.id not in visible_ids


@pytest.mark.asyncio
async def test_college_sees_only_general_during_general_period(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    config = _make_config_in_general_phase(test_scholarship.id, role="college", config_code="COL-GEN")
    db.add(config)
    await db.commit()
    await db.refresh(config)

    renewal_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=True,
        app_id_suffix="00031",
    )
    general_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=False,
        app_id_suffix="00032",
    )

    stmt = select(Application).where(Application.status == ApplicationStatus.under_review.value)
    stmt = apply_renewal_phase_filter(stmt, role="college")

    result = await db.execute(stmt)
    visible_ids = {row.id for row in result.scalars().all()}

    assert general_app.id in visible_ids
    assert renewal_app.id not in visible_ids


# --------------------------------------------------------------------------- #
# Edge case: outside any window → nothing visible
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Integration tests: exercise the filter through the actual service methods
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_application_service_pending_list_splits_by_professor_review_existence(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
    test_professor: User,
):
    """End-to-end check that ApplicationService.get_professor_applications_paginated
    buckets applications by whether THIS professor has already reviewed them,
    not by Application.status or the renewal review phase.

    The professor listing no longer applies apply_renewal_phase_filter: a
    professor "approve" on a requires-college scholarship keeps status at
    under_review (issue #182), so status-based bucketing kept already-reviewed
    apps in 待審核. The sound signal is the existence of an ApplicationReview
    row authored by the professor.

    Expectation:
      - pending   → only apps with NO review by this professor
      - completed → only apps the professor has already reviewed
      - all/None  → 全部 = pending + completed (every assigned app)
    """
    from app.models.review import ApplicationReview
    from app.services.application_service import ApplicationService

    # Config sits in its renewal window (general window in the future). Under the
    # old phase gate the general app would have been hidden from pending — it must
    # now surface because phase gating is gone.
    config = _make_config_in_renewal_phase(test_scholarship.id, role="professor", config_code="SVC-PROF-RENEW")
    config.requires_professor_recommendation = True
    db.add(config)
    await db.commit()
    await db.refresh(config)

    reviewed_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=True,
        app_id_suffix="00051",
    )
    unreviewed_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=False,
        app_id_suffix="00052",
    )
    reviewed_app.professor_id = test_professor.id
    unreviewed_app.professor_id = test_professor.id

    # Record a professor review for one app only. Its status stays under_review
    # (mirrors the issue #182 behaviour) yet it must count as 已完成.
    db.add(
        ApplicationReview(
            application_id=reviewed_app.id,
            reviewer_id=test_professor.id,
            recommendation="approve",
            reviewed_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    service = ApplicationService(db)

    pending, pending_total = await service.get_professor_applications_paginated(
        professor_id=test_professor.id, status_filter="pending", page=1, size=20
    )
    pending_ids = {a.id for a in pending}
    assert unreviewed_app.id in pending_ids, "un-reviewed app must be in 待審核"
    assert reviewed_app.id not in pending_ids, "reviewed app must NOT be in 待審核 despite under_review status"
    assert pending_total == 1

    completed, completed_total = await service.get_professor_applications_paginated(
        professor_id=test_professor.id, status_filter="completed", page=1, size=20
    )
    completed_ids = {a.id for a in completed}
    assert reviewed_app.id in completed_ids, "reviewed app must be in 已完成"
    assert unreviewed_app.id not in completed_ids, "un-reviewed app must NOT be in 已完成"
    assert completed_total == 1

    all_apps, all_total = await service.get_professor_applications_paginated(
        professor_id=test_professor.id, status_filter="all", page=1, size=20
    )
    all_ids = {a.id for a in all_apps}
    assert all_ids == {reviewed_app.id, unreviewed_app.id}, "全部 must equal 待審核 + 已完成"
    assert all_total == pending_total + completed_total


@pytest.mark.asyncio
async def test_college_service_pending_list_shows_all_regardless_of_phase(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """End-to-end check that CollegeReviewService.get_applications_for_review
    shows EVERY application in the college regardless of the renewal/general
    review phase.

    This intentionally reverses the earlier phase-gated college behaviour:
    「學院端應該要可以看到隸屬於該學院的所有申請，即使還卡在教授審核的階段」.
    The college listing is no longer time-gated, so both the renewal and the
    general pending apps surface even while only the renewal_college_review
    window is open. The professor listing likewise no longer phase-gates — it
    buckets by professor-review existence (see the service test above).
    """
    from app.services.college_review_service import CollegeReviewService

    # Configuration currently in renewal_college_review window with the general
    # college_review window still in the future. Under the old phase-gated
    # behaviour this would have hidden the general pending app.
    config = _make_config_in_renewal_phase(test_scholarship.id, role="college", config_code="SVC-COL-RENEW")
    db.add(config)
    await db.commit()
    await db.refresh(config)

    # Pending renewal app — visible.
    renewal_pending = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=True,
        app_id_suffix="00061",
    )
    # Pending general app — now ALSO visible (previously hidden by the gate).
    general_pending = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=False,
        app_id_suffix="00062",
    )
    # Approved general app — historical visibility unchanged.
    approved_general = Application(
        app_id=f"APP-{CURRENT_ACADEMIC_YEAR}-0-00063",
        user_id=test_user.id,
        scholarship_type_id=test_scholarship.id,
        scholarship_configuration_id=config.id,
        scholarship_subtype_list=["nstc"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
        academic_year=CURRENT_ACADEMIC_YEAR,
        semester=None,
        status=ApplicationStatus.approved,
        is_renewal=False,
        agree_terms=True,
    )
    db.add(approved_general)
    await db.commit()
    await db.refresh(approved_general)

    service = CollegeReviewService(db)
    rows = await service.get_applications_for_review(
        scholarship_type_id=test_scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
    )
    visible_ids = {r["id"] for r in rows}

    assert renewal_pending.id in visible_ids, "renewal pending app should be visible"
    assert general_pending.id in visible_ids, "general pending app should now be visible (no college phase gate)"
    assert approved_general.id in visible_ids, "approved app should always remain visible"


@pytest.mark.asyncio
async def test_college_service_sees_pending_app_still_in_professor_stage(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """Regression for 「學院端應該看得到還卡在教授審核階段的申請」.

    The configuration's professor review window is open NOW; the college
    review window is not set / not open yet. Previously the college listing
    was time-gated by apply_renewal_phase_filter(role="college"), so a
    professor-stage application was invisible to the college until the college
    window opened. It must now be visible.
    """
    from app.services.college_review_service import CollegeReviewService

    # Professor general window open now; college windows left unset (None) →
    # the old gate would have hidden every pending row for the college.
    config = _make_config_in_general_phase(test_scholarship.id, role="professor", config_code="SVC-PROF-STAGE")
    db.add(config)
    await db.commit()
    await db.refresh(config)

    professor_stage_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=False,
        app_id_suffix="00071",
    )

    service = CollegeReviewService(db)
    rows = await service.get_applications_for_review(
        scholarship_type_id=test_scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
    )
    visible_ids = {r["id"] for r in rows}

    assert professor_stage_app.id in visible_ids, "college must see apps still in the professor review stage"


@pytest.mark.asyncio
async def test_nothing_visible_when_outside_any_review_window(
    db: AsyncSession,
    test_user: User,
    test_scholarship: ScholarshipType,
):
    """If both the renewal and general windows for a configuration are closed
    relative to NOW, the filter must hide BOTH renewal and general apps.
    """
    now = datetime.now(timezone.utc)
    config = ScholarshipConfiguration(
        scholarship_type_id=test_scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
        semester=None,
        config_name="Config Closed",
        config_code="PROF-CLOSED",
        amount=30000,
        currency="TWD",
        is_active=True,
        # All windows are firmly in the past
        renewal_professor_review_start=now - timedelta(days=30),
        renewal_professor_review_end=now - timedelta(days=20),
        professor_review_start=now - timedelta(days=19),
        professor_review_end=now - timedelta(days=10),
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    renewal_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=True,
        app_id_suffix="00041",
    )
    general_app = await _make_pending_application(
        db,
        user=test_user,
        scholarship_type=test_scholarship,
        configuration_id=config.id,
        is_renewal=False,
        app_id_suffix="00042",
    )

    stmt = select(Application).where(Application.status == ApplicationStatus.under_review.value)
    stmt = apply_renewal_phase_filter(stmt, role="professor")

    result = await db.execute(stmt)
    visible_ids = {row.id for row in result.scalars().all()}

    assert renewal_app.id not in visible_ids
    assert general_app.id not in visible_ids

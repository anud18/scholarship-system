"""
Regression tests for ReviewService.update_application_status — issue #182.

Before the fix, a single professor "approve" recommendation flipped
``application.status`` straight to ``approved``, even when the scholarship
configuration had ``requires_college_review=True``. That bypassed the
college step AND locked the student out of withdrawal (``withdraw`` only
accepts ``submitted`` / ``under_review``).

These tests pin the gating behavior in place: with college review required,
a professor "approve" must keep the app at ``under_review``; once college
also approves, status flips to ``approved``.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus, ReviewStage
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.review_service import ReviewService


def _val(x):
    """Normalise enum/string for stable equality assertions."""
    return x.value if hasattr(x, "value") else x


def _user(role: UserRole, suffix: str) -> User:
    return User(
        nycu_id=f"gating_{role.value}_{suffix}",
        name=f"Gating {role.value} {suffix}",
        email=f"gating_{role.value}_{suffix}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
    )


async def _seed_scholarship_and_config(db: AsyncSession, *, requires_college_review: bool) -> ScholarshipConfiguration:
    """Insert a minimal ScholarshipType + ScholarshipConfiguration pair."""
    stype = ScholarshipType(
        code=f"phd_test_{int(requires_college_review)}",
        name=f"PhD test ({'college' if requires_college_review else 'no-college'})",
        status="active",
    )
    db.add(stype)
    await db.commit()
    await db.refresh(stype)

    config = ScholarshipConfiguration(
        scholarship_type_id=stype.id,
        config_code=f"phd_test_cfg_{int(requires_college_review)}",
        config_name="PhD test config",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=True,
        requires_college_review=requires_college_review,
        amount=0,
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def _seed_app(
    db: AsyncSession,
    *,
    student: User,
    config: ScholarshipConfiguration,
    subtypes: list[str] | None = None,
) -> Application:
    """Seed an application. ``subtypes`` is the configured sub-type list; leaving
    it None keeps the column at its default ``[]``, which the service treats as
    the single implicit "default" sub-type."""
    app = Application(
        app_id=f"APP-GATING-{config.id}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=ApplicationStatus.submitted.value,
        scholarship_subtype_list=subtypes if subtypes is not None else [],
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
    sub_type_code: str,
    recommendation: str,
) -> None:
    review = ApplicationReview(
        application_id=application.id,
        reviewer_id=reviewer.id,
        recommendation=recommendation,
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    item = ApplicationReviewItem(
        review_id=review.id,
        sub_type_code=sub_type_code,
        recommendation=recommendation,
    )
    db.add(item)
    await db.commit()


async def _seed_multi_item_review(
    db: AsyncSession,
    *,
    application: Application,
    reviewer: User,
    items: list[tuple[str, str]],
    overall_recommendation: str,
) -> None:
    """Seed ONE review carrying several sub-type items.

    ``application_reviews`` is uniquely constrained on (application_id,
    reviewer_id), so a reviewer's verdicts across sub-types all hang off a
    single review row — this is the shape a split verdict actually has in the
    database. ``items`` is a list of (sub_type_code, recommendation) pairs.
    """
    review = ApplicationReview(
        application_id=application.id,
        reviewer_id=reviewer.id,
        recommendation=overall_recommendation,
        reviewed_at=datetime.now(timezone.utc),
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)

    for sub_type_code, recommendation in items:
        db.add(
            ApplicationReviewItem(
                review_id=review.id,
                sub_type_code=sub_type_code,
                recommendation=recommendation,
            )
        )
    await db.commit()


# ---------------------------------------------------------------------------
# The bug fix — issue #182
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_professor_approve_keeps_status_under_review_when_college_required(db: AsyncSession):
    """The exact scenario from issue #182.

    Config: requires_professor_recommendation=True, requires_college_review=True.
    Action: a professor approves the only sub-type.
    Expected: status stays at under_review (NOT approved); review_stage=professor_reviewed.
    """
    student = _user(UserRole.student, "s")
    professor = _user(UserRole.professor, "p")
    db.add_all([student, professor])
    await db.commit()
    await db.refresh(student)
    await db.refresh(professor)

    config = await _seed_scholarship_and_config(db, requires_college_review=True)
    app = await _seed_app(db, student=student, config=config)
    await _seed_review(db, application=app, reviewer=professor, sub_type_code="default", recommendation="approve")

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert (
        _val(final_status) == ApplicationStatus.under_review.value
    ), f"professor approve should not promote to approved when college review required; got {final_status}"
    # Identity-mapped — the object the test holds is the same one the service
    # mutated. We assert directly rather than db.refresh, because refresh would
    # revert the in-memory change back to the (still-uncommitted) DB row.
    assert _val(app.status) == ApplicationStatus.under_review.value
    assert _val(app.review_stage) == ReviewStage.professor_reviewed.value


@pytest.mark.asyncio
async def test_college_approve_after_professor_promotes_to_approved(db: AsyncSession):
    """Continuing #182 — once college also approves, status should flip to approved."""
    student = _user(UserRole.student, "s2")
    professor = _user(UserRole.professor, "p2")
    college = _user(UserRole.college, "c2")
    db.add_all([student, professor, college])
    await db.commit()
    for u in (student, professor, college):
        await db.refresh(u)

    config = await _seed_scholarship_and_config(db, requires_college_review=True)
    app = await _seed_app(db, student=student, config=config)
    await _seed_review(db, application=app, reviewer=professor, sub_type_code="default", recommendation="approve")
    await _seed_review(db, application=app, reviewer=college, sub_type_code="default", recommendation="approve")

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert _val(final_status) == ApplicationStatus.approved.value
    assert _val(app.review_stage) == ReviewStage.college_reviewed.value


@pytest.mark.asyncio
async def test_professor_approve_promotes_to_approved_when_no_college_review(db: AsyncSession):
    """Pre-fix happy path must not regress.

    Config: requires_college_review=False.
    A professor approve should still flip status to approved immediately
    (there's no college step in the configured pipeline).
    """
    student = _user(UserRole.student, "s3")
    professor = _user(UserRole.professor, "p3")
    db.add_all([student, professor])
    await db.commit()
    await db.refresh(student)
    await db.refresh(professor)

    config = await _seed_scholarship_and_config(db, requires_college_review=False)
    app = await _seed_app(db, student=student, config=config)
    await _seed_review(db, application=app, reviewer=professor, sub_type_code="default", recommendation="approve")

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert _val(final_status) == ApplicationStatus.approved.value
    assert _val(app.review_stage) == ReviewStage.professor_reviewed.value


@pytest.mark.asyncio
async def test_full_reject_is_terminal_regardless_of_pipeline(db: AsyncSession):
    """A professor full-reject sets status=rejected.

    (Policy: a professor reject means the application is rejected. College/admin
    still retain the right to edit / send it back — 回發 — afterwards, but that is
    a separate explicit action, not this update_application_status path.)"""
    student = _user(UserRole.student, "s4")
    professor = _user(UserRole.professor, "p4")
    db.add_all([student, professor])
    await db.commit()
    await db.refresh(student)
    await db.refresh(professor)

    config = await _seed_scholarship_and_config(db, requires_college_review=True)
    app = await _seed_app(db, student=student, config=config)
    await _seed_review(db, application=app, reviewer=professor, sub_type_code="default", recommendation="reject")

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert _val(final_status) == ApplicationStatus.rejected.value


# ---------------------------------------------------------------------------
# Multi-sub-type coverage — a verdict is only final once EVERY configured
# sub-type has been decided.
#
# Two defects lived in the same expression. `get_subtype_cumulative_status`
# only returns sub-types somebody actually reviewed, and the professor branch
# judged all_approved/all_rejected over that partial set while having no
# `else` for a mixed verdict. So:
#   * approve + reject in one submission -> neither branch fired, status was
#     left at whatever it was (`submitted`), which is what surfaced in the
#     college queue as 已提交 next to an otherwise identical 審核中 row.
#   * reject on 1 of 2 sub-types -> read as "all rejected", terminally
#     rejecting the application (and locking the professor out per the
#     professor-reject-is-terminal policy) before sub-type 2 was ever seen.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_professor_split_verdict_advances_to_under_review(db: AsyncSession):
    """approve on one sub-type + reject on the other must not leave status untouched.

    This is the reported scenario: an application configured for [nstc, moe_1w]
    whose professor recommended nstc and rejected moe_1w sat at ``submitted``
    (已提交) while a single-sub-type application at the very same stage showed
    ``under_review`` (審核中).
    """
    student = _user(UserRole.student, "s5")
    professor = _user(UserRole.professor, "p5")
    db.add_all([student, professor])
    await db.commit()
    await db.refresh(student)
    await db.refresh(professor)

    config = await _seed_scholarship_and_config(db, requires_college_review=True)
    app = await _seed_app(db, student=student, config=config, subtypes=["nstc", "moe_1w"])
    await _seed_multi_item_review(
        db,
        application=app,
        reviewer=professor,
        items=[("nstc", "approve"), ("moe_1w", "reject")],
        overall_recommendation="partial_approve",
    )

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert _val(final_status) == ApplicationStatus.under_review.value, (
        "a split professor verdict must advance the application, not leave it at "
        f"the pre-review status; got {final_status}"
    )
    assert _val(app.status) == ApplicationStatus.under_review.value
    assert _val(app.review_stage) == ReviewStage.professor_reviewed.value


@pytest.mark.asyncio
async def test_reject_on_one_of_two_subtypes_is_not_terminal(db: AsyncSession):
    """Rejecting 1 of 2 sub-types must NOT terminally reject the application.

    The UI lets a professor decide sub-types one at a time ("審核進度 X / N"),
    so an un-decided sub-type is simply absent from the cumulative status. Read
    naively that lone reject looks like a unanimous rejection, which would set
    status=rejected and lock the professor out of ever reviewing sub-type 2.
    """
    student = _user(UserRole.student, "s6")
    professor = _user(UserRole.professor, "p6")
    db.add_all([student, professor])
    await db.commit()
    await db.refresh(student)
    await db.refresh(professor)

    config = await _seed_scholarship_and_config(db, requires_college_review=True)
    app = await _seed_app(db, student=student, config=config, subtypes=["nstc", "moe_1w"])
    # Only nstc is decided; moe_1w is left untouched for a later submission.
    await _seed_review(db, application=app, reviewer=professor, sub_type_code="nstc", recommendation="reject")

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert _val(final_status) != ApplicationStatus.rejected.value, (
        "a reject covering only some sub-types must not be treated as a full "
        "rejection — that permanently locks the professor out of the rest"
    )
    assert _val(final_status) == ApplicationStatus.under_review.value


@pytest.mark.asyncio
async def test_approve_on_one_of_two_subtypes_does_not_finalize(db: AsyncSession):
    """Approving 1 of 2 sub-types must not finalize, even with no college step.

    ``requires_college_review=False`` removes the college gate, so this isolates
    the coverage check: the only thing keeping the app off ``approved`` is that
    moe_1w has not been decided by anyone yet.
    """
    student = _user(UserRole.student, "s7")
    professor = _user(UserRole.professor, "p7")
    db.add_all([student, professor])
    await db.commit()
    await db.refresh(student)
    await db.refresh(professor)

    config = await _seed_scholarship_and_config(db, requires_college_review=False)
    app = await _seed_app(db, student=student, config=config, subtypes=["nstc", "moe_1w"])
    await _seed_review(db, application=app, reviewer=professor, sub_type_code="nstc", recommendation="approve")

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert (
        _val(final_status) == ApplicationStatus.under_review.value
    ), f"moe_1w is still undecided, so the application is not approved; got {final_status}"


@pytest.mark.asyncio
async def test_verdict_finalizes_once_every_subtype_is_decided(db: AsyncSession):
    """The counterpart to the coverage gate: full coverage still resolves.

    Same config as above (no college step). With every sub-type decided, the
    mixed verdict resolves to ``partial_approved`` rather than sitting at
    ``under_review`` forever.
    """
    student = _user(UserRole.student, "s8")
    professor = _user(UserRole.professor, "p8")
    db.add_all([student, professor])
    await db.commit()
    await db.refresh(student)
    await db.refresh(professor)

    config = await _seed_scholarship_and_config(db, requires_college_review=False)
    app = await _seed_app(db, student=student, config=config, subtypes=["nstc", "moe_1w"])
    await _seed_multi_item_review(
        db,
        application=app,
        reviewer=professor,
        items=[("nstc", "approve"), ("moe_1w", "reject")],
        overall_recommendation="partial_approve",
    )

    service = ReviewService(db)
    final_status = await service.update_application_status(app.id)

    assert _val(final_status) == ApplicationStatus.partial_approved.value

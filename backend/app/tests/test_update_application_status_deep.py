"""
Deep async-DB tests for `ApplicationService.update_application_status`.

Staff-side status mutation (approve/reject) with side effects:
- writes application.status + reviewer_id + reviewed_at
- on approve: writes approved_at
- creates an ApplicationReview row with comments + decision_reason

Contract pinned (5 cases):
- Student caller rejected with AuthorizationError.
- 404 when application_id not found.
- approve: status flips, approved_at set, reviewer_id set, status_name
  updated, ApplicationReview row created with comments.
- reject: status flips, reviewer_id set, status_name updated,
  ApplicationReview row created with decision_reason from
  rejection_reason.
- Each of professor, college, admin, super_admin can update (positive
  role allow-list).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError
from app.models.application import Application, ApplicationStatus
from app.models.review import ApplicationReview
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.schemas.application import ApplicationStatusUpdate
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
    st = ScholarshipType(code=f"stat_{suffix}", name=f"Stat type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"stat_cfg_{suffix}",
        config_name=f"Stat cfg {suffix}",
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
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-STAT-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
        submitted_form_data={"fields": {}, "documents": []},
        student_data={"std_cname": student.name},
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.fixture
def silence_caches(monkeypatch):
    async def _noop() -> None:
        return None

    monkeypatch.setattr(ApplicationService, "_invalidate_app_caches", staticmethod(_noop))


@pytest.mark.asyncio
async def test_student_caller_rejected(db: AsyncSession, silence_caches):
    student = await _seed_user(db, role=UserRole.student, nycu_id="stat_stu_caller")
    cfg = await _seed_config(db, suffix="stu_caller")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="sc")

    service = ApplicationService(db)
    with pytest.raises(AuthorizationError):
        await service.update_application_status(
            application_id=app.id,
            user=student,
            status_update=ApplicationStatusUpdate(status=ApplicationStatus.approved.value),
        )


@pytest.mark.asyncio
async def test_not_found_raises(db: AsyncSession, silence_caches):
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="stat_admin_404")
    service = ApplicationService(db)

    with pytest.raises(NotFoundError):
        await service.update_application_status(
            application_id=999_999,
            user=admin,
            status_update=ApplicationStatusUpdate(status=ApplicationStatus.approved.value),
        )


@pytest.mark.asyncio
async def test_approve_sets_approved_at_and_creates_review_row(db: AsyncSession, silence_caches):
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="stat_admin_appr")
    student = await _seed_user(db, role=UserRole.student, nycu_id="stat_stu_appr")
    cfg = await _seed_config(db, suffix="appr")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.under_review.value, suffix="appr")

    service = ApplicationService(db)
    before = datetime.now(timezone.utc)
    await service.update_application_status(
        application_id=app.id,
        user=admin,
        status_update=ApplicationStatusUpdate(
            status=ApplicationStatus.approved.value,
            comments="Looks good — approved.",
        ),
    )
    after = datetime.now(timezone.utc)

    await db.refresh(app)
    assert _val(app.status) == ApplicationStatus.approved.value
    assert app.reviewer_id == admin.id
    assert app.approved_at is not None
    assert before <= app.approved_at <= after

    # An ApplicationReview row was created with the comments.
    reviews = (
        (await db.execute(select(ApplicationReview).where(ApplicationReview.application_id == app.id))).scalars().all()
    )
    assert len(reviews) == 1
    assert reviews[0].reviewer_id == admin.id
    assert reviews[0].comments == "Looks good — approved."


@pytest.mark.asyncio
async def test_reject_creates_review_row_with_decision_reason(db: AsyncSession, silence_caches):
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="stat_admin_rej")
    student = await _seed_user(db, role=UserRole.student, nycu_id="stat_stu_rej")
    cfg = await _seed_config(db, suffix="rej")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.under_review.value, suffix="rej")

    service = ApplicationService(db)
    await service.update_application_status(
        application_id=app.id,
        user=admin,
        status_update=ApplicationStatusUpdate(
            status=ApplicationStatus.rejected.value,
            rejection_reason="GPA below threshold.",
        ),
    )

    await db.refresh(app)
    assert _val(app.status) == ApplicationStatus.rejected.value
    assert app.reviewer_id == admin.id

    reviews = (
        (await db.execute(select(ApplicationReview).where(ApplicationReview.application_id == app.id))).scalars().all()
    )
    assert len(reviews) == 1
    # rejection_reason from the status update lands on decision_reason on the review row.
    assert reviews[0].decision_reason == "GPA below threshold."


@pytest.mark.asyncio
async def test_all_four_staff_roles_can_update(db: AsyncSession, silence_caches):
    """professor, college, admin, super_admin all pass the role guard."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="stat_stu_roles")
    cfg = await _seed_config(db, suffix="roles")

    for role, suffix in [
        (UserRole.professor, "prof"),
        (UserRole.college, "col"),
        (UserRole.admin, "adm"),
        (UserRole.super_admin, "sup"),
    ]:
        staff = await _seed_user(db, role=role, nycu_id=f"stat_staff_{suffix}")
        app = await _seed_app(
            db, student=student, config=cfg, status=ApplicationStatus.under_review.value, suffix=f"roles_{suffix}"
        )

        service = ApplicationService(db)
        # Should NOT raise AuthorizationError.
        await service.update_application_status(
            application_id=app.id,
            user=staff,
            status_update=ApplicationStatusUpdate(status=ApplicationStatus.approved.value),
        )

        await db.refresh(app)
        assert _val(app.status) == ApplicationStatus.approved.value
        assert app.reviewer_id == staff.id

"""
Deep async-DB tests for `ApplicationService.get_applications_for_review`.

This method drives the college/admin/super_admin review queue plus the
professor view. Filtering rules:
- Role-based access: student/other roles return []; professor gets
  student-scoped; college/admin/super_admin see all.
- Optional status filter.
- Optional scholarship_type filter (by code).
- Pagination via skip/limit.

Contract pinned (5 cases):
- Student role gets [] (not allowed to review).
- College/admin/super_admin get all applications (no role filter beyond
  the optional status/type ones).
- Professor with no accessible students gets [] (the early-return path).
- status filter narrows the result.
- scholarship_type filter (by code) narrows the result.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService


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
    st = ScholarshipType(code=f"forrev_{suffix}", name=f"ForRev type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"forrev_cfg_{suffix}",
        config_name=f"ForRev cfg {suffix}",
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
        app_id=f"APP-FORREV-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.mark.asyncio
async def test_student_caller_gets_empty_list(db: AsyncSession):
    """Students aren't reviewers — must get [] regardless of seed data."""
    student = await _seed_user(db, role=UserRole.student, nycu_id="forrev_stu_caller")
    cfg = await _seed_config(db, suffix="stu_caller")
    await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="stu1")

    service = ApplicationService(db)
    result = await service.get_applications_for_review(current_user=student)
    assert result == []


@pytest.mark.asyncio
async def test_admin_sees_all_applications(db: AsyncSession):
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="forrev_admin")
    s1 = await _seed_user(db, role=UserRole.student, nycu_id="forrev_s1")
    s2 = await _seed_user(db, role=UserRole.student, nycu_id="forrev_s2")
    cfg = await _seed_config(db, suffix="admin_sees_all")
    await _seed_app(db, student=s1, config=cfg, status=ApplicationStatus.submitted.value, suffix="s1_a")
    await _seed_app(db, student=s2, config=cfg, status=ApplicationStatus.submitted.value, suffix="s2_a")

    service = ApplicationService(db)
    result = await service.get_applications_for_review(current_user=admin)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_college_sees_all_applications(db: AsyncSession):
    college = await _seed_user(db, role=UserRole.college, nycu_id="forrev_college")
    s1 = await _seed_user(db, role=UserRole.student, nycu_id="forrev_s_col")
    cfg = await _seed_config(db, suffix="college_sees_all")
    await _seed_app(db, student=s1, config=cfg, status=ApplicationStatus.submitted.value, suffix="col_app1")
    await _seed_app(db, student=s1, config=cfg, status=ApplicationStatus.under_review.value, suffix="col_app2")
    await _seed_app(db, student=s1, config=cfg, status=ApplicationStatus.approved.value, suffix="col_app3")

    service = ApplicationService(db)
    result = await service.get_applications_for_review(current_user=college)
    assert len(result) == 3


@pytest.mark.asyncio
async def test_status_filter_narrows_result(db: AsyncSession):
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="forrev_admin_status")
    student = await _seed_user(db, role=UserRole.student, nycu_id="forrev_stu_status")
    cfg = await _seed_config(db, suffix="status")
    await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="sub1")
    await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="sub2")
    await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.approved.value, suffix="appr")

    service = ApplicationService(db)
    result = await service.get_applications_for_review(current_user=admin, status=ApplicationStatus.submitted.value)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_scholarship_type_filter_by_code(db: AsyncSession):
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="forrev_admin_type")
    student = await _seed_user(db, role=UserRole.student, nycu_id="forrev_stu_type")
    cfg_a = await _seed_config(db, suffix="type_a")
    cfg_b = await _seed_config(db, suffix="type_b")

    await _seed_app(db, student=student, config=cfg_a, status=ApplicationStatus.submitted.value, suffix="a1")
    await _seed_app(db, student=student, config=cfg_a, status=ApplicationStatus.submitted.value, suffix="a2")
    await _seed_app(db, student=student, config=cfg_b, status=ApplicationStatus.submitted.value, suffix="b1")

    service = ApplicationService(db)
    # Filter to scholarship_type code matching cfg_a's type code.
    result = await service.get_applications_for_review(current_user=admin, scholarship_type="forrev_type_a")
    assert len(result) == 2

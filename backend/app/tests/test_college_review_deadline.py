"""
Regression tests for CollegeReviewService.assert_ranking_within_deadline — issue #63.

College users must not be able to create / update / finalize / unfinalize a
ranking once the scholarship_configuration's college_review_end deadline has
passed. Admins / super_admins keep an escape hatch. The deadline lives on
ScholarshipConfiguration scoped by (type_id, academic_year, semester).
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.college_review_service import CollegeReviewService


def _make_user(role: UserRole, suffix: str) -> User:
    return User(
        nycu_id=f"deadlinetest_{role.value}_{suffix}",
        name=f"Deadline Test {role.value} {suffix}",
        email=f"deadlinetest_{role.value}_{suffix}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
    )


async def _make_scholarship_with_config(
    db: AsyncSession,
    code_suffix: str,
    college_review_end: Optional[datetime],
    academic_year: int = 114,
    semester: Optional[str] = "first",
) -> tuple[ScholarshipType, ScholarshipConfiguration]:
    sch = ScholarshipType(
        code=f"deadlinetest_{code_suffix.lower()}",
        name=f"Deadline Test {code_suffix}",
        description="Test fixture for #63 deadline guard",
    )
    db.add(sch)
    await db.commit()
    await db.refresh(sch)

    cfg = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=academic_year,
        semester=semester,
        config_name=f"Deadline Test Config {code_suffix}",
        config_code=f"deadlinetest_cfg_{code_suffix.lower()}",
        amount=10000,
        college_review_end=college_review_end,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return sch, cfg


@pytest.mark.asyncio
async def test_passes_when_deadline_in_future(db: AsyncSession):
    college_user = _make_user(UserRole.college, "future")
    db.add(college_user)
    await db.commit()
    await db.refresh(college_user)
    sch, _ = await _make_scholarship_with_config(
        db, "future", datetime.now(timezone.utc) + timedelta(days=3)
    )

    service = CollegeReviewService(db)
    await service.assert_ranking_within_deadline(sch.id, 114, "first", college_user)


@pytest.mark.asyncio
async def test_passes_when_no_deadline_set(db: AsyncSession):
    college_user = _make_user(UserRole.college, "none")
    db.add(college_user)
    await db.commit()
    await db.refresh(college_user)
    sch, _ = await _make_scholarship_with_config(db, "none", None)

    service = CollegeReviewService(db)
    await service.assert_ranking_within_deadline(sch.id, 114, "first", college_user)


@pytest.mark.asyncio
async def test_passes_when_no_matching_config(db: AsyncSession):
    """No-op when there's no config matching (year, semester) — let other validation surface that."""
    college_user = _make_user(UserRole.college, "noconfig")
    db.add(college_user)
    await db.commit()
    await db.refresh(college_user)
    sch, _ = await _make_scholarship_with_config(
        db, "noconfig", datetime.now(timezone.utc) - timedelta(days=10), academic_year=110, semester="first"
    )

    service = CollegeReviewService(db)
    # Asking about academic_year=999 (no matching config) should NOT raise
    await service.assert_ranking_within_deadline(sch.id, 999, "first", college_user)


@pytest.mark.asyncio
async def test_raises_when_deadline_in_past_for_college_user(db: AsyncSession):
    college_user = _make_user(UserRole.college, "past")
    db.add(college_user)
    await db.commit()
    await db.refresh(college_user)
    sch, _ = await _make_scholarship_with_config(
        db, "past", datetime.now(timezone.utc) - timedelta(days=1)
    )

    service = CollegeReviewService(db)
    with pytest.raises(AuthorizationError) as exc_info:
        await service.assert_ranking_within_deadline(sch.id, 114, "first", college_user)
    assert "已過排名截止時間" in str(exc_info.value)


@pytest.mark.asyncio
async def test_admin_bypasses_passed_deadline(db: AsyncSession):
    admin_user = _make_user(UserRole.admin, "bypass")
    db.add(admin_user)
    await db.commit()
    await db.refresh(admin_user)
    sch, _ = await _make_scholarship_with_config(
        db, "bypass", datetime.now(timezone.utc) - timedelta(days=1)
    )

    service = CollegeReviewService(db)
    # Admin bypass — should NOT raise even though deadline is in the past
    await service.assert_ranking_within_deadline(sch.id, 114, "first", admin_user)


@pytest.mark.asyncio
async def test_super_admin_bypasses_passed_deadline(db: AsyncSession):
    super_admin = _make_user(UserRole.super_admin, "sbypass")
    db.add(super_admin)
    await db.commit()
    await db.refresh(super_admin)
    sch, _ = await _make_scholarship_with_config(
        db, "sbypass", datetime.now(timezone.utc) - timedelta(hours=1)
    )

    service = CollegeReviewService(db)
    await service.assert_ranking_within_deadline(sch.id, 114, "first", super_admin)

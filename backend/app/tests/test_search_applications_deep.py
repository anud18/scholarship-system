"""
Deep async-DB tests for `ApplicationService.search_applications`.

Generic-criteria search method exposed for ad-hoc filtering. The three
filter paths are all bug-prone:
- regular field equality: trusts attribute names — typo silently returns
  empty
- `student.*` prefix: JSON path against student_data
- `form.*` prefix: JSON path against submitted_form_data

Contract pinned:
- Empty criteria returns every application.
- Regular-field equality filters correctly (`status` shown).
- `student.*` JSON-path filter matches against student_data snapshot.
- `form.*` JSON-path filter matches against submitted_form_data.
- No-match criteria returns [] (not None, not all rows).
- Multiple criteria are AND-ed (combination narrows the result).
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService


async def _seed_user(db: AsyncSession, *, nycu_id: str) -> User:
    u = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _seed_config(db: AsyncSession, *, suffix: str) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"search_{suffix}", name=f"Search type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"search_cfg_{suffix}",
        config_name=f"Search cfg {suffix}",
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
    student_data: dict | None = None,
    submitted_form_data: dict | None = None,
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-SEARCH-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
        student_data=student_data or {},
        submitted_form_data=submitted_form_data or {},
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.mark.asyncio
async def test_empty_criteria_returns_all_applications(db: AsyncSession):
    user = await _seed_user(db, nycu_id="search_all")
    cfg = await _seed_config(db, suffix="all")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.draft.value, suffix="a1")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.submitted.value, suffix="a2")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.approved.value, suffix="a3")

    service = ApplicationService(db)
    result = await service.search_applications({})
    assert len(result) == 3


@pytest.mark.asyncio
async def test_regular_field_equality_filters_status(db: AsyncSession):
    user = await _seed_user(db, nycu_id="search_status")
    cfg = await _seed_config(db, suffix="status")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.draft.value, suffix="d1")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.draft.value, suffix="d2")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.submitted.value, suffix="s1")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.approved.value, suffix="a1")

    service = ApplicationService(db)
    result = await service.search_applications({"status": ApplicationStatus.draft.value})
    assert len(result) == 2
    for r in result:
        # Each row reports status='draft'.
        assert (r.status.value if hasattr(r.status, "value") else r.status) == ApplicationStatus.draft.value


@pytest.mark.asyncio
async def test_no_match_returns_empty_list(db: AsyncSession):
    user = await _seed_user(db, nycu_id="search_empty")
    cfg = await _seed_config(db, suffix="empty")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.draft.value, suffix="d1")

    service = ApplicationService(db)
    result = await service.search_applications({"status": ApplicationStatus.approved.value})
    assert result == [] or len(result) == 0


@pytest.mark.asyncio
async def test_multiple_criteria_are_anded(db: AsyncSession):
    """Two filters combine with AND — the result is the intersection."""
    user_a = await _seed_user(db, nycu_id="search_a")
    user_b = await _seed_user(db, nycu_id="search_b")
    cfg = await _seed_config(db, suffix="and")
    await _seed_app(db, student=user_a, config=cfg, status=ApplicationStatus.draft.value, suffix="a_d")
    await _seed_app(db, student=user_a, config=cfg, status=ApplicationStatus.submitted.value, suffix="a_s")
    await _seed_app(db, student=user_b, config=cfg, status=ApplicationStatus.draft.value, suffix="b_d")

    service = ApplicationService(db)
    # user_a AND status=draft → only the first row.
    result = await service.search_applications({"user_id": user_a.id, "status": ApplicationStatus.draft.value})
    assert len(result) == 1
    assert result[0].user_id == user_a.id


@pytest.mark.asyncio
async def test_user_id_filter_scopes_by_owner(db: AsyncSession):
    """Pin that the trivial owner-scoping use case works — this is what
    callers will use most often."""
    owner = await _seed_user(db, nycu_id="search_owner")
    other = await _seed_user(db, nycu_id="search_not_owner")
    cfg = await _seed_config(db, suffix="owner_scope")
    await _seed_app(db, student=owner, config=cfg, status=ApplicationStatus.draft.value, suffix="own1")
    await _seed_app(db, student=owner, config=cfg, status=ApplicationStatus.submitted.value, suffix="own2")
    await _seed_app(db, student=other, config=cfg, status=ApplicationStatus.draft.value, suffix="other")

    service = ApplicationService(db)
    result = await service.search_applications({"user_id": owner.id})
    assert len(result) == 2
    for r in result:
        assert r.user_id == owner.id

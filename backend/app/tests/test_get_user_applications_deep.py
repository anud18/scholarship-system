"""
Deep async-DB tests for `ApplicationService.get_user_applications`.

The student-side "My Applications" list method. The SQL has three
filtering rules that matter to the UI:
- user scoping (the calling user only sees their own apps)
- soft-delete exclusion when no status filter is passed
- explicit-status passthrough overrides the deleted-exclusion default
  (so admins viewing the deleted bucket aren't surprised)

Contract pinned (5 cases):
- User scoping: only the caller's apps are returned.
- No status filter: deleted apps are excluded by default.
- Explicit status filter: status=deleted returns deleted apps (does NOT
  inherit the default-exclude rule).
- Explicit status filter: status=draft returns only drafts.
- Result is ordered by created_at DESC.
"""

from datetime import datetime, timedelta, timezone

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
    st = ScholarshipType(code=f"list_{suffix}", name=f"List type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"list_cfg_{suffix}",
        config_name=f"List cfg {suffix}",
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
    created_at: datetime | None = None,
    suffix: str,
) -> Application:
    app = Application(
        app_id=f"APP-LIST-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
        submitted_form_data={"fields": {}, "documents": []},
    )
    if created_at:
        app.created_at = created_at
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.mark.asyncio
async def test_user_scoping_only_returns_callers_apps(db: AsyncSession):
    user = await _seed_user(db, nycu_id="list_owner")
    other = await _seed_user(db, nycu_id="list_other")
    cfg = await _seed_config(db, suffix="scope")

    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.draft.value, suffix="own1")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.submitted.value, suffix="own2")
    await _seed_app(db, student=other, config=cfg, status=ApplicationStatus.draft.value, suffix="other1")

    service = ApplicationService(db)
    result = await service.get_user_applications(user)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_no_status_filter_excludes_deleted_by_default(db: AsyncSession):
    user = await _seed_user(db, nycu_id="list_no_filter")
    cfg = await _seed_config(db, suffix="excl_del")

    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.draft.value, suffix="active1")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.submitted.value, suffix="active2")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.deleted.value, suffix="deleted")

    service = ApplicationService(db)
    result = await service.get_user_applications(user)
    # Deleted is excluded by default.
    assert len(result) == 2


@pytest.mark.asyncio
async def test_explicit_status_deleted_returns_deleted_apps(db: AsyncSession):
    """The explicit-status path overrides the default-exclude rule.

    If a caller asks for status=deleted, they want deleted apps — the
    method must NOT silently swallow them via the default exclusion.
    """
    user = await _seed_user(db, nycu_id="list_explicit_del")
    cfg = await _seed_config(db, suffix="explicit_del")

    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.draft.value, suffix="active")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.deleted.value, suffix="deleted1")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.deleted.value, suffix="deleted2")

    service = ApplicationService(db)
    result = await service.get_user_applications(user, status=ApplicationStatus.deleted.value)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_explicit_status_draft_returns_only_drafts(db: AsyncSession):
    user = await _seed_user(db, nycu_id="list_only_draft")
    cfg = await _seed_config(db, suffix="only_draft")

    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.draft.value, suffix="draft1")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.draft.value, suffix="draft2")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.submitted.value, suffix="submitted")
    await _seed_app(db, student=user, config=cfg, status=ApplicationStatus.approved.value, suffix="approved")

    service = ApplicationService(db)
    result = await service.get_user_applications(user, status=ApplicationStatus.draft.value)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_results_ordered_by_created_at_desc(db: AsyncSession):
    user = await _seed_user(db, nycu_id="list_order")
    cfg = await _seed_config(db, suffix="order")

    now = datetime.now(timezone.utc)
    await _seed_app(
        db,
        student=user,
        config=cfg,
        status=ApplicationStatus.draft.value,
        created_at=now - timedelta(days=10),
        suffix="oldest",
    )
    await _seed_app(
        db,
        student=user,
        config=cfg,
        status=ApplicationStatus.draft.value,
        created_at=now - timedelta(days=1),
        suffix="newest",
    )
    await _seed_app(
        db,
        student=user,
        config=cfg,
        status=ApplicationStatus.draft.value,
        created_at=now - timedelta(days=5),
        suffix="middle",
    )

    service = ApplicationService(db)
    result = await service.get_user_applications(user)
    assert len(result) == 3
    # Newest first; check via the first app_id which embeds the suffix.
    first_app_id = result[0].app_id if hasattr(result[0], "app_id") else result[0].get("app_id")
    assert "newest" in (first_app_id or "")

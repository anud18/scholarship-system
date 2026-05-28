"""
Core-path real-DB tests for ApplicationService.

Pattern mirrors `test_submit_application_deep.py` (sibling file): an async
SQLite `db` fixture from conftest, a `silence_collaborators` monkeypatch to
no-op the MinIO clone + Redis cache invalidation side effects, and small
local seed helpers that build the smallest valid graph of User /
ScholarshipType / ScholarshipConfiguration / Application rows.

Scope is the highest-risk methods that have *no* real-DB coverage today:
- `withdraw_application` (zero existing tests anywhere)
- `get_application_by_id` access-control branches
- `delete_application` hard/soft delete + staff vs student rules
- `update_application` editable / non-editable branches

Methods already deep-tested elsewhere (submit_application, professor
auto-assign, app_id sequence format) are intentionally skipped here to
avoid duplicating `test_submit_application_deep.py`,
`test_application_sequence_format.py`, etc.
"""

from datetime import datetime, timezone
from typing import Any, Optional

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.enums import ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.schemas.application import ApplicationFormData, ApplicationUpdate, DynamicFormField
from app.services.application_service import ApplicationService


# ---------------------------------------------------------------------------
# Seed helpers (copied from test_submit_application_deep.py to keep this
# file self-contained; both files exercise different methods of the same
# service so divergence is acceptable).
# ---------------------------------------------------------------------------
async def _seed_user(
    db: AsyncSession,
    *,
    role: UserRole,
    name: str,
    nycu_id: str,
    dept_code: Optional[str] = None,
) -> User:
    u = User(
        nycu_id=nycu_id,
        name=name,
        email=f"{nycu_id}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
        dept_code=dept_code,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


async def _seed_config(db: AsyncSession, *, suffix: str) -> ScholarshipConfiguration:
    st = ScholarshipType(code=f"core_{suffix}", name=f"Core type {suffix}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"core_cfg_{suffix}",
        config_name=f"Core cfg {suffix}",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=False,
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
    professor_id: Optional[int] = None,
    suffix: str,
    review_stage: str = ReviewStage.student_draft.value,
    submitted_form_data: Optional[dict] = None,
) -> Application:
    app = Application(
        app_id=f"APP-CORE-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=status,
        review_stage=review_stage,
        professor_id=professor_id,
        submitted_form_data=submitted_form_data if submitted_form_data is not None else {"fields": {}, "documents": []},
        student_data={"std_cname": student.name},
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.fixture
def silence_collaborators(monkeypatch):
    """No-op the MinIO clone helper and the Redis cache invalidator.

    `withdraw_application` and `delete_application` both call
    `_invalidate_app_caches` (Redis), and `delete_application` /
    `update_application` also reach the MinIO-bound clone helper. These
    would otherwise fail when run outside the dev docker network.
    """

    async def _noop_clone(self: Any, application: Any, user: Any) -> None:
        return None

    async def _noop_cache() -> None:
        return None

    monkeypatch.setattr(ApplicationService, "_clone_user_profile_documents", _noop_clone)
    monkeypatch.setattr(ApplicationService, "_invalidate_app_caches", staticmethod(_noop_cache))


def _minio_noop(monkeypatch):
    """No-op MinIO delete used by delete_application's hard-delete branch."""

    def _delete_file(object_name: str) -> bool:
        return True

    monkeypatch.setattr("app.services.application_service.minio_service.delete_file", _delete_file)


# ---------------------------------------------------------------------------
# withdraw_application — zero coverage in the existing suite. These pin the
# documented behaviour from CLAUDE.md / models/enums.py: withdraw returns
# the application to DRAFT, clears the professor assignment, and resets
# review_stage. There is no separate "withdrawn" terminal state on this
# path despite ApplicationStatus.withdrawn existing in the enum.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_withdraw_from_submitted_returns_to_draft(db: AsyncSession, silence_collaborators):
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_wd_sub")
    cfg = await _seed_config(db, suffix="wd_sub")
    # Pre-populate professor_id so we can prove withdraw clears it.
    prof = await _seed_user(db, role=UserRole.professor, name="P", nycu_id="prof_wd_sub")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.submitted.value,
        professor_id=prof.id,
        suffix="wd_sub",
        review_stage=ReviewStage.student_submitted.value,
    )
    service = ApplicationService(db)

    result = await service.withdraw_application(app.id, student)

    await db.refresh(app)
    # Service returns the Application model.
    assert result is app or result.id == app.id
    assert app.status == ApplicationStatus.draft
    # `review_stage` can come back as either the Enum member or its raw string
    # depending on SQLite vs PG return path; compare via .value for portability.
    rs_value = app.review_stage.value if hasattr(app.review_stage, "value") else app.review_stage
    assert rs_value == ReviewStage.student_draft.value
    assert app.professor_id is None, "withdraw must release the assigned professor so reviewers' queue is correct"


@pytest.mark.asyncio
async def test_withdraw_from_under_review_returns_to_draft(db: AsyncSession, silence_collaborators):
    """The second allowed starting state for withdraw."""
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_wd_ur")
    cfg = await _seed_config(db, suffix="wd_ur")
    app = await _seed_app(
        db,
        student=student,
        config=cfg,
        status=ApplicationStatus.under_review.value,
        suffix="wd_ur",
        review_stage=ReviewStage.professor_review.value,
    )
    service = ApplicationService(db)

    await service.withdraw_application(app.id, student)

    await db.refresh(app)
    assert app.status == ApplicationStatus.draft


@pytest.mark.asyncio
async def test_withdraw_draft_raises_validation_error(db: AsyncSession, silence_collaborators):
    """Withdrawing a draft (or a previously-withdrawn-now-draft) app is rejected."""
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_wd_dr")
    cfg = await _seed_config(db, suffix="wd_dr")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.draft.value, suffix="wd_dr")
    service = ApplicationService(db)

    with pytest.raises(ValidationError, match="Only submitted or under-review"):
        await service.withdraw_application(app.id, student)


@pytest.mark.asyncio
async def test_withdraw_other_students_application_raises_authorization(db: AsyncSession, silence_collaborators):
    """A student must not be able to withdraw a peer's submission."""
    owner = await _seed_user(db, role=UserRole.student, name="Owner", nycu_id="s_wd_own")
    other = await _seed_user(db, role=UserRole.student, name="Other", nycu_id="s_wd_oth")
    cfg = await _seed_config(db, suffix="wd_auth")
    app = await _seed_app(db, student=owner, config=cfg, status=ApplicationStatus.submitted.value, suffix="wd_auth")
    service = ApplicationService(db)

    with pytest.raises(AuthorizationError):
        await service.withdraw_application(app.id, other)


@pytest.mark.asyncio
async def test_withdraw_nonexistent_raises_not_found(db: AsyncSession, silence_collaborators):
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_wd_404")
    service = ApplicationService(db)

    with pytest.raises(NotFoundError):
        await service.withdraw_application(999_999, student)


# ---------------------------------------------------------------------------
# get_application_by_id — access control branches. The service's contract
# is that mismatched-owner reads return `None` (not raise); that's the
# branch most likely to drift if someone "fixes" the seemingly-missing
# error path.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_get_returns_owned_application_for_student(db: AsyncSession, silence_collaborators):
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_get_own")
    cfg = await _seed_config(db, suffix="get_own")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.draft.value, suffix="get_own")
    service = ApplicationService(db)

    result = await service.get_application_by_id(app.id, student)

    assert result is not None
    assert result.id == app.id
    assert result.user_id == student.id


@pytest.mark.asyncio
async def test_get_other_students_application_returns_none(db: AsyncSession, silence_collaborators):
    """Cross-student reads are silently denied (returns None, not raise)."""
    owner = await _seed_user(db, role=UserRole.student, name="Owner", nycu_id="s_get_own2")
    intruder = await _seed_user(db, role=UserRole.student, name="Other", nycu_id="s_get_int")
    cfg = await _seed_config(db, suffix="get_cross")
    app = await _seed_app(db, student=owner, config=cfg, status=ApplicationStatus.draft.value, suffix="get_cross")
    service = ApplicationService(db)

    result = await service.get_application_by_id(app.id, intruder)

    assert result is None, "cross-student read must return None to avoid leaking existence"


@pytest.mark.asyncio
async def test_get_nonexistent_application_returns_none(db: AsyncSession, silence_collaborators):
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_get_404")
    service = ApplicationService(db)

    result = await service.get_application_by_id(999_999, student)

    assert result is None


# ---------------------------------------------------------------------------
# delete_application — hard delete (draft) vs soft delete (submitted), and
# the staff-vs-student permission split.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_student_hard_deletes_own_draft(db: AsyncSession, silence_collaborators, monkeypatch):
    _minio_noop(monkeypatch)
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_del_draft")
    cfg = await _seed_config(db, suffix="del_draft")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.draft.value, suffix="del_draft")
    app_pk = app.id
    service = ApplicationService(db)

    await service.delete_application(app_pk, student)

    # Hard-delete: row removed from DB.
    result = await db.execute(select(Application).where(Application.id == app_pk))
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_student_cannot_delete_submitted(db: AsyncSession, silence_collaborators, monkeypatch):
    _minio_noop(monkeypatch)
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_del_sub")
    cfg = await _seed_config(db, suffix="del_sub")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="del_sub")
    service = ApplicationService(db)

    with pytest.raises(ValidationError, match="draft applications can be deleted"):
        await service.delete_application(app.id, student)


@pytest.mark.asyncio
async def test_student_cannot_delete_other_students_draft(db: AsyncSession, silence_collaborators, monkeypatch):
    _minio_noop(monkeypatch)
    owner = await _seed_user(db, role=UserRole.student, name="Owner", nycu_id="s_del_own")
    other = await _seed_user(db, role=UserRole.student, name="Other", nycu_id="s_del_oth")
    cfg = await _seed_config(db, suffix="del_cross")
    app = await _seed_app(db, student=owner, config=cfg, status=ApplicationStatus.draft.value, suffix="del_cross")
    service = ApplicationService(db)

    with pytest.raises(AuthorizationError):
        await service.delete_application(app.id, other)


@pytest.mark.asyncio
async def test_staff_soft_deletes_submitted_with_reason(db: AsyncSession, silence_collaborators, monkeypatch):
    _minio_noop(monkeypatch)
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_del_softS")
    admin = await _seed_user(db, role=UserRole.admin, name="A", nycu_id="adm_del_soft")
    cfg = await _seed_config(db, suffix="del_soft")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="del_soft")
    service = ApplicationService(db)

    await service.delete_application(app.id, admin, reason="duplicate submission")

    await db.refresh(app)
    # Soft delete: row preserved with status=deleted plus tracking metadata.
    assert app.status == ApplicationStatus.deleted
    assert app.deleted_at is not None
    assert app.deleted_by_id == admin.id
    assert app.deletion_reason == "duplicate submission"


@pytest.mark.asyncio
async def test_staff_delete_without_reason_raises(db: AsyncSession, silence_collaborators, monkeypatch):
    _minio_noop(monkeypatch)
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_del_norS")
    admin = await _seed_user(db, role=UserRole.admin, name="A", nycu_id="adm_del_nor")
    cfg = await _seed_config(db, suffix="del_nor")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="del_nor")
    service = ApplicationService(db)

    with pytest.raises(ValidationError, match="reason"):
        await service.delete_application(app.id, admin, reason=None)


@pytest.mark.asyncio
async def test_delete_already_deleted_raises(db: AsyncSession, silence_collaborators, monkeypatch):
    """Double-delete must be rejected; the prior soft-deleted row is preserved."""
    _minio_noop(monkeypatch)
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_del_dupS")
    admin = await _seed_user(db, role=UserRole.admin, name="A", nycu_id="adm_del_dup")
    cfg = await _seed_config(db, suffix="del_dup")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.submitted.value, suffix="del_dup")
    service = ApplicationService(db)

    await service.delete_application(app.id, admin, reason="first")
    with pytest.raises(ValidationError, match="already deleted"):
        await service.delete_application(app.id, admin, reason="second")


# ---------------------------------------------------------------------------
# update_application — editable-state gate. This is the user-facing
# "save my draft" path; a regression that allowed updating a submitted app
# would silently bypass the review state machine.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_update_draft_persists_new_form_data(db: AsyncSession, silence_collaborators):
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_up_dr")
    cfg = await _seed_config(db, suffix="up_dr")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.draft.value, suffix="up_dr")
    service = ApplicationService(db)

    new_form = ApplicationFormData(
        fields={
            "bank_account": DynamicFormField(
                field_id="bank_account",
                field_type="text",
                value="0123456789",
                required=False,
            )
        },
        documents=[],
    )
    update = ApplicationUpdate(form_data=new_form)

    result = await service.update_application(app.id, update, student)

    assert result.id == app.id
    # Re-read independently to confirm persistence rather than relying on the
    # session-cached object the service returned.
    await db.refresh(app)
    fields = (app.submitted_form_data or {}).get("fields") or {}
    assert "bank_account" in fields
    bank = fields["bank_account"]
    # Pydantic v2 .dict() output keeps the field-object shape.
    assert bank.get("value") == "0123456789"


@pytest.mark.asyncio
async def test_update_non_editable_status_raises(db: AsyncSession, silence_collaborators):
    """Approved (or any non-editable) applications must not accept edits."""
    student = await _seed_user(db, role=UserRole.student, name="S", nycu_id="s_up_ap")
    cfg = await _seed_config(db, suffix="up_ap")
    app = await _seed_app(db, student=student, config=cfg, status=ApplicationStatus.approved.value, suffix="up_ap")
    service = ApplicationService(db)

    update = ApplicationUpdate(
        form_data=ApplicationFormData(fields={}, documents=[]),
    )

    with pytest.raises(ValidationError, match="cannot be edited"):
        await service.update_application(app.id, update, student)

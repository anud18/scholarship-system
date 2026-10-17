"""
SIS term-data resync of an application snapshot (app.services.student_snapshot_resync),
the admin POST /admin/applications/{id}/resync-sis-term-data endpoint and the
backfill script.

Prod case: the draft's term-2 SIS lookup timed out, the snapshot was stored with
_term_data_status='error' and no trm_* fields, so 系所 / 年級 exported blank.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.admin import applications as admin_apps
from app.core.college_mappings import ORIGINAL_ACADEMY_CODES_KEY
from app.core.exceptions import NotFoundError, ServiceUnavailableError, ValidationError
from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.scripts import backfill_sis_term_snapshots as backfill
from app.services import student_snapshot_resync as resync

STUDENT_CODE = "411651009"

BROKEN_SNAPSHOT = {
    "std_stdcode": STUDENT_CODE,
    "std_cname": "王小明",
    "std_depno": "4651",
    "_api_fetched_at": "2026-10-06T08:26:36+00:00",
    "_term_data_status": "error",
    "_term_error_message": "Student API request timed out",
    "financial_info": {"bank_code": "700"},
}

FRESH_SNAPSHOT = {
    "std_stdcode": STUDENT_CODE,
    "std_cname": "王小明(新)",
    "std_depno": "9999",
    "trm_depname": "電機工程學系",
    "trm_termcount": 8,
    "_term_data_status": "success",
    "_term_error_message": None,
}


def _student_service(snapshot=None, error=None) -> MagicMock:
    svc = MagicMock()
    svc.get_student_snapshot = AsyncMock(return_value=snapshot, side_effect=error)
    return svc


def _application(student_data, semester=None) -> Application:
    return Application(app_id="APP-115-0-00182", academic_year=115, semester=semester, student_data=student_data)


# ---------------------------------------------------------------- pure helpers


@pytest.mark.parametrize(
    "student_data, expected",
    [
        (None, True),
        ({}, True),
        ({"_term_data_status": "error"}, True),
        ({"_term_data_status": "partial"}, True),
        ({"_term_data_status": "not_requested"}, True),
        ({"_term_data_status": "success"}, False),
    ],
)
def test_needs_term_resync(student_data, expected):
    assert resync.needs_term_resync(student_data) is expected


def test_merge_takes_only_term_fields_and_keeps_basic_and_non_sis_data():
    current = dict(BROKEN_SNAPSHOT)

    merged = resync.merge_term_snapshot(current, FRESH_SNAPSHOT, "2026-10-17T00:00:00+00:00")

    assert merged["trm_depname"] == "電機工程學系"
    assert merged["trm_termcount"] == 8
    assert merged["_term_data_status"] == "success"
    assert merged["_term_error_message"] is None
    assert merged["_term_resynced_at"] == "2026-10-17T00:00:00+00:00"
    # 申請當時 basic data and non-SIS keys are untouched
    assert merged["std_cname"] == "王小明"
    assert merged["std_depno"] == "4651"
    assert merged["_api_fetched_at"] == "2026-10-06T08:26:36+00:00"
    assert merged["financial_info"] == {"bank_code": "700"}
    # inputs are not mutated
    assert current == BROKEN_SNAPSHOT
    assert "trm_depname" not in current


def test_merge_keeps_basic_original_codes_and_takes_term_ones_fresh():
    current = {**BROKEN_SNAPSHOT, ORIGINAL_ACADEMY_CODES_KEY: {"std_academyno": "Y", "trm_academyno": "Y"}}
    fresh = {**FRESH_SNAPSHOT, ORIGINAL_ACADEMY_CODES_KEY: {"std_academyno": "Z", "trm_academyno": "W"}}

    merged = resync.merge_term_snapshot(current, fresh, "t")

    assert merged[ORIGINAL_ACADEMY_CODES_KEY] == {"std_academyno": "Y", "trm_academyno": "W"}


def test_merge_drops_stale_term_original_codes_when_fresh_has_none():
    current = {**BROKEN_SNAPSHOT, ORIGINAL_ACADEMY_CODES_KEY: {"trm_academyno": "Y"}}

    merged = resync.merge_term_snapshot(current, FRESH_SNAPSHOT, "t")

    assert ORIGINAL_ACADEMY_CODES_KEY not in merged


def test_merge_drops_stale_term_fields_of_a_partial_snapshot():
    current = {**BROKEN_SNAPSHOT, "_term_data_status": "partial", "trm_term": "1", "trm_ascore_gpa": 3.9}
    fresh = {**FRESH_SNAPSHOT, "trm_term": "2"}

    merged = resync.merge_term_snapshot(current, fresh, "t")

    assert merged["trm_term"] == "2"
    assert "trm_ascore_gpa" not in merged


def test_application_student_code_requires_snapshot_code():
    with pytest.raises(ValidationError):
        resync.application_student_code(_application({"_term_data_status": "error"}))


# ---------------------------------------------------------------- DB-backed helpers


async def _seed_user(db: AsyncSession, *, role: UserRole, nycu_id: str) -> User:
    user = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seed_app(db: AsyncSession, *, student: User, status: str, student_data: dict, seq: int = 1) -> Application:
    st = ScholarshipType(code=f"resync_{status}_{seq}", name=f"Resync {status} {seq}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"resync_cfg_{status}_{seq}",
        config_name=f"Resync cfg {status} {seq}",
        academic_year=115,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        amount=0,
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    app = Application(
        app_id=f"APP-115-0-{seq:05d}",
        user_id=student.id,
        scholarship_type_id=st.id,
        scholarship_configuration_id=cfg.id,
        academic_year=115,
        semester=Semester.yearly,
        sub_type_selection_mode="single",
        student_data=student_data,
        status=status,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def _stored(db: AsyncSession, app_pk: int) -> dict:
    db.expire_all()
    return (await db.execute(select(Application).where(Application.id == app_pk))).scalar_one().student_data


async def _broken_app(db: AsyncSession, seq: int = 1) -> int:
    student = await _seed_user(db, role=UserRole.student, nycu_id=f"{STUDENT_CODE}{seq}")
    app = await _seed_app(db, student=student, status="submitted", student_data=dict(BROKEN_SNAPSHOT), seq=seq)
    return app.id


# ---------------------------------------------------------------- resync_application_term_data


@pytest.mark.asyncio
async def test_resync_fetches_the_applications_own_year_and_merges(db: AsyncSession):
    app_pk = await _broken_app(db)
    svc = _student_service(snapshot=dict(FRESH_SNAPSHOT))

    result = await resync.resync_application_term_data(db, app_pk, svc)
    await db.commit()

    svc.get_student_snapshot.assert_awaited_once_with(STUDENT_CODE, academic_year="115", semester="yearly", fresh=True)
    assert result.updated is True
    assert (result.previous_status, result.new_status) == ("error", "success")
    stored = await _stored(db, app_pk)
    assert stored["trm_depname"] == "電機工程學系"
    assert stored["std_cname"] == "王小明"


@pytest.mark.asyncio
async def test_resync_without_term_data_leaves_snapshot_untouched_and_says_why(db: AsyncSession):
    app_pk = await _broken_app(db)
    svc = _student_service(
        snapshot={
            "std_stdcode": STUDENT_CODE,
            "_term_data_status": "error",
            "_term_error_message": "Student API request timed out",
        }
    )

    result = await resync.resync_application_term_data(db, app_pk, svc)
    await db.commit()

    assert result.updated is False
    assert result.error_message == "Student API request timed out"
    assert await _stored(db, app_pk) == BROKEN_SNAPSHOT


@pytest.mark.asyncio
async def test_resync_propagates_basic_sis_failure(db: AsyncSession):
    app_pk = await _broken_app(db)
    svc = _student_service(error=ServiceUnavailableError("Student API request timed out"))

    with pytest.raises(ServiceUnavailableError):
        await resync.resync_application_term_data(db, app_pk, svc)
    await db.rollback()
    assert await _stored(db, app_pk) == BROKEN_SNAPSHOT


@pytest.mark.asyncio
async def test_resync_never_overwrites_a_snapshot_completed_during_the_sis_call(db: AsyncSession):
    """A slower resync whose term-2 lookup fell back to term 1 must not replace a finished repair."""
    app_pk = await _broken_app(db)
    completed = {**BROKEN_SNAPSHOT, **FRESH_SNAPSHOT, "std_cname": "王小明"}
    partial = {**FRESH_SNAPSHOT, "trm_depname": "第一學期系所", "_term_data_status": "partial"}

    async def slow_sis(*args, **kwargs):
        await db.execute(update(Application).where(Application.id == app_pk).values(student_data=completed))
        return partial

    svc = MagicMock()
    svc.get_student_snapshot = AsyncMock(side_effect=slow_sis)

    result = await resync.resync_application_term_data(db, app_pk, svc)
    await db.commit()

    assert result.updated is False
    assert result.new_status == "success"
    assert result.error_message == resync.ALREADY_COMPLETE_MESSAGE
    assert await _stored(db, app_pk) == completed


@pytest.mark.asyncio
async def test_resync_merges_into_the_latest_snapshot_not_the_pre_sis_copy(db: AsyncSession):
    app_pk = await _broken_app(db)
    changed_meanwhile = {**BROKEN_SNAPSHOT, "financial_info": {"bank_code": "812"}}

    async def slow_sis(*args, **kwargs):
        await db.execute(update(Application).where(Application.id == app_pk).values(student_data=changed_meanwhile))
        return dict(FRESH_SNAPSHOT)

    svc = MagicMock()
    svc.get_student_snapshot = AsyncMock(side_effect=slow_sis)

    result = await resync.resync_application_term_data(db, app_pk, svc)
    await db.commit()

    assert result.updated is True
    stored = await _stored(db, app_pk)
    assert stored["financial_info"] == {"bank_code": "812"}
    assert stored["trm_depname"] == "電機工程學系"


@pytest.mark.asyncio
async def test_resync_of_an_application_deleted_during_the_sis_call_is_not_found(db: AsyncSession):
    app_pk = await _broken_app(db)

    async def slow_sis(*args, **kwargs):
        await db.execute(delete(Application).where(Application.id == app_pk))
        return dict(FRESH_SNAPSHOT)

    svc = MagicMock()
    svc.get_student_snapshot = AsyncMock(side_effect=slow_sis)

    with pytest.raises(NotFoundError):
        await resync.resync_application_term_data(db, app_pk, svc)


@pytest.mark.asyncio
async def test_resync_unknown_application(db: AsyncSession):
    with pytest.raises(NotFoundError):
        await resync.resync_application_term_data(db, 999999, _student_service(snapshot=dict(FRESH_SNAPSHOT)))


# ---------------------------------------------------------------- DB-backed: admin endpoint


@pytest.fixture
def fake_sis(monkeypatch):
    """Route every StudentService() built by the resync module to a fake SIS."""
    svc = _student_service(snapshot=dict(FRESH_SNAPSHOT))
    monkeypatch.setattr(resync, "StudentService", lambda: svc)
    return svc


@pytest.mark.asyncio
async def test_admin_endpoint_resyncs_and_audits(db: AsyncSession, fake_sis):
    app_pk = await _broken_app(db)
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="admin01")

    response = await admin_apps.resync_sis_term_data(id=app_pk, request=None, current_user=admin, db=db)

    assert response["success"] is True
    assert response["data"]["updated"] is True
    assert response["data"]["new_status"] == "success"
    stored = await _stored(db, app_pk)
    assert stored["trm_depname"] == "電機工程學系"
    assert stored["std_cname"] == "王小明"
    log = (await db.execute(select(AuditLog).where(AuditLog.resource_id == str(app_pk)))).scalar_one()
    assert log.meta_data["update_type"] == "sis_term_resync"
    assert log.status == "success"


@pytest.mark.asyncio
async def test_admin_endpoint_rejects_complete_snapshot(db: AsyncSession, fake_sis):
    student = await _seed_user(db, role=UserRole.student, nycu_id=STUDENT_CODE)
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="admin01")
    app = await _seed_app(db, student=student, status="submitted", student_data=dict(FRESH_SNAPSHOT))

    with pytest.raises(ValidationError):
        await admin_apps.resync_sis_term_data(id=app.id, request=None, current_user=admin, db=db)
    fake_sis.get_student_snapshot.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_endpoint_reports_the_reason_without_writing(db: AsyncSession, fake_sis):
    fake_sis.get_student_snapshot.return_value = {
        "_term_data_status": "error",
        "_term_error_message": "Student API request timed out",
    }
    app_pk = await _broken_app(db)
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="admin01")

    response = await admin_apps.resync_sis_term_data(id=app_pk, request=None, current_user=admin, db=db)

    assert response["data"]["updated"] is False
    assert response["message"] == "未變更：Student API request timed out"
    assert await _stored(db, app_pk) == BROKEN_SNAPSHOT
    log = (await db.execute(select(AuditLog).where(AuditLog.resource_id == str(app_pk)))).scalar_one()
    assert log.status == "failed"
    assert log.error_message == "Student API request timed out"


# ---------------------------------------------------------------- backfill script


@pytest.mark.asyncio
async def test_backfill_continues_after_a_sis_failure(db: AsyncSession):
    """A failed SIS lookup is recorded and the next candidate is still processed (no MissingGreenlet)."""
    first_pk = await _broken_app(db, seq=1)
    second_pk = await _broken_app(db, seq=2)
    svc = MagicMock()
    svc.get_student_snapshot = AsyncMock(
        side_effect=[ServiceUnavailableError("Student API request timed out"), dict(FRESH_SNAPSHOT)]
    )
    stats = backfill.Stats()

    candidates = await backfill._load_candidates(db, 115, [])
    for candidate in candidates:
        await backfill._process(db, candidate, svc, True, stats)

    assert [c.id for c in candidates] == [first_pk, second_pk]
    assert stats.failed == ["APP-115-0-00001"]
    assert stats.resynced == ["APP-115-0-00002"]
    assert (await _stored(db, second_pk))["trm_depname"] == "電機工程學系"
    assert await _stored(db, first_pk) == BROKEN_SNAPSHOT


@pytest.mark.asyncio
async def test_backfill_dry_run_writes_nothing(db: AsyncSession):
    app_pk = await _broken_app(db)
    stats = backfill.Stats()

    for candidate in await backfill._load_candidates(db, 115, []):
        await backfill._process(db, candidate, _student_service(snapshot=dict(FRESH_SNAPSHOT)), False, stats)

    assert stats.resynced == ["APP-115-0-00001"]
    assert await _stored(db, app_pk) == BROKEN_SNAPSHOT

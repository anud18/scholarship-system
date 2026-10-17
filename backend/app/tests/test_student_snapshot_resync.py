"""
SIS term-data resync of an application snapshot (app.services.student_snapshot_resync),
the admin POST /admin/applications/{id}/resync-sis-term-data endpoint, and the
refresh_from_api path of ApplicationService.update_student_data.

Prod case: the draft's term-2 SIS lookup timed out, the snapshot was stored with
_term_data_status='error' and no trm_* fields, so 系所 / 年級 exported blank.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.admin import applications as admin_apps
from app.core.college_mappings import ORIGINAL_ACADEMY_CODES_KEY
from app.core.exceptions import ServiceUnavailableError, ValidationError
from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.schemas.application import StudentDataSchema
from app.services import student_snapshot_resync as resync
from app.services.application_service import ApplicationService

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


# ---------------------------------------------------------------- resync_application_term_data


@pytest.mark.asyncio
async def test_resync_fetches_the_applications_own_year_and_merges():
    svc = _student_service(snapshot=dict(FRESH_SNAPSHOT))
    app = _application(dict(BROKEN_SNAPSHOT), semester=Semester.yearly)

    result = await resync.resync_application_term_data(app, svc)

    svc.get_student_snapshot.assert_awaited_once_with(STUDENT_CODE, academic_year="115", semester="yearly", fresh=True)
    assert result.updated is True
    assert (result.previous_status, result.new_status) == ("error", "success")
    assert app.student_data["trm_depname"] == "電機工程學系"
    assert app.student_data["std_cname"] == "王小明"


@pytest.mark.asyncio
async def test_resync_with_still_no_term_data_leaves_snapshot_untouched():
    svc = _student_service(
        snapshot={"std_stdcode": STUDENT_CODE, "_term_data_status": "error", "_term_error_message": "No data"}
    )
    original = dict(BROKEN_SNAPSHOT)
    app = _application(original)

    result = await resync.resync_application_term_data(app, svc)

    assert result.updated is False
    assert result.error_message == "No data"
    assert app.student_data is original
    assert app.student_data == BROKEN_SNAPSHOT


@pytest.mark.asyncio
async def test_resync_propagates_sis_failure():
    svc = _student_service(error=ServiceUnavailableError("Student API request timed out"))
    app = _application(dict(BROKEN_SNAPSHOT))

    with pytest.raises(ServiceUnavailableError):
        await resync.resync_application_term_data(app, svc)
    assert app.student_data == BROKEN_SNAPSHOT


# ---------------------------------------------------------------- DB-backed: endpoint + update_student_data


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


async def _seed_app(db: AsyncSession, *, student: User, status: str, student_data: dict) -> Application:
    st = ScholarshipType(code=f"resync_{status}", name=f"Resync {status}", status="active")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=st.id,
        config_code=f"resync_cfg_{status}",
        config_name=f"Resync cfg {status}",
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
        app_id=f"APP-115-0-{status[:5]}",
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


@pytest.fixture
def fake_sis(monkeypatch):
    """Route every StudentService() built by the resync module to a fake SIS."""
    svc = _student_service(snapshot=dict(FRESH_SNAPSHOT))
    monkeypatch.setattr(resync, "StudentService", lambda: svc)
    return svc


@pytest.mark.asyncio
async def test_admin_endpoint_resyncs_and_audits(db: AsyncSession, fake_sis):
    student = await _seed_user(db, role=UserRole.student, nycu_id=STUDENT_CODE)
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="admin01")
    app = await _seed_app(db, student=student, status="submitted", student_data=dict(BROKEN_SNAPSHOT))
    app_pk = app.id

    response = await admin_apps.resync_sis_term_data(id=app_pk, request=None, current_user=admin, db=db)

    assert response["success"] is True
    assert response["data"]["updated"] is True
    assert response["data"]["new_status"] == "success"
    db.expire_all()
    stored = (await db.execute(select(Application).where(Application.id == app_pk))).scalar_one()
    assert stored.student_data["trm_depname"] == "電機工程學系"
    assert stored.student_data["std_cname"] == "王小明"
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
async def test_admin_endpoint_reports_still_missing_without_writing(db: AsyncSession, fake_sis):
    fake_sis.get_student_snapshot.return_value = {"_term_data_status": "error", "_term_error_message": "No data"}
    student = await _seed_user(db, role=UserRole.student, nycu_id=STUDENT_CODE)
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="admin01")
    app = await _seed_app(db, student=student, status="submitted", student_data=dict(BROKEN_SNAPSHOT))
    app_pk = app.id

    response = await admin_apps.resync_sis_term_data(id=app_pk, request=None, current_user=admin, db=db)

    assert response["data"]["updated"] is False
    db.expire_all()
    stored = (await db.execute(select(Application).where(Application.id == app_pk))).scalar_one()
    assert stored.student_data == BROKEN_SNAPSHOT


@pytest.mark.asyncio
async def test_update_student_data_refresh_uses_the_applications_student_not_the_caller(db: AsyncSession, monkeypatch):
    student = await _seed_user(db, role=UserRole.student, nycu_id=STUDENT_CODE)
    admin = await _seed_user(db, role=UserRole.admin, nycu_id="admin01")
    stale = {**BROKEN_SNAPSHOT, "_term_data_status": "partial", "trm_ascore_gpa": 3.9}
    app = await _seed_app(db, student=student, status="draft", student_data=stale)
    service = ApplicationService(db)
    service.student_service = _student_service(snapshot=dict(FRESH_SNAPSHOT))

    updated = await service.update_student_data(
        application_id=app.id,
        student_data_update=StudentDataSchema(),
        current_user=admin,
        refresh_from_api=True,
    )

    service.student_service.get_student_snapshot.assert_awaited_once_with(
        STUDENT_CODE, academic_year="115", semester="yearly", fresh=True
    )
    assert updated.student_data["trm_depname"] == "電機工程學系"
    assert "trm_ascore_gpa" not in updated.student_data  # stale term field of the old snapshot
    assert updated.student_data["financial_info"] == {"bank_code": "700"}

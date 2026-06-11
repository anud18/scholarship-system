"""G20 (#982): MinIO deletion failures must be detected and leave a trace.

minio_service.delete_file() never raises — it swallows errors internally and
returns False. The old delete path ignored that bool (and wrapped the call in
a dead try/except), so a storage failure orphaned the object with zero trace.
Now a False return must (a) not block the DB deletion — storage cleanup never
holds the user-facing operation hostage — and (b) leave a queryable 'failed'
AuditLog row listing the orphaned object names for a later sweep.
"""

from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.application import Application, ApplicationFile
from app.models.audit_log import AuditLog
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def draft_with_file(db):
    admin = User(
        nycu_id="g20admin",
        name="G20 Admin",
        email="g20admin@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    student = User(
        nycu_id="g20stu001",
        name="G20 學生",
        email="g20stu@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add_all([admin, student])
    await db.flush()

    stype = ScholarshipType(code="g20_test", name="G20 Test Scholarship")
    db.add(stype)
    await db.flush()
    cfg = ScholarshipConfiguration(
        config_code="G20-CFG",
        config_name="G20 Config",
        is_active=True,
        scholarship_type_id=stype.id,
        academic_year=114,
        amount=1000,
    )
    db.add(cfg)
    await db.flush()

    app_row = Application(
        app_id="APP-G20-DRAFT",
        user_id=student.id,
        scholarship_type_id=stype.id,
        scholarship_configuration_id=cfg.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status="draft",
    )
    db.add(app_row)
    await db.flush()

    file_row = ApplicationFile(
        application_id=app_row.id,
        file_type="transcript",
        filename="g20.pdf",
        object_name="applications/g20/transcript.pdf",
    )
    db.add(file_row)
    await db.commit()
    await db.refresh(app_row)
    return {"admin": admin, "app": app_row}


async def test_minio_failure_leaves_failed_audit_row_and_db_delete_proceeds(db, draft_with_file):
    app_db_id = draft_with_file["app"].id

    with patch("app.services.application_service.minio_service") as mock_minio:
        mock_minio.delete_file.return_value = False  # storage failure, no exception
        svc = ApplicationService(db)
        await svc.delete_application(app_db_id, draft_with_file["admin"], reason="G20 test")

    mock_minio.delete_file.assert_called_once_with("applications/g20/transcript.pdf")

    # DB deletion proceeded despite the storage failure.
    gone = await db.execute(select(Application).where(Application.id == app_db_id))
    assert gone.scalar_one_or_none() is None

    # ...and the orphan left a queryable trace.
    res = await db.execute(
        select(AuditLog).where(
            AuditLog.resource_type == "application",
            AuditLog.resource_id == str(app_db_id),
            AuditLog.status == "failed",
        )
    )
    failed_rows = res.scalars().all()
    assert len(failed_rows) == 1
    assert failed_rows[0].meta_data["orphaned_objects"] == ["applications/g20/transcript.pdf"]
    assert failed_rows[0].meta_data["app_id"] == "APP-G20-DRAFT"


async def test_minio_success_leaves_no_failed_row(db, draft_with_file):
    app_db_id = draft_with_file["app"].id

    with patch("app.services.application_service.minio_service") as mock_minio:
        mock_minio.delete_file.return_value = True
        svc = ApplicationService(db)
        await svc.delete_application(app_db_id, draft_with_file["admin"], reason="G20 test")

    res = await db.execute(
        select(AuditLog).where(
            AuditLog.resource_id == str(app_db_id),
            AuditLog.status == "failed",
        )
    )
    assert res.scalars().all() == []

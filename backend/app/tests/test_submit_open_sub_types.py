"""Every student submit refuses a sub-type the admin has not opened this round."""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipSubTypeConfig, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.models.user_profile import UserProfile
from app.schemas.application import ApplicationCreate, ApplicationFormData, ApplicationUpdate
from app.services.application_service import ApplicationService

CLOSED_NSTC_MESSAGE = "國科會 本次未開放申請，請取消勾選"


@pytest.fixture(autouse=True)
def silence_collaborators(monkeypatch):
    async def _noop_clone(self: Any, application: Any, user: Any) -> None:
        return None

    async def _noop_cache() -> None:
        return None

    monkeypatch.setattr(ApplicationService, "_clone_user_profile_documents", _noop_clone)
    monkeypatch.setattr(ApplicationService, "_invalidate_app_caches", staticmethod(_noop_cache))


async def _seed(db: AsyncSession, *, nycu_id: str):
    student = User(
        nycu_id=nycu_id, name="S", email=f"{nycu_id}@u.edu", user_type=UserType.student, role=UserRole.student
    )
    scholarship_type = ScholarshipType(
        code=f"phd_{nycu_id}", name="PhD", status="active", sub_type_list=["nstc", "moe_1w"]
    )
    db.add_all([student, scholarship_type])
    await db.commit()

    now = datetime.now(timezone.utc)
    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type.id,
        config_code=f"cfg_{nycu_id}",
        config_name="114 PhD",
        academic_year=114,
        amount=40000,
        is_active=True,
        application_start_date=now - timedelta(days=1),
        application_end_date=now + timedelta(days=30),
        open_sub_types=["moe_1w"],
    )
    db.add_all(
        [
            config,
            UserProfile(user_id=student.id, bank_document_photo_url="/api/v1/user-profiles/files/bank_documents/p.jpg"),
            ScholarshipSubTypeConfig(scholarship_type_id=scholarship_type.id, sub_type_code="nstc", name="國科會"),
            ScholarshipSubTypeConfig(scholarship_type_id=scholarship_type.id, sub_type_code="moe_1w", name="教育部"),
        ]
    )
    await db.commit()
    await db.refresh(config)
    return student, scholarship_type, config


async def _seed_app(db, *, student, config, status, sub_types, is_renewal=False, suffix):
    app = Application(
        app_id=f"APP-OPEN-{suffix}",
        user_id=student.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="multiple",
        scholarship_subtype_list=sub_types,
        sub_scholarship_type=sub_types[0],
        is_renewal=is_renewal,
        status=status,
        submitted_form_data={"fields": {}, "documents": []},
        student_data={"std_cname": "S"},
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def _status(db, app) -> ApplicationStatus:
    await db.refresh(app)
    return ApplicationStatus(app.status)


@pytest.mark.asyncio
async def test_draft_with_closed_sub_type_cannot_submit(db: AsyncSession):
    student, _, config = await _seed(db, nycu_id="open_draft_closed")
    app = await _seed_app(
        db, student=student, config=config, status=ApplicationStatus.draft, sub_types=["nstc", "moe_1w"], suffix="d1"
    )

    with pytest.raises(ValidationError, match=CLOSED_NSTC_MESSAGE):
        await ApplicationService(db).submit_application(app.id, student)
    assert await _status(db, app) == ApplicationStatus.draft


@pytest.mark.asyncio
async def test_draft_with_open_sub_type_submits(db: AsyncSession):
    student, _, config = await _seed(db, nycu_id="open_draft_ok")
    app = await _seed_app(
        db, student=student, config=config, status=ApplicationStatus.draft, sub_types=["MOE_1W"], suffix="d2"
    )

    await ApplicationService(db).submit_application(app.id, student)
    assert await _status(db, app) == ApplicationStatus.submitted


@pytest.mark.asyncio
async def test_returned_app_must_untick_closed_sub_type_before_resubmit(db: AsyncSession):
    student, _, config = await _seed(db, nycu_id="open_returned")
    app = await _seed_app(
        db, student=student, config=config, status=ApplicationStatus.returned, sub_types=["nstc", "moe_1w"], suffix="r1"
    )
    service = ApplicationService(db)

    with pytest.raises(ValidationError, match=CLOSED_NSTC_MESSAGE):
        await service.submit_application(app.id, student)
    assert await _status(db, app) == ApplicationStatus.returned

    await service.update_application(app.id, ApplicationUpdate(scholarship_subtype_list=["moe_1w"]), student)
    await service.submit_application(app.id, student)
    assert await _status(db, app) == ApplicationStatus.submitted


@pytest.mark.asyncio
async def test_renewal_keeps_its_closed_sub_type(db: AsyncSession):
    student, _, config = await _seed(db, nycu_id="open_renewal")
    app = await _seed_app(
        db,
        student=student,
        config=config,
        status=ApplicationStatus.draft,
        sub_types=["nstc"],
        is_renewal=True,
        suffix="rn",
    )

    await ApplicationService(db).submit_application(app.id, student)
    assert await _status(db, app) == ApplicationStatus.submitted


@pytest.mark.asyncio
async def test_create_and_submit_with_closed_sub_type_is_rejected(db: AsyncSession):
    student, scholarship_type, config = await _seed(db, nycu_id="open_create")

    with patch("app.services.application_service.StudentService") as student_service_cls:
        student_service = AsyncMock()
        student_service.get_student_snapshot.return_value = {"std_stdcode": student.nycu_id, "std_cname": "S"}
        student_service_cls.return_value = student_service
        service = ApplicationService(db)

        def payload(sub_types):
            return ApplicationCreate(
                scholarship_type=scholarship_type.code,
                configuration_id=config.id,
                scholarship_subtype_list=sub_types,
                form_data=ApplicationFormData(fields={}, documents=[]),
                agree_terms=True,
            )

        with pytest.raises(ValidationError, match=CLOSED_NSTC_MESSAGE):
            await service.create_application(student.id, student.nycu_id, payload(["nstc"]), is_draft=False)

        draft = await service.create_application(student.id, student.nycu_id, payload(["nstc"]), is_draft=True)
        assert draft.scholarship_subtype_list == ["nstc"]

        submitted = await service.create_application(student.id, student.nycu_id, payload(["moe_1w"]), is_draft=False)
        assert ApplicationStatus(submitted.status) == ApplicationStatus.submitted

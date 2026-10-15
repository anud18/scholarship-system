"""
The 存摺封面 is copied from the student's profile into the application, and the
student may replace the profile document after an earlier draft save already
copied it. The application must follow the profile's current document instead of
keeping the first copy.

Covered here (`ApplicationService._clone_user_profile_documents`):
- the first clone creates the file row and records which profile object it came from
- an unchanged profile document is not copied again, including across real draft
  saves (`update_application` rewrites `submitted_form_data` on every save)
- a replaced profile document re-points the SAME file row, updates the document
  entry and deletes the superseded copy
- the superseded copy is kept once the application has left draft
- a copy made before the source was recorded is refreshed once
"""

from datetime import datetime, timezone
from itertools import count

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationFile, ApplicationStatus
from app.schemas.application import ApplicationFormData, ApplicationUpdate
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.models.user_profile import UserProfile
from app.services import application_service as application_service_module
from app.services.application_service import ApplicationService

FILE_TYPE = "bank_account_proof"


class FakeMinio:
    """Records clones and deletions instead of touching object storage."""

    def __init__(self) -> None:
        self._ids = count(1)
        self.cloned: list[tuple[str, str]] = []
        self.deleted: list[str] = []

    def clone_file_to_application(self, source_object_name: str, application_id: str) -> str:
        new_object_name = f"applications/{application_id}/documents/copy{next(self._ids)}.pdf"
        self.cloned.append((source_object_name, new_object_name))
        return new_object_name

    def delete_file(self, object_name: str) -> bool:
        self.deleted.append(object_name)
        return True


@pytest.fixture
def fake_minio(monkeypatch) -> FakeMinio:
    fake = FakeMinio()
    monkeypatch.setattr(application_service_module, "minio_service", fake)
    return fake


async def _seed(db: AsyncSession) -> tuple[User, Application, UserProfile]:
    student = User(
        nycu_id="cpd_stu",
        name="Student",
        email="cpd_stu@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    scholarship_type = ScholarshipType(code="cpd_type", name="CPD type", status="active")
    db.add_all([student, scholarship_type])
    await db.commit()

    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type.id,
        config_code="cpd_cfg",
        config_name="CPD cfg",
        academic_year=114,
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2030, 1, 1, tzinfo=timezone.utc),
        requires_professor_recommendation=True,
        requires_college_review=False,
        amount=0,
        is_active=True,
    )
    db.add(config)
    await db.commit()

    application = Application(
        app_id="APP-CPD-1",
        user_id=student.id,
        scholarship_type_id=scholarship_type.id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        student_data={},
        status=ApplicationStatus.draft.value,
        scholarship_subtype_list=[],
        submitted_form_data={"fields": {}, "documents": []},
        is_renewal=False,
    )
    profile = UserProfile(user_id=student.id)
    db.add_all([application, profile])
    await db.commit()
    await db.refresh(application)
    await db.refresh(profile)
    return student, application, profile


async def _set_profile_document(db: AsyncSession, profile: UserProfile, user_id: int, name: str) -> str:
    object_name = f"user-profiles/{user_id}/bank-documents/{name}"
    profile.bank_document_photo_url = f"/api/v1/user-profiles/files/bank_documents/{name}"
    profile.bank_document_object_name = object_name
    await db.commit()
    return object_name


async def _files(db: AsyncSession, application: Application) -> list[ApplicationFile]:
    result = await db.execute(select(ApplicationFile).where(ApplicationFile.application_id == application.id))
    return list(result.scalars().all())


def _bank_documents(application: Application) -> list[dict]:
    return [d for d in application.submitted_form_data["documents"] if d["document_type"] == FILE_TYPE]


@pytest.mark.asyncio
async def test_first_clone_records_the_profile_source(db: AsyncSession, fake_minio: FakeMinio):
    student, application, profile = await _seed(db)
    source = await _set_profile_document(db, profile, student.id, "first.pdf")

    await ApplicationService(db)._clone_user_profile_documents(application, student)

    (file,) = await _files(db, application)
    assert fake_minio.cloned == [(source, file.object_name)]
    assert file.source_object_name == source
    (document,) = _bank_documents(application)
    assert document["file_id"] == file.id
    assert fake_minio.deleted == []


@pytest.mark.asyncio
async def test_unchanged_profile_document_is_not_cloned_again(db: AsyncSession, fake_minio: FakeMinio):
    student, application, profile = await _seed(db)
    await _set_profile_document(db, profile, student.id, "first.pdf")
    service = ApplicationService(db)

    await service._clone_user_profile_documents(application, student)
    await service._clone_user_profile_documents(application, student)

    assert len(fake_minio.cloned) == 1
    assert len(await _files(db, application)) == 1
    assert fake_minio.deleted == []


@pytest.mark.asyncio
async def test_draft_saves_do_not_clone_an_unchanged_document_again(db: AsyncSession, fake_minio: FakeMinio):
    student, application, profile = await _seed(db)
    await _set_profile_document(db, profile, student.id, "first.pdf")
    service = ApplicationService(db)
    update = ApplicationUpdate(form_data=ApplicationFormData(fields={}, documents=[]))

    await service.update_application(application.id, update, student)
    await service.update_application(application.id, update, student)

    assert len(fake_minio.cloned) == 1
    assert len(await _files(db, application)) == 1
    assert fake_minio.deleted == []


@pytest.mark.asyncio
async def test_replaced_profile_document_refreshes_the_application_copy(db: AsyncSession, fake_minio: FakeMinio):
    student, application, profile = await _seed(db)
    await _set_profile_document(db, profile, student.id, "first.pdf")
    service = ApplicationService(db)
    await service._clone_user_profile_documents(application, student)
    (first_file,) = await _files(db, application)
    first_copy = first_file.object_name

    new_source = await _set_profile_document(db, profile, student.id, "second.jpg")
    await service._clone_user_profile_documents(application, student)

    (file,) = await _files(db, application)
    assert file.id == first_file.id
    assert file.object_name != first_copy
    assert file.source_object_name == new_source
    assert fake_minio.cloned[-1] == (new_source, file.object_name)
    assert fake_minio.deleted == [first_copy]
    (document,) = _bank_documents(application)
    assert document["object_name"] == file.object_name
    assert document["file_id"] == file.id


@pytest.mark.asyncio
async def test_replaced_profile_document_through_draft_save(db: AsyncSession, fake_minio: FakeMinio):
    student, application, profile = await _seed(db)
    await _set_profile_document(db, profile, student.id, "first.pdf")
    service = ApplicationService(db)
    update = ApplicationUpdate(form_data=ApplicationFormData(fields={}, documents=[]))
    await service.update_application(application.id, update, student)

    new_source = await _set_profile_document(db, profile, student.id, "second.jpg")
    await service.update_application(application.id, update, student)

    (file,) = await _files(db, application)
    assert file.source_object_name == new_source
    assert [pair[0] for pair in fake_minio.cloned][-1] == new_source
    assert len(fake_minio.cloned) == 2


@pytest.mark.asyncio
async def test_superseded_copy_is_kept_once_the_application_left_draft(db: AsyncSession, fake_minio: FakeMinio):
    student, application, profile = await _seed(db)
    await _set_profile_document(db, profile, student.id, "first.pdf")
    service = ApplicationService(db)
    await service._clone_user_profile_documents(application, student)

    application.status = ApplicationStatus.returned.value
    await db.commit()
    await _set_profile_document(db, profile, student.id, "second.jpg")
    await service._clone_user_profile_documents(application, student)

    assert len(fake_minio.cloned) == 2
    assert fake_minio.deleted == []


@pytest.mark.asyncio
async def test_copy_made_before_the_source_was_recorded_is_refreshed_once(db: AsyncSession, fake_minio: FakeMinio):
    student, application, profile = await _seed(db)
    source = await _set_profile_document(db, profile, student.id, "current.pdf")
    legacy_copy = "applications/APP-CPD-1/documents/legacy.pdf"
    legacy_file = ApplicationFile(
        application_id=application.id,
        file_type=FILE_TYPE,
        filename="old.pdf",
        original_filename="old.pdf",
        object_name=legacy_copy,
        is_verified=True,
    )
    db.add(legacy_file)
    await db.commit()
    service = ApplicationService(db)

    await service._clone_user_profile_documents(application, student)
    await service._clone_user_profile_documents(application, student)

    assert [pair[0] for pair in fake_minio.cloned] == [source]
    assert fake_minio.deleted == [legacy_copy]
    (file,) = await _files(db, application)
    assert file.source_object_name == source


@pytest.mark.asyncio
async def test_duplicate_bank_rows_do_not_block_the_refresh(db: AsyncSession, fake_minio: FakeMinio):
    student, application, profile = await _seed(db)
    source = await _set_profile_document(db, profile, student.id, "current.pdf")
    for index in range(2):
        db.add(
            ApplicationFile(
                application_id=application.id,
                file_type=FILE_TYPE,
                filename=f"old{index}.pdf",
                object_name=f"applications/APP-CPD-1/documents/old{index}.pdf",
            )
        )
    await db.commit()

    await ApplicationService(db)._clone_user_profile_documents(application, student)

    assert [pair[0] for pair in fake_minio.cloned] == [source]
    files = await _files(db, application)
    assert sorted(f.source_object_name or "" for f in files) == ["", source]

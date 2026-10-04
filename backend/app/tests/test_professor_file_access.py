"""Professor access to application files through the file proxy.

The professor 查看申請 dialog lists the documents of every application assigned
to the professor (``Application.professor_id``, the same scope as
``GET /applications/{id}``). The proxy's professor branch used to call
``User.can_access_student_data``, which walks the lazy
``professor_relationships`` collection — under an AsyncSession that raises
MissingGreenlet (issue #1130), so every professor preview 500'd. These tests
pin the replacement: assigned professor streams, any other professor gets the
same 404 as a nonexistent file.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import files as files_endpoint
from app.models.application import Application, ApplicationFile, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType

PROXIES = [files_endpoint.get_file_proxy, files_endpoint.download_file_proxy]


async def _seed_user(db, *, role, nycu_id):
    user = User(
        nycu_id=nycu_id,
        name=f"User {nycu_id}",
        email=f"{nycu_id}@u.edu",
        user_type=UserType.student if role == UserRole.student else UserType.employee,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.fixture
async def assigned(db: AsyncSession):
    """One application assigned to ``professor``, with one uploaded file."""
    scholarship_type = ScholarshipType(code="pf_type", name="Type pf", status="active")
    db.add(scholarship_type)
    await db.commit()
    await db.refresh(scholarship_type)
    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type.id,
        config_code="pf_cfg",
        config_name="Cfg pf",
        academic_year=114,
        amount=0,
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    student = await _seed_user(db, role=UserRole.student, nycu_id="pf_stu")
    professor = await _seed_user(db, role=UserRole.professor, nycu_id="pf_prof")
    other_professor = await _seed_user(db, role=UserRole.professor, nycu_id="pf_other_prof")

    application = Application(
        app_id="APP-PF-1",
        user_id=student.id,
        professor_id=professor.id,
        scholarship_type_id=config.scholarship_type_id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=ApplicationStatus.submitted.value,
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)

    file_record = ApplicationFile(
        application_id=application.id,
        filename="transcript.pdf",
        object_name="applications/pf/transcript.pdf",
    )
    db.add(file_record)
    await db.commit()
    await db.refresh(file_record)

    return {
        "professor": professor,
        "other_professor": other_professor,
        "application": application,
        "file": file_record,
    }


@pytest.fixture
def token_for(monkeypatch):
    """Make the proxy resolve the query-string token straight to a user id."""
    monkeypatch.setattr(files_endpoint, "verify_token", lambda token: {"sub": token})
    stream = MagicMock()
    stream.stream.return_value = iter([b"%PDF-1.4"])
    monkeypatch.setattr(files_endpoint.minio_service, "get_file_stream", MagicMock(return_value=stream))
    return lambda user: str(user.id)


def test_helper_allows_the_assigned_professor():
    professor = User(id=7, role=UserRole.professor)
    application = Application(id=1, professor_id=7)
    files_endpoint._assert_professor_may_access(professor, application, file_id=1)


@pytest.mark.parametrize("assigned_professor_id", [8, None])
def test_helper_denies_with_404_otherwise(assigned_professor_id):
    """An unassigned (or not-yet-assigned) application looks like a missing file."""
    professor = User(id=7, role=UserRole.professor)
    application = Application(id=1, professor_id=assigned_professor_id)
    with pytest.raises(HTTPException) as exc:
        files_endpoint._assert_professor_may_access(professor, application, file_id=1)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("proxy", PROXIES)
async def test_assigned_professor_streams_the_file(db: AsyncSession, assigned, token_for, proxy):
    response = await proxy(
        application_id=assigned["application"].id,
        file_id=assigned["file"].id,
        token=token_for(assigned["professor"]),
        db=db,
    )
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "application/pdf"


@pytest.mark.asyncio
@pytest.mark.parametrize("proxy", PROXIES)
async def test_unassigned_professor_gets_404(db: AsyncSession, assigned, token_for, proxy):
    with pytest.raises(HTTPException) as exc:
        await proxy(
            application_id=assigned["application"].id,
            file_id=assigned["file"].id,
            token=token_for(assigned["other_professor"]),
            db=db,
        )
    assert exc.value.status_code == 404

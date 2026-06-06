"""
Test application renewal functionality
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import ApplicationStatus
from app.models.enums import QuotaManagementMode, Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationFormData
from app.services.application_service import ApplicationService


def _build_form_data() -> ApplicationFormData:
    """Build a minimal valid form payload."""
    return ApplicationFormData(
        fields={
            "bank_account": {
                "field_id": "bank_account",
                "field_type": "text",
                "value": "123456789",
                "required": True,
            }
        },
        documents=[],
    )


async def _create_active_configuration(db: AsyncSession, scholarship: ScholarshipType) -> ScholarshipConfiguration:
    """Create an active scholarship configuration with an open application period.

    create_application() now requires a concrete configuration_id, so every
    test needs a real ScholarshipConfiguration row tied to the scholarship type.
    """
    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        config_code="RENEWAL_TEST_CONFIG",
        config_name="Renewal Test Configuration",
        academic_year=113,
        semester=Semester.first,
        amount=50000,
        is_active=True,
        effective_start_date=datetime.now(timezone.utc) - timedelta(days=1),
        effective_end_date=datetime.now(timezone.utc) + timedelta(days=30),
        application_start_date=datetime.now(timezone.utc) - timedelta(days=1),
        application_end_date=datetime.now(timezone.utc) + timedelta(days=30),
        has_quota_limit=True,
        total_quota=100,
        quota_management_mode=QuotaManagementMode.simple,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


def _mock_student_service():
    """Patch StudentService so the external SIS snapshot fetch is mocked.

    Returns the patch context manager; the service under test must be
    instantiated *inside* the with-block so ApplicationService.__init__ picks
    up the mocked StudentService class.
    """
    patcher = patch("app.services.application_service.StudentService")
    return patcher


_STUDENT_SNAPSHOT = {
    "std_stdcode": "112550001",
    "std_cname": "Test Student",
    "std_academyno": "A",
    "std_depno": "4460",
    "_api_fetched_at": "2025-10-22T17:27:08Z",
    "_term_data_status": "success",
}


class TestApplicationRenewal:
    """Test application renewal functionality"""

    @pytest.mark.asyncio
    async def test_create_renewal_application(
        self, db: AsyncSession, test_user: User, test_scholarship: ScholarshipType
    ):
        """Test creating an application normalizes the renewal flag at create time.

        create_application() deliberately forces is_renewal=False for newly
        created applications (renewals are produced through the dedicated
        renewal flow, not the generic create path). The renewal flag is then
        toggled via update_application (see test_update_application_renewal_status).
        """
        # Arrange
        config = await _create_active_configuration(db, test_scholarship)

        with _mock_student_service() as mock_student:
            mock_instance = AsyncMock()
            mock_student.return_value = mock_instance
            mock_instance.get_student_basic_info.return_value = _STUDENT_SNAPSHOT
            mock_instance.get_student_snapshot.return_value = _STUDENT_SNAPSHOT

            service = ApplicationService(db)
            application_data = ApplicationCreate(
                scholarship_type=test_scholarship.code,
                configuration_id=config.id,
                scholarship_subtype_list=["general"],
                form_data=_build_form_data(),
                agree_terms=True,
                is_renewal=True,  # 標記為續領申請（建立時會被正規化為 False）
            )

            # Act
            application = await service.create_application(
                user_id=test_user.id,
                student_code="112550001",
                application_data=application_data,
                is_draft=False,
            )

        # Assert: create always normalizes is_renewal to False
        assert application.is_renewal is False
        assert application.status == ApplicationStatus.submitted.value

    @pytest.mark.asyncio
    async def test_create_new_application(self, db: AsyncSession, test_user: User, test_scholarship: ScholarshipType):
        """Test creating a new (non-renewal) application"""
        # Arrange
        config = await _create_active_configuration(db, test_scholarship)

        with _mock_student_service() as mock_student:
            mock_instance = AsyncMock()
            mock_student.return_value = mock_instance
            mock_instance.get_student_basic_info.return_value = _STUDENT_SNAPSHOT
            mock_instance.get_student_snapshot.return_value = _STUDENT_SNAPSHOT

            service = ApplicationService(db)
            application_data = ApplicationCreate(
                scholarship_type=test_scholarship.code,
                configuration_id=config.id,
                scholarship_subtype_list=["general"],
                form_data=_build_form_data(),
                agree_terms=True,
                is_renewal=False,  # 標記為新申請
            )

            # Act
            application = await service.create_application(
                user_id=test_user.id,
                student_code="112550001",
                application_data=application_data,
                is_draft=False,
            )

        # Assert
        assert application.is_renewal is False
        assert application.status == ApplicationStatus.submitted.value

    @pytest.mark.asyncio
    async def test_update_application_renewal_status(
        self, db: AsyncSession, test_user: User, test_scholarship: ScholarshipType
    ):
        """Test updating application renewal status"""
        # Arrange
        config = await _create_active_configuration(db, test_scholarship)

        with _mock_student_service() as mock_student:
            mock_instance = AsyncMock()
            mock_student.return_value = mock_instance
            mock_instance.get_student_basic_info.return_value = _STUDENT_SNAPSHOT
            mock_instance.get_student_snapshot.return_value = _STUDENT_SNAPSHOT

            service = ApplicationService(db)
            application_data = ApplicationCreate(
                scholarship_type=test_scholarship.code,
                configuration_id=config.id,
                scholarship_subtype_list=["general"],
                form_data=_build_form_data(),
                agree_terms=True,
                is_renewal=False,
            )

            # Create initial draft application
            application = await service.create_application(
                user_id=test_user.id,
                student_code="112550001",
                application_data=application_data,
                is_draft=True,
            )

        # Act - Update to renewal
        from app.schemas.application import ApplicationUpdate

        update_data = ApplicationUpdate(is_renewal=True)

        updated_application = await service.update_application(
            application_id=application.id,
            update_data=update_data,
            current_user=test_user,
        )

        # Assert
        assert updated_application.is_renewal is True

    @pytest.mark.asyncio
    async def test_get_user_applications_includes_renewal_flag(
        self, db: AsyncSession, test_user: User, test_scholarship: ScholarshipType
    ):
        """Test that user applications include renewal flag"""
        # Arrange
        config = await _create_active_configuration(db, test_scholarship)

        with _mock_student_service() as mock_student:
            mock_instance = AsyncMock()
            mock_student.return_value = mock_instance
            mock_instance.get_student_basic_info.return_value = _STUDENT_SNAPSHOT
            mock_instance.get_student_snapshot.return_value = _STUDENT_SNAPSHOT

            service = ApplicationService(db)
            application_data = ApplicationCreate(
                scholarship_type=test_scholarship.code,
                configuration_id=config.id,
                scholarship_subtype_list=["general"],
                form_data=_build_form_data(),
                agree_terms=True,
                is_renewal=False,
            )

            application = await service.create_application(
                user_id=test_user.id,
                student_code="112550001",
                application_data=application_data,
                is_draft=True,
            )

        # Toggle the renewal flag through the update path (the only path that
        # honors is_renewal) so the list response genuinely carries the flag.
        from app.schemas.application import ApplicationUpdate

        await service.update_application(
            application_id=application.id,
            update_data=ApplicationUpdate(is_renewal=True),
            current_user=test_user,
        )

        # Act
        applications = await service.get_user_applications(test_user)

        # Assert
        assert len(applications) > 0
        assert applications[0].is_renewal is True

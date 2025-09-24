"""
Test application renewal functionality
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import ApplicationStatus
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.schemas.application import ApplicationCreate, ApplicationFormData
from app.services.application_service import ApplicationService


class TestApplicationRenewal:
    """Test application renewal functionality"""

    @pytest.mark.asyncio
    async def test_create_renewal_application(
        self, db: AsyncSession, test_user: User, test_scholarship: ScholarshipType
    ):
        """Test creating a renewal application"""
        # Arrange
        service = ApplicationService(db)

        # Create form data
        form_data = ApplicationFormData(
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

        application_data = ApplicationCreate(
            scholarship_type=test_scholarship.code,
            scholarship_subtype_list=["general"],
            form_data=form_data,
            agree_terms=True,
            is_renewal=True,  # 標記為續領申請
        )

        # Act
        application = await service.create_application(
            user_id=test_user.id,
            student_id="STU001",  # Use mock student ID
            application_data=application_data,
            is_draft=False,
        )

        # Assert
        assert application.is_renewal is True
        assert application.status == ApplicationStatus.SUBMITTED.value

    @pytest.mark.asyncio
    async def test_create_new_application(
        self, db: AsyncSession, test_user: User, test_scholarship: ScholarshipType
    ):
        """Test creating a new (non-renewal) application"""
        # Arrange
        service = ApplicationService(db)

        # Create form data
        form_data = ApplicationFormData(
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

        application_data = ApplicationCreate(
            scholarship_type=test_scholarship.code,
            scholarship_subtype_list=["general"],
            form_data=form_data,
            agree_terms=True,
            is_renewal=False,  # 標記為新申請
        )

        # Act
        application = await service.create_application(
            user_id=test_user.id,
            student_id="STU001",  # Use mock student ID
            application_data=application_data,
            is_draft=False,
        )

        # Assert
        assert application.is_renewal is False
        assert application.status == ApplicationStatus.SUBMITTED.value

    @pytest.mark.asyncio
    async def test_update_application_renewal_status(
        self, db: AsyncSession, test_user: User, test_scholarship: ScholarshipType
    ):
        """Test updating application renewal status"""
        # Arrange
        service = ApplicationService(db)

        # Create initial application
        form_data = ApplicationFormData(
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

        application_data = ApplicationCreate(
            scholarship_type=test_scholarship.code,
            scholarship_subtype_list=["general"],
            form_data=form_data,
            agree_terms=True,
            is_renewal=False,
        )

        application = await service.create_application(
            user_id=test_user.id,
            student_id="STU001",  # Use mock student ID
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
        service = ApplicationService(db)

        # Create renewal application
        form_data = ApplicationFormData(
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

        application_data = ApplicationCreate(
            scholarship_type=test_scholarship.code,
            scholarship_subtype_list=["general"],
            form_data=form_data,
            agree_terms=True,
            is_renewal=True,
        )

        await service.create_application(
            user_id=test_user.id,
            student_id="STU001",  # Use mock student ID
            application_data=application_data,
            is_draft=False,
        )

        # Act
        applications = await service.get_user_applications(test_user)

        # Assert
        assert len(applications) > 0
        assert applications[0].is_renewal is True

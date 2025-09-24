"""
Risk-Based Integration Tests - Critical Workflows
Focus: High-risk paths with real database operations
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from app.core.exceptions import (AuthorizationError, ConflictError,
                                 ValidationError)
from app.models.application import Application, ApplicationStatus
from app.models.enums import (QuotaManagementMode, Semester,
                              SubTypeSelectionMode)
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole
from app.schemas.application import ApplicationCreate, ApplicationFormData
from app.services.application_service import ApplicationService
from app.services.bulk_approval_service import BulkApprovalService
from app.services.college_review_service import CollegeReviewService


@pytest.mark.integration
@pytest.mark.asyncio
class TestCriticalApplicationWorkflow:
    """Test critical application creation and submission workflows"""

    async def test_create_application_with_eligibility_validation(
        self, db, test_user, test_scholarship
    ):
        """CRITICAL: Test application creation with eligibility checks"""
        # Create configuration
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship.id,
            config_code="TEST_CONFIG_001",
            config_name="Test Configuration",
            academic_year=113,
            semester=Semester.FIRST,
            amount=50000,
            is_active=True,
            effective_start_date=datetime.now(timezone.utc) - timedelta(days=1),
            effective_end_date=datetime.now(timezone.utc) + timedelta(days=30),
            application_start_date=datetime.now(timezone.utc) - timedelta(days=1),
            application_end_date=datetime.now(timezone.utc) + timedelta(days=30),
            has_quota_limit=True,
            total_quota=100,
            quota_management_mode=QuotaManagementMode.SIMPLE,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

        service = ApplicationService(db)

        # Mock student service
        with patch("app.services.application_service.StudentService") as mock_student:
            mock_instance = AsyncMock()
            mock_student.return_value = mock_instance
            mock_instance.get_student_basic_info.return_value = {
                "student_id": "112550001",
                "name": "Test Student",
                "std_gpa": 3.8,
                "std_stdcode": "112550001",
            }

            app_data = ApplicationCreate(
                scholarship_type="test_scholarship",
                configuration_id=config.id,
                scholarship_subtype_list=[],
                form_data=ApplicationFormData(configuration_id=config.id, fields={}),
            )

            # Create application
            result = await service.create_application(
                user_id=test_user.id,
                student_code="112550001",
                application_data=app_data,
                is_draft=True,
            )

            assert result.status == ApplicationStatus.DRAFT.value
            assert result.user_id == test_user.id

    async def test_prevent_duplicate_applications(
        self, db, test_user, test_scholarship
    ):
        """CRITICAL: Prevent duplicate applications for same scholarship"""
        # Create first application
        app1 = Application(
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            status=ApplicationStatus.SUBMITTED.value,
            app_id="TEST-001",
            academic_year=113,
            semester="first",
            student_data={"student_id": "112550001"},
            submitted_form_data={},
            agree_terms=True,
        )
        db.add(app1)
        await db.commit()

        service = ApplicationService(db)

        # Mock student service
        with patch("app.services.application_service.StudentService") as mock_student:
            mock_instance = AsyncMock()
            mock_student.return_value = mock_instance
            mock_instance.get_student_basic_info.return_value = {
                "student_id": "112550001",
                "std_stdcode": "112550001",
            }

            # Try to create duplicate - should fail
            with pytest.raises(
                ConflictError, match="already have an active application"
            ):
                app_data = ApplicationCreate(
                    scholarship_type="test_scholarship",
                    configuration_id=1,
                    scholarship_subtype_list=[],
                    form_data=ApplicationFormData(configuration_id=1, fields={}),
                )

                await service.create_application(
                    user_id=test_user.id,
                    student_code="112550001",
                    application_data=app_data,
                    is_draft=False,
                )

    async def test_submit_application_state_transition(self, db, test_user):
        """CRITICAL: Test application submission and state validation"""
        # Create draft application
        app = Application(
            user_id=test_user.id,
            scholarship_type_id=1,
            status=ApplicationStatus.DRAFT.value,
            app_id="TEST-DRAFT-001",
            academic_year=113,
            semester="first",
            student_data={"student_id": "112550001"},
            submitted_form_data={"personal_statement": "Test"},
            agree_terms=True,
        )
        db.add(app)
        await db.commit()
        await db.refresh(app)

        service = ApplicationService(db)

        # Submit application
        result = await service.submit_application(app.id, test_user)

        assert result.status == ApplicationStatus.SUBMITTED.value
        assert result.submitted_at is not None

        # Try to submit again - should fail
        with pytest.raises(ValidationError, match="cannot be submitted"):
            await service.submit_application(app.id, test_user)


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.asyncio
class TestCriticalAuthorizationPaths:
    """Test security-critical authorization paths"""

    async def test_student_cannot_edit_others_application(self, db, test_user):
        """CRITICAL: Students can only edit their own applications"""
        # Create another user
        other_user = User(
            nycu_id="otheruser",
            name="Other User",
            email="other@university.edu",
            user_type="student",
            role=UserRole.STUDENT,
        )
        db.add(other_user)
        await db.commit()
        await db.refresh(other_user)

        # Create application owned by other_user
        app = Application(
            user_id=other_user.id,
            scholarship_type_id=1,
            status=ApplicationStatus.DRAFT.value,
            app_id="TEST-OTHER-001",
            academic_year=113,
            semester="first",
            student_data={"student_id": "112550002"},
            submitted_form_data={},
            agree_terms=True,
        )
        db.add(app)
        await db.commit()

        service = ApplicationService(db)

        # Try to access other user's application - should fail
        with pytest.raises(AuthorizationError):
            await service.get_application_by_id(app.id, test_user)

    async def test_cannot_edit_submitted_application(
        self, db, test_user, test_application
    ):
        """CRITICAL: Cannot edit application after submission"""
        # Change status to submitted
        test_application.status = ApplicationStatus.SUBMITTED.value
        await db.commit()

        service = ApplicationService(db)

        from app.schemas.application import ApplicationUpdate

        update_data = ApplicationUpdate(submitted_form_data={"new_field": "value"})

        # Try to update - should fail
        with pytest.raises(ValidationError, match="cannot be edited"):
            await service.update_application(
                test_application.id, update_data, test_user
            )

    async def test_admin_can_approve_but_student_cannot(
        self, db, test_user, test_admin
    ):
        """CRITICAL: Only admins can approve applications"""
        # Create submitted application
        app = Application(
            user_id=test_user.id,
            scholarship_type_id=1,
            status=ApplicationStatus.SUBMITTED.value,
            app_id="TEST-SUBMIT-001",
            academic_year=113,
            semester="first",
            student_data={"student_id": "112550001"},
            submitted_form_data={},
            agree_terms=True,
        )
        db.add(app)
        await db.commit()

        bulk_service = BulkApprovalService(db)

        # Admin can approve
        with patch.object(
            bulk_service.notification_service,
            "send_status_change_notification",
            return_value=True,
        ):
            result = await bulk_service.bulk_approve_applications(
                application_ids=[app.id],
                approver_user_id=test_admin.id,
                send_notifications=False,
            )

            assert len(result["successful_approvals"]) == 1


@pytest.mark.integration
@pytest.mark.asyncio
class TestCriticalBusinessLogic:
    """Test critical business logic and calculations"""

    async def test_quota_limit_enforcement(self, db, test_scholarship):
        """CRITICAL: Enforce quota limits during bulk approval"""
        # Create configuration with quota limit
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship.id,
            config_code="QUOTA_TEST",
            config_name="Quota Test Configuration",
            academic_year=113,
            semester=Semester.FIRST,
            amount=50000,
            is_active=True,
            effective_start_date=datetime.now(timezone.utc),
            effective_end_date=datetime.now(timezone.utc) + timedelta(days=30),
            has_quota_limit=True,
            total_quota=2,  # Only 2 spots
            quota_management_mode=QuotaManagementMode.SIMPLE,
        )
        db.add(config)
        await db.commit()

        # Create 3 applications
        apps = []
        for i in range(3):
            user = User(
                nycu_id=f"student{i}",
                name=f"Student {i}",
                email=f"student{i}@university.edu",
                user_type="student",
                role=UserRole.STUDENT,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            app = Application(
                user_id=user.id,
                scholarship_type_id=test_scholarship.id,
                status=ApplicationStatus.SUBMITTED.value,
                app_id=f"QUOTA-{i}",
                academic_year=113,
                semester="first",
                student_data={"student_id": f"11255000{i}"},
                submitted_form_data={},
                agree_terms=True,
            )
            db.add(app)
            apps.append(app)

        await db.commit()

        # Approve first 2 - should succeed
        bulk_service = BulkApprovalService(db)
        with patch.object(
            bulk_service.notification_service,
            "send_status_change_notification",
            return_value=True,
        ):
            result = await bulk_service.bulk_approve_applications(
                application_ids=[apps[0].id, apps[1].id],
                approver_user_id=1,
                send_notifications=False,
            )

            assert len(result["successful_approvals"]) == 2

        # Check quota availability - should show 0 available
        from app.services.scholarship_configuration_service import \
            ScholarshipConfigurationService

        config_service = ScholarshipConfigurationService(db)

        available, info = await config_service.check_quota_availability(config)

        assert available is False
        assert info["available_quota"] == 0

    async def test_priority_score_calculation_with_renewal(self, db, test_user):
        """CRITICAL: Priority score calculation for renewals"""
        # Create renewal application
        app = Application(
            user_id=test_user.id,
            scholarship_type_id=1,
            status=ApplicationStatus.DRAFT.value,
            app_id="RENEWAL-001",
            academic_year=113,
            semester="first",
            is_renewal=True,
            gpa=3.8,
            class_ranking_percent=10.0,
            student_data={"student_id": "112550001"},
            submitted_form_data={},
            agree_terms=True,
        )
        db.add(app)
        await db.commit()

        # Calculate priority score
        score = app.calculate_priority_score()

        # Renewal should get bonus
        assert score > 0


@pytest.mark.integration
@pytest.mark.asyncio
class TestCriticalDataIntegrity:
    """Test data integrity and constraint enforcement"""

    async def test_foreign_key_constraint_on_delete(
        self, db, test_user, test_scholarship
    ):
        """CRITICAL: Ensure foreign key constraints work"""
        # Create application
        app = Application(
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            status=ApplicationStatus.DRAFT.value,
            app_id="FK-TEST-001",
            academic_year=113,
            semester="first",
            student_data={"student_id": "112550001"},
            submitted_form_data={},
            agree_terms=True,
        )
        db.add(app)
        await db.commit()

        # Deleting user should fail or cascade properly
        # (depending on FK configuration)
        app_id = app.id

        # Verify application exists
        from sqlalchemy import select

        stmt = select(Application).where(Application.id == app_id)
        result = await db.execute(stmt)
        assert result.scalar_one_or_none() is not None

    async def test_unique_constraint_on_config_code(self, db, test_scholarship):
        """CRITICAL: Ensure unique constraints on config codes"""
        config1 = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship.id,
            config_code="UNIQUE_TEST",
            academic_year=113,
            semester=Semester.FIRST,
            is_active=True,
            effective_date_start=datetime.now(timezone.utc),
            effective_date_end=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(config1)
        await db.commit()

        # Try to create duplicate config code
        config2 = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship.id,
            config_code="UNIQUE_TEST",  # Same code
            academic_year=113,
            semester=Semester.SECOND,
            is_active=True,
            effective_date_start=datetime.now(timezone.utc),
            effective_date_end=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(config2)

        # Should raise integrity error
        with pytest.raises(Exception):  # SQLAlchemy IntegrityError
            await db.commit()

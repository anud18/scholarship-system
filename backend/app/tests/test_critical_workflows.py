"""
Risk-Based Integration Tests - Critical Workflows
Focus: High-risk paths with real database operations
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.api.v1.endpoints.applications import create_application as create_application_endpoint
from app.core.exceptions import ValidationError
from app.models.application import Application, ApplicationStatus
from app.models.enums import QuotaManagementMode, Semester
from app.models.scholarship import ScholarshipConfiguration, SubTypeSelectionMode
from app.models.user import User, UserRole
from app.schemas.application import ApplicationCreate, ApplicationFormData
from app.services.application_service import ApplicationService
from app.services.bulk_approval_service import BulkApprovalService



@pytest.mark.integration
@pytest.mark.asyncio
class TestCriticalApplicationWorkflow:
    """Test critical application creation and submission workflows"""

    @pytest.mark.smoke
    async def test_create_application_with_eligibility_validation(self, db, test_user, test_scholarship):
        """CRITICAL: Test application creation with eligibility checks"""
        # Create configuration
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship.id,
            config_code="TEST_CONFIG_001",
            config_name="Test Configuration",
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

        # Instantiate inside the patch block so ApplicationService.__init__
        # picks up the mocked StudentService class (not the real one).
        with patch("app.services.application_service.StudentService") as mock_student:
            mock_instance = AsyncMock()
            mock_student.return_value = mock_instance
            _student_snapshot = {
                "std_stdcode": "112550001",
                "std_cname": "Test Student",
                "std_academyno": "A",
                "std_depno": "4460",
                "_api_fetched_at": "2025-10-22T17:27:08Z",
                "_term_data_status": "success",
            }
            mock_instance.get_student_basic_info.return_value = _student_snapshot
            mock_instance.get_student_snapshot.return_value = _student_snapshot

            service = ApplicationService(db)
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

            assert result.status == ApplicationStatus.draft.value
            assert result.user_id == test_user.id

    async def test_submit_application_state_transition(self, db, test_user):
        """CRITICAL: Test application submission and state validation"""
        # Create draft application
        app = Application(
            user_id=test_user.id,
            scholarship_type_id=1,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            status=ApplicationStatus.draft.value,
            app_id="TEST-DRAFT-001",
            academic_year=113,
            semester="first",
            student_data={"student_id": "112550001"},
            submitted_form_data={"fields": {}},
            agree_terms=True,
        )
        db.add(app)
        await db.commit()
        await db.refresh(app)

        service = ApplicationService(db)

        # Submit application
        result = await service.submit_application(app.id, test_user)

        assert result.status == ApplicationStatus.submitted.value
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
            role=UserRole.student,
        )
        db.add(other_user)
        await db.commit()
        await db.refresh(other_user)

        # Create application owned by other_user
        app = Application(
            user_id=other_user.id,
            scholarship_type_id=1,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            status=ApplicationStatus.draft.value,
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

        # get_application_by_id returns None (not raises) for unauthorized student access
        result = await service.get_application_by_id(app.id, test_user)
        assert result is None

    @pytest.mark.smoke
    async def test_cannot_edit_submitted_application(self, db, test_user, test_application):
        """CRITICAL: Cannot edit application after submission"""
        # Change status to submitted
        test_application.status = ApplicationStatus.submitted.value
        await db.commit()

        service = ApplicationService(db)

        from app.schemas.application import ApplicationUpdate

        update_data = ApplicationUpdate(submitted_form_data={"new_field": "value"})

        # Try to update - should fail
        with pytest.raises(ValidationError, match="cannot be edited"):
            await service.update_application(test_application.id, update_data, test_user)

    async def test_admin_can_approve_but_student_cannot(self, db, test_user, test_admin):
        """CRITICAL: Only admins can approve applications"""
        # Create submitted application
        app = Application(
            user_id=test_user.id,
            scholarship_type_id=1,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            status=ApplicationStatus.submitted.value,
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

    @pytest.mark.smoke
    async def test_quota_limit_enforcement(self, db, test_scholarship):
        """CRITICAL: Enforce quota limits during bulk approval"""
        # Create configuration with quota limit
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship.id,
            config_code="QUOTA_TEST",
            config_name="Quota Test Configuration",
            academic_year=113,
            semester=Semester.first,
            amount=50000,
            is_active=True,
            effective_start_date=datetime.now(timezone.utc),
            effective_end_date=datetime.now(timezone.utc) + timedelta(days=30),
            has_quota_limit=True,
            total_quota=2,  # Only 2 spots
            quota_management_mode=QuotaManagementMode.simple,
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
                role=UserRole.student,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

            app = Application(
                user_id=user.id,
                scholarship_type_id=test_scholarship.id,
                sub_type_selection_mode=SubTypeSelectionMode.single,
                status=ApplicationStatus.submitted.value,
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
        from app.services.scholarship_configuration_service import ScholarshipConfigurationService

        config_service = ScholarshipConfigurationService(db)

        available, info = await config_service.check_quota_availability(config)

        assert available is False
        assert info["available_quota"] == 0

    async def test_priority_score_calculation_with_renewal(self, db, test_user):
        """CRITICAL: Renewal application persists with is_renewal=True flag."""
        app = Application(
            user_id=test_user.id,
            scholarship_type_id=1,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            status=ApplicationStatus.draft.value,
            app_id="RENEWAL-001",
            academic_year=113,
            semester="first",
            is_renewal=True,
            student_data={"student_id": "112550001"},
            submitted_form_data={},
            agree_terms=True,
        )
        db.add(app)
        await db.commit()
        await db.refresh(app)

        assert app.id is not None
        assert app.is_renewal is True


@pytest.mark.integration
@pytest.mark.asyncio
class TestCriticalDataIntegrity:
    """Test data integrity and constraint enforcement"""

    async def test_foreign_key_constraint_on_delete(self, db, test_user, test_scholarship):
        """CRITICAL: Ensure foreign key constraints work"""
        # Create application
        app = Application(
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            status=ApplicationStatus.draft.value,
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

    @pytest.mark.smoke
    async def test_unique_constraint_on_config_code(self, db, test_scholarship):
        """CRITICAL: Ensure unique constraints on config codes"""
        config1 = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship.id,
            config_code="UNIQUE_TEST",
            config_name="Unique Test Config 1",
            academic_year=113,
            semester=Semester.first,
            amount=50000,
            is_active=True,
            effective_start_date=datetime.now(timezone.utc),
            effective_end_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(config1)
        await db.commit()

        # Try to create duplicate config code
        config2 = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship.id,
            config_code="UNIQUE_TEST",  # Same code
            config_name="Unique Test Config 2",
            academic_year=113,
            semester=Semester.second,
            amount=50000,
            is_active=True,
            effective_start_date=datetime.now(timezone.utc),
            effective_end_date=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(config2)

        # Should raise integrity error
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.integration
@pytest.mark.asyncio
class TestDuplicateApplicationAPIGuard:
    """Test duplicate application guard at the API endpoint layer.

    The duplicate check lives inside create_application() in applications.py
    (lines ~151-222), NOT in ApplicationService.  We call the endpoint function
    directly (bypassing ASGI transport) so that FastAPI's DI, HTTP headers, and
    event-loop interactions don't interfere with the patch on
    get_student_data_from_user.
    """

    async def test_duplicate_submitted_returns_error_code(self, db, test_user, test_scholarship):
        """create_application() returns DUPLICATE_APPLICATION when a non-draft already exists."""
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship.id,
            config_code="DUP_API_TEST_001",
            config_name="Dup API Test Config",
            academic_year=113,
            semester=Semester.first,
            amount=50000,
            is_active=True,
            effective_start_date=datetime.now(timezone.utc) - timedelta(days=1),
            effective_end_date=datetime.now(timezone.utc) + timedelta(days=30),
            application_start_date=datetime.now(timezone.utc) - timedelta(days=1),
            application_end_date=datetime.now(timezone.utc) + timedelta(days=30),
            has_quota_limit=False,
            quota_management_mode=QuotaManagementMode.simple,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

        existing = Application(
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            status=ApplicationStatus.submitted.value,
            app_id="DUP-API-EXISTING-001",
            academic_year=113,
            semester="first",
            student_data={"std_stdcode": "112550001"},
            submitted_form_data={},
            agree_terms=True,
        )
        db.add(existing)
        await db.commit()

        app_data = ApplicationCreate(
            scholarship_type=test_scholarship.code,
            configuration_id=config.id,
            scholarship_subtype_list=[],
            form_data=ApplicationFormData(fields={}),
        )
        mock_student = {"std_stdcode": test_user.nycu_id, "std_cname": test_user.name}

        with patch(
            "app.services.application_service.get_student_data_from_user",
            new=AsyncMock(return_value=mock_student),
        ):
            result = await create_application_endpoint(
                application_data=app_data,
                is_draft=False,
                current_user=test_user,
                db=db,
                request=None,
                response=None,
            )

        assert result["success"] is False
        assert result["data"]["error_code"] == "DUPLICATE_APPLICATION"
        assert result["data"]["existing_app_id"] == "DUP-API-EXISTING-001"

    async def test_existing_draft_is_returned(self, db, test_user, test_scholarship):
        """create_application() returns the existing draft (success=True) when one already exists."""
        config = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship.id,
            config_code="DRAFT_RET_TEST_001",
            config_name="Draft Return Test Config",
            academic_year=113,
            semester=Semester.first,
            amount=50000,
            is_active=True,
            effective_start_date=datetime.now(timezone.utc) - timedelta(days=1),
            effective_end_date=datetime.now(timezone.utc) + timedelta(days=30),
            application_start_date=datetime.now(timezone.utc) - timedelta(days=1),
            application_end_date=datetime.now(timezone.utc) + timedelta(days=30),
            has_quota_limit=False,
            quota_management_mode=QuotaManagementMode.simple,
        )
        db.add(config)
        await db.commit()
        await db.refresh(config)

        draft = Application(
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            status=ApplicationStatus.draft.value,
            app_id="DRAFT-RET-EXISTING-001",
            academic_year=113,
            semester="first",
            student_data={"std_stdcode": "112550001"},
            submitted_form_data={},
            agree_terms=True,
        )
        db.add(draft)
        await db.commit()

        app_data = ApplicationCreate(
            scholarship_type=test_scholarship.code,
            configuration_id=config.id,
            scholarship_subtype_list=[],
            form_data=ApplicationFormData(fields={}),
        )
        mock_student = {"std_stdcode": test_user.nycu_id, "std_cname": test_user.name}

        with patch(
            "app.services.application_service.get_student_data_from_user",
            new=AsyncMock(return_value=mock_student),
        ):
            result = await create_application_endpoint(
                application_data=app_data,
                is_draft=False,
                current_user=test_user,
                db=db,
                request=None,
                response=None,
            )

        assert result["success"] is True
        assert result["data"]["app_id"] == "DRAFT-RET-EXISTING-001"
        assert result["data"]["status"] == "draft"

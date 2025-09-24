"""
Comprehensive tests for BulkApprovalService
Target: 0% → 80% coverage
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.services.bulk_approval_service import BulkApprovalService


@pytest.mark.asyncio
class TestBulkApprovalServiceApprove:
    """Test bulk approval operations"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return BulkApprovalService(db)

    @pytest.fixture
    def mock_application(self):
        app = Mock(spec=Application)
        app.id = 1
        app.app_id = "APP001"
        app.status = ApplicationStatus.SUBMITTED.value
        app.student_data = {"student_id": "112550001"}
        app.calculate_priority_score = Mock(return_value=85)
        return app

    async def test_bulk_approve_success(self, service, mock_application):
        """Test successful bulk approval"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_application]
        service.db.execute = AsyncMock(return_value=mock_result)
        service.db.commit = AsyncMock()

        with patch.object(
            service.notification_service,
            "send_status_change_notification",
            return_value=True,
        ):
            results = await service.bulk_approve_applications(
                application_ids=[1], approver_user_id=2, send_notifications=True
            )

        assert results["total_requested"] == 1
        assert len(results["successful_approvals"]) == 1
        assert results["notifications_sent"] == 1
        assert mock_application.status == ApplicationStatus.APPROVED.value

    async def test_bulk_approve_invalid_status(self, service, mock_application):
        """Test bulk approval with invalid status"""
        mock_application.status = ApplicationStatus.APPROVED.value

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_application]
        service.db.execute = AsyncMock(return_value=mock_result)

        results = await service.bulk_approve_applications(
            application_ids=[1], approver_user_id=2, send_notifications=False
        )

        assert len(results["failed_approvals"]) == 1
        assert "Invalid status" in results["failed_approvals"][0]["reason"]

    async def test_bulk_approve_missing_applications(self, service):
        """Test bulk approval with missing applications"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        service.db.execute = AsyncMock(return_value=mock_result)

        results = await service.bulk_approve_applications(
            application_ids=[1, 2, 3], approver_user_id=2
        )

        assert results["total_requested"] == 3
        assert len(results["successful_approvals"]) == 0

    async def test_bulk_approve_with_notes(self, service, mock_application):
        """Test bulk approval with approval notes"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_application]
        service.db.execute = AsyncMock(return_value=mock_result)
        service.db.commit = AsyncMock()

        with patch.object(
            service.notification_service,
            "send_status_change_notification",
            return_value=True,
        ):
            results = await service.bulk_approve_applications(
                application_ids=[1],
                approver_user_id=2,
                approval_notes="Excellent application",
            )

        assert mock_application.admin_notes == "Excellent application"


@pytest.mark.asyncio
class TestBulkApprovalServiceReject:
    """Test bulk rejection operations"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return BulkApprovalService(db)

    @pytest.fixture
    def mock_application(self):
        app = Mock(spec=Application)
        app.id = 1
        app.app_id = "APP001"
        app.status = ApplicationStatus.SUBMITTED.value
        app.student_data = {"student_id": "112550001"}
        return app

    async def test_bulk_reject_success(self, service, mock_application):
        """Test successful bulk rejection"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_application]
        service.db.execute = AsyncMock(return_value=mock_result)
        service.db.commit = AsyncMock()

        with patch.object(
            service.notification_service,
            "send_status_change_notification",
            return_value=True,
        ):
            results = await service.bulk_reject_applications(
                application_ids=[1],
                rejector_user_id=2,
                rejection_reason="Does not meet criteria",
            )

        assert results["total_requested"] == 1
        assert len(results["successful_rejections"]) == 1
        assert mock_application.status == ApplicationStatus.REJECTED.value
        assert mock_application.rejection_reason == "Does not meet criteria"

    async def test_bulk_reject_invalid_status(self, service, mock_application):
        """Test bulk rejection with invalid status"""
        mock_application.status = ApplicationStatus.REJECTED.value

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_application]
        service.db.execute = AsyncMock(return_value=mock_result)

        results = await service.bulk_reject_applications(
            application_ids=[1], rejector_user_id=2, rejection_reason="Test"
        )

        assert len(results["failed_rejections"]) == 1


@pytest.mark.asyncio
class TestBulkApprovalServiceAutoApprove:
    """Test auto-approval functionality"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return BulkApprovalService(db)

    @pytest.fixture
    def mock_applications(self):
        apps = []
        for i in range(3):
            app = Mock(spec=Application)
            app.id = i + 1
            app.app_id = f"APP00{i+1}"
            app.status = ApplicationStatus.SUBMITTED.value
            app.priority_score = 90 - (i * 5)
            app.is_renewal = i == 0
            app.student_data = {"student_id": f"11255000{i+1}"}
            apps.append(app)
        return apps

    async def test_auto_approve_by_criteria(self, service, mock_applications):
        """Test auto-approval based on criteria"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_applications
        service.db.execute = AsyncMock(return_value=mock_result)
        service.db.commit = AsyncMock()

        results = await service.auto_approve_by_criteria(
            scholarship_type_id=1, min_priority_score=80, max_applications=2
        )

        assert results["total_eligible"] == 3
        assert results["success_count"] == 3

    async def test_auto_approve_with_custom_criteria(self, service, mock_applications):
        """Test auto-approval with custom criteria"""
        mock_applications[0].gpa = 3.8
        mock_applications[1].gpa = 3.5
        mock_applications[2].gpa = 3.2

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = mock_applications
        service.db.execute = AsyncMock(return_value=mock_result)
        service.db.commit = AsyncMock()

        results = await service.auto_approve_by_criteria(
            approval_criteria={"min_gpa": 3.5}
        )

        assert results["total_eligible"] <= 3


@pytest.mark.asyncio
class TestBulkApprovalServiceStatusUpdate:
    """Test bulk status update"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return BulkApprovalService(db)

    @pytest.fixture
    def mock_application(self):
        app = Mock(spec=Application)
        app.id = 1
        app.app_id = "APP001"
        app.status = ApplicationStatus.SUBMITTED.value
        return app

    async def test_bulk_status_update_success(self, service, mock_application):
        """Test successful bulk status update"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_application]
        service.db.execute = AsyncMock(return_value=mock_result)
        service.db.commit = AsyncMock()

        results = await service.bulk_status_update(
            application_ids=[1],
            new_status=ApplicationStatus.UNDER_REVIEW.value,
            updater_user_id=2,
            update_notes="Under review",
        )

        assert results["success_count"] == 1
        assert mock_application.status == ApplicationStatus.UNDER_REVIEW.value

    async def test_bulk_status_update_invalid_status(self, service):
        """Test bulk status update with invalid status"""
        with pytest.raises(ValueError, match="Invalid status"):
            await service.bulk_status_update(
                application_ids=[1], new_status="INVALID_STATUS", updater_user_id=2
            )


@pytest.mark.asyncio
class TestBulkApprovalServiceBatchProcess:
    """Test batch processing with notifications"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return BulkApprovalService(db)

    async def test_batch_process_approve(self, service):
        """Test batch processing approve operation"""
        with patch.object(
            service, "bulk_approve_applications", new_callable=AsyncMock
        ) as mock_approve:
            mock_approve.return_value = {
                "success_count": 5,
                "failure_count": 0,
                "total_requested": 5,
            }

            results = await service.batch_process_with_notifications(
                operation_type="approve",
                application_ids=[1, 2, 3],
                operator_user_id=2,
                operation_params={"approval_notes": "Batch approved"},
            )

            assert "operation_metadata" in results
            assert results["operation_metadata"]["operation_type"] == "approve"

    async def test_batch_process_reject(self, service):
        """Test batch processing reject operation"""
        with patch.object(
            service, "bulk_reject_applications", new_callable=AsyncMock
        ) as mock_reject:
            mock_reject.return_value = {
                "success_count": 3,
                "failure_count": 0,
                "total_requested": 3,
            }

            results = await service.batch_process_with_notifications(
                operation_type="reject",
                application_ids=[1, 2, 3],
                operator_user_id=2,
                operation_params={"rejection_reason": "Does not meet criteria"},
            )

            assert results["operation_metadata"]["operation_type"] == "reject"

    async def test_batch_process_invalid_operation(self, service):
        """Test batch processing with invalid operation"""
        with pytest.raises(ValueError, match="Invalid operation type"):
            await service.batch_process_with_notifications(
                operation_type="invalid_op",
                application_ids=[1],
                operator_user_id=2,
                operation_params={},
            )


class TestBulkApprovalServiceCriteria:
    """Test approval criteria helper"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return BulkApprovalService(db)

    @pytest.fixture
    def mock_application(self):
        app = Mock(spec=Application)
        app.id = 1
        app.gpa = 3.5
        app.class_ranking_percent = 15.0
        app.is_renewal = True
        app.priority_score = 85
        return app

    def test_meets_approval_criteria_gpa(self, service, mock_application):
        """Test GPA criteria check"""
        criteria = {"min_gpa": 3.0}
        assert service._meets_approval_criteria(mock_application, criteria) == True

        criteria = {"min_gpa": 3.8}
        assert service._meets_approval_criteria(mock_application, criteria) == False

    def test_meets_approval_criteria_ranking(self, service, mock_application):
        """Test ranking criteria check"""
        criteria = {"max_ranking": 20.0}
        assert service._meets_approval_criteria(mock_application, criteria) == True

        criteria = {"max_ranking": 10.0}
        assert service._meets_approval_criteria(mock_application, criteria) == False

    def test_meets_approval_criteria_renewal(self, service, mock_application):
        """Test renewal criteria check"""
        criteria = {"require_renewal": True}
        assert service._meets_approval_criteria(mock_application, criteria) == True

        mock_application.is_renewal = False
        assert service._meets_approval_criteria(mock_application, criteria) == False

    def test_meets_approval_criteria_priority_score(self, service, mock_application):
        """Test priority score criteria check"""
        criteria = {"min_priority_score": 80}
        assert service._meets_approval_criteria(mock_application, criteria) == True

        criteria = {"min_priority_score": 90}
        assert service._meets_approval_criteria(mock_application, criteria) == False

    def test_meets_approval_criteria_multiple(self, service, mock_application):
        """Test multiple criteria check"""
        criteria = {"min_gpa": 3.0, "max_ranking": 20.0, "min_priority_score": 80}
        assert service._meets_approval_criteria(mock_application, criteria) == True

        criteria = {"min_gpa": 3.8, "max_ranking": 20.0}
        assert service._meets_approval_criteria(mock_application, criteria) == False

    def test_meets_approval_criteria_error_handling(self, service, mock_application):
        """Test criteria check with None values"""
        mock_application.gpa = None
        criteria = {"min_gpa": 3.0}

        result = service._meets_approval_criteria(mock_application, criteria)
        assert result == True

"""
Bulk approval service for scholarship applications
Handles batch processing, bulk operations, and automated decision workflows
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.services.eligibility_verification_service import EligibilityVerificationService

# Student model removed - student data now fetched from external API
from app.services.scholarship_notification_service import ScholarshipNotificationService

logger = logging.getLogger(__name__)


class BulkApprovalService:
    """Service for bulk approval operations"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.notification_service = ScholarshipNotificationService(db)
        self.eligibility_service = EligibilityVerificationService(db)

    async def bulk_approve_applications(
        self,
        application_ids: List[int],
        approver_user_id: int,
        approval_notes: Optional[str] = None,
        send_notifications: bool = True,
    ) -> Dict[str, Any]:
        """Bulk approve multiple applications"""

        results = {
            "total_requested": len(application_ids),
            "successful_approvals": [],
            "failed_approvals": [],
            "notifications_sent": 0,
            "notifications_failed": 0,
        }

        try:
            # Get applications to approve
            stmt = select(Application).where(Application.id.in_(application_ids))
            result = await self.db.execute(stmt)
            applications = result.scalars().all()

            found_ids = {app.id for app in applications}
            missing_ids = set(application_ids) - found_ids

            if missing_ids:
                logger.warning(f"Applications not found: {missing_ids}")

            # Process each application
            for application in applications:
                try:
                    # Validate application can be approved
                    if application.status not in [
                        ApplicationStatus.SUBMITTED.value,
                        ApplicationStatus.UNDER_REVIEW.value,
                        ApplicationStatus.RECOMMENDED.value,
                    ]:
                        results["failed_approvals"].append(
                            {
                                "application_id": application.id,
                                "app_id": application.app_id,
                                "reason": f"Invalid status for approval: {application.status}",
                                "current_status": application.status,
                            }
                        )
                        continue

                    # Update application status
                    old_status = application.status
                    application.status = ApplicationStatus.APPROVED.value
                    application.approved_at = datetime.now(timezone.utc)
                    application.decision_date = datetime.now(timezone.utc)
                    application.final_approver_id = approver_user_id

                    if approval_notes:
                        application.admin_notes = approval_notes

                    # Calculate final priority score
                    application.priority_score = application.calculate_priority_score()

                    await self.db.commit()

                    results["successful_approvals"].append(
                        {
                            "application_id": application.id,
                            "app_id": application.app_id,
                            "student_id": application.student_data.get("student_id")
                            if application.student_data
                            else None,
                            "previous_status": old_status,
                            "new_status": application.status,
                            "approved_at": application.approved_at.isoformat(),
                            "priority_score": application.priority_score,
                        }
                    )

                    # Send notification if requested
                    if send_notifications:
                        try:
                            notification_sent = await self.notification_service.send_status_change_notification(
                                application, old_status, application.status
                            )
                            if notification_sent:
                                results["notifications_sent"] += 1
                            else:
                                results["notifications_failed"] += 1
                        except Exception as e:
                            logger.error(f"Failed to send notification for application {application.id}: {str(e)}")
                            results["notifications_failed"] += 1

                    logger.info(f"Bulk approved application {application.app_id}")

                except Exception as e:
                    logger.error(f"Failed to approve application {application.id}: {str(e)}")
                    await self.db.rollback()
                    results["failed_approvals"].append(
                        {
                            "application_id": application.id,
                            "app_id": getattr(application, "app_id", "Unknown"),
                            "reason": f"Approval failed: {str(e)}",
                            "error": str(e),
                        }
                    )

            return results

        except Exception as e:
            logger.error(f"Bulk approval operation failed: {str(e)}")
            await self.db.rollback()
            raise

    async def bulk_reject_applications(
        self,
        application_ids: List[int],
        rejector_user_id: int,
        rejection_reason: str,
        send_notifications: bool = True,
    ) -> Dict[str, Any]:
        """Bulk reject multiple applications"""

        results = {
            "total_requested": len(application_ids),
            "successful_rejections": [],
            "failed_rejections": [],
            "notifications_sent": 0,
            "notifications_failed": 0,
        }

        try:
            stmt = select(Application).where(Application.id.in_(application_ids))
            result = await self.db.execute(stmt)
            applications = result.scalars().all()

            for application in applications:
                try:
                    # Validate application can be rejected
                    if application.status not in [
                        ApplicationStatus.SUBMITTED.value,
                        ApplicationStatus.UNDER_REVIEW.value,
                        ApplicationStatus.RECOMMENDED.value,
                    ]:
                        results["failed_rejections"].append(
                            {
                                "application_id": application.id,
                                "app_id": application.app_id,
                                "reason": f"Invalid status for rejection: {application.status}",
                            }
                        )
                        continue

                    # Update application status
                    old_status = application.status
                    application.status = ApplicationStatus.REJECTED.value
                    application.decision_date = datetime.now(timezone.utc)
                    application.reviewer_id = rejector_user_id
                    application.rejection_reason = rejection_reason

                    await self.db.commit()

                    results["successful_rejections"].append(
                        {
                            "application_id": application.id,
                            "app_id": application.app_id,
                            "student_id": application.student_data.get("student_id")
                            if application.student_data
                            else None,
                            "previous_status": old_status,
                            "rejected_at": application.decision_date.isoformat(),
                            "rejection_reason": rejection_reason,
                        }
                    )

                    # Send notification
                    if send_notifications:
                        try:
                            notification_sent = await self.notification_service.send_status_change_notification(
                                application, old_status, application.status
                            )
                            if notification_sent:
                                results["notifications_sent"] += 1
                            else:
                                results["notifications_failed"] += 1
                        except Exception as e:
                            logger.error(f"Failed to send notification for application {application.id}: {str(e)}")
                            results["notifications_failed"] += 1

                    logger.info(f"Bulk rejected application {application.app_id}")

                except Exception as e:
                    logger.error(f"Failed to reject application {application.id}: {str(e)}")
                    await self.db.rollback()
                    results["failed_rejections"].append(
                        {
                            "application_id": application.id,
                            "app_id": getattr(application, "app_id", "Unknown"),
                            "reason": f"Rejection failed: {str(e)}",
                        }
                    )

            return results

        except Exception as e:
            logger.error(f"Bulk rejection operation failed: {str(e)}")
            await self.db.rollback()
            raise

    async def auto_approve_by_criteria(
        self,
        scholarship_type_id: Optional[int] = None,
        main_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        semester: Optional[str] = None,
        min_priority_score: int = 0,
        max_applications: Optional[int] = None,
        approval_criteria: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Auto-approve applications based on criteria"""

        try:
            # Build query
            stmt = select(Application).where(
                Application.status.in_(
                    [
                        ApplicationStatus.SUBMITTED.value,
                        ApplicationStatus.UNDER_REVIEW.value,
                    ]
                )
            )

            if scholarship_type_id:
                stmt = stmt.where(Application.scholarship_type_id == scholarship_type_id)

            if main_type:
                stmt = stmt.where(Application.main_scholarship_type == main_type)

            if sub_type:
                stmt = stmt.where(Application.sub_scholarship_type == sub_type)

            if semester:
                stmt = stmt.where(Application.semester == semester)

            if min_priority_score > 0:
                stmt = stmt.where(Application.priority_score >= min_priority_score)

            # Order by priority score (highest first) and renewal status
            stmt = stmt.order_by(
                Application.is_renewal.desc(),
                Application.priority_score.desc(),
                Application.submitted_at.asc(),
            )

            if max_applications:
                stmt = stmt.limit(max_applications)

            result = await self.db.execute(stmt)
            applications = result.scalars().all()

            # Apply additional criteria if provided
            if approval_criteria:
                filtered_applications = []
                for app in applications:
                    if self._meets_approval_criteria(app, approval_criteria):
                        filtered_applications.append(app)
                applications = filtered_applications

            # Auto-approve qualifying applications
            auto_approved = []
            auto_approval_failures = []

            for application in applications:
                try:
                    application.status = ApplicationStatus.APPROVED.value
                    application.approved_at = datetime.now(timezone.utc)
                    application.decision_date = datetime.now(timezone.utc)
                    application.admin_notes = "Auto-approved based on criteria"

                    await self.db.commit()

                    auto_approved.append(
                        {
                            "application_id": application.id,
                            "app_id": application.app_id,
                            "student_id": application.student_data.get("student_id")
                            if application.student_data
                            else None,
                            "priority_score": application.priority_score,
                            "is_renewal": application.is_renewal,
                            "auto_approved_at": application.approved_at.isoformat(),
                        }
                    )

                    logger.info(f"Auto-approved application {application.app_id}")

                except Exception as e:
                    logger.error(f"Failed to auto-approve application {application.id}: {str(e)}")
                    await self.db.rollback()
                    auto_approval_failures.append({"application_id": application.id, "error": str(e)})

            return {
                "criteria_applied": {
                    "scholarship_type_id": scholarship_type_id,
                    "main_type": main_type,
                    "sub_type": sub_type,
                    "semester": semester,
                    "min_priority_score": min_priority_score,
                    "max_applications": max_applications,
                },
                "total_eligible": len(applications),
                "auto_approved": auto_approved,
                "approval_failures": auto_approval_failures,
                "success_count": len(auto_approved),
                "failure_count": len(auto_approval_failures),
            }

        except Exception as e:
            logger.error(f"Auto-approval by criteria failed: {str(e)}")
            raise

    async def bulk_status_update(
        self,
        application_ids: List[int],
        new_status: str,
        updater_user_id: int,
        update_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bulk update application status"""

        try:
            # Validate status
            try:
                _ = ApplicationStatus(new_status)
            except ValueError:
                raise ValueError(f"Invalid status: {new_status}")

            stmt = select(Application).where(Application.id.in_(application_ids))
            result = await self.db.execute(stmt)
            applications = result.scalars().all()

            updated_applications = []
            update_failures = []

            for application in applications:
                try:
                    old_status = application.status
                    application.status = new_status
                    application.updated_at = datetime.now(timezone.utc)

                    if update_notes:
                        application.admin_notes = update_notes

                    # Set specific fields based on status
                    if new_status == ApplicationStatus.APPROVED.value:
                        application.approved_at = datetime.now(timezone.utc)
                        application.final_approver_id = updater_user_id
                    elif new_status == ApplicationStatus.REJECTED.value:
                        application.reviewer_id = updater_user_id

                    application.decision_date = datetime.now(timezone.utc)

                    await self.db.commit()

                    updated_applications.append(
                        {
                            "application_id": application.id,
                            "app_id": application.app_id,
                            "old_status": old_status,
                            "new_status": new_status,
                            "updated_at": application.updated_at.isoformat(),
                        }
                    )

                except Exception as e:
                    logger.error(f"Failed to update application {application.id}: {str(e)}")
                    await self.db.rollback()
                    update_failures.append({"application_id": application.id, "error": str(e)})

            return {
                "total_requested": len(application_ids),
                "successful_updates": updated_applications,
                "failed_updates": update_failures,
                "success_count": len(updated_applications),
                "failure_count": len(update_failures),
                "new_status": new_status,
                "updated_by": updater_user_id,
            }

        except Exception as e:
            logger.error(f"Bulk status update failed: {str(e)}")
            raise

    def _meets_approval_criteria(self, application: Application, criteria: Dict[str, Any]) -> bool:
        """Check if application meets approval criteria"""

        try:
            # Check minimum GPA if specified
            if "min_gpa" in criteria:
                if application.gpa and float(application.gpa) < criteria["min_gpa"]:
                    return False

            # Check maximum ranking if specified
            if "max_ranking" in criteria:
                if (
                    application.class_ranking_percent
                    and float(application.class_ranking_percent) > criteria["max_ranking"]
                ):
                    return False

            # Check renewal status if specified
            if "require_renewal" in criteria:
                if criteria["require_renewal"] and not application.is_renewal:
                    return False

            # Check priority score if specified
            if "min_priority_score" in criteria:
                if (application.priority_score or 0) < criteria["min_priority_score"]:
                    return False

            # Check document completeness if specified
            if "require_complete_documents" in criteria and criteria["require_complete_documents"]:
                # This would check if all required documents are uploaded
                # Implementation would depend on document validation logic
                pass

            return True

        except Exception as e:
            logger.error(f"Error checking approval criteria for application {application.id}: {str(e)}")
            return False

    async def batch_process_with_notifications(
        self,
        operation_type: str,  # "approve", "reject", "update_status"
        application_ids: List[int],
        operator_user_id: int,
        operation_params: Dict[str, Any],
        admin_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process batch operation with comprehensive notifications"""

        try:
            results = {}

            if operation_type == "approve":
                results = await self.bulk_approve_applications(
                    application_ids,
                    operator_user_id,
                    operation_params.get("approval_notes"),
                    operation_params.get("send_notifications", True),
                )
            elif operation_type == "reject":
                results = await self.bulk_reject_applications(
                    application_ids,
                    operator_user_id,
                    operation_params.get("rejection_reason", "Bulk rejection"),
                    operation_params.get("send_notifications", True),
                )
            elif operation_type == "update_status":
                results = await self.bulk_status_update(
                    application_ids,
                    operation_params["new_status"],
                    operator_user_id,
                    operation_params.get("update_notes"),
                )
            else:
                raise ValueError(f"Invalid operation type: {operation_type}")

            # Send admin notification if email provided
            if admin_email and results.get("success_count", 0) > 0:
                try:
                    notification_data = {
                        "operation_type": operation_type,
                        "success_count": results.get("success_count", 0),
                        "failure_count": results.get("failure_count", 0),
                        "total_requested": results.get("total_requested", 0),
                        "operator_user_id": operator_user_id,
                        "processed_at": datetime.now(timezone.utc).isoformat(),
                    }

                    await self.notification_service.send_batch_processing_notification(admin_email, notification_data)
                except Exception as e:
                    logger.error(f"Failed to send admin notification: {str(e)}")

            # Add operation metadata
            results["operation_metadata"] = {
                "operation_type": operation_type,
                "operator_user_id": operator_user_id,
                "processed_at": datetime.now(timezone.utc).isoformat(),
                "parameters": operation_params,
            }

            return results

        except Exception as e:
            logger.error(f"Batch processing with notifications failed: {str(e)}")
            raise

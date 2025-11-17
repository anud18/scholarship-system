"""
Email notification service for scholarship management system
Handles automated notifications for application status changes, reminders, and deadlines
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.user import User

# Student model removed - student data now fetched from external API
from app.services.email_service import EmailService
from app.services.student_service import StudentService

logger = logging.getLogger(__name__)


class ScholarshipNotificationService:
    """Service for managing scholarship-related email notifications"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.email_service = EmailService()
        self.student_service = StudentService()

    async def send_application_submitted_notification(self, application: Application) -> bool:
        """Send notification when application is submitted"""
        try:
            # Get student data from external API and user information
            stmt = select(User).where(User.id == application.user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            if not user:
                logger.error("User not found for application %s", application.id)
                return False

            # Get student data from snapshot or external API
            student_data = application.student_data
            if not student_data:
                logger.error("Student data not found for application %s", application.id)
                return False

            student_name = student_data.get("std_cname", "N/A")

            # Prepare email content
            subject = f"Scholarship Application Submitted - {application.app_id}"

            # HTML template for application submission
            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #2c5282;">Scholarship Application Submitted Successfully</h2>

                <p>Dear {student_name},</p>

                <p>Your scholarship application has been successfully submitted and received for review.</p>

                <div style="background-color: #f7fafc; padding: 20px; border-left: 4px solid #4299e1; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #2d3748;">Application Details:</h3>
                    <ul style="margin: 10px 0;">
                        <li><strong>Application ID:</strong> {application.app_id}</li>
                        <li><strong>Scholarship Name:</strong> {application.scholarship_name or 'N/A'}</li>
                        <li><strong>Sub Type:</strong> {application.sub_scholarship_type or 'general'}</li>
                        <li><strong>Semester:</strong> {application.semester}</li>
                        <li><strong>Academic Year:</strong> {application.academic_year}</li>
                        <li><strong>Submission Date:</strong> {application.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if application.submitted_at else 'N/A'}</li>
                        <li><strong>Review Deadline:</strong> {application.review_deadline.strftime('%Y-%m-%d') if application.review_deadline else 'To be determined'}</li>
                    </ul>
                </div>

                {"<div style='background-color: #edf2f7; padding: 15px; border-radius: 5px; margin: 15px 0;'><strong>🔄 Renewal Application:</strong> This is a renewal application and will receive priority processing.</div>" if application.is_renewal else ""}

                <h3 style="color: #2d3748;">What happens next?</h3>
                <ol>
                    <li>Your application will be reviewed by our scholarship committee</li>
                    <li>You will receive updates on the application status via email</li>
                    <li>{"Renewal applications are processed with priority" if application.is_renewal else "Applications are processed in order of submission and priority"}</li>
                    <li>Final decisions will be communicated before the semester begins</li>
                </ol>

                <div style="background-color: #fef5e7; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>Important:</strong> Please keep this email for your records. Your application ID is <strong>{application.app_id}</strong></p>
                </div>

                <p>If you have any questions, please contact the scholarship office.</p>

                <p>Best regards,<br>
                Scholarship Management Team</p>

                <hr style="margin-top: 30px; border: none; border-top: 1px solid #e2e8f0;">
                <p style="font-size: 12px; color: #718096;">
                    This is an automated message. Please do not reply to this email.
                </p>
            </div>
            """

            # Send email
            await self.email_service.send_email(
                to=user.email,
                subject=subject,
                html_content=html_content,
                db=self.db,
            )

            logger.info(
                "Application submission notification sent to %s for application %s",
                user.email,
                application.app_id,
            )
            return True

        except Exception as exc:
            logger.exception(
                "Error sending application submission notification for application %s: %s",
                application.app_id,
                exc,
            )
            return False

    async def send_status_change_notification(self, application: Application, old_status: str, new_status: str) -> bool:
        """Send notification when application status changes"""
        try:
            stmt = select(User).where(User.id == application.user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()
            if not user:
                logger.error("User record missing for application %s", application.id)
                return False

            # Get student data from snapshot
            student_data = application.student_data
            if not student_data:
                logger.error("Student data not found for application %s", application.id)
                return False

            student_name = student_data.get("std_cname", "N/A")

            # Determine notification content based on status
            status_messages = {
                ApplicationStatus.under_review.value: {
                    "title": "Application Under Review",
                    "message": "Your scholarship application is now under review by our committee.",
                    "color": "#4299e1",
                },
                ApplicationStatus.approved.value: {
                    "title": "Application Approved! 🎉",
                    "message": "Congratulations! Your scholarship application has been approved.",
                    "color": "#48bb78",
                },
                ApplicationStatus.rejected.value: {
                    "title": "Application Decision",
                    "message": "We regret to inform you that your scholarship application was not approved this time.",
                    "color": "#f56565",
                },
                ApplicationStatus.returned.value: {
                    "title": "Application Returned for Revision",
                    "message": "Your application requires additional information or corrections.",
                    "color": "#ed8936",
                },
            }

            status_info = status_messages.get(
                new_status,
                {
                    "title": "Application Status Updated",
                    "message": f"Your application status has been updated to: {new_status}",
                    "color": "#4299e1",
                },
            )

            # Note: rejection_reason moved to ApplicationReview model
            # Get rejection reason from latest ApplicationReview if applicable
            rejection_reason = None
            if new_status == ApplicationStatus.rejected.value and application.reviews:
                # Get the latest review with a decision_reason
                for review in reversed(application.reviews):
                    if review.decision_reason:
                        rejection_reason = review.decision_reason
                        break

            subject = f"{status_info['title']} - {application.app_id}"

            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: {status_info['color']};">{status_info['title']}</h2>

                <p>Dear {student_name},</p>

                <p>{status_info['message']}</p>

                <div style="background-color: #f7fafc; padding: 20px; border-left: 4px solid {status_info['color']}; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #2d3748;">Application Information:</h3>
                    <ul style="margin: 10px 0;">
                        <li><strong>Application ID:</strong> {application.app_id}</li>
                        <li><strong>Scholarship Type:</strong> {application.scholarship_type}</li>
                        <li><strong>Previous Status:</strong> {old_status.replace('_', ' ').title()}</li>
                        <li><strong>Current Status:</strong> {new_status.replace('_', ' ').title()}</li>
                        <li><strong>Status Changed:</strong> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}</li>
                    </ul>
                </div>

                {"<div style='background-color: #f0fff4; padding: 15px; border-radius: 5px; margin: 15px 0; border: 1px solid #9ae6b4;'><p style='margin: 0; color: #22543d;'><strong>Next Steps:</strong> Please log in to your student portal to view full details and any required actions.</p></div>" if new_status in [ApplicationStatus.approved.value, ApplicationStatus.returned.value] else ""}

                {f"<div style='background-color: #fef5e7; padding: 15px; border-radius: 5px; margin: 15px 0;'><p style='margin: 0;'><strong>Rejection Reason:</strong> {rejection_reason}</p></div>" if new_status == ApplicationStatus.rejected.value and rejection_reason else ""}

                <p>For questions or concerns, please contact the scholarship office.</p>

                <p>Best regards,<br>
                Scholarship Management Team</p>
            </div>
            """

            await self.email_service.send_email(
                to=user.email,
                subject=subject,
                html_content=html_content,
                db=self.db,
            )

            logger.info(
                "Status change notification sent for application %s: %s -> %s",
                application.app_id,
                old_status,
                new_status,
            )
            return True

        except Exception as exc:
            logger.exception(
                "Error sending status change notification for application %s: %s",
                application.app_id,
                exc,
            )
            return False

    async def send_deadline_reminder_notifications(self, days_before: int = 7) -> Dict[str, int]:
        """Send reminder notifications for approaching deadlines"""
        try:
            cutoff_date = datetime.now(timezone.utc) + timedelta(days=days_before)

            # Find applications with approaching review deadlines
            stmt = select(Application).where(
                and_(
                    Application.review_deadline.isnot(None),
                    Application.review_deadline <= cutoff_date,
                    Application.status.in_(
                        [
                            ApplicationStatus.submitted.value,
                            ApplicationStatus.under_review.value,
                        ]
                    ),
                )
            )
            result = await self.db.execute(stmt)
            applications = result.scalars().all()

            sent_count = 0
            failed_count = 0

            for application in applications:
                try:
                    stmt = select(User).where(User.id == application.user_id)
                    result = await self.db.execute(stmt)
                    user = result.scalar_one_or_none()
                    if not user:
                        logger.error("Deadline reminder skipped: user not found for application %s", application.id)
                        failed_count += 1
                        continue

                    # Get student data from snapshot
                    student_data = application.student_data
                    if not student_data:
                        logger.error(
                            "Deadline reminder skipped: student data missing for application %s",
                            application.id,
                        )
                        failed_count += 1
                        continue

                    student_name = student_data.get("std_cname", "N/A")

                    days_remaining = (application.review_deadline - datetime.now(timezone.utc)).days

                    subject = f"Scholarship Review Deadline Reminder - {application.app_id}"

                    html_content = f"""
                    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                        <h2 style="color: #ed8936;">Review Deadline Reminder</h2>

                        <p>Dear {student_name},</p>

                        <p>This is a reminder that your scholarship application review deadline is approaching.</p>

                        <div style="background-color: #fef5e7; padding: 20px; border-left: 4px solid #ed8936; margin: 20px 0;">
                            <h3 style="margin-top: 0; color: #2d3748;">Deadline Information:</h3>
                            <ul style="margin: 10px 0;">
                                <li><strong>Application ID:</strong> {application.app_id}</li>
                                <li><strong>Scholarship Type:</strong> {application.scholarship_type}</li>
                                <li><strong>Review Deadline:</strong> {application.review_deadline.strftime('%Y-%m-%d')}</li>
                                <li><strong>Days Remaining:</strong> {days_remaining} days</li>
                                <li><strong>Current Status:</strong> {application.status.replace('_', ' ').title()}</li>
                            </ul>
                        </div>

                        <p>Your application is currently being processed. No action is required from your side at this time.</p>

                        <p>Best regards,<br>
                        Scholarship Management Team</p>
                    </div>
                    """

                    await self.email_service.send_email(
                        to=user.email,
                        subject=subject,
                        html_content=html_content,
                        db=self.db,
                    )

                    sent_count += 1

                except Exception as exc:
                    logger.exception(
                        "Error sending deadline reminder for application %s: %s",
                        application.id,
                        exc,
                    )
                    failed_count += 1

            logger.info(
                "Deadline reminders sent: %s successful, %s failed",
                sent_count,
                failed_count,
            )

            return {
                "sent": sent_count,
                "failed": failed_count,
                "total_applications": len(applications),
            }

        except Exception as exc:
            logger.exception("Error in deadline reminder batch process: %s", exc)
            return {"sent": 0, "failed": 0, "total_applications": 0}

    async def send_professor_review_request(self, application: Application, professor_user: User) -> bool:
        """Send email to professor requesting review"""
        try:
            # Get student data from snapshot
            student_data = application.student_data
            if not student_data:
                logger.error("Student data not found for application %s", application.id)
                return False

            student_name = student_data.get("std_cname", "N/A")
            student_no = student_data.get("std_stdcode", "N/A")

            subject = f"Professor Review Request - {application.app_id}"

            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #2c5282;">Professor Review Request</h2>

                <p>Dear Professor {professor_user.name or professor_user.email},</p>

                <p>You have been requested to review a scholarship application for one of your students.</p>

                <div style="background-color: #f7fafc; padding: 20px; border-left: 4px solid #4299e1; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #2d3748;">Application Details:</h3>
                    <ul style="margin: 10px 0;">
                        <li><strong>Student:</strong> {student_name}</li>
                        <li><strong>Student ID:</strong> {student_no}</li>
                        <li><strong>Application ID:</strong> {application.app_id}</li>
                        <li><strong>Scholarship Type:</strong> {application.scholarship_type}</li>
                        <li><strong>Application Status:</strong> {application.status.replace('_', ' ').title()}</li>
                        <li><strong>Submitted:</strong> {application.submitted_at.strftime('%Y-%m-%d') if application.submitted_at else 'N/A'}</li>
                    </ul>
                </div>

                <div style="background-color: #fef5e7; padding: 15px; border-radius: 5px; margin: 15px 0;">
                    <p style="margin: 0;"><strong>Action Required:</strong> Please log in to the system to complete your review and recommendation.</p>
                </div>

                <p>Your review is important for the scholarship evaluation process. Please complete your review at your earliest convenience.</p>

                <p>Thank you for your time and expertise.</p>

                <p>Best regards,<br>
                Scholarship Management Team</p>
            </div>
            """

            await self.email_service.send_email(
                to=professor_user.email,
                subject=subject,
                html_content=html_content,
                db=self.db,
            )

            logger.info(
                "Professor review request sent to %s for application %s",
                professor_user.email,
                application.app_id,
            )
            return True

        except Exception as exc:
            logger.exception(
                "Error sending professor review request for application %s: %s",
                application.app_id,
                exc,
            )
            return False

    async def send_batch_processing_notification(self, admin_email: str, processing_results: Dict[str, Any]) -> bool:
        """Send notification to admin about batch processing results"""
        try:
            subject = f"Scholarship Batch Processing Complete - {processing_results.get('semester', 'N/A')}"

            html_content = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #2c5282;">Batch Processing Complete</h2>

                <p>The scholarship application batch processing has been completed.</p>

                <div style="background-color: #f7fafc; padding: 20px; border-left: 4px solid #4299e1; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #2d3748;">Processing Results:</h3>
                    <ul style="margin: 10px 0;">
                        <li><strong>Semester:</strong> {processing_results.get('semester', 'N/A')}</li>
                        <li><strong>Total Processed:</strong> {processing_results.get('processed', 0)}</li>
                        <li><strong>Approved:</strong> {processing_results.get('approved', 0)}</li>
                        <li><strong>Rejected:</strong> {processing_results.get('rejected', 0)}</li>
                        <li><strong>Main Type:</strong> {processing_results.get('main_type', 'N/A')}</li>
                        <li><strong>Sub Type:</strong> {processing_results.get('sub_type', 'N/A')}</li>
                    </ul>
                </div>

                <p>All affected students have been notified of their application status via email.</p>

                <p>Best regards,<br>
                Scholarship Management System</p>
            </div>
            """

            await self.email_service.send_email(
                to=admin_email,
                subject=subject,
                html_content=html_content,
                db=self.db,
            )

            logger.info("Batch processing notification sent to %s", admin_email)
            return True

        except Exception as exc:
            logger.exception("Error sending batch processing notification to %s: %s", admin_email, exc)
            return False

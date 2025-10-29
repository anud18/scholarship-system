"""
Email management service for handling email history and scheduled emails
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.email_management import EmailCategory, EmailHistory, EmailStatus, ScheduledEmail, ScheduleStatus
from app.models.user import AdminScholarship, User
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)


class EmailManagementService:
    """Service for managing email history and scheduled emails with permission-based access"""

    def __init__(self):
        self.email_service = EmailService()

    async def get_email_history(
        self,
        db: AsyncSession,
        user: User,
        skip: int = 0,
        limit: int = 100,
        email_category: Optional[EmailCategory] = None,
        status: Optional[EmailStatus] = None,
        scholarship_type_id: Optional[int] = None,
        recipient_email: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> tuple[List[EmailHistory], int]:
        """
        Get email history with permission-based filtering

        Args:
            db: Database session
            user: Current user (for permission filtering)
            skip: Pagination offset
            limit: Pagination limit
            email_category: Filter by email category
            status: Filter by email status
            scholarship_type_id: Filter by scholarship type
            recipient_email: Filter by recipient email
            date_from: Filter emails sent after this date
            date_to: Filter emails sent before this date

        Returns:
            Tuple of (email_history_list, total_count)
        """
        # Base query
        query = select(EmailHistory).options(
            selectinload(EmailHistory.application),
            selectinload(EmailHistory.scholarship_type),
            selectinload(EmailHistory.sent_by),
            selectinload(EmailHistory.template),
        )

        # Permission-based filtering
        if not user.is_super_admin():
            # Regular admins only see emails for their assigned scholarships
            admin_scholarships_query = select(AdminScholarship.scholarship_id).where(
                AdminScholarship.admin_id == user.id
            )
            admin_scholarship_ids = (await db.execute(admin_scholarships_query)).scalars().all()

            if not admin_scholarship_ids:
                # Admin has no scholarship assignments, return empty result
                return [], 0

            query = query.where(
                or_(
                    EmailHistory.scholarship_type_id.in_(admin_scholarship_ids),
                    EmailHistory.scholarship_type_id.is_(None),  # Include system emails
                )
            )

        # Apply filters
        conditions = []

        if email_category:
            conditions.append(EmailHistory.email_category == email_category)

        if status:
            conditions.append(EmailHistory.status == status)

        if scholarship_type_id:
            conditions.append(EmailHistory.scholarship_type_id == scholarship_type_id)

        if recipient_email:
            conditions.append(EmailHistory.recipient_email.ilike(f"%{recipient_email}%"))

        if date_from:
            conditions.append(EmailHistory.sent_at >= date_from)

        if date_to:
            conditions.append(EmailHistory.sent_at <= date_to)

        if conditions:
            query = query.where(and_(*conditions))

        # Get total count
        count_query = select(EmailHistory.id)
        if not user.is_super_admin():
            if admin_scholarship_ids:
                count_query = count_query.where(
                    or_(
                        EmailHistory.scholarship_type_id.in_(admin_scholarship_ids),
                        EmailHistory.scholarship_type_id.is_(None),
                    )
                )
            else:
                count_query = count_query.where(False)  # No results for admin with no assignments

        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_count = len((await db.execute(count_query)).scalars().all())

        # Apply pagination and ordering
        query = query.order_by(desc(EmailHistory.sent_at)).offset(skip).limit(limit)

        result = await db.execute(query)
        email_history = result.scalars().all()

        return list(email_history), total_count

    async def get_scheduled_emails(
        self,
        db: AsyncSession,
        user: User,
        skip: int = 0,
        limit: int = 100,
        status: Optional[ScheduleStatus] = None,
        scholarship_type_id: Optional[int] = None,
        requires_approval: Optional[bool] = None,
        email_category: Optional[EmailCategory] = None,
        scheduled_from: Optional[datetime] = None,
        scheduled_to: Optional[datetime] = None,
    ) -> tuple[List[ScheduledEmail], int]:
        """
        Get scheduled emails with permission-based filtering

        Args:
            db: Database session
            user: Current user (for permission filtering)
            skip: Pagination offset
            limit: Pagination limit
            status: Filter by schedule status
            scholarship_type_id: Filter by scholarship type
            requires_approval: Filter by approval requirement
            email_category: Filter by email category
            scheduled_from: Filter emails scheduled after this date
            scheduled_to: Filter emails scheduled before this date

        Returns:
            Tuple of (scheduled_emails_list, total_count)
        """
        # Base query
        query = select(ScheduledEmail).options(
            selectinload(ScheduledEmail.application),
            selectinload(ScheduledEmail.scholarship_type),
            selectinload(ScheduledEmail.created_by),
            selectinload(ScheduledEmail.approved_by),
            selectinload(ScheduledEmail.template),
        )

        # Permission-based filtering
        if not user.is_super_admin():
            # Regular admins only see emails for their assigned scholarships
            admin_scholarships_query = select(AdminScholarship.scholarship_id).where(
                AdminScholarship.admin_id == user.id
            )
            admin_scholarship_ids = (await db.execute(admin_scholarships_query)).scalars().all()

            if not admin_scholarship_ids:
                # Admin has no scholarship assignments, return empty result
                return [], 0

            query = query.where(
                or_(
                    ScheduledEmail.scholarship_type_id.in_(admin_scholarship_ids),
                    ScheduledEmail.scholarship_type_id.is_(None),  # Include system emails
                    ScheduledEmail.created_by_user_id == user.id,  # Include emails created by this admin
                )
            )

        # Apply filters
        conditions = []

        if status:
            conditions.append(ScheduledEmail.status == status)

        if scholarship_type_id:
            conditions.append(ScheduledEmail.scholarship_type_id == scholarship_type_id)

        if requires_approval is not None:
            conditions.append(ScheduledEmail.requires_approval == requires_approval)

        if email_category:
            conditions.append(ScheduledEmail.email_category == email_category)

        if scheduled_from:
            conditions.append(ScheduledEmail.scheduled_for >= scheduled_from)

        if scheduled_to:
            conditions.append(ScheduledEmail.scheduled_for <= scheduled_to)

        if conditions:
            query = query.where(and_(*conditions))

        # Get total count
        count_query = select(ScheduledEmail.id)
        if not user.is_super_admin():
            if admin_scholarship_ids:
                count_query = count_query.where(
                    or_(
                        ScheduledEmail.scholarship_type_id.in_(admin_scholarship_ids),
                        ScheduledEmail.scholarship_type_id.is_(None),
                        ScheduledEmail.created_by_user_id == user.id,
                    )
                )
            else:
                count_query = count_query.where(ScheduledEmail.created_by_user_id == user.id)

        if conditions:
            count_query = count_query.where(and_(*conditions))

        total_count = len((await db.execute(count_query)).scalars().all())

        # Apply pagination and ordering
        query = query.order_by(desc(ScheduledEmail.scheduled_for)).offset(skip).limit(limit)

        result = await db.execute(query)
        scheduled_emails = result.scalars().all()

        return list(scheduled_emails), total_count

    async def get_due_scheduled_emails(self, db: AsyncSession, limit: int = 50) -> List[ScheduledEmail]:
        """
        Get scheduled emails that are due to be sent

        Args:
            db: Database session
            limit: Maximum number of emails to return

        Returns:
            List of due scheduled emails
        """
        now = datetime.now(timezone.utc)

        query = (
            select(ScheduledEmail)
            .options(
                selectinload(ScheduledEmail.application),
                selectinload(ScheduledEmail.scholarship_type),
                selectinload(ScheduledEmail.template),
            )
            .where(
                and_(
                    ScheduledEmail.scheduled_for <= now,
                    ScheduledEmail.status == ScheduleStatus.pending,
                    or_(
                        ScheduledEmail.requires_approval.is_(False),
                        and_(
                            ScheduledEmail.requires_approval.is_(True),
                            ScheduledEmail.approved_by_user_id.is_not(None),
                        ),
                    ),
                )
            )
            .order_by(asc(ScheduledEmail.priority), asc(ScheduledEmail.scheduled_for))
            .limit(limit)
        )

        result = await db.execute(query)
        return list(result.scalars().all())

    async def approve_scheduled_email(
        self,
        db: AsyncSession,
        email_id: int,
        approved_by_user_id: int,
        notes: Optional[str] = None,
    ) -> ScheduledEmail:
        """
        Approve a scheduled email

        Args:
            db: Database session
            email_id: ID of scheduled email to approve
            approved_by_user_id: ID of user approving the email
            notes: Optional approval notes

        Returns:
            Updated scheduled email

        Raises:
            ValueError: If email not found or already processed
        """
        query = select(ScheduledEmail).where(ScheduledEmail.id == email_id)
        result = await db.execute(query)
        scheduled_email = result.scalar_one_or_none()

        if not scheduled_email:
            raise ValueError(f"Scheduled email with ID {email_id} not found")

        if scheduled_email.status != ScheduleStatus.pending:
            raise ValueError(f"Cannot approve email with status {scheduled_email.status}")

        if not scheduled_email.requires_approval:
            raise ValueError("Email does not require approval")

        if scheduled_email.approved_by_user_id:
            raise ValueError("Email is already approved")

        scheduled_email.approve(approved_by_user_id, notes)
        await db.commit()
        await db.refresh(scheduled_email)

        logger.info(f"Scheduled email {email_id} approved by user {approved_by_user_id}")
        return scheduled_email

    async def cancel_scheduled_email(self, db: AsyncSession, email_id: int) -> ScheduledEmail:
        """
        Cancel a scheduled email

        Args:
            db: Database session
            email_id: ID of scheduled email to cancel

        Returns:
            Updated scheduled email

        Raises:
            ValueError: If email not found or already processed
        """
        query = select(ScheduledEmail).where(ScheduledEmail.id == email_id)
        result = await db.execute(query)
        scheduled_email = result.scalar_one_or_none()

        if not scheduled_email:
            raise ValueError(f"Scheduled email with ID {email_id} not found")

        if scheduled_email.status != ScheduleStatus.pending:
            raise ValueError(f"Cannot cancel email with status {scheduled_email.status}")

        scheduled_email.cancel()
        await db.commit()
        await db.refresh(scheduled_email)

        logger.info(f"Scheduled email {email_id} cancelled")
        return scheduled_email

    async def update_scheduled_email(
        self,
        db: AsyncSession,
        email_id: int,
        subject: Optional[str] = None,
        body: Optional[str] = None,
    ) -> ScheduledEmail:
        """
        Update a scheduled email's subject and body

        Args:
            db: Database session
            email_id: ID of scheduled email to update
            subject: New subject (optional)
            body: New body (optional)

        Returns:
            Updated scheduled email

        Raises:
            ValueError: If email not found or already processed
        """
        query = select(ScheduledEmail).where(ScheduledEmail.id == email_id)
        result = await db.execute(query)
        scheduled_email = result.scalar_one_or_none()

        if not scheduled_email:
            raise ValueError(f"Scheduled email with ID {email_id} not found")

        if scheduled_email.status != ScheduleStatus.pending:
            raise ValueError(f"Cannot update email with status {scheduled_email.status}")

        # Update fields if provided
        if subject is not None:
            scheduled_email.subject = subject
        if body is not None:
            scheduled_email.body = body

        await db.commit()
        await db.refresh(scheduled_email)

        logger.info(f"Scheduled email {email_id} updated")
        return scheduled_email

    async def process_due_emails(self, db: AsyncSession, batch_size: int = 10) -> Dict[str, int]:
        """
        Process due scheduled emails by sending them

        Args:
            db: Database session
            batch_size: Maximum number of emails to process in one batch

        Returns:
            Dictionary with processing statistics
        """
        due_emails = await self.get_due_scheduled_emails(db, limit=batch_size)

        stats = {"processed": 0, "sent": 0, "failed": 0, "skipped": 0}

        for scheduled_email in due_emails:
            stats["processed"] += 1

            try:
                # Prepare email data
                cc_emails = None
                bcc_emails = None

                if scheduled_email.cc_emails:
                    import json

                    cc_emails = json.loads(scheduled_email.cc_emails)

                if scheduled_email.bcc_emails:
                    import json

                    bcc_emails = json.loads(scheduled_email.bcc_emails)

                # Prepare metadata
                metadata = {
                    "email_category": scheduled_email.email_category,
                    "application_id": scheduled_email.application_id,
                    "scholarship_type_id": scheduled_email.scholarship_type_id,
                    "sent_by_system": True,
                    "template_key": scheduled_email.template_key,
                }

                # Send the email
                await self.email_service.send_email(
                    to=scheduled_email.recipient_email,
                    subject=scheduled_email.subject,
                    body=scheduled_email.body,
                    cc=cc_emails,
                    bcc=bcc_emails,
                    db=db,
                    **metadata,
                )

                # Mark as sent
                scheduled_email.mark_as_sent()
                stats["sent"] += 1

                logger.info(
                    f"Successfully sent scheduled email {scheduled_email.id} to {scheduled_email.recipient_email}"
                )

            except Exception as e:
                # Mark as failed
                scheduled_email.mark_as_failed(str(e))
                stats["failed"] += 1

                logger.error(f"Failed to send scheduled email {scheduled_email.id}: {e}")

            # Commit changes for this email
            await db.commit()

        logger.info(f"Processed {stats['processed']} emails: {stats['sent']} sent, {stats['failed']} failed")
        return stats

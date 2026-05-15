"""
Bank Verification Task Service

Handles async batch bank verification tasks with progress tracking.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.bank_verification_task import BankVerificationTask, BankVerificationTaskStatus
from app.models.student_bank_account import StudentBankAccount
from app.services.bank_verification_service import BankVerificationService

logger = logging.getLogger(__name__)


class BankVerificationTaskService:
    """Service for managing async bank verification tasks"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_task(
        self,
        application_ids: List[int],
        created_by_user_id: int,
    ) -> BankVerificationTask:
        """
        Create a new bank verification task

        Args:
            application_ids: List of application IDs to verify
            created_by_user_id: User ID who created the task

        Returns:
            Created BankVerificationTask
        """
        task_id = str(uuid.uuid4())

        task = BankVerificationTask(
            task_id=task_id,
            status=BankVerificationTaskStatus.pending,
            application_ids=application_ids,
            total_count=len(application_ids),
            created_by_user_id=created_by_user_id,
        )

        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)

        logger.info(f"Created bank verification task {task_id} for {len(application_ids)} applications")

        return task

    async def get_task(self, task_id: str) -> Optional[BankVerificationTask]:
        """
        Get task by task_id

        Args:
            task_id: UUID string of the task

        Returns:
            BankVerificationTask or None if not found
        """
        stmt = select(BankVerificationTask).where(BankVerificationTask.task_id == task_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        status: Optional[BankVerificationTaskStatus] = None,
        created_by_user_id: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[BankVerificationTask]:
        """
        List tasks with optional filtering

        Args:
            status: Filter by task status
            created_by_user_id: Filter by creator
            limit: Maximum number of results
            offset: Pagination offset

        Returns:
            List of BankVerificationTasks
        """
        stmt = select(BankVerificationTask).order_by(BankVerificationTask.created_at.desc())

        if status:
            stmt = stmt.where(BankVerificationTask.status == status)
        if created_by_user_id:
            stmt = stmt.where(BankVerificationTask.created_by_user_id == created_by_user_id)

        stmt = stmt.limit(limit).offset(offset)

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def update_task_progress(
        self,
        task_id: str,
        processed_count: int,
        verified_count: int = 0,
        needs_review_count: int = 0,
        failed_count: int = 0,
        skipped_count: int = 0,
        results: Optional[Dict] = None,
    ) -> None:
        """
        Update task progress

        Args:
            task_id: Task UUID
            processed_count: Number of applications processed
            verified_count: Number verified
            needs_review_count: Number needing review
            failed_count: Number failed
            skipped_count: Number skipped
            results: Detailed results dict
        """
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.processed_count = processed_count
        task.verified_count = verified_count
        task.needs_review_count = needs_review_count
        task.failed_count = failed_count
        task.skipped_count = skipped_count

        if results:
            task.results = results

        await self.db.commit()

    async def mark_task_as_processing(self, task_id: str) -> None:
        """Mark task as processing and set started_at"""
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = BankVerificationTaskStatus.processing
        task.started_at = datetime.now(timezone.utc)

        await self.db.commit()
        logger.info(f"Task {task_id} started processing")

    async def mark_task_as_completed(self, task_id: str) -> None:
        """Mark task as completed and set completed_at"""
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = BankVerificationTaskStatus.completed
        task.completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        logger.info(f"Task {task_id} completed successfully")

    async def mark_task_as_failed(self, task_id: str, error_message: str) -> None:
        """Mark task as failed with error message"""
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = BankVerificationTaskStatus.failed
        task.error_message = error_message
        task.completed_at = datetime.now(timezone.utc)

        await self.db.commit()
        logger.error(f"Task {task_id} failed: {error_message}")

    async def process_batch_verification_task(self, task_id: str) -> None:
        """
        Process batch verification task in background

        This method runs the actual verification for all applications in the task.

        Args:
            task_id: Task UUID to process
        """
        try:
            # Mark as processing
            await self.mark_task_as_processing(task_id)

            task = await self.get_task(task_id)
            if not task:
                raise ValueError(f"Task {task_id} not found")

            application_ids = task.application_ids
            verification_service = BankVerificationService(self.db)

            # Track results
            results = {}
            verified_count = 0
            needs_review_count = 0
            failed_count = 0
            skipped_count = 0

            # Process each application
            for idx, app_id in enumerate(application_ids):
                try:
                    # Skip if this application's bank account is already an
                    # active verified StudentBankAccount for the same user.
                    # Issue #217 / CLAUDE.md §7 — avoids re-verifying accounts
                    # that have already been verified by another application.
                    if await self._application_uses_verified_account(app_id, verification_service):
                        logger.info(
                            "Skipping bank verification for application %s: already-verified account",
                            app_id,
                        )
                        skipped_count += 1
                        results[app_id] = {
                            "status": "skipped",
                            "success": True,
                            "reason": "Bank account already verified",
                        }
                        # Still advance progress for skipped items
                        await self.update_task_progress(
                            task_id=task_id,
                            processed_count=idx + 1,
                            verified_count=verified_count,
                            needs_review_count=needs_review_count,
                            failed_count=failed_count,
                            skipped_count=skipped_count,
                            results=results,
                        )
                        continue

                    # Perform verification
                    result = await verification_service.verify_bank_account(app_id)

                    # Categorize result
                    if result.get("success"):
                        status = result.get("verification_status")
                        if status == "verified":
                            verified_count += 1
                        elif status in ["needs_manual_review", "likely_verified"]:
                            needs_review_count += 1
                        else:
                            failed_count += 1

                        results[app_id] = {
                            "status": status,
                            "success": True,
                            "account_number_status": result.get("account_number_status"),
                            "account_holder_status": result.get("account_holder_status"),
                            "average_confidence": result.get("average_confidence"),
                        }
                    else:
                        failed_count += 1
                        results[app_id] = {
                            "status": "error",
                            "success": False,
                            "error": result.get("error"),
                        }

                except Exception as e:
                    logger.exception(f"Error verifying application {app_id}")
                    failed_count += 1
                    results[app_id] = {
                        "status": "error",
                        "success": False,
                        "error": str(e),
                    }

                # Update progress
                await self.update_task_progress(
                    task_id=task_id,
                    processed_count=idx + 1,
                    verified_count=verified_count,
                    needs_review_count=needs_review_count,
                    failed_count=failed_count,
                    skipped_count=skipped_count,
                    results=results,
                )

                # Small delay to avoid overwhelming the system
                await asyncio.sleep(0.1)

            # Mark as completed
            await self.mark_task_as_completed(task_id)

            logger.info(
                f"Task {task_id} completed: {verified_count} verified, "
                f"{needs_review_count} need review, {failed_count} failed, {skipped_count} skipped"
            )

        except Exception as e:
            logger.exception(f"Fatal error processing task {task_id}")
            await self.mark_task_as_failed(task_id, str(e))
            raise

    async def _application_uses_verified_account(
        self,
        application_id: int,
        verification_service: BankVerificationService,
    ) -> bool:
        """
        Return True if this application's submitted bank account number matches
        an active, verified StudentBankAccount for the same user.

        Used by `process_batch_verification_task` to short-circuit
        re-verification of accounts that the student has already had verified
        through a previous application. Safe-by-default: any error (missing
        application, unreadable form data, no account number) returns False so
        the normal verification path runs.

        Issue #217.
        """
        try:
            application = await self.db.get(Application, application_id)
            if application is None or not application.submitted_form_data:
                return False

            bank_fields = verification_service.extract_bank_fields_from_application(application)
            account_number = bank_fields.get("account_number")
            if not account_number:
                return False

            normalized = verification_service.normalize_account_number(account_number)
            if not normalized:
                return False

            stmt = select(StudentBankAccount.id).where(
                and_(
                    StudentBankAccount.user_id == application.user_id,
                    StudentBankAccount.account_number == normalized,
                    StudentBankAccount.verification_status == "verified",
                    StudentBankAccount.is_active.is_(True),
                )
            )
            result = await self.db.execute(stmt)
            return result.scalar_one_or_none() is not None
        except Exception as exc:  # noqa: BLE001
            # Fall through to normal verification on any lookup error — this is
            # an optimisation, not a correctness boundary, so we don't want it
            # to mask real verification work.
            logger.warning(
                "Skip-check failed for application %s; falling through to full verification: %s",
                application_id,
                exc,
            )
            return False

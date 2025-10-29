"""
Bank Verification Task Model

Tracks async batch bank verification tasks for monitoring progress and results.
"""

import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.college_review import get_json_type


class BankVerificationTaskStatus(enum.Enum):
    """Bank verification task status"""

    pending = "pending"  # Task created, not started
    processing = "processing"  # Task is running
    completed = "completed"  # Task completed successfully
    failed = "failed"  # Task failed with errors
    cancelled = "cancelled"  # Task was cancelled


class BankVerificationTask(Base):
    """
    Async bank verification task tracking

    Stores information about batch verification tasks including progress and results.
    """

    __tablename__ = "bank_verification_tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID

    # Task status
    status = Column(
        Enum(BankVerificationTaskStatus, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=BankVerificationTaskStatus.pending,
    )

    # Target applications
    application_ids = Column(get_json_type(), nullable=False)  # List of application IDs to verify

    # Progress counters
    total_count = Column(Integer, nullable=False, default=0)
    processed_count = Column(Integer, nullable=False, default=0)
    verified_count = Column(Integer, nullable=False, default=0)  # Auto verified (high confidence)
    needs_review_count = Column(Integer, nullable=False, default=0)  # Needs manual review
    failed_count = Column(Integer, nullable=False, default=0)  # Verification failed
    skipped_count = Column(Integer, nullable=False, default=0)  # Using verified account

    # Detailed results
    results = Column(get_json_type(), nullable=True)  # {app_id: {status, details, ...}}

    # Task metadata
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    def __repr__(self):
        return (
            f"<BankVerificationTask(id={self.id}, task_id={self.task_id}, "
            f"status={self.status}, progress={self.processed_count}/{self.total_count})>"
        )

    @property
    def is_completed(self) -> bool:
        """Check if task is completed"""
        return self.status in [BankVerificationTaskStatus.completed, BankVerificationTaskStatus.failed]

    @property
    def is_running(self) -> bool:
        """Check if task is currently running"""
        return self.status == BankVerificationTaskStatus.processing

    @property
    def progress_percentage(self) -> float:
        """Calculate progress percentage"""
        if self.total_count == 0:
            return 0.0
        return (self.processed_count / self.total_count) * 100

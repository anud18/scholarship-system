"""
Student Bank Account Model

Tracks verified bank account information for students.
When an administrator verifies a student's bank account through manual review,
the verified account is saved here so the student can see the verification status
in future applications.
"""

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class StudentBankAccount(Base):
    """
    Student's verified bank account information

    This table stores bank accounts that have been verified by administrators.
    Students can see their verified accounts when filling out new applications.
    """

    __tablename__ = "student_bank_accounts"

    # Ensure one user can only have one active account number at a time
    __table_args__ = (UniqueConstraint("user_id", "account_number", name="uq_student_bank_account_user_number"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Bank account information
    account_number = Column(String(20), nullable=False, index=True)  # 郵局帳號
    account_holder = Column(String(100), nullable=False)  # 戶名

    # Verification information
    verification_status = Column(String(20), nullable=False, default="verified")  # verified, failed, pending, revoked
    verified_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    verified_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verification_source_application_id = Column(
        Integer, ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )

    # Activity status
    is_active = Column(Boolean, default=True, nullable=False)  # Whether this is the student's current verified account

    # Additional information
    verification_notes = Column(String(500))  # Notes from verification process

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    user = relationship("User", foreign_keys=[user_id], back_populates="verified_bank_accounts")
    verified_by = relationship("User", foreign_keys=[verified_by_user_id])
    verification_source_application = relationship("Application")

    def __repr__(self):
        return (
            f"<StudentBankAccount(id={self.id}, user_id={self.user_id}, "
            f"account_number={self.account_number}, status={self.verification_status})>"
        )

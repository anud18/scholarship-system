"""
Document Request Model

Tracks requests for missing or additional documents from students
"""

import enum
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.application import Application
    from app.models.user import User


class DocumentRequestStatus(enum.Enum):
    """Document request status enum"""

    pending = "pending"  # Request sent, waiting for student response
    fulfilled = "fulfilled"  # Student has uploaded requested documents
    cancelled = "cancelled"  # Request was cancelled by reviewer


class DocumentRequest(Base):
    """
    Document Request Model

    Tracks requests from reviewers to students for missing or additional documents
    """

    __tablename__ = "document_requests"

    id = Column(Integer, primary_key=True, index=True)

    # Application reference
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, index=True)

    # Requester info
    requested_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    requested_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Request details
    requested_documents = Column(
        JSONB,
        nullable=False,
        comment="List of document types/categories needed, e.g., ['transcript', 'recommendation_letter', 'research_plan']",
    )
    reason = Column(Text, nullable=False, comment="Why these documents are needed")
    notes = Column(Text, nullable=True, comment="Additional notes or instructions")

    # Status tracking
    # Use String instead of Enum to match migration definition (with CHECK constraint)
    status = Column(
        String(20),
        nullable=False,
        default=DocumentRequestStatus.pending.value,
        index=True,
    )
    fulfilled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    application = relationship("Application", back_populates="document_requests")
    requested_by = relationship("User", foreign_keys=[requested_by_id])
    cancelled_by = relationship("User", foreign_keys=[cancelled_by_id])

    def __repr__(self):
        return f"<DocumentRequest(id={self.id}, application_id={self.application_id}, status={self.status})>"

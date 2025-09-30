"""
Professor-Student relationship model for access control
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class ProfessorStudentRelationship(Base):
    """
    Professor-Student relationship model for access control

    This model defines which professors can access which students' data,
    including scholarship applications, documents, and other academic records.
    """

    __tablename__ = "professor_student_relationships"

    id = Column(Integer, primary_key=True, index=True)
    professor_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    student_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Relationship metadata
    relationship_type = Column(String(50), nullable=False)  # advisor, co_advisor, committee_member, supervisor
    department = Column(String(100))  # Department where relationship exists
    academic_year = Column(Integer)  # Academic year when relationship started
    semester = Column(String(20))  # Semester when relationship started

    # Status and permissions
    is_active = Column(Boolean, default=True, nullable=False)
    can_view_applications = Column(Boolean, default=True, nullable=False)
    can_upload_documents = Column(Boolean, default=False, nullable=False)
    can_review_applications = Column(Boolean, default=False, nullable=False)

    # Audit fields
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )
    created_by = Column(Integer, ForeignKey("users.id"))
    notes = Column(String(500))  # Administrative notes about the relationship

    # Relationships
    professor = relationship("User", foreign_keys=[professor_id], lazy="select")
    student = relationship("User", foreign_keys=[student_id], lazy="select")
    creator = relationship("User", foreign_keys=[created_by], lazy="select")

    # Constraints
    __table_args__ = (UniqueConstraint("professor_id", "student_id", "relationship_type", name="uq_prof_student_type"),)

    def __repr__(self):
        return (
            f"<ProfessorStudentRelationship(id={self.id}, "
            f"professor_id={self.professor_id}, student_id={self.student_id}, "
            f"type={self.relationship_type}, active={self.is_active})>"
        )

    @property
    def is_advisor(self) -> bool:
        """Check if this is an advisor relationship"""
        return self.relationship_type in ["advisor", "co_advisor"]

    @property
    def can_access_sensitive_data(self) -> bool:
        """Check if professor can access sensitive student data"""
        return self.is_active and self.relationship_type in ["advisor", "co_advisor", "supervisor"]

    def has_permission(self, permission: str) -> bool:
        """Check if relationship has specific permission"""
        if not self.is_active:
            return False

        permission_map = {
            "view_applications": self.can_view_applications,
            "upload_documents": self.can_upload_documents,
            "review_applications": self.can_review_applications,
        }

        return permission_map.get(permission, False)

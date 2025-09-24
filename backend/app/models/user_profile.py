"""
User Profile model for storing editable user information
Separate from core User model which contains API-sourced data
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class UserProfile(Base):
    """User profile with editable information"""

    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # Bank account information (simplified)
    bank_code = Column(String(20))
    account_number = Column(String(50))
    bank_document_photo_url = Column(
        String(500)
    )  # URL or file path to bank document photo
    bank_document_object_name = Column(
        String(500)
    )  # MinIO object name for the bank document

    # Advisor information (simplified)
    advisor_name = Column(String(100))  # Professor name
    advisor_email = Column(String(100))
    advisor_nycu_id = Column(String(20))  # NYCU ID of the advisor

    # Personal preferences and notes
    preferred_language = Column(String(10), default="zh-TW")  # zh-TW, en-US

    # Custom fields for future extensibility
    custom_fields = Column(JSON)

    # Privacy settings
    privacy_settings = Column(JSON)  # What information is visible to others

    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    # Relationship
    user = relationship("User", backref="profile")

    def __repr__(self):
        return f"<UserProfile(user_id={self.user_id}, advisor={self.advisor_email})>"

    @property
    def has_complete_bank_info(self) -> bool:
        """Check if user has complete bank account information"""
        return all([self.bank_code, self.account_number])

    @property
    def has_advisor_info(self) -> bool:
        """Check if user has advisor information"""
        return all([self.advisor_name, self.advisor_email, self.advisor_nycu_id])

    @property
    def profile_completion_percentage(self) -> int:
        """Calculate profile completion percentage"""
        # Count completed sections instead of individual fields
        completed_sections = 0
        total_sections = 2

        # Bank info section (both fields required)
        if self.has_complete_bank_info:
            completed_sections += 1

        # Advisor info section (all three fields required)
        if self.has_advisor_info:
            completed_sections += 1

        return int((completed_sections / total_sections) * 100)


class UserProfileHistory(Base):
    """History of user profile changes for audit purposes"""

    __tablename__ = "user_profile_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    field_name = Column(String(100), nullable=False)
    old_value = Column(Text)
    new_value = Column(Text)
    change_reason = Column(String(255))  # User-provided reason for change
    changed_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    ip_address = Column(String(45))  # IPv4 or IPv6
    user_agent = Column(String(500))

    # Relationship
    user = relationship("User")

    def __repr__(self):
        return f"<UserProfileHistory(user_id={self.user_id}, field={self.field_name}, changed_at={self.changed_at})>"

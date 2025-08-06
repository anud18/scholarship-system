"""
User Profile model for storing editable user information
Separate from core User model which contains API-sourced data
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timezone

from app.db.base_class import Base


class UserProfile(Base):
    """User profile with editable information"""
    __tablename__ = "user_profiles"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    
    # Bank account information (simplified)
    bank_code = Column(String(20))
    account_number = Column(String(50))
    bank_document_photo_url = Column(String(500))  # URL or file path to bank document photo
    
    # Advisor information (simplified)
    advisor_email = Column(String(100))
    advisor_nycu_id = Column(String(20))  # NYCU ID of the advisor
    
    # Personal preferences and notes
    preferred_language = Column(String(10), default="zh-TW")  # zh-TW, en-US
    bio = Column(Text)  # Personal bio/description
    interests = Column(Text)  # Academic interests, hobbies, etc.
    
    # Social media links
    social_links = Column(JSON)  # {"linkedin": "url", "github": "url", etc.}
    
    # Custom fields for future extensibility
    custom_fields = Column(JSON)
    
    # Privacy settings
    privacy_settings = Column(JSON)  # What information is visible to others
    
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    # Relationship
    user = relationship("User", backref="profile")

    def __repr__(self):
        return f"<UserProfile(user_id={self.user_id}, advisor={self.advisor_email})>"
    
    @property
    def has_complete_bank_info(self) -> bool:
        """Check if user has complete bank account information"""
        return all([
            self.bank_code,
            self.account_number
        ])
    
    @property
    def has_advisor_info(self) -> bool:
        """Check if user has advisor information"""
        return bool(self.advisor_email or self.advisor_nycu_id)
    
    @property
    def profile_completion_percentage(self) -> int:
        """Calculate profile completion percentage"""
        fields_to_check = [
            self.bank_code, self.account_number,
            self.advisor_email, self.advisor_nycu_id,
            self.bio
        ]
        
        filled_fields = sum(1 for field in fields_to_check if field)
        return int((filled_fields / len(fields_to_check)) * 100)


class UserProfileHistory(Base):
    """History of user profile changes for audit purposes"""
    __tablename__ = "user_profile_history"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
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
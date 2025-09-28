import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, Text, func, ForeignKey
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class ConfigCategory(enum.Enum):
    """Configuration categories for organizing system settings"""
    DATABASE = "database"
    API_KEYS = "api_keys"
    EMAIL = "email"
    OCR = "ocr"
    FILE_STORAGE = "file_storage"
    SECURITY = "security"
    FEATURES = "features"
    INTEGRATIONS = "integrations"
    PERFORMANCE = "performance"
    LOGGING = "logging"


class ConfigDataType(enum.Enum):
    """Data types for configuration values"""
    STRING = "string"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    JSON = "json"
    FLOAT = "float"


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    category = Column(Enum(ConfigCategory, values_callable=lambda obj: [e.value for e in obj]), nullable=False, default=ConfigCategory.FEATURES)
    data_type = Column(Enum(ConfigDataType, values_callable=lambda obj: [e.value for e in obj]), nullable=False, default=ConfigDataType.STRING)
    is_sensitive = Column(Boolean, nullable=False, default=False)
    is_readonly = Column(Boolean, nullable=False, default=False)
    description = Column(Text, nullable=True)
    validation_regex = Column(String(255), nullable=True)
    default_value = Column(Text, nullable=True)
    last_modified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationship to user who last modified this setting
    modified_by_user = relationship("User", foreign_keys=[last_modified_by])


class ConfigurationAuditLog(Base):
    """Audit log for configuration changes"""
    __tablename__ = "configuration_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(100), nullable=False, index=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=False)
    action = Column(String(20), nullable=False)  # CREATE, UPDATE, DELETE
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    change_reason = Column(Text, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to user who made the change
    changed_by_user = relationship("User", foreign_keys=[changed_by])


class SendingType(enum.Enum):
    SINGLE = "single"
    BULK = "bulk"


class EmailTemplate(Base):
    __tablename__ = "email_templates"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    subject_template = Column(String(255), nullable=False)
    body_template = Column(Text, nullable=False)
    cc = Column(Text, nullable=True)  # 逗號分隔或 JSON
    bcc = Column(Text, nullable=True)
    sending_type = Column(Enum(SendingType, values_callable=lambda obj: [e.value for e in obj]), nullable=False, default=SendingType.SINGLE)
    recipient_options = Column(JSON, nullable=True)  # JSON array of recipient options
    requires_approval = Column(Boolean, nullable=False, default=False)
    max_recipients = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

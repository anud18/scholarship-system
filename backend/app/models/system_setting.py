import enum

from sqlalchemy import Boolean, Column, DateTime, Enum, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON

from app.db.base_class import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


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
    sending_type = Column(Enum(SendingType), nullable=False, default=SendingType.SINGLE)
    recipient_options = Column(JSON, nullable=True)  # JSON array of recipient options
    requires_approval = Column(Boolean, nullable=False, default=False)
    max_recipients = Column(Integer, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

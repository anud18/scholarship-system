"""
Application field configuration models
"""

import enum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class FieldType(enum.Enum):
    """Field type enum"""

    TEXT = "text"
    TEXTAREA = "textarea"
    NUMBER = "number"
    EMAIL = "email"
    DATE = "date"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"


class ApplicationField(Base):
    """Application field configuration model"""

    __tablename__ = "application_fields"

    id = Column(Integer, primary_key=True, index=True)
    scholarship_type = Column(String(50), nullable=False, index=True)  # undergraduate, phd, direct_phd

    # Field information
    field_name = Column(String(100), nullable=False)  # 欄位名稱 (英文)
    field_label = Column(String(200), nullable=False)  # 欄位顯示名稱 (中文)
    field_label_en = Column(String(200))  # 英文顯示名稱
    field_type = Column(String(20), nullable=False, default=FieldType.TEXT.value)

    # Validation settings
    is_required = Column(Boolean, default=False)
    placeholder = Column(String(500))  # 提示文字
    placeholder_en = Column(String(500))  # 英文提示文字
    max_length = Column(Integer)  # 字數限制
    min_value = Column(Float)  # 最小值 (for number fields)
    max_value = Column(Float)  # 最大值 (for number fields)
    step_value = Column(Float)  # 步進值 (for number fields)

    # Options for select/radio fields
    field_options = Column(JSON)  # 選項列表 [{"value": "option1", "label": "選項1", "label_en": "Option 1"}]

    # Display settings
    display_order = Column(Integer, default=0)  # 顯示順序
    is_active = Column(Boolean, default=True)  # 是否啟用
    help_text = Column(Text)  # 幫助文字
    help_text_en = Column(Text)  # 英文幫助文字

    # Additional validation rules
    validation_rules = Column(JSON)  # 額外驗證規則
    conditional_rules = Column(JSON)  # 條件顯示規則

    # Meta data
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_by = Column(Integer, ForeignKey("users.id"))

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return (
            f"<ApplicationField(id={self.id}, scholarship_type={self.scholarship_type}, field_name={self.field_name})>"
        )


class ApplicationDocument(Base):
    """Application document configuration model"""

    __tablename__ = "application_documents"

    id = Column(Integer, primary_key=True, index=True)
    scholarship_type = Column(String(50), nullable=False, index=True)  # undergraduate, phd, direct_phd

    # Document information
    document_name = Column(String(200), nullable=False)  # 文件名稱
    document_name_en = Column(String(200))  # 英文文件名稱
    description = Column(Text)  # 文件說明
    description_en = Column(Text)  # 英文說明

    # Requirements
    is_required = Column(Boolean, default=True)
    accepted_file_types = Column(JSON)  # 接受的檔案類型 ["PDF", "JPG", "PNG"]
    max_file_size = Column(String(20), default="5MB")  # 檔案大小限制
    max_file_count = Column(Integer, default=1)  # 檔案數量限制

    # Display settings
    display_order = Column(Integer, default=0)  # 顯示順序
    is_active = Column(Boolean, default=True)  # 是否啟用
    upload_instructions = Column(Text)  # 上傳說明
    upload_instructions_en = Column(Text)  # 英文上傳說明

    # Validation settings
    validation_rules = Column(JSON)  # 驗證規則 (OCR檢查、內容驗證等)

    # Meta data
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"))
    updated_by = Column(Integer, ForeignKey("users.id"))

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    def __repr__(self):
        return f"<ApplicationDocument(id={self.id}, scholarship_type={self.scholarship_type}, document_name={self.document_name})>"

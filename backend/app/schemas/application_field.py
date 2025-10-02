"""
Application field configuration schemas
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.application_field import FieldType


class ApplicationFieldBase(BaseModel):
    """Base schema for application field"""

    scholarship_type: str = Field(..., description="Scholarship type")
    field_name: str = Field(..., description="Field name (English)")
    field_label: str = Field(..., description="Field label (Chinese)")
    field_label_en: Optional[str] = Field(None, description="Field label (English)")
    field_type: str = Field(default=FieldType.TEXT.value, description="Field type")
    is_required: bool = Field(default=False, description="Is field required")
    placeholder: Optional[str] = Field(None, description="Placeholder text")
    placeholder_en: Optional[str] = Field(None, description="Placeholder text (English)")
    max_length: Optional[int] = Field(None, description="Maximum length")
    min_value: Optional[float] = Field(None, description="Minimum value")
    max_value: Optional[float] = Field(None, description="Maximum value")
    step_value: Optional[float] = Field(None, description="Step value")
    field_options: Optional[List[Dict[str, Any]]] = Field(None, description="Field options")
    display_order: int = Field(default=0, description="Display order")
    is_active: bool = Field(default=True, description="Is field active")
    help_text: Optional[str] = Field(None, description="Help text")
    help_text_en: Optional[str] = Field(None, description="Help text (English)")
    validation_rules: Optional[Dict[str, Any]] = Field(None, description="Validation rules")
    conditional_rules: Optional[Dict[str, Any]] = Field(None, description="Conditional rules")


class ApplicationFieldCreate(ApplicationFieldBase):
    """Schema for creating application field"""

    pass


class ApplicationFieldUpdate(BaseModel):
    """Schema for updating application field"""

    field_label: Optional[str] = None
    field_label_en: Optional[str] = None
    field_type: Optional[str] = None
    is_required: Optional[bool] = None
    placeholder: Optional[str] = None
    placeholder_en: Optional[str] = None
    max_length: Optional[int] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    step_value: Optional[float] = None
    field_options: Optional[List[Dict[str, Any]]] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    help_text: Optional[str] = None
    help_text_en: Optional[str] = None
    validation_rules: Optional[Dict[str, Any]] = None
    conditional_rules: Optional[Dict[str, Any]] = None


class ApplicationFieldResponse(ApplicationFieldBase):
    """Schema for application field response"""

    id: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    # Fixed field properties
    is_fixed: Optional[bool] = Field(None, description="Is this a fixed field")
    prefill_value: Optional[str] = Field(None, description="Prefilled value from user profile")
    bank_code: Optional[str] = Field(None, description="Bank code for bank account fields")

    class Config:
        from_attributes = True


class ApplicationDocumentBase(BaseModel):
    """Base schema for application document"""

    scholarship_type: str = Field(..., description="Scholarship type")
    document_name: str = Field(..., description="Document name")
    document_name_en: Optional[str] = Field(None, description="Document name (English)")
    description: Optional[str] = Field(None, description="Document description")
    description_en: Optional[str] = Field(None, description="Document description (English)")
    is_required: bool = Field(default=True, description="Is document required")
    accepted_file_types: List[str] = Field(default=["PDF"], description="Accepted file types")
    max_file_size: str = Field(default="5MB", description="Maximum file size")
    max_file_count: int = Field(default=1, description="Maximum file count")
    display_order: int = Field(default=0, description="Display order")
    is_active: bool = Field(default=True, description="Is document active")
    upload_instructions: Optional[str] = Field(None, description="Upload instructions")
    upload_instructions_en: Optional[str] = Field(None, description="Upload instructions (English)")
    validation_rules: Optional[Dict[str, Any]] = Field(None, description="Validation rules")


class ApplicationDocumentCreate(ApplicationDocumentBase):
    """Schema for creating application document"""

    pass


class ApplicationDocumentUpdate(BaseModel):
    """Schema for updating application document"""

    document_name: Optional[str] = None
    document_name_en: Optional[str] = None
    description: Optional[str] = None
    description_en: Optional[str] = None
    is_required: Optional[bool] = None
    accepted_file_types: Optional[List[str]] = None
    max_file_size: Optional[str] = None
    max_file_count: Optional[int] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    upload_instructions: Optional[str] = None
    upload_instructions_en: Optional[str] = None
    validation_rules: Optional[Dict[str, Any]] = None


class ApplicationDocumentResponse(ApplicationDocumentBase):
    """Schema for application document response"""

    id: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    # Fixed document properties
    is_fixed: Optional[bool] = Field(None, description="Is this a fixed document")
    existing_file_url: Optional[str] = Field(None, description="URL of existing file from user profile")

    class Config:
        from_attributes = True


class ScholarshipFormConfigResponse(BaseModel):
    """Schema for complete scholarship form configuration"""

    scholarship_type: str
    fields: List[ApplicationFieldResponse]
    documents: List[ApplicationDocumentResponse]
    title: Optional[str] = None
    title_en: Optional[str] = None
    color: Optional[str] = None
    hasWhitelist: Optional[bool] = None
    terms_document_url: Optional[str] = None

    class Config:
        from_attributes = True

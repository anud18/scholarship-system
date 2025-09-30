"""
Configuration Management Schemas
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.system_setting import ConfigCategory, ConfigDataType


class ConfigurationItemSchema(BaseModel):
    """Schema for individual configuration item"""
    model_config = ConfigDict(from_attributes=True)

    key: str = Field(..., description="Configuration key")
    value: str = Field(..., description="Configuration value (may be encrypted)")
    category: ConfigCategory = Field(..., description="Configuration category")
    data_type: ConfigDataType = Field(..., description="Data type of the value")
    is_sensitive: bool = Field(False, description="Whether the value is sensitive")
    is_readonly: bool = Field(False, description="Whether the configuration is readonly")
    description: Optional[str] = Field(None, description="Description of the configuration")
    validation_regex: Optional[str] = Field(None, description="Validation regex pattern")
    default_value: Optional[str] = Field(None, description="Default value")
    last_modified_by: Optional[int] = Field(None, description="ID of user who last modified")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class ConfigurationItemWithDecryptedValueSchema(BaseModel):
    """Schema for configuration item with decrypted value"""
    model_config = ConfigDict(from_attributes=True)

    key: str
    decrypted_value: Any = Field(..., description="Decrypted and type-converted value")
    display_value: str = Field(..., description="Value safe for display (masked if sensitive)")
    category: ConfigCategory
    data_type: ConfigDataType
    is_sensitive: bool
    is_readonly: bool
    description: Optional[str]
    validation_regex: Optional[str]
    default_value: Optional[str]
    last_modified_by: Optional[int]
    modified_by_username: Optional[str] = Field(None, description="Username of modifier")
    created_at: datetime
    updated_at: datetime


class ConfigurationUpdateSchema(BaseModel):
    """Schema for updating a configuration"""
    key: str = Field(..., description="Configuration key")
    value: Any = Field(..., description="New value")
    change_reason: Optional[str] = Field(None, description="Reason for the change")


class ConfigurationCreateSchema(BaseModel):
    """Schema for creating a new configuration"""
    key: str = Field(..., description="Configuration key")
    value: Any = Field(..., description="Configuration value")
    category: ConfigCategory = Field(..., description="Configuration category")
    data_type: ConfigDataType = Field(ConfigDataType.STRING, description="Data type")
    is_sensitive: bool = Field(False, description="Whether the value is sensitive")
    is_readonly: bool = Field(False, description="Whether the configuration is readonly")
    description: Optional[str] = Field(None, description="Description")
    validation_regex: Optional[str] = Field(None, description="Validation regex")
    default_value: Optional[str] = Field(None, description="Default value")
    change_reason: Optional[str] = Field(None, description="Reason for creation")


class ConfigurationCategorySchema(BaseModel):
    """Schema for configuration category with all items"""
    category: ConfigCategory = Field(..., description="Category name")
    display_name: str = Field(..., description="Human-readable category name")
    description: str = Field(..., description="Category description")
    configurations: List[ConfigurationItemWithDecryptedValueSchema] = Field(
        [], description="Configurations in this category"
    )
    total_count: int = Field(0, description="Total configurations in category")
    sensitive_count: int = Field(0, description="Number of sensitive configurations")
    readonly_count: int = Field(0, description="Number of readonly configurations")


class ConfigurationBulkUpdateSchema(BaseModel):
    """Schema for bulk configuration updates"""
    updates: List[ConfigurationUpdateSchema] = Field(..., description="List of updates")
    change_reason: Optional[str] = Field(None, description="Reason for bulk update")


class ConfigurationValidationSchema(BaseModel):
    """Schema for configuration validation request"""
    key: str = Field(..., description="Configuration key")
    value: Any = Field(..., description="Value to validate")
    data_type: ConfigDataType = Field(..., description="Expected data type")
    validation_regex: Optional[str] = Field(None, description="Validation regex")


class ConfigurationValidationResultSchema(BaseModel):
    """Schema for configuration validation result"""
    is_valid: bool = Field(..., description="Whether the value is valid")
    message: str = Field(..., description="Validation message")
    suggested_value: Optional[str] = Field(None, description="Suggested corrected value")


class ConfigurationAuditLogSchema(BaseModel):
    """Schema for configuration audit log"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    setting_key: str
    old_value: Optional[str]
    new_value: str
    action: str
    changed_by: int
    changed_by_username: Optional[str] = Field(None, description="Username of changer")
    change_reason: Optional[str]
    changed_at: datetime


class BankVerificationRequestSchema(BaseModel):
    """Schema for bank account verification request"""
    application_id: int = Field(..., description="Application ID to verify")
    force_recheck: bool = Field(False, description="Force re-verification even if cached")


class BankFieldComparisonSchema(BaseModel):
    """Schema for individual bank field comparison"""
    field_name: str = Field(..., description="Human-readable field name")
    form_value: str = Field(..., description="Value from application form")
    ocr_value: str = Field(..., description="Value extracted from OCR")
    similarity_score: float = Field(..., description="Similarity score (0.0-1.0)")
    is_match: bool = Field(..., description="Whether values match within threshold")
    confidence: str = Field(..., description="Confidence level (low/medium/high)")


class BankVerificationResultSchema(BaseModel):
    """Schema for bank account verification result"""
    success: bool = Field(..., description="Whether verification was successful")
    application_id: int = Field(..., description="Application ID")
    verification_status: str = Field(..., description="Overall verification status")
    overall_match: bool = Field(..., description="Whether all fields match")
    average_confidence: float = Field(..., description="Average confidence score")
    compared_fields: int = Field(..., description="Number of fields compared")
    comparisons: Dict[str, BankFieldComparisonSchema] = Field(
        {}, description="Detailed field comparisons"
    )
    form_data: Dict[str, str] = Field({}, description="Bank data from form")
    ocr_data: Dict[str, Any] = Field({}, description="Bank data from OCR")
    passbook_document: Optional[Dict[str, str]] = Field(
        None, description="Information about passbook document"
    )
    recommendations: List[str] = Field([], description="Verification recommendations")
    error: Optional[str] = Field(None, description="Error message if failed")


class BankVerificationBatchRequestSchema(BaseModel):
    """Schema for batch bank verification request"""
    application_ids: List[int] = Field(..., description="List of application IDs")
    force_recheck: bool = Field(False, description="Force re-verification")


class BankVerificationBatchResultSchema(BaseModel):
    """Schema for batch bank verification result"""
    results: Dict[int, BankVerificationResultSchema] = Field(
        {}, description="Verification results by application ID"
    )
    total_processed: int = Field(..., description="Total applications processed")
    successful_verifications: int = Field(..., description="Number of successful verifications")
    failed_verifications: int = Field(..., description="Number of failed verifications")
    summary: Dict[str, int] = Field({}, description="Summary by verification status")


class ConfigurationExportSchema(BaseModel):
    """Schema for configuration export"""
    export_timestamp: datetime = Field(..., description="Export timestamp")
    categories: List[ConfigurationCategorySchema] = Field(
        [], description="All configuration categories"
    )
    total_configurations: int = Field(..., description="Total number of configurations")
    sensitive_configurations: int = Field(..., description="Number of sensitive configurations")
    export_notes: Optional[str] = Field(None, description="Export notes")


class ConfigurationImportSchema(BaseModel):
    """Schema for configuration import"""
    configurations: List[ConfigurationCreateSchema] = Field(
        [], description="Configurations to import"
    )
    overwrite_existing: bool = Field(False, description="Whether to overwrite existing configs")
    change_reason: Optional[str] = Field(None, description="Reason for import")


class ConfigurationImportResultSchema(BaseModel):
    """Schema for configuration import result"""
    success: bool = Field(..., description="Whether import was successful")
    imported_count: int = Field(..., description="Number of configurations imported")
    updated_count: int = Field(..., description="Number of configurations updated")
    skipped_count: int = Field(..., description="Number of configurations skipped")
    errors: List[str] = Field([], description="Import errors")
    imported_keys: List[str] = Field([], description="Keys of imported configurations")


# Helper functions for schema transformations
def get_category_display_name(category: ConfigCategory) -> str:
    """Get human-readable category name"""
    display_names = {
        ConfigCategory.DATABASE: "資料庫設定",
        ConfigCategory.API_KEYS: "API 金鑰",
        ConfigCategory.EMAIL: "電子郵件設定",
        ConfigCategory.OCR: "OCR 設定",
        ConfigCategory.FILE_STORAGE: "檔案儲存設定",
        ConfigCategory.SECURITY: "安全性設定",
        ConfigCategory.FEATURES: "功能開關",
        ConfigCategory.INTEGRATIONS: "系統整合",
        ConfigCategory.PERFORMANCE: "效能設定",
        ConfigCategory.LOGGING: "日誌設定",
    }
    return display_names.get(category, category.value)


def get_category_description(category: ConfigCategory) -> str:
    """Get category description"""
    descriptions = {
        ConfigCategory.DATABASE: "資料庫連接與設定相關選項",
        ConfigCategory.API_KEYS: "外部服務 API 金鑰與認證資訊",
        ConfigCategory.EMAIL: "SMTP 伺服器與電子郵件發送設定",
        ConfigCategory.OCR: "OCR 服務與 Gemini API 設定",
        ConfigCategory.FILE_STORAGE: "MinIO 與檔案上傳儲存設定",
        ConfigCategory.SECURITY: "安全性、CORS 與驗證相關設定",
        ConfigCategory.FEATURES: "系統功能開關與特性設定",
        ConfigCategory.INTEGRATIONS: "NYCU API 與外部系統整合設定",
        ConfigCategory.PERFORMANCE: "系統效能與快取設定",
        ConfigCategory.LOGGING: "日誌記錄與除錯設定",
    }
    return descriptions.get(category, "系統設定分類")


def mask_sensitive_value(value: str, is_sensitive: bool) -> str:
    """Mask sensitive values for display"""
    if not is_sensitive:
        return value

    if len(value) <= 8:
        return "*" * len(value)
    else:
        return value[:3] + "*" * (len(value) - 6) + value[-3:]
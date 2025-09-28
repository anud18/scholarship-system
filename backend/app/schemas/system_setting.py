from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, validator

from app.models.system_setting import ConfigCategory, ConfigDataType


class SystemSettingBase(BaseModel):
    key: str = Field(..., description="配置鍵名")
    value: str = Field(..., description="配置值")
    category: ConfigCategory = Field(..., description="配置類別")
    data_type: ConfigDataType = Field(..., description="數據類型")
    description: Optional[str] = Field(None, description="配置描述")
    is_sensitive: bool = Field(False, description="是否為敏感數據")
    validation_regex: Optional[str] = Field(None, description="驗證正則表達式")

    @validator("key")
    def validate_key(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Configuration key cannot be empty")
        if len(v) > 100:
            raise ValueError("Configuration key cannot exceed 100 characters")
        # 確保鍵名符合命名規範
        if not v.replace("_", "").replace(".", "").replace("-", "").isalnum():
            raise ValueError(
                "Configuration key can only contain alphanumeric characters, underscores, dots, and hyphens"
            )
        return v.strip()

    @validator("value")
    def validate_value(cls, v):
        if v is None:
            raise ValueError("Configuration value cannot be None")
        return str(v)

    @validator("description")
    def validate_description(cls, v):
        if v and len(v) > 500:
            raise ValueError("Description cannot exceed 500 characters")
        return v


class SystemSettingCreate(SystemSettingBase):
    """創建系統配置的請求模型"""

    pass


class SystemSettingUpdate(BaseModel):
    """更新系統配置的請求模型"""

    value: Optional[str] = Field(None, description="配置值")
    category: Optional[ConfigCategory] = Field(None, description="配置類別")
    data_type: Optional[ConfigDataType] = Field(None, description="數據類型")
    description: Optional[str] = Field(None, description="配置描述")
    is_sensitive: Optional[bool] = Field(None, description="是否為敏感數據")
    validation_regex: Optional[str] = Field(None, description="驗證正則表達式")

    @validator("value")
    def validate_value(cls, v):
        if v is not None:
            return str(v)
        return v

    @validator("description")
    def validate_description(cls, v):
        if v and len(v) > 500:
            raise ValueError("Description cannot exceed 500 characters")
        return v


class SystemSettingResponse(BaseModel):
    """系統配置的響應模型"""

    id: int
    key: str
    value: str  # 如果是敏感數據且未請求顯示，則為 "***"
    category: ConfigCategory
    data_type: ConfigDataType
    description: Optional[str]
    is_sensitive: bool
    validation_regex: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]
    created_by: Optional[int]
    updated_by: Optional[int]

    class Config:
        orm_mode = True


class ConfigValidationRequest(BaseModel):
    """配置值驗證請求模型"""

    value: str = Field(..., description="要驗證的值")
    data_type: ConfigDataType = Field(..., description="數據類型")
    validation_regex: Optional[str] = Field(None, description="驗證正則表達式")


class ConfigValidationResponse(BaseModel):
    """配置值驗證響應模型"""

    is_valid: bool = Field(..., description="是否有效")
    error_message: Optional[str] = Field(None, description="錯誤訊息")


class ConfigurationAuditLogResponse(BaseModel):
    """配置審計日誌響應模型"""

    id: int
    config_key: str
    action: str  # 'create', 'update', 'delete'
    old_value: Optional[str]
    new_value: Optional[str]
    changed_by: int
    changed_at: datetime
    user_name: Optional[str]  # 操作者姓名

    class Config:
        orm_mode = True


class SystemSettingListResponse(BaseModel):
    """系統配置列表響應模型"""

    configurations: list[SystemSettingResponse]
    total_count: int
    categories: list[str]
    data_types: list[str]


class ConfigCategoryInfo(BaseModel):
    """配置類別信息模型"""

    value: str
    label: str
    description: Optional[str]


class ConfigDataTypeInfo(BaseModel):
    """配置數據類型信息模型"""

    value: str
    label: str
    description: Optional[str]
    validation_example: Optional[str]


class SystemConfigurationMetadata(BaseModel):
    """系統配置元數據響應模型"""

    categories: list[ConfigCategoryInfo]
    data_types: list[ConfigDataTypeInfo]
    total_configurations: int
    sensitive_configurations: int

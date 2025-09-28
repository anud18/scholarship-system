from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.system_setting import ConfigCategory, ConfigDataType, SystemSetting
from app.models.user import User
from app.schemas.system_setting import (
    ConfigValidationRequest,
    ConfigValidationResponse,
    SystemSettingCreate,
    SystemSettingResponse,
    SystemSettingUpdate,
)
from app.services.config_management_service import ConfigurationService

router = APIRouter()


@router.get("/", response_model=List[SystemSettingResponse])
async def get_all_configurations(
    category: Optional[ConfigCategory] = None,
    include_sensitive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    獲取所有系統配置
    """
    config_service = ConfigurationService(db)

    try:
        configurations = config_service.get_configurations_sync(category=category, include_sensitive=include_sensitive)
        return configurations
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve configurations: {str(e)}"
        )


@router.get("/{config_key}", response_model=SystemSettingResponse)
async def get_configuration(
    config_key: str,
    include_sensitive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    獲取單一系統配置
    """
    config_service = ConfigurationService(db)

    try:
        configuration = config_service.get_configuration_sync(key=config_key, include_sensitive=include_sensitive)
        if not configuration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration with key '{config_key}' not found"
            )
        return configuration
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve configuration: {str(e)}"
        )


@router.post("/", response_model=SystemSettingResponse)
async def create_configuration(
    configuration: SystemSettingCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    """
    創建新的系統配置
    """
    config_service = ConfigurationService(db)

    try:
        # Check if configuration already exists
        existing = config_service.get_configuration_sync(configuration.key, include_sensitive=True)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Configuration with key '{configuration.key}' already exists",
            )

        new_configuration = config_service.set_configuration_sync(
            key=configuration.key,
            value=configuration.value,
            category=configuration.category,
            data_type=configuration.data_type,
            description=configuration.description,
            is_sensitive=configuration.is_sensitive,
            validation_regex=configuration.validation_regex,
            user_id=current_user.id,
        )
        return new_configuration
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create configuration: {str(e)}"
        )


@router.put("/{config_key}", response_model=SystemSettingResponse)
async def update_configuration(
    config_key: str,
    configuration: SystemSettingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    更新系統配置
    """
    config_service = ConfigurationService(db)

    try:
        # Check if configuration exists
        existing = config_service.get_configuration_sync(config_key, include_sensitive=True)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration with key '{config_key}' not found"
            )

        updated_configuration = config_service.set_configuration_sync(
            key=config_key,
            value=configuration.value if configuration.value is not None else existing.value,
            category=configuration.category if configuration.category is not None else existing.category,
            data_type=configuration.data_type if configuration.data_type is not None else existing.data_type,
            description=configuration.description if configuration.description is not None else existing.description,
            is_sensitive=configuration.is_sensitive
            if configuration.is_sensitive is not None
            else existing.is_sensitive,
            validation_regex=configuration.validation_regex
            if configuration.validation_regex is not None
            else existing.validation_regex,
            user_id=current_user.id,
        )
        return updated_configuration
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update configuration: {str(e)}"
        )


@router.delete("/{config_key}")
async def delete_configuration(
    config_key: str, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    """
    刪除系統配置
    """
    config_service = ConfigurationService(db)

    try:
        # Check if configuration exists
        existing = config_service.get_configuration_sync(config_key, include_sensitive=True)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration with key '{config_key}' not found"
            )

        success = config_service.delete_configuration_sync(config_key, current_user.id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete configuration"
            )

        return {"message": "Configuration deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete configuration: {str(e)}"
        )


@router.post("/validate", response_model=ConfigValidationResponse)
async def validate_configuration(
    validation_request: ConfigValidationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    驗證配置值
    """
    config_service = ConfigurationService(db)

    try:
        is_valid, error_message = config_service.validate_configuration_value(
            value=validation_request.value,
            data_type=validation_request.data_type,
            validation_regex=validation_request.validation_regex,
        )

        return ConfigValidationResponse(is_valid=is_valid, error_message=error_message)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to validate configuration: {str(e)}"
        )


@router.get("/categories/", response_model=List[str])
async def get_configuration_categories(current_user: User = Depends(require_admin)):
    """
    獲取所有配置類別
    """
    return [category.value for category in ConfigCategory]


@router.get("/data-types/", response_model=List[str])
async def get_configuration_data_types(current_user: User = Depends(require_admin)):
    """
    獲取所有配置數據類型
    """
    return [data_type.value for data_type in ConfigDataType]


@router.get("/audit-logs/{config_key}")
async def get_configuration_audit_logs(
    config_key: str, limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(require_admin)
):
    """
    獲取配置變更審計日誌
    """
    config_service = ConfigurationService(db)

    try:
        audit_logs = config_service.get_audit_logs_sync(config_key, limit)
        return audit_logs
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve audit logs: {str(e)}"
        )

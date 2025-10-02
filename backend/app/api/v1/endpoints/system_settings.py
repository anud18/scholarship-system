from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.system_setting import ConfigCategory, ConfigDataType
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


@router.get("")
async def get_all_configurations(
    category: Optional[ConfigCategory] = None,
    include_sensitive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    獲取所有系統配置
    """
    config_service = ConfigurationService(db)

    try:
        if category:
            configurations = await config_service.get_configurations_by_category(category)
        else:
            configurations = await config_service.get_all_configurations()

        # Convert to response models
        response_configs = []
        for config in configurations:
            if include_sensitive:
                value = config.value
            else:
                value = config.value if not config.is_sensitive else "***HIDDEN***"

            response_configs.append(
                {
                    "key": config.key,
                    "value": value,
                    "category": config.category,
                    "data_type": config.data_type,
                    "description": config.description,
                    "is_sensitive": config.is_sensitive,
                    "is_readonly": config.is_readonly,
                    "validation_regex": config.validation_regex,
                    "default_value": config.default_value,
                    "last_modified_by": config.last_modified_by,
                    "created_at": config.created_at,
                    "updated_at": config.updated_at,
                }
            )

        return {
            "success": True,
            "message": f"Retrieved {len(response_configs)} system settings",
            "data": response_configs,
            "errors": None,
            "trace_id": None,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve configurations: {str(e)}"
        )


@router.get("/{config_key}")
async def get_configuration(
    config_key: str,
    include_sensitive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    獲取單一系統配置
    """
    config_service = ConfigurationService(db)

    try:
        configuration = await config_service.get_configuration(config_key)
        if not configuration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration with key '{config_key}' not found"
            )

        # Convert to response model
        if include_sensitive:
            value = configuration.value
        else:
            value = configuration.value if not configuration.is_sensitive else "***HIDDEN***"

        config_data = {
            "key": configuration.key,
            "value": value,
            "category": configuration.category,
            "data_type": configuration.data_type,
            "description": configuration.description,
            "is_sensitive": configuration.is_sensitive,
            "is_readonly": configuration.is_readonly,
            "validation_regex": configuration.validation_regex,
            "default_value": configuration.default_value,
            "last_modified_by": configuration.last_modified_by,
            "created_at": configuration.created_at,
            "updated_at": configuration.updated_at,
        }

        return {
            "success": True,
            "message": f"Retrieved configuration '{config_key}'",
            "data": config_data,
            "errors": None,
            "trace_id": None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve configuration: {str(e)}"
        )


@router.post("", response_model=SystemSettingResponse)
async def create_configuration(
    configuration: SystemSettingCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """
    創建新的系統配置
    """
    config_service = ConfigurationService(db)

    try:
        # Check if configuration already exists
        existing = await config_service.get_configuration(configuration.key)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Configuration with key '{configuration.key}' already exists",
            )

        new_configuration = await config_service.set_configuration(
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    更新系統配置
    """
    config_service = ConfigurationService(db)

    try:
        # Check if configuration exists
        existing = await config_service.get_configuration(config_key)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration with key '{config_key}' not found"
            )

        updated_configuration = await config_service.set_configuration(
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
    config_key: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """
    刪除系統配置
    """
    config_service = ConfigurationService(db)

    try:
        # Check if configuration exists
        existing = await config_service.get_configuration(config_key)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration with key '{config_key}' not found"
            )

        success = await config_service.delete_configuration(config_key, current_user.id)
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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    驗證配置值
    """
    config_service = ConfigurationService(db)

    try:
        is_valid, error_message = await config_service.validate_configuration(
            key="temp",  # Use temp key for validation
            value=validation_request.value,
            data_type=validation_request.data_type,
        )

        return ConfigValidationResponse(is_valid=is_valid, error_message=error_message)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to validate configuration: {str(e)}"
        )


@router.get("/categories")
async def get_configuration_categories(current_user: User = Depends(require_admin)):
    """
    獲取所有配置類別
    """
    categories = [category.value for category in ConfigCategory]
    return {
        "success": True,
        "message": f"Retrieved {len(categories)} configuration categories",
        "data": categories,
        "errors": None,
        "trace_id": None,
    }


@router.get("/data-types")
async def get_configuration_data_types(current_user: User = Depends(require_admin)):
    """
    獲取所有配置數據類型
    """
    data_types = [data_type.value for data_type in ConfigDataType]
    return {
        "success": True,
        "message": f"Retrieved {len(data_types)} data types",
        "data": data_types,
        "errors": None,
        "trace_id": None,
    }


@router.get("/audit-logs/{config_key}")
async def get_configuration_audit_logs(
    config_key: str, limit: int = 50, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """
    獲取配置變更審計日誌
    """
    config_service = ConfigurationService(db)

    try:
        audit_logs = await config_service.get_audit_logs(config_key, limit)
        return audit_logs
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve audit logs: {str(e)}"
        )

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin
from app.db.deps import get_db
from app.models.system_setting import ConfigCategory, ConfigDataType
from app.models.user import User
from app.schemas.system_setting import (
    ConfigValidationRequest,
    ConfigValidationResponse,
    SystemSettingCreate,
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
            # Display logic for values
            if not config.value:  # Empty value
                value = "(空值)" if config.allow_empty else ""
            elif include_sensitive:
                value = config.value  # Show actual value (may be encrypted if legacy data)
            elif config.is_sensitive:
                value = "***HIDDEN***"  # Hide sensitive non-empty values
            else:
                value = config.value

            response_configs.append(
                {
                    "key": config.key,
                    "value": value,
                    "category": config.category,
                    "data_type": config.data_type,
                    "description": config.description,
                    "is_sensitive": config.is_sensitive,
                    "is_readonly": config.is_readonly,
                    "allow_empty": config.allow_empty,
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


_ALLOWED_DOC_KEYS = {"regulations_url", "sample_document_url"}


@router.get("/public-docs")
async def get_public_docs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return object_names for 獎學金要點 and 申請文件範例檔.
    Accessible by any authenticated user.
    """
    from sqlalchemy import select

    from app.models.system_setting import SystemSetting

    stmt = select(SystemSetting).where(SystemSetting.key.in_(list(_ALLOWED_DOC_KEYS)))
    result = await db.execute(stmt)
    rows = result.scalars().all()
    data = {row.key: row.value for row in rows}
    return {"success": True, "message": "OK", "data": data}


@router.post("/upload/{doc_key}")
async def upload_system_doc(
    doc_key: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a global system document (獎學金要點 or 申請文件範例檔). Admin only.
    Stores object_name in system_settings under the given key.
    """
    import io
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.core.path_security import validate_upload_file
    from app.models.system_setting import ConfigCategory, ConfigDataType, SystemSetting
    from app.services.minio_service import minio_service

    if doc_key not in _ALLOWED_DOC_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid doc_key. Allowed: {_ALLOWED_DOC_KEYS}")

    allowed_extensions = [".pdf", ".doc", ".docx"]
    file_content = await file.read()
    validate_upload_file(
        filename=file.filename,
        allowed_extensions=allowed_extensions,
        max_size_mb=10,
        file_size=len(file_content),
        allow_unicode=True,
    )

    ext = ""
    if file.filename:
        for e in allowed_extensions:
            if file.filename.lower().endswith(e):
                ext = e
                break

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    object_name = f"system-docs/{doc_key}_{timestamp}{ext}"

    minio_service.client.put_object(
        bucket_name=minio_service.default_bucket,
        object_name=object_name,
        data=io.BytesIO(file_content),
        length=len(file_content),
        content_type=file.content_type or "application/octet-stream",
    )

    # Upsert into system_settings
    stmt = select(SystemSetting).where(SystemSetting.key == doc_key)
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = object_name
        setting.last_modified_by = current_user.id
    else:
        setting = SystemSetting(
            key=doc_key,
            value=object_name,
            category=ConfigCategory.file_storage,
            data_type=ConfigDataType.string,
            description="獎學金要點" if doc_key == "regulations_url" else "申請文件範例檔",
            is_sensitive=False,
            is_readonly=False,
            allow_empty=True,
            last_modified_by=current_user.id,
        )
        db.add(setting)

    await db.commit()
    return {"success": True, "message": "上傳成功", "data": {"key": doc_key, "object_name": object_name}}


@router.get("/file/{doc_key}")
async def get_system_doc_file(
    doc_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Proxy a global system document from MinIO. Any authenticated user."""
    import io

    from sqlalchemy import select

    from app.models.system_setting import SystemSetting
    from app.services.minio_service import minio_service

    if doc_key not in _ALLOWED_DOC_KEYS:
        raise HTTPException(status_code=400, detail="Invalid doc_key")

    stmt = select(SystemSetting).where(SystemSetting.key == doc_key)
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()

    if not setting or not setting.value:
        raise HTTPException(status_code=404, detail="文件尚未上傳")

    try:
        response = minio_service.client.get_object(
            bucket_name=minio_service.default_bucket,
            object_name=setting.value,
        )
        file_content = response.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法取得文件: {str(e)}")

    content_type = "application/pdf"
    if setting.value.endswith(".doc"):
        content_type = "application/msword"
    elif setting.value.endswith(".docx"):
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return StreamingResponse(
        io.BytesIO(file_content),
        media_type=content_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{doc_key}.pdf"},
    )


@router.get("/{id}")
async def get_configuration(
    id: str,
    include_sensitive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    獲取單一系統配置
    """
    config_service = ConfigurationService(db)

    try:
        configuration = await config_service.get_configuration(id)
        if not configuration:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration with key '{id}' not found"
            )

        # Convert to response model with display logic
        if not configuration.value:  # Empty value
            value = "(空值)" if configuration.allow_empty else ""
        elif include_sensitive:
            value = configuration.value  # Show actual value (may be encrypted if legacy data)
        elif configuration.is_sensitive:
            value = "***HIDDEN***"  # Hide sensitive non-empty values
        else:
            value = configuration.value

        config_data = {
            "key": configuration.key,
            "value": value,
            "category": configuration.category,
            "data_type": configuration.data_type,
            "description": configuration.description,
            "is_sensitive": configuration.is_sensitive,
            "is_readonly": configuration.is_readonly,
            "allow_empty": configuration.allow_empty,
            "validation_regex": configuration.validation_regex,
            "default_value": configuration.default_value,
            "last_modified_by": configuration.last_modified_by,
            "created_at": configuration.created_at,
            "updated_at": configuration.updated_at,
        }

        return {
            "success": True,
            "message": f"Retrieved configuration '{id}'",
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


@router.post("")
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
            allow_empty=configuration.allow_empty,
            validation_regex=configuration.validation_regex,
            user_id=current_user.id,
        )

        # Convert to dict for response
        config_dict = {
            "key": new_configuration.key,
            "value": new_configuration.value if not new_configuration.is_sensitive else "***HIDDEN***",
            "category": new_configuration.category,
            "data_type": new_configuration.data_type,
            "description": new_configuration.description,
            "is_sensitive": new_configuration.is_sensitive,
            "is_readonly": new_configuration.is_readonly,
            "allow_empty": new_configuration.allow_empty,
            "validation_regex": new_configuration.validation_regex,
            "default_value": new_configuration.default_value,
            "last_modified_by": new_configuration.last_modified_by,
            "created_at": new_configuration.created_at,
            "updated_at": new_configuration.updated_at,
        }

        return {
            "success": True,
            "message": "Configuration created successfully",
            "data": config_dict,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create configuration: {str(e)}"
        )


@router.put("/{id}")
async def update_configuration(
    id: str,
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
        existing = await config_service.get_configuration(id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration with key '{id}' not found"
            )

        updated_configuration = await config_service.set_configuration(
            key=id,
            value=configuration.value if configuration.value is not None else existing.value,
            category=configuration.category if configuration.category is not None else existing.category,
            data_type=configuration.data_type if configuration.data_type is not None else existing.data_type,
            description=configuration.description if configuration.description is not None else existing.description,
            is_sensitive=(
                configuration.is_sensitive if configuration.is_sensitive is not None else existing.is_sensitive
            ),
            allow_empty=configuration.allow_empty if configuration.allow_empty is not None else existing.allow_empty,
            validation_regex=(
                configuration.validation_regex
                if configuration.validation_regex is not None
                else existing.validation_regex
            ),
            user_id=current_user.id,
        )

        # Convert to dict for response
        config_dict = {
            "key": updated_configuration.key,
            "value": updated_configuration.value if not updated_configuration.is_sensitive else "***HIDDEN***",
            "category": updated_configuration.category,
            "data_type": updated_configuration.data_type,
            "description": updated_configuration.description,
            "is_sensitive": updated_configuration.is_sensitive,
            "is_readonly": updated_configuration.is_readonly,
            "allow_empty": updated_configuration.allow_empty,
            "validation_regex": updated_configuration.validation_regex,
            "default_value": updated_configuration.default_value,
            "last_modified_by": updated_configuration.last_modified_by,
            "created_at": updated_configuration.created_at,
            "updated_at": updated_configuration.updated_at,
        }

        return {
            "success": True,
            "message": "Configuration updated successfully",
            "data": config_dict,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update configuration: {str(e)}"
        )


@router.delete("/{id}")
async def delete_configuration(
    id: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """
    刪除系統配置
    """
    config_service = ConfigurationService(db)

    try:
        # Check if configuration exists
        existing = await config_service.get_configuration(id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"Configuration with key '{id}' not found"
            )

        success = await config_service.delete_configuration(id, current_user.id)
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


@router.post("/validate")
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

        response_data = ConfigValidationResponse(is_valid=is_valid, error_message=error_message)

        return {
            "success": True,
            "message": "Validation completed",
            "data": response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict(),
        }
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
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.system_setting import ConfigurationAuditLog

    try:
        # 查詢並加載用戶關聯
        stmt = (
            select(ConfigurationAuditLog)
            .options(selectinload(ConfigurationAuditLog.changed_by_user))
            .where(ConfigurationAuditLog.setting_key == config_key)
            .order_by(ConfigurationAuditLog.changed_at.desc())
            .limit(limit)
        )

        result = await db.execute(stmt)
        audit_logs = result.scalars().all()

        # 轉換為字典格式
        audit_data = []
        for log in audit_logs:
            user_name = None
            if log.changed_by_user:
                user_name = log.changed_by_user.name or log.changed_by_user.nycu_id

            audit_data.append(
                {
                    "id": log.id,
                    "setting_key": log.setting_key,
                    "action": log.action,
                    "old_value": log.old_value,
                    "new_value": log.new_value,
                    "changed_by": log.changed_by,
                    "user_name": user_name,
                    "change_reason": log.change_reason,
                    "changed_at": log.changed_at.isoformat() if log.changed_at else None,
                }
            )

        # 返回標準 ApiResponse 格式
        return {
            "success": True,
            "message": f"Retrieved {len(audit_data)} audit log entries",
            "data": audit_data,
            "errors": None,
            "trace_id": None,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve audit logs: {str(e)}"
        )

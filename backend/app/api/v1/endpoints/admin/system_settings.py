"""
Admin System Settings API Endpoints

Handles system-level configuration settings
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.user import User
from app.schemas.common import SystemSettingSchema
from app.services.system_setting_service import SystemSettingService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/system-setting")
async def get_system_setting(
    key: str = Query(..., description="Setting key"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get system setting by key (admin only)"""
    setting = await SystemSettingService.get_setting(db, key)
    if not setting:
        return {
            "success": True,
            "message": "System setting retrieved successfully",
            "data": SystemSettingSchema(key=key, value=""),
        }
    return {
        "success": True,
        "message": "System setting retrieved successfully",
        "data": SystemSettingSchema.model_validate(setting),
    }


@router.put("/system-setting")
async def set_system_setting(
    data: SystemSettingSchema, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """Update system setting (admin only).

    SECURITY: System-config mutation. Audit-logged with actor_user_id /
    actor_role / key / value-length so any unexpected change to runtime
    settings (e.g., feature flags, integration toggles) is traceable
    back to an admin actor.
    """
    # Capture pre-existing value so the audit row can show old -> new.
    previous = await SystemSettingService.get_setting(db, data.key)
    previous_value = previous.value if previous is not None else None

    setting = await SystemSettingService.set_setting(db, key=data.key, value=data.value)

    logger.info(
        "system-setting updated: key=%s by user_id=%s",
        data.key,
        current_user.id,
        extra={
            "actor_user_id": current_user.id,
            "actor_role": current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
            "setting_key": data.key,
            "previous_value_len": len(previous_value) if previous_value is not None else None,
            "new_value_len": len(data.value) if data.value is not None else 0,
            "previous_existed": previous is not None,
        },
    )

    return {
        "success": True,
        "message": "System setting updated successfully",
        "data": SystemSettingSchema.model_validate(setting),
    }

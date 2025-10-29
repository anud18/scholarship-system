"""
Admin System Settings API Endpoints

Handles system-level configuration settings
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.user import User
from app.schemas.common import SystemSettingSchema
from app.services.system_setting_service import SystemSettingService

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
    """Update system setting (admin only)"""
    setting = await SystemSettingService.set_setting(db, key=data.key, value=data.value)
    return {
        "success": True,
        "message": "System setting updated successfully",
        "data": SystemSettingSchema.model_validate(setting),
    }

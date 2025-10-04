"""
Email Automation Rules Management API
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.email_management import EmailAutomationRule, TriggerEvent
from app.models.user import User
from app.schemas.api_response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic schemas
class EmailAutomationRuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    trigger_event: str
    template_key: str
    delay_hours: int = 0
    condition_query: Optional[str] = None
    is_active: bool = True


class EmailAutomationRuleCreate(EmailAutomationRuleBase):
    pass


class EmailAutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger_event: Optional[str] = None
    template_key: Optional[str] = None
    delay_hours: Optional[int] = None
    condition_query: Optional[str] = None
    is_active: Optional[bool] = None


class EmailAutomationRuleResponse(EmailAutomationRuleBase):
    id: int
    created_by_user_id: Optional[int]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


@router.get("", response_model=ApiResponse[List[EmailAutomationRuleResponse]])
async def get_automation_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    is_active: Optional[bool] = None,
    trigger_event: Optional[str] = None,
):
    """
    獲取所有郵件自動化規則

    權限：管理員
    """
    try:
        stmt = select(EmailAutomationRule)

        if is_active is not None:
            stmt = stmt.where(EmailAutomationRule.is_active == is_active)

        if trigger_event:
            stmt = stmt.where(EmailAutomationRule.trigger_event == TriggerEvent(trigger_event))

        stmt = stmt.order_by(EmailAutomationRule.created_at.desc())

        result = await db.execute(stmt)
        rules = result.scalars().all()

        rules_data = [
            {
                "id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "trigger_event": rule.trigger_event.value,
                "template_key": rule.template_key,
                "delay_hours": rule.delay_hours,
                "condition_query": rule.condition_query,
                "is_active": rule.is_active,
                "created_by_user_id": rule.created_by_user_id,
                "created_at": rule.created_at.isoformat() if rule.created_at else None,
                "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
            }
            for rule in rules
        ]

        return ApiResponse(
            success=True,
            message=f"成功獲取 {len(rules_data)} 條自動化規則",
            data=rules_data,
        )

    except Exception as e:
        logger.error(f"獲取自動化規則失敗: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"獲取自動化規則失敗: {str(e)}")


@router.post("", response_model=ApiResponse[EmailAutomationRuleResponse])
async def create_automation_rule(
    rule_data: EmailAutomationRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    創建新的郵件自動化規則

    權限：管理員
    """
    try:
        # Validate trigger event
        try:
            trigger_enum = TriggerEvent(rule_data.trigger_event)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"無效的觸發事件: {rule_data.trigger_event}",
            )

        # Create new rule
        new_rule = EmailAutomationRule(
            name=rule_data.name,
            description=rule_data.description,
            trigger_event=trigger_enum,
            template_key=rule_data.template_key,
            delay_hours=rule_data.delay_hours,
            condition_query=rule_data.condition_query,
            is_active=rule_data.is_active,
            created_by_user_id=current_user.id,
        )

        db.add(new_rule)
        await db.commit()
        await db.refresh(new_rule)

        response_data = {
            "id": new_rule.id,
            "name": new_rule.name,
            "description": new_rule.description,
            "trigger_event": new_rule.trigger_event.value,
            "template_key": new_rule.template_key,
            "delay_hours": new_rule.delay_hours,
            "condition_query": new_rule.condition_query,
            "is_active": new_rule.is_active,
            "created_by_user_id": new_rule.created_by_user_id,
            "created_at": new_rule.created_at.isoformat() if new_rule.created_at else None,
            "updated_at": new_rule.updated_at.isoformat() if new_rule.updated_at else None,
        }

        return ApiResponse(
            success=True,
            message="成功創建自動化規則",
            data=response_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"創建自動化規則失敗: {e}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"創建自動化規則失敗: {str(e)}")


@router.put("/{rule_id}", response_model=ApiResponse[EmailAutomationRuleResponse])
async def update_automation_rule(
    rule_id: int,
    rule_data: EmailAutomationRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    更新郵件自動化規則

    權限：管理員
    """
    try:
        # Get existing rule
        stmt = select(EmailAutomationRule).where(EmailAutomationRule.id == rule_id)
        result = await db.execute(stmt)
        rule = result.scalar_one_or_none()

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"找不到 ID 為 {rule_id} 的自動化規則",
            )

        # Update fields
        if rule_data.name is not None:
            rule.name = rule_data.name
        if rule_data.description is not None:
            rule.description = rule_data.description
        if rule_data.trigger_event is not None:
            try:
                rule.trigger_event = TriggerEvent(rule_data.trigger_event)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"無效的觸發事件: {rule_data.trigger_event}",
                )
        if rule_data.template_key is not None:
            rule.template_key = rule_data.template_key
        if rule_data.delay_hours is not None:
            rule.delay_hours = rule_data.delay_hours
        if rule_data.condition_query is not None:
            rule.condition_query = rule_data.condition_query
        if rule_data.is_active is not None:
            rule.is_active = rule_data.is_active

        await db.commit()
        await db.refresh(rule)

        response_data = {
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "trigger_event": rule.trigger_event.value,
            "template_key": rule.template_key,
            "delay_hours": rule.delay_hours,
            "condition_query": rule.condition_query,
            "is_active": rule.is_active,
            "created_by_user_id": rule.created_by_user_id,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        }

        return ApiResponse(
            success=True,
            message="成功更新自動化規則",
            data=response_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新自動化規則失敗: {e}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新自動化規則失敗: {str(e)}")


@router.delete("/{rule_id}", response_model=ApiResponse)
async def delete_automation_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    刪除郵件自動化規則

    權限：管理員
    """
    try:
        # Get existing rule
        stmt = select(EmailAutomationRule).where(EmailAutomationRule.id == rule_id)
        result = await db.execute(stmt)
        rule = result.scalar_one_or_none()

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"找不到 ID 為 {rule_id} 的自動化規則",
            )

        await db.delete(rule)
        await db.commit()

        return ApiResponse(
            success=True,
            message="成功刪除自動化規則",
            data=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"刪除自動化規則失敗: {e}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"刪除自動化規則失敗: {str(e)}")


@router.patch("/{rule_id}/toggle", response_model=ApiResponse[EmailAutomationRuleResponse])
async def toggle_automation_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    切換郵件自動化規則的啟用狀態

    權限：管理員
    """
    try:
        # Get existing rule
        stmt = select(EmailAutomationRule).where(EmailAutomationRule.id == rule_id)
        result = await db.execute(stmt)
        rule = result.scalar_one_or_none()

        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"找不到 ID 為 {rule_id} 的自動化規則",
            )

        # Toggle is_active
        rule.is_active = not rule.is_active

        await db.commit()
        await db.refresh(rule)

        response_data = {
            "id": rule.id,
            "name": rule.name,
            "description": rule.description,
            "trigger_event": rule.trigger_event.value,
            "template_key": rule.template_key,
            "delay_hours": rule.delay_hours,
            "condition_query": rule.condition_query,
            "is_active": rule.is_active,
            "created_by_user_id": rule.created_by_user_id,
            "created_at": rule.created_at.isoformat() if rule.created_at else None,
            "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
        }

        return ApiResponse(
            success=True,
            message=f"成功{'啟用' if rule.is_active else '停用'}自動化規則",
            data=response_data,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切換自動化規則狀態失敗: {e}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"切換自動化規則狀態失敗: {str(e)}")


@router.get("/trigger-events", response_model=ApiResponse[List[dict]])
async def get_trigger_events(
    current_user: User = Depends(require_admin),
):
    """
    獲取所有可用的觸發事件

    權限：管理員
    """
    trigger_events = [
        {
            "value": TriggerEvent.application_submitted.value,
            "label": "申請提交時",
            "description": "當學生提交申請時觸發",
        },
        {
            "value": TriggerEvent.professor_review_submitted.value,
            "label": "教授審核提交時",
            "description": "當指導教授提交審核意見時觸發",
        },
        {
            "value": TriggerEvent.college_review_submitted.value,
            "label": "學院審核提交時",
            "description": "當學院提交審核意見時觸發",
        },
        {
            "value": TriggerEvent.final_result_decided.value,
            "label": "最終結果決定時",
            "description": "當最終審核結果確定時觸發",
        },
        {
            "value": TriggerEvent.supplement_requested.value,
            "label": "要求補件時",
            "description": "當要求申請者補充資料時觸發",
        },
        {
            "value": TriggerEvent.deadline_approaching.value,
            "label": "截止日期接近時",
            "description": "當申請截止日期接近時觸發",
        },
    ]

    return ApiResponse(
        success=True,
        message=f"成功獲取 {len(trigger_events)} 種觸發事件",
        data=trigger_events,
    )

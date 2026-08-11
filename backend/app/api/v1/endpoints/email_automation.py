"""
Email Automation Rules Management API
"""

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.regex_validator import RegexValidationError, safe_regex_search
from app.core.security import require_admin
from app.core.sql_read_only_guard import describe_if_unsafe
from app.db.deps import get_db
from app.models.email_management import EmailAutomationRule, TriggerEvent
from app.models.user import User
from app.schemas.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter()


def validate_condition_query(query: Optional[str]) -> None:
    """
    Validate condition_query to prevent SQL injection and ReDoS attacks.

    SECURITY: Multi-layer validation:
    1. Input length and pattern checks (prevent ReDoS attacks)
    2. SQL keyword blacklist (prevent SQL injection)
    3. Placeholder format validation with timeout protection (prevent ReDoS)

    Raises:
        HTTPException: If query contains dangerous SQL keywords, patterns, or exceeds limits
    """
    if not query:
        return

    # SECURITY LAYER 1: Pre-validation checks to prevent obvious ReDoS attacks.
    # The LENGTH check lives in sql_read_only_guard (layer 2) and is not repeated
    # here — a second local MAX_QUERY_LENGTH constant is exactly how the old
    # inline blacklist drifted away from the executor's own rules.
    MAX_CONSECUTIVE_BRACES = 50

    # Check for excessive consecutive braces (potential ReDoS attack pattern)
    consecutive_open_braces = re.search(r"\{{50,}", query)
    consecutive_close_braces = re.search(r"\}{50,}", query)
    if consecutive_open_braces or consecutive_close_braces:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"condition_query contains suspicious pattern: excessive consecutive braces (max {MAX_CONSECUTIVE_BRACES})",
        )

    # SECURITY LAYER 2: shape + keyword checks, delegated to the SHARED guard that
    # also runs at execution time (app/core/sql_read_only_guard.py). Keeping a second
    # private copy here is what let the two drift: the old inline blacklist did plain
    # substring matching on the uppercased query, so it
    #   * rejected legitimate columns — CREATE ⊂ created_at, UPDATE ⊂ updated_at,
    #     SET ⊂ OFFSET — which made the seeded 申請提交確認郵件 rule unsaveable;
    #   * rejected UNION, which that same seeded rule uses; and
    #   * let `SELECT 1; LOCK TABLE users;` through, because its multi-statement test
    #     only fired when the query did NOT end in a semicolon.
    # The shared guard masks string literals and comments before matching and uses
    # word boundaries, so none of those hold.
    # describe_if_unsafe returns a CURATED, documented client-safe reason (or None)
    # rather than tunnelling str(exc) into the body — see
    # test_no_exception_leak_in_endpoints for why endpoints must not echo exception
    # text. The admin needs the specific reason to fix their query.
    rejection = describe_if_unsafe(query)
    if rejection is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"condition_query {rejection}",
        )

    # SECURITY LAYER 3: Placeholder validation with ReDoS protection
    # Validate placeholder format: only {word_characters}
    try:
        # SECURITY: Use safe_regex_search with timeout to prevent ReDoS attacks
        # Strategy: Find all placeholders, then validate each one
        # Pattern 1: Find all placeholders (any content between braces)
        all_placeholders_pattern = r"\{[^}]*\}"
        remaining_query = query
        all_invalid = []

        while True:
            match = safe_regex_search(all_placeholders_pattern, remaining_query, timeout_seconds=1)
            if not match:
                break

            placeholder = match.group(0)
            # Extract content between braces
            content = placeholder[1:-1]  # Remove { and }

            # Check if content is valid (only word characters: a-z, A-Z, 0-9, _)
            if not content or not re.match(r"^[a-zA-Z0-9_]+$", content):
                all_invalid.append(placeholder)

            # Move past this match
            remaining_query = remaining_query[match.end() :]

        if all_invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid placeholder format. Only {{word_characters}} allowed. Found: {all_invalid[:5]}",
            )

    except RegexValidationError as e:
        # Regex pattern itself is malicious or causes ReDoS
        logger.exception("Regex validation error in condition_query")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="condition_query contains invalid pattern that cannot be safely validated",
        ) from e

    logger.info(f"✓ Query validation passed: {query[:100]}...")


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

    model_config = ConfigDict(from_attributes=True)


@router.get("")
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

        return ApiResponse(success=True, message=f"成功獲取 {len(rules_data)} 條自動化規則", data=rules_data)

    except Exception as e:
        logger.exception("獲取自動化規則失敗")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="獲取自動化規則失敗") from e


@router.post("")
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
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"無效的觸發事件: {rule_data.trigger_event}"
            ) from exc

        # SECURITY: Validate condition_query to prevent SQL injection
        validate_condition_query(rule_data.condition_query)

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

        logger.info(
            "Email automation rule created",
            extra={
                "rule_id": new_rule.id,
                "rule_name": new_rule.name,
                "trigger_event": new_rule.trigger_event.value,
                "template_key": new_rule.template_key,
                "is_active": new_rule.is_active,
                "actor_user_id": current_user.id,
            },
        )

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

        return ApiResponse(success=True, message="成功創建自動化規則", data=response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to create email automation rule",
            extra={"actor_user_id": current_user.id, "rule_name": rule_data.name},
        )
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="創建自動化規則失敗") from e


@router.put("/{rule_id}")
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"找不到 ID 為 {rule_id} 的自動化規則")

        # Update fields
        if rule_data.name is not None:
            rule.name = rule_data.name
        if rule_data.description is not None:
            rule.description = rule_data.description
        if rule_data.trigger_event is not None:
            try:
                rule.trigger_event = TriggerEvent(rule_data.trigger_event)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"無效的觸發事件: {rule_data.trigger_event}"
                ) from exc
        if rule_data.template_key is not None:
            rule.template_key = rule_data.template_key
        if rule_data.delay_hours is not None:
            rule.delay_hours = rule_data.delay_hours
        if rule_data.condition_query is not None:
            # SECURITY: Validate condition_query to prevent SQL injection
            validate_condition_query(rule_data.condition_query)
            rule.condition_query = rule_data.condition_query
        if rule_data.is_active is not None:
            rule.is_active = rule_data.is_active

        await db.commit()
        await db.refresh(rule)

        logger.info(
            "Email automation rule updated",
            extra={
                "rule_id": rule.id,
                "rule_name": rule.name,
                "is_active": rule.is_active,
                "actor_user_id": current_user.id,
            },
        )

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

        return ApiResponse(success=True, message="成功更新自動化規則", data=response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to update email automation rule",
            extra={"actor_user_id": current_user.id, "rule_id": rule_id},
        )
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="更新自動化規則失敗") from e


@router.delete("/{rule_id}")
async def delete_automation_rule(
    rule_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"找不到 ID 為 {rule_id} 的自動化規則")

        deleted_name = rule.name
        await db.delete(rule)
        await db.commit()

        logger.info(
            "Email automation rule deleted",
            extra={"rule_id": rule_id, "rule_name": deleted_name, "actor_user_id": current_user.id},
        )

        return ApiResponse(success=True, message="成功刪除自動化規則", data=None)

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to delete email automation rule",
            extra={"actor_user_id": current_user.id, "rule_id": rule_id},
        )
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="刪除自動化規則失敗") from e


@router.patch("/{rule_id}/toggle")
async def toggle_automation_rule(
    rule_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"找不到 ID 為 {rule_id} 的自動化規則")

        # SECURITY (#1223 A): re-validate before ACTIVATING. This endpoint used to
        # flip is_active without looking at condition_query, so a rule whose query
        # was written by a seed, a migration or direct DB access could be switched on
        # having never passed the validator. (Deactivating is always allowed — that
        # can only reduce what runs.)
        if not rule.is_active and rule.condition_query:
            validate_condition_query(rule.condition_query)

        # Toggle is_active
        rule.is_active = not rule.is_active

        await db.commit()
        await db.refresh(rule)

        logger.info(
            "Email automation rule toggled",
            extra={
                "rule_id": rule.id,
                "rule_name": rule.name,
                "is_active": rule.is_active,
                "actor_user_id": current_user.id,
            },
        )

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
            success=True, message=f"成功{'啟用' if rule.is_active else '停用'}自動化規則", data=response_data
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Failed to toggle email automation rule",
            extra={"actor_user_id": current_user.id, "rule_id": rule_id},
        )
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="切換自動化規則狀態失敗") from e


@router.get("/trigger-events")
async def get_trigger_events(current_user: User = Depends(require_admin)):
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

    return ApiResponse(success=True, message=f"成功獲取 {len(trigger_events)} 種觸發事件", data=trigger_events)

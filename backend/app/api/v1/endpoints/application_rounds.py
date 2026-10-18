"""
多梯次申請 administration endpoints.

A configuration's own application window is 第一梯次 (every sub-type). The admin opens
later rounds here, each with its own application window, the sub-types it accepts and
optional professor / college review windows. Mounted under /scholarship-configurations.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.endpoints.scholarship_configurations import get_user_accessible_scholarship_ids
from app.core.cache import invalidate
from app.core.security import require_admin
from app.db.deps import get_db
from app.models.application import Application
from app.models.application_round import ScholarshipApplicationRound
from app.models.audit_log import AuditAction, AuditLog
from app.models.scholarship import ScholarshipConfiguration
from app.models.user import User
from app.schemas.application_round import ApplicationRoundInput, ApplicationRoundsUpdate
from app.schemas.response import ApiResponse
from app.services.application_round_rules import ApplicationRoundRuleError, validate_rounds_against_config
from app.services.ranking_groups import round_label

logger = logging.getLogger(__name__)

router = APIRouter()

_ROUND_FIELDS = (
    "application_start_date",
    "application_end_date",
    "open_sub_types",
    "professor_review_start",
    "professor_review_end",
    "college_review_start",
    "college_review_end",
)


async def _load_accessible_config(db: AsyncSession, config_id: int, current_user: User) -> ScholarshipConfiguration:
    accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)
    stmt = (
        select(ScholarshipConfiguration)
        .where(
            and_(
                ScholarshipConfiguration.id == config_id,
                ScholarshipConfiguration.scholarship_type_id.in_(accessible_scholarship_ids),
            )
        )
        .options(
            selectinload(ScholarshipConfiguration.scholarship_type),
            selectinload(ScholarshipConfiguration.application_rounds),
        )
        # Re-read the rounds even when the configuration is already in the session.
        .execution_options(populate_existing=True)
    )
    config = (await db.execute(stmt)).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在或您沒有存取權限")
    return config


def _rounds_payload(config: ScholarshipConfiguration) -> Dict[str, Any]:
    return {
        "configuration_id": config.id,
        "first_round": {
            "round_number": 1,
            "application_start_date": (
                config.application_start_date.isoformat() if config.application_start_date else None
            ),
            "application_end_date": config.application_end_date.isoformat() if config.application_end_date else None,
        },
        "current_application_round": config.current_application_round,
        "available_sub_types": [
            code for code in (config.scholarship_type.sub_type_list or []) if code and code.lower() != "general"
        ],
        "rounds": [application_round.to_dict() for application_round in config.extra_application_rounds],
    }


def _validate_against_config(config: ScholarshipConfiguration, rounds: List[ApplicationRoundInput]) -> None:
    """Rounds follow round 1, open only the scholarship's sub-types and stay reviewable."""
    try:
        validate_rounds_against_config(config, rounds)
    except ApplicationRoundRuleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=exc.message) from exc


async def _assert_removed_rounds_unused(db: AsyncSession, config_id: int, removed_numbers: List[int]) -> None:
    """A round that already holds applications cannot be removed."""
    if not removed_numbers:
        return
    stmt = (
        select(Application.application_round, func.count(Application.id))
        .where(
            Application.scholarship_configuration_id == config_id,
            Application.application_round.in_(removed_numbers),
            Application.deleted_at.is_(None),
        )
        .group_by(Application.application_round)
    )
    used = {round_number: count for round_number, count in (await db.execute(stmt)).all() if count}
    if used:
        detail = "、".join(f"{round_label(number)}（{count} 件）" for number, count in sorted(used.items()))
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"以下梯次已有申請，無法刪除：{detail}")


@router.get("/configurations/{id}/application-rounds")
async def get_application_rounds(
    id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List a configuration's 申請梯次 (第一梯次 = its own application window)."""
    config = await _load_accessible_config(db, id, current_user)
    return ApiResponse(success=True, message="申請梯次取得成功", data=_rounds_payload(config))


@router.put("/configurations/{id}/application-rounds")
async def update_application_rounds(
    id: int,
    body: ApplicationRoundsUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Replace a configuration's later 申請梯次 (第二梯次起).

    Rounds missing from the body are removed (409 when a round already holds
    applications); an empty list turns the configuration back into a single round.
    """
    config = await _load_accessible_config(db, id, current_user)
    _validate_against_config(config, body.rounds)

    existing = {application_round.round_number: application_round for application_round in config.application_rounds}
    requested = {application_round.round_number: application_round for application_round in body.rounds}
    removed_numbers = sorted(set(existing) - set(requested))
    await _assert_removed_rounds_unused(db, config.id, removed_numbers)

    old_values = {"rounds": [application_round.to_dict() for application_round in config.extra_application_rounds]}

    for number in removed_numbers:
        config.application_rounds.remove(existing[number])
    for number, application_round_input in sorted(requested.items()):
        values = application_round_input.model_dump(include=set(_ROUND_FIELDS))
        row = existing.get(number)
        if row is None:
            config.application_rounds.append(
                ScholarshipApplicationRound(round_number=number, created_by=current_user.id, **values)
            )
            continue
        for field, value in values.items():
            setattr(row, field, value)
        row.updated_by = current_user.id

    config.updated_by = current_user.id
    await db.flush()
    await db.refresh(config, attribute_names=["application_rounds"])

    db.add(
        AuditLog.create_log(
            user_id=current_user.id,
            action=AuditAction.update.value,
            resource_type="scholarship_configuration",
            resource_id=str(config.id),
            description=f"update application rounds: {len(body.rounds)} extra round(s)",
            old_values=old_values,
            new_values={
                "rounds": [application_round.to_dict() for application_round in config.extra_application_rounds]
            },
        )
    )
    await db.commit()
    await db.refresh(config, attribute_names=["application_rounds"])

    try:
        await invalidate("formconfig:")
        await invalidate("quota:")
    except Exception:
        logger.warning("Failed to invalidate caches after updating application rounds", exc_info=True)

    return ApiResponse(success=True, message="申請梯次已更新", data=_rounds_payload(config))

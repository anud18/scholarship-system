"""Admin endpoint: system-wide audit-log viewer (issue #976 / audit gap G14).

Until now the only audit read path was a per-scholarship trail endpoint that
no frontend component consumed — answering「誰在某日刪了申請 X」meant raw
SQL against the database. This endpoint exposes audit_logs (paginated,
filterable) to admins so the trail is usable by the people responsible for
it; the 稽核日誌 tab in AdminManagementShell renders it.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.audit_log import AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/audit-logs")
async def list_audit_logs(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    resource_type: Optional[str] = Query(None, description="e.g. application / college_ranking / batch_import"),
    resource_id: Optional[str] = Query(None, description="Exact resource id (string match)"),
    action: Optional[str] = Query(None, description="AuditAction value, e.g. revoke / delete / import"),
    user_id: Optional[int] = Query(None, description="Acting user id"),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    search: Optional[str] = Query(None, description="Substring match on description / resource_name"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Paginated, filterable system-wide audit-log listing (admin only)."""
    stmt = select(
        AuditLog,
        User.name.label("actor_name"),
        User.nycu_id.label("actor_nycu_id"),
    ).outerjoin(User, AuditLog.user_id == User.id)

    if resource_type:
        stmt = stmt.where(AuditLog.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AuditLog.resource_id == str(resource_id))
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    if search:
        term = f"%{search}%"
        stmt = stmt.where(
            or_(
                AuditLog.description.ilike(term),
                AuditLog.resource_name.ilike(term),
                AuditLog.resource_id.ilike(term),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = stmt.order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size)
    rows = (await db.execute(stmt)).all()

    items = [
        {
            "id": log.id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "user_id": log.user_id,
            "actor_name": actor_name,
            "actor_nycu_id": actor_nycu_id,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "resource_name": log.resource_name,
            "description": log.description,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "status": log.status,
            "ip_address": log.ip_address,
            "meta_data": log.meta_data,
        }
        for log, actor_name, actor_nycu_id in rows
    ]

    return {
        "success": True,
        "message": "Audit logs retrieved successfully",
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "pages": (total + size - 1) // size,
        },
    }

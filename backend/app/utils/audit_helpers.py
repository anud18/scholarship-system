"""
Audit Logging Helper Functions

This module provides utility functions to simplify audit logging operations
and reduce code duplication across endpoints.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)


async def log_college_review_action(
    db: AsyncSession,
    user: User,
    action: AuditAction,
    resource_type: str,
    resource_id: str,
    description: str,
    new_values: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
    status: str = "success",
) -> AuditLog:
    """
    Log a college review action to the audit trail.

    This helper function consolidates common audit logging logic to reduce
    code duplication across endpoints.

    Args:
        db: Database session
        user: Current user performing the action
        action: The audit action being performed
        resource_type: Type of resource (e.g., "review", "ranking", "distribution")
        resource_id: ID of the resource
        description: Human-readable description of the action
        new_values: Dictionary of new values set by this action
        request: FastAPI Request object (used to extract IP and user agent)
        status: Status of the action (default: "success")

    Returns:
        The created AuditLog entry

    Example:
        audit_log = await log_college_review_action(
            db=db,
            user=current_user,
            action=AuditAction.execute_distribution,
            resource_type="distribution",
            resource_id=str(distribution.id),
            description=f"Executed distribution for ranking {ranking_id}",
            new_values={"total_allocated": 50},
            request=request,
        )
    """
    # Extract request metadata if available
    ip_address = None
    user_agent = None

    if request:
        try:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
        except Exception as e:
            logger.warning(f"Failed to extract request metadata: {e}")

    # Create and save audit log
    audit_log = AuditLog.create_log(
        user_id=user.id,
        action=action.value,
        resource_type=resource_type,
        resource_id=resource_id,
        description=description,
        new_values=new_values or {},
        ip_address=ip_address,
        user_agent=user_agent,
        status=status,
    )

    try:
        db.add(audit_log)
        await db.commit()
        logger.info(f"Audit log created for {action.value} by user {user.id} on {resource_type} {resource_id}")
        return audit_log
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
        await db.rollback()
        # Don't raise - audit logging should not break the operation
        raise


async def log_college_review_action_with_changes(
    db: AsyncSession,
    user: User,
    action: AuditAction,
    resource_type: str,
    resource_id: str,
    description: str,
    old_values: Optional[Dict[str, Any]] = None,
    new_values: Optional[Dict[str, Any]] = None,
    request: Optional[Request] = None,
    status: str = "success",
) -> AuditLog:
    """
    Log a college review action with before/after values for comparison.

    Similar to log_college_review_action but includes both old and new values
    for auditing purposes.

    Args:
        db: Database session
        user: Current user performing the action
        action: The audit action being performed
        resource_type: Type of resource
        resource_id: ID of the resource
        description: Human-readable description
        old_values: Dictionary of values before the change
        new_values: Dictionary of values after the change
        request: FastAPI Request object
        status: Status of the action (default: "success")

    Returns:
        The created AuditLog entry
    """
    # Combine old and new values for the audit record
    combined_values = {
        "old_values": old_values or {},
        "new_values": new_values or {},
    }

    # Extract request metadata if available
    ip_address = None
    user_agent = None

    if request:
        try:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
        except Exception as e:
            logger.warning(f"Failed to extract request metadata: {e}")

    # Create and save audit log
    audit_log = AuditLog.create_log(
        user_id=user.id,
        action=action.value,
        resource_type=resource_type,
        resource_id=resource_id,
        description=description,
        new_values=combined_values,
        ip_address=ip_address,
        user_agent=user_agent,
        status=status,
    )

    try:
        db.add(audit_log)
        await db.commit()
        logger.info(f"Audit log created for {action.value} by user {user.id} on {resource_type} {resource_id}")
        return audit_log
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
        await db.rollback()
        # Don't raise - audit logging should not break the operation
        raise

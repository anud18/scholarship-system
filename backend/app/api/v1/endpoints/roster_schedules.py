"""
Roster Schedule API endpoints
造冊排程管理 API 端點
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.functions import count

from app.core.deps import get_current_user
from app.core.security import check_user_roles
from app.db.deps import get_db
from app.models.roster_schedule import RosterSchedule, RosterScheduleStatus
from app.models.user import User, UserRole
from app.schemas.response import ApiResponse
from app.schemas.roster_schedule import (
    RosterScheduleCreate,
    RosterScheduleResponse,
    RosterScheduleStatusUpdate,
    RosterScheduleUpdate,
)
from app.services.roster_scheduler_service import roster_scheduler

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_roster_schedules(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    status_filter: Optional[RosterScheduleStatus] = Query(None, description="Filter by status"),
    scholarship_configuration_id: Optional[int] = Query(None, description="Filter by scholarship configuration"),
    search: Optional[str] = Query(None, description="Search in schedule name"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    列出造冊排程
    List roster schedules with filtering and pagination
    """
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    try:
        # Build query
        stmt = select(RosterSchedule)

        # Apply filters
        if status_filter:
            stmt = stmt.where(RosterSchedule.status == status_filter)

        if scholarship_configuration_id:
            stmt = stmt.where(RosterSchedule.scholarship_configuration_id == scholarship_configuration_id)

        if search:
            search_term = f"%{search}%"
            stmt = stmt.where(
                or_(RosterSchedule.schedule_name.ilike(search_term), RosterSchedule.description.ilike(search_term))
            )

        # Get total count
        count_stmt = select(count()).select_from(stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar()

        # Apply pagination and ordering
        stmt = stmt.order_by(RosterSchedule.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(stmt)
        schedules = result.scalars().all()

        # Get scheduler status for each schedule
        schedule_data = []
        for schedule in schedules:
            schedule_dict = schedule.to_dict()

            # Get scheduler status
            scheduler_status = roster_scheduler.get_schedule_status(schedule.id)
            if scheduler_status:
                schedule_dict["scheduler_info"] = scheduler_status
            else:
                schedule_dict["scheduler_info"] = None

            schedule_data.append(schedule_dict)

        return ApiResponse(
            success=True,
            message="查詢成功",
            data={
                "items": schedule_data,
                "total": total or 0,
                "skip": skip,
                "limit": limit,
            },
        )

    except Exception as e:
        logger.error(f"Error listing roster schedules: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list roster schedules")


@router.post("")
async def create_roster_schedule(
    schedule_data: RosterScheduleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    建立新的造冊排程
    Create a new roster schedule
    """
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    try:
        # Validate cron expression if provided
        if schedule_data.cron_expression:
            from croniter import croniter

            if not croniter.is_valid(schedule_data.cron_expression):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cron expression")

        # Check if scholarship configuration exists
        from app.models.scholarship import ScholarshipConfiguration

        stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.id == schedule_data.scholarship_configuration_id
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scholarship configuration not found")

        # Create new schedule
        new_schedule = RosterSchedule(
            schedule_name=schedule_data.schedule_name,
            description=schedule_data.description,
            scholarship_configuration_id=schedule_data.scholarship_configuration_id,
            roster_cycle=schedule_data.roster_cycle,
            cron_expression=schedule_data.cron_expression,
            auto_lock=schedule_data.auto_lock,
            student_verification_enabled=schedule_data.student_verification_enabled,
            notification_enabled=schedule_data.notification_enabled,
            notification_emails=schedule_data.notification_emails,
            notification_settings=schedule_data.notification_settings,
            created_by_user_id=current_user.id,
            created_at=datetime.utcnow(),
        )

        db.add(new_schedule)
        await db.commit()
        await db.refresh(new_schedule)

        # Add to scheduler if active and has cron expression
        if new_schedule.status == RosterScheduleStatus.ACTIVE and new_schedule.cron_expression:
            schedule_dict = new_schedule.to_dict()
            success = await roster_scheduler.add_schedule(schedule_dict)
            if not success:
                logger.warning(f"Failed to add schedule {new_schedule.id} to scheduler")

        logger.info(f"Created roster schedule {new_schedule.id} by user {current_user.id}")

        response_data = RosterScheduleResponse(**new_schedule.to_dict())
        return ApiResponse(
            success=True,
            message="建立成功",
            data=response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict(),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating roster schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create roster schedule"
        )


@router.get("/{schedule_id}")
async def get_roster_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    取得特定造冊排程詳情
    Get specific roster schedule details
    """
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    stmt = select(RosterSchedule).where(RosterSchedule.id == schedule_id)
    result = await db.execute(stmt)
    schedule = result.scalar_one_or_none()

    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roster schedule not found")

    # Get scheduler status
    schedule_dict = schedule.to_dict()
    scheduler_status = roster_scheduler.get_schedule_status(schedule.id)
    if scheduler_status:
        schedule_dict["scheduler_info"] = scheduler_status

    response_data = RosterScheduleResponse(**schedule_dict)
    return ApiResponse(
        success=True,
        message="查詢成功",
        data=response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict(),
    )


@router.put("/{schedule_id}")
async def update_roster_schedule(
    schedule_id: int,
    schedule_data: RosterScheduleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新造冊排程
    Update roster schedule
    """
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    try:
        stmt = select(RosterSchedule).where(RosterSchedule.id == schedule_id)
        result = await db.execute(stmt)
        schedule = result.scalar_one_or_none()

        if not schedule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roster schedule not found")

        # Validate cron expression if provided
        if schedule_data.cron_expression:
            from croniter import croniter

            if not croniter.is_valid(schedule_data.cron_expression):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cron expression")

        # Update fields
        update_data = schedule_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(schedule, field, value)

        schedule.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(schedule)

        # Update scheduler if needed
        if schedule.status == RosterScheduleStatus.ACTIVE and schedule.cron_expression:
            schedule_dict = schedule.to_dict()
            success = await roster_scheduler.add_schedule(schedule_dict)  # This will replace existing
            if not success:
                logger.warning(f"Failed to update schedule {schedule_id} in scheduler")
        else:
            # Remove from scheduler if not active
            await roster_scheduler.remove_schedule(schedule_id)

        logger.info(f"Updated roster schedule {schedule_id} by user {current_user.id}")

        response_data = RosterScheduleResponse(**schedule.to_dict())
        return ApiResponse(
            success=True,
            message="更新成功",
            data=response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict(),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating roster schedule {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update roster schedule"
        )


@router.patch("/{schedule_id}/status")
async def update_schedule_status(
    schedule_id: int,
    status_data: RosterScheduleStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新排程狀態
    Update schedule status (active, paused, disabled)
    """
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    try:
        stmt = select(RosterSchedule).where(RosterSchedule.id == schedule_id)
        result = await db.execute(stmt)
        schedule = result.scalar_one_or_none()

        if not schedule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roster schedule not found")

        old_status = schedule.status
        schedule.status = status_data.status
        schedule.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(schedule)

        # Handle scheduler operations based on status change
        if status_data.status == RosterScheduleStatus.ACTIVE:
            if old_status == RosterScheduleStatus.PAUSED:
                await roster_scheduler.resume_schedule(schedule_id)
            else:
                # Add to scheduler
                if schedule.cron_expression:
                    schedule_dict = schedule.to_dict()
                    await roster_scheduler.add_schedule(schedule_dict)

        elif status_data.status == RosterScheduleStatus.PAUSED:
            await roster_scheduler.pause_schedule(schedule_id)

        elif status_data.status == RosterScheduleStatus.DISABLED:
            await roster_scheduler.remove_schedule(schedule_id)

        logger.info(f"Updated schedule {schedule_id} status from {old_status} to {status_data.status}")

        response_data = RosterScheduleResponse(**schedule.to_dict())
        return ApiResponse(
            success=True,
            message="狀態更新成功",
            data=response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict(),
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating schedule status {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update schedule status"
        )


@router.delete("/{schedule_id}")
async def delete_roster_schedule(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    刪除造冊排程
    Delete roster schedule
    """
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    try:
        stmt = select(RosterSchedule).where(RosterSchedule.id == schedule_id)
        result = await db.execute(stmt)
        schedule = result.scalar_one_or_none()

        if not schedule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roster schedule not found")

        # Remove from scheduler
        await roster_scheduler.remove_schedule(schedule_id)

        # Delete from database
        db.delete(schedule)
        await db.commit()

        logger.info(f"Deleted roster schedule {schedule_id} by user {current_user.id}")

        return ApiResponse(success=True, message="Roster schedule deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting roster schedule {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete roster schedule"
        )


@router.post("/{schedule_id}/execute")
async def execute_schedule_now(
    schedule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    立即執行排程
    Execute schedule immediately (manual trigger)
    """
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    try:
        stmt = select(RosterSchedule).where(RosterSchedule.id == schedule_id)
        result = await db.execute(stmt)
        schedule = result.scalar_one_or_none()

        if not schedule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roster schedule not found")

        # Execute immediately in background
        await roster_scheduler._execute_roster_generation(schedule_id)

        logger.info(f"Manually triggered schedule {schedule_id} by user {current_user.id}")

        return ApiResponse(
            success=True,
            message="Schedule execution triggered successfully",
            data={"schedule_id": schedule_id},
        )

    except Exception as e:
        logger.error(f"Error executing schedule {schedule_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to execute schedule")


@router.get("/scheduler/status")
async def get_scheduler_status(
    current_user: User = Depends(get_current_user),
):
    """
    取得排程器狀態
    Get scheduler status and all active jobs
    """
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    try:
        jobs = roster_scheduler.list_all_jobs()
        scheduler = roster_scheduler.scheduler

        # Get scheduler state
        scheduler_running = scheduler.running if scheduler else False
        scheduler_state = "running" if scheduler_running else "stopped"

        # Count active and pending jobs
        active_jobs = sum(1 for job in jobs if job.get("next_run_time"))
        pending_jobs = len(jobs) - active_jobs

        # Get executor info (APScheduler default)
        executor_info = {"class": "ThreadPoolExecutor", "max_workers": 10, "current_workers": 0}

        # Get jobstore info
        jobstore_info = {"class": "MemoryJobStore", "connected": scheduler_running}

        return ApiResponse(
            success=True,
            message="Scheduler status retrieved successfully",
            data={
                "scheduler_running": scheduler_running,
                "scheduler_state": scheduler_state,
                "job_count": len(jobs),
                "active_jobs": active_jobs,
                "pending_jobs": pending_jobs,
                "executor_info": executor_info,
                "jobstore_info": jobstore_info,
                "jobs": jobs,
            },
        )

    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get scheduler status")

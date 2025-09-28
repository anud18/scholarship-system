"""
Roster Schedule API endpoints
造冊排程管理 API 端點
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import check_user_roles
from app.db.deps import get_db
from app.models.roster_schedule import RosterSchedule, RosterScheduleStatus
from app.models.user import User, UserRole
from app.schemas.roster_schedule import (
    RosterScheduleCreate,
    RosterScheduleListResponse,
    RosterScheduleResponse,
    RosterScheduleStatusUpdate,
    RosterScheduleUpdate,
)
from app.services.roster_scheduler_service import roster_scheduler

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=RosterScheduleListResponse)
async def list_roster_schedules(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    status: Optional[RosterScheduleStatus] = Query(None, description="Filter by status"),
    scholarship_configuration_id: Optional[int] = Query(None, description="Filter by scholarship configuration"),
    search: Optional[str] = Query(None, description="Search in schedule name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    列出造冊排程
    List roster schedules with filtering and pagination
    """
    check_user_roles([UserRole.ADMIN, UserRole.SCHOLARSHIP_MANAGER], current_user)

    try:
        # Build query
        query = db.query(RosterSchedule)

        # Apply filters
        if status:
            query = query.filter(RosterSchedule.status == status)

        if scholarship_configuration_id:
            query = query.filter(RosterSchedule.scholarship_configuration_id == scholarship_configuration_id)

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(RosterSchedule.schedule_name.ilike(search_term), RosterSchedule.description.ilike(search_term))
            )

        # Get total count
        total = query.count()

        # Apply pagination and ordering
        schedules = query.order_by(RosterSchedule.created_at.desc()).offset(skip).limit(limit).all()

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

        return RosterScheduleListResponse(schedules=schedule_data, total=total, skip=skip, limit=limit)

    except Exception as e:
        logger.error(f"Error listing roster schedules: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list roster schedules")


@router.post("/", response_model=RosterScheduleResponse)
async def create_roster_schedule(
    schedule_data: RosterScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    建立新的造冊排程
    Create a new roster schedule
    """
    check_user_roles([UserRole.ADMIN, UserRole.SCHOLARSHIP_MANAGER], current_user)

    try:
        # Validate cron expression if provided
        if schedule_data.cron_expression:
            from croniter import croniter

            if not croniter.is_valid(schedule_data.cron_expression):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid cron expression")

        # Check if scholarship configuration exists
        from app.models.scholarship import ScholarshipConfiguration

        config = (
            db.query(ScholarshipConfiguration)
            .filter(ScholarshipConfiguration.id == schedule_data.scholarship_configuration_id)
            .first()
        )

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
        db.commit()
        db.refresh(new_schedule)

        # Add to scheduler if active and has cron expression
        if new_schedule.status == RosterScheduleStatus.ACTIVE and new_schedule.cron_expression:
            schedule_dict = new_schedule.to_dict()
            success = await roster_scheduler.add_schedule(schedule_dict)
            if not success:
                logger.warning(f"Failed to add schedule {new_schedule.id} to scheduler")

        logger.info(f"Created roster schedule {new_schedule.id} by user {current_user.id}")

        return RosterScheduleResponse(**new_schedule.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating roster schedule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create roster schedule"
        )


@router.get("/{schedule_id}", response_model=RosterScheduleResponse)
async def get_roster_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    取得特定造冊排程詳情
    Get specific roster schedule details
    """
    check_user_roles([UserRole.ADMIN, UserRole.SCHOLARSHIP_MANAGER], current_user)

    schedule = db.query(RosterSchedule).filter(RosterSchedule.id == schedule_id).first()

    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roster schedule not found")

    # Get scheduler status
    schedule_dict = schedule.to_dict()
    scheduler_status = roster_scheduler.get_schedule_status(schedule.id)
    if scheduler_status:
        schedule_dict["scheduler_info"] = scheduler_status

    return RosterScheduleResponse(**schedule_dict)


@router.put("/{schedule_id}", response_model=RosterScheduleResponse)
async def update_roster_schedule(
    schedule_id: int,
    schedule_data: RosterScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新造冊排程
    Update roster schedule
    """
    check_user_roles([UserRole.ADMIN, UserRole.SCHOLARSHIP_MANAGER], current_user)

    try:
        schedule = db.query(RosterSchedule).filter(RosterSchedule.id == schedule_id).first()

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

        db.commit()
        db.refresh(schedule)

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

        return RosterScheduleResponse(**schedule.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating roster schedule {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update roster schedule"
        )


@router.patch("/{schedule_id}/status", response_model=RosterScheduleResponse)
async def update_schedule_status(
    schedule_id: int,
    status_data: RosterScheduleStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新排程狀態
    Update schedule status (active, paused, disabled)
    """
    check_user_roles([UserRole.ADMIN, UserRole.SCHOLARSHIP_MANAGER], current_user)

    try:
        schedule = db.query(RosterSchedule).filter(RosterSchedule.id == schedule_id).first()

        if not schedule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roster schedule not found")

        old_status = schedule.status
        schedule.status = status_data.status
        schedule.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(schedule)

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

        return RosterScheduleResponse(**schedule.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating schedule status {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update schedule status"
        )


@router.delete("/{schedule_id}")
async def delete_roster_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    刪除造冊排程
    Delete roster schedule
    """
    check_user_roles([UserRole.ADMIN], current_user)

    try:
        schedule = db.query(RosterSchedule).filter(RosterSchedule.id == schedule_id).first()

        if not schedule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roster schedule not found")

        # Remove from scheduler
        await roster_scheduler.remove_schedule(schedule_id)

        # Delete from database
        db.delete(schedule)
        db.commit()

        logger.info(f"Deleted roster schedule {schedule_id} by user {current_user.id}")

        return {"success": True, "message": "Roster schedule deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting roster schedule {schedule_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete roster schedule"
        )


@router.post("/{schedule_id}/execute")
async def execute_schedule_now(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    立即執行排程
    Execute schedule immediately (manual trigger)
    """
    check_user_roles([UserRole.ADMIN, UserRole.SCHOLARSHIP_MANAGER], current_user)

    try:
        schedule = db.query(RosterSchedule).filter(RosterSchedule.id == schedule_id).first()

        if not schedule:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roster schedule not found")

        # Execute immediately in background
        await roster_scheduler._execute_roster_generation(schedule_id)

        logger.info(f"Manually triggered schedule {schedule_id} by user {current_user.id}")

        return {"success": True, "message": "Schedule execution triggered successfully", "schedule_id": schedule_id}

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
    check_user_roles([UserRole.ADMIN, UserRole.SCHOLARSHIP_MANAGER], current_user)

    try:
        jobs = roster_scheduler.list_all_jobs()

        return {
            "success": True,
            "scheduler_running": roster_scheduler.scheduler.running if roster_scheduler.scheduler else False,
            "total_jobs": len(jobs),
            "jobs": jobs,
        }

    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get scheduler status")

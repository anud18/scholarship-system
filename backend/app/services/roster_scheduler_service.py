"""
Roster Scheduler Service
造冊排程服務 - 使用APScheduler進行自動造冊排程
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from croniter import croniter
from sqlalchemy import select

from app.core.config import settings
from app.db.session import get_db_session
from app.models.payment_roster import RosterCycle, RosterTriggerType
from app.models.roster_schedule import RosterSchedule, RosterScheduleStatus
from app.services.roster_service import RosterService

logger = logging.getLogger(__name__)


class RosterSchedulerService:
    """造冊排程服務"""

    def __init__(self):
        self.scheduler: Optional[AsyncIOScheduler] = None
        # RosterService will be instantiated with db session when needed
        self._setup_scheduler()

    def _setup_scheduler(self):
        """設定APScheduler"""
        # 設定Redis作為Job Store
        jobstores = {
            "default": RedisJobStore(
                host=settings.redis_url.split("://")[1].split(":")[0],
                port=int(settings.redis_url.split(":")[-1].split("/")[0]),
                db=1,  # 使用不同的Redis資料庫避免衝突
                password=None,
            )
        }

        # 設定Executor
        executors = {"default": AsyncIOExecutor()}

        # Job預設設定
        job_defaults = {
            "coalesce": True,  # 合併延遲的作業
            "max_instances": 1,  # 每個作業最多一個實例
            "misfire_grace_time": 30,  # 錯過作業的容錯時間(秒)
        }

        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores, executors=executors, job_defaults=job_defaults, timezone=timezone.utc
        )

        # 設定事件監聽器
        self.scheduler.add_listener(self._job_executed_listener, EVENT_JOB_EXECUTED)
        self.scheduler.add_listener(self._job_error_listener, EVENT_JOB_ERROR)
        self.scheduler.add_listener(self._job_missed_listener, EVENT_JOB_MISSED)

    async def start_scheduler(self):
        """啟動排程器"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Roster scheduler started")

            # 載入現有的排程
            await self.load_active_schedules()
        else:
            logger.warning("Scheduler is already running")

    async def stop_scheduler(self):
        """停止排程器"""
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Roster scheduler stopped")

    async def load_active_schedules(self):
        """載入啟用中的排程"""
        try:
            async with get_db_session() as db:
                result = await db.execute(
                    select(RosterSchedule).where(RosterSchedule.status == RosterScheduleStatus.ACTIVE)
                )
                schedules = result.scalars().all()

                for schedule in schedules:
                    await self._add_schedule_job(schedule.to_dict())

                logger.info("Loaded %s active schedules", len(schedules))

        except Exception as e:
            logger.error(f"Failed to load active schedules: {e}")

    async def _add_schedule_job(self, schedule_data: Dict):
        """添加排程作業"""
        try:
            schedule_id = schedule_data["id"]
            cron_expression = schedule_data["cron_expression"]

            if not cron_expression:
                logger.warning(f"Schedule {schedule_id} has no cron expression")
                return

            # 驗證Cron表達式
            if not croniter.is_valid(cron_expression):
                logger.error(f"Invalid cron expression for schedule {schedule_id}: {cron_expression}")
                return

            # 添加作業到排程器
            job_id = f"roster_schedule_{schedule_id}"

            # 移除現有作業（如果存在）
            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)

            # 使用CronTrigger添加作業
            self.scheduler.add_job(
                func=self._execute_roster_generation,
                trigger="cron",
                id=job_id,
                args=[schedule_id],
                **self._parse_cron_expression(cron_expression),
                replace_existing=True,
                timezone=timezone.utc,
            )

            logger.info(f"Added schedule job: {job_id} with cron: {cron_expression}")

        except Exception as e:
            logger.error(f"Failed to add schedule job: {e}")

    def _parse_cron_expression(self, cron_expr: str) -> Dict[str, Any]:
        """解析Cron表達式為APScheduler參數"""
        # 標準Cron格式: 分 時 日 月 星期
        # APScheduler支援: second, minute, hour, day, month, day_of_week, year

        parts = cron_expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression format: {cron_expr}")

        minute, hour, day, month, day_of_week = parts

        return {"minute": minute, "hour": hour, "day": day, "month": month, "day_of_week": day_of_week}

    async def _execute_roster_generation(self, schedule_id: int):
        """執行造冊產生"""
        logger.info(f"Executing roster generation for schedule {schedule_id}")

        error_message = None
        success = False

        try:
            async with get_db_session() as db:
                # 更新排程執行狀態
                await self._update_schedule_execution_start(db, schedule_id)

                # 取得排程配置
                schedule = await self._get_schedule_by_id(db, schedule_id)
                if not schedule:
                    raise Exception(f"Schedule {schedule_id} not found")

                # 執行造冊產生
                result = await self._create_roster_from_schedule(schedule)

                if result and result.get("success"):
                    success = True
                    logger.info(f"Roster generation completed for schedule {schedule_id}: {result.get('roster_id')}")
                else:
                    error_message = result.get("error", "Unknown error occurred")

        except Exception as e:
            error_message = str(e)
            logger.error(f"Roster generation failed for schedule {schedule_id}: {e}")

        finally:
            # 更新排程執行結果
            try:
                async with get_db_session() as db:
                    await self._update_schedule_execution_result(db, schedule_id, success, error_message)
            except Exception as e:
                logger.error(f"Failed to update schedule execution result: {e}")

    async def _update_schedule_execution_start(self, db, schedule_id: int):
        """更新排程開始執行"""
        schedule = await db.get(RosterSchedule, schedule_id)
        if not schedule:
            logger.warning("Schedule %s not found when marking execution start", schedule_id)
            return

        schedule.last_run_at = datetime.now(timezone.utc)
        schedule.next_run_at = None
        await db.commit()

    async def _update_schedule_execution_result(
        self, db, schedule_id: int, success: bool, error_message: Optional[str]
    ):
        """更新排程執行結果"""
        schedule = await db.get(RosterSchedule, schedule_id)
        if not schedule:
            logger.warning("Schedule %s not found when updating execution result", schedule_id)
            return

        schedule.total_runs = (schedule.total_runs or 0) + 1

        if success:
            schedule.successful_runs = (schedule.successful_runs or 0) + 1
            schedule.last_run_result = "success"
            schedule.last_error_message = None
            if schedule.status == RosterScheduleStatus.ERROR:
                schedule.status = RosterScheduleStatus.ACTIVE
        else:
            schedule.failed_runs = (schedule.failed_runs or 0) + 1
            schedule.last_run_result = "failed"
            schedule.last_error_message = error_message
            schedule.status = RosterScheduleStatus.ERROR

        await db.commit()

    async def _create_roster_from_schedule(self, schedule: Dict) -> Dict:
        """從排程建立造冊"""
        try:
            # 取得當前學年度（這裡需要根據系統邏輯調整）
            from datetime import datetime

            current_year = datetime.now().year

            # 根據月份判斷學年度（假設9月開始新學年）
            academic_year = current_year if datetime.now().month >= 9 else current_year - 1

            # 轉換 roster_cycle 字串為 enum
            roster_cycle_value = schedule["roster_cycle"]
            if isinstance(roster_cycle_value, str):
                roster_cycle = RosterCycle(roster_cycle_value)
            else:
                roster_cycle = roster_cycle_value

            # 產生期間標記
            with get_db_session() as db:
                roster_service = RosterService(db)

                # 從排程產生期間標記
                period_label = roster_service.generate_period_label(
                    roster_cycle=roster_cycle, target_date=datetime.now()
                )

                # 呼叫 RosterService 建立造冊
                roster = roster_service.generate_roster(
                    scholarship_configuration_id=schedule["scholarship_configuration_id"],
                    period_label=period_label,
                    roster_cycle=roster_cycle,
                    academic_year=academic_year + 113,  # 轉換為民國年
                    created_by_user_id=schedule["created_by_user_id"],
                    trigger_type=RosterTriggerType.SCHEDULED,
                    student_verification_enabled=schedule.get("student_verification_enabled", True),
                    force_regenerate=False,
                )

                return {
                    "success": True,
                    "roster_id": roster.id,
                    "roster_code": roster.roster_code,
                    "message": f"Successfully created roster {roster.roster_code}",
                }

        except Exception as e:
            logger.error(f"Failed to create roster from schedule: {e}")
            return {"success": False, "error": str(e), "message": f"Failed to create roster: {e}"}

    async def _get_schedule_by_id(self, db, schedule_id: int) -> Optional[Dict]:
        """根據ID取得排程"""
        result = await db.execute(select(RosterSchedule).where(RosterSchedule.id == schedule_id))
        schedule = result.scalar_one_or_none()
        return schedule.to_dict() if schedule else None

    async def add_schedule(self, schedule_data: Dict) -> bool:
        """添加新排程"""
        try:
            # 驗證Cron表達式
            cron_expr = schedule_data.get("cron_expression")
            if cron_expr and not croniter.is_valid(cron_expr):
                raise ValueError(f"Invalid cron expression: {cron_expr}")

            # 添加到排程器
            await self._add_schedule_job(schedule_data)

            return True

        except Exception as e:
            logger.error(f"Failed to add schedule: {e}")
            return False

    async def remove_schedule(self, schedule_id: int) -> bool:
        """移除排程"""
        try:
            job_id = f"roster_schedule_{schedule_id}"

            if self.scheduler.get_job(job_id):
                self.scheduler.remove_job(job_id)
                logger.info(f"Removed schedule job: {job_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to remove schedule: {e}")
            return False

    async def pause_schedule(self, schedule_id: int) -> bool:
        """暫停排程"""
        try:
            job_id = f"roster_schedule_{schedule_id}"

            if self.scheduler.get_job(job_id):
                self.scheduler.pause_job(job_id)
                logger.info(f"Paused schedule job: {job_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to pause schedule: {e}")
            return False

    async def resume_schedule(self, schedule_id: int) -> bool:
        """恢復排程"""
        try:
            job_id = f"roster_schedule_{schedule_id}"

            if self.scheduler.get_job(job_id):
                self.scheduler.resume_job(job_id)
                logger.info(f"Resumed schedule job: {job_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to resume schedule: {e}")
            return False

    def get_schedule_status(self, schedule_id: int) -> Optional[Dict]:
        """取得排程狀態"""
        try:
            job_id = f"roster_schedule_{schedule_id}"
            job = self.scheduler.get_job(job_id)

            if job:
                return {
                    "job_id": job.id,
                    "next_run_time": job.next_run_time,
                    "trigger": str(job.trigger),
                    "pending": job.pending,
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get schedule status: {e}")
            return None

    def list_all_jobs(self) -> List[Dict]:
        """列出所有作業"""
        try:
            jobs = []
            for job in self.scheduler.get_jobs():
                jobs.append(
                    {
                        "id": job.id,
                        "name": job.name,
                        "next_run_time": job.next_run_time,
                        "trigger": str(job.trigger),
                        "pending": job.pending,
                    }
                )
            return jobs

        except Exception as e:
            logger.error(f"Failed to list jobs: {e}")
            return []

    def _job_executed_listener(self, event):
        """作業執行完成監聽器"""
        logger.info(f"Job {event.job_id} executed successfully")

    def _job_error_listener(self, event):
        """作業執行錯誤監聽器"""
        logger.error(f"Job {event.job_id} failed: {event.exception}")

    def _job_missed_listener(self, event):
        """作業錯過執行監聽器"""
        logger.warning(f"Job {event.job_id} was missed")


# 全局排程器實例
roster_scheduler = RosterSchedulerService()


@asynccontextmanager
async def get_scheduler():
    """取得排程器實例"""
    yield roster_scheduler


async def cleanup_expired_batch_data():
    """
    Clean up expired batch import data (scheduled job).
    Runs daily to delete parsed_data older than 7 days.
    """
    from app.db.session import get_db_session
    from app.services.batch_import_service import BatchImportService

    try:
        async with get_db_session() as db:
            service = BatchImportService(db)
            count = await service.cleanup_expired_data()
            if count > 0:
                logger.info(f"Cleaned up expired data from {count} batch imports")
            else:
                logger.debug("No expired batch import data to clean up")
    except Exception as e:
        logger.error(f"Failed to cleanup expired batch data: {e}")


async def init_scheduler():
    """初始化排程器"""
    await roster_scheduler.start_scheduler()

    # Add daily cleanup job for batch import data (runs at 2 AM daily)
    try:
        roster_scheduler.scheduler.add_job(
            cleanup_expired_batch_data,
            "cron",
            hour=2,
            minute=0,
            id="batch_import_cleanup",
            replace_existing=True,
            name="Batch Import Data Cleanup",
        )
        logger.info("Added batch import cleanup job (runs daily at 2 AM)")
    except Exception as e:
        logger.error(f"Failed to add batch import cleanup job: {e}")

    # Add deadline checker job (runs at 9 AM daily)
    try:
        from app.tasks.deadline_checker import run_deadline_check

        roster_scheduler.scheduler.add_job(
            run_deadline_check,
            "cron",
            hour=9,
            minute=0,
            id="deadline_checker",
            replace_existing=True,
            name="Deadline Checker",
        )
        logger.info("Added deadline checker job (runs daily at 9 AM)")
    except Exception as e:
        logger.error(f"Failed to add deadline checker job: {e}")

    # Add email processor job with configurable interval
    # Note: The job itself has startup delay protection (see email_processor.py)
    try:
        from app.services.config_management_service import ConfigurationService
        from app.tasks.email_processor import run_email_processor

        # Get email processor interval from system settings (default 60 seconds)
        interval_seconds = 60  # Default fallback
        try:
            async with get_db_session() as db:
                config_service = ConfigurationService(db)
                interval_config = await config_service.get_configuration("email_processor_interval_seconds")
                if interval_config and interval_config.value:
                    interval_seconds = int(interval_config.value)
                    logger.info(f"Email processor interval configured to {interval_seconds} seconds")
                else:
                    logger.info(f"Using default email processor interval: {interval_seconds} seconds")
        except Exception as e:
            logger.warning(
                f"Failed to read email processor interval from settings, using default {interval_seconds}s: {e}"
            )

        roster_scheduler.scheduler.add_job(
            run_email_processor,
            "interval",
            seconds=interval_seconds,
            id="email_processor",
            replace_existing=True,
            name="Email Processor",
        )
        logger.info(f"Added email processor job (runs every {interval_seconds} seconds with startup protection)")
    except Exception as e:
        logger.error(f"Failed to add email processor job: {e}")


async def shutdown_scheduler():
    """關閉排程器"""
    await roster_scheduler.stop_scheduler()

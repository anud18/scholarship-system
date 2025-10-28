"""
College Review Service

This service handles college-level review operations including:
- Application ranking and scoring
- Quota-based distribution
- Review workflow management
- Integration with GitHub issue creation
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, asc, case
from sqlalchemy import func as sa_func
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BusinessLogicError, NotFoundError
from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem, QuotaDistribution
from app.models.enums import Semester
from app.models.review import ApplicationReview  # Unified review system
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.services.email_automation_service import email_automation_service

func: Any = sa_func

logger = logging.getLogger(__name__)


# Custom exceptions for college review operations
class CollegeReviewError(Exception):
    """Base exception for college review operations"""

    pass


class RankingNotFoundError(CollegeReviewError):
    """Raised when a ranking is not found"""

    pass


class RankingModificationError(CollegeReviewError):
    """Raised when attempting to modify a finalized ranking"""

    pass


class InvalidRankingDataError(CollegeReviewError):
    """Raised when ranking data is invalid"""

    pass


class ReviewPermissionError(CollegeReviewError):
    """Raised when user lacks permission for review operation"""

    pass


class CollegeReviewService:
    """Service for managing college-level reviews and rankings"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_ranking_roster_status(self, ranking_id: int) -> Dict[str, Any]:
        """
        檢查排名是否已開始造冊
        Returns:
            {
                "has_roster": bool,
                "can_redistribute": bool,
                "roster_info": {...} or None,
                "roster_statistics": {...} or None
            }
        """
        from app.models.payment_roster import PaymentRoster, RosterStatus

        stmt = (
            select(PaymentRoster)
            .where(PaymentRoster.ranking_id == ranking_id)
            .order_by(PaymentRoster.created_at.desc())
        )

        result = await self.db.execute(stmt)
        roster = result.scalar_one_or_none()

        if not roster:
            return {"has_roster": False, "can_redistribute": True, "roster_info": None, "roster_statistics": None}

        # 如果造冊狀態是 draft 或 failed，視為可以重新分發
        can_redistribute = roster.status in [RosterStatus.DRAFT, RosterStatus.FAILED]

        # 計算統計資訊：查詢同一 scholarship_configuration_id 下的所有造冊
        stats_stmt = select(PaymentRoster).where(
            and_(
                PaymentRoster.scholarship_configuration_id == roster.scholarship_configuration_id,
                PaymentRoster.status.in_([RosterStatus.COMPLETED, RosterStatus.LOCKED]),
            )
        )
        stats_result = await self.db.execute(stats_stmt)
        completed_rosters = stats_result.scalars().all()

        # 計算預期總期數（根據週期類型）
        expected_total_periods = self._calculate_expected_periods(roster.roster_cycle, roster.academic_year)
        total_periods_completed = len(completed_rosters)
        completion_rate = (total_periods_completed / expected_total_periods * 100) if expected_total_periods > 0 else 0

        return {
            "has_roster": True,
            "can_redistribute": can_redistribute,
            "roster_info": {
                "roster_code": roster.roster_code,
                "status": roster.status.value,
                "roster_cycle": roster.roster_cycle.value,
                "period_label": roster.period_label,
                "created_at": roster.created_at.isoformat(),
                "completed_at": roster.completed_at.isoformat() if roster.completed_at else None,
            },
            "roster_statistics": {
                "total_periods_completed": total_periods_completed,
                "expected_total_periods": expected_total_periods,
                "completion_rate": round(completion_rate, 1),
            },
        }

    def _calculate_expected_periods(self, roster_cycle, academic_year: int) -> int:
        """
        根據造冊週期計算預期總期數

        Args:
            roster_cycle: 造冊週期枚舉
            academic_year: 學年度

        Returns:
            int: 預期總期數
        """
        from app.models.payment_roster import RosterCycle

        if roster_cycle == RosterCycle.MONTHLY:
            return 12  # 按月造冊，一年 12 個月
        elif roster_cycle == RosterCycle.SEMI_YEARLY:
            return 2  # 按半年造冊，一年 2 期
        elif roster_cycle == RosterCycle.YEARLY:
            return 1  # 按年造冊，一年 1 期
        else:
            return 1  # 預設為 1

    async def auto_redistribute_after_status_change(self, application_id: int, executor_id: int) -> Dict[str, Any]:
        """
        Check and execute auto-redistribution for ALL rankings under the scholarship configuration.

        When an application's status changes, this redistributes ALL rankings that share the same
        scholarship_type_id, academic_year, and semester to ensure quota allocation consistency.

        Args:
            application_id: ID of the application whose status changed
            executor_id: ID of the user who triggered the status change

        Returns:
            Dict containing:
            - auto_redistributed: bool - Whether any redistribution was executed
            - total_allocated: int - Total number of students allocated across all rankings
            - rankings_processed: int - Number of rankings processed
            - results: list - List of results for each ranking
            - reason: str - Reason for redistribution or skip
        """
        # Get application information
        app_stmt = select(Application).where(Application.id == application_id)
        app_result = await self.db.execute(app_stmt)
        application = app_result.scalar_one_or_none()

        if not application:
            logger.warning(f"Application {application_id} not found, skip auto-redistribution")
            return {"auto_redistributed": False, "reason": "application_not_found"}

        logger.info(
            f"Starting auto-redistribution for scholarship configuration: "
            f"type_id={application.scholarship_type_id}, year={application.academic_year}, "
            f"semester={application.semester}"
        )

        # Get all rankings for this scholarship configuration
        rankings_stmt = select(CollegeRanking).where(
            and_(
                CollegeRanking.scholarship_type_id == application.scholarship_type_id,
                CollegeRanking.academic_year == application.academic_year,
                CollegeRanking.semester == application.semester,
            )
        )
        rankings_result = await self.db.execute(rankings_stmt)
        rankings = rankings_result.scalars().all()

        if not rankings:
            logger.warning(
                f"No rankings found for scholarship configuration "
                f"(type_id={application.scholarship_type_id}, year={application.academic_year}, "
                f"semester={application.semester}), skip auto-redistribution"
            )
            return {"auto_redistributed": False, "reason": "no_rankings"}

        logger.info(f"Found {len(rankings)} rankings to process for auto-redistribution")

        # Process each ranking
        redistribution_results = []
        total_allocated = 0
        successful_count = 0

        for ranking in rankings:
            ranking_result = {
                "ranking_id": ranking.id,
                "sub_type_code": ranking.sub_type_code,
            }

            # Check roster status
            roster_status = await self.check_ranking_roster_status(ranking.id)
            logger.info(
                f"Ranking {ranking.id} ({ranking.sub_type_code}): "
                f"has_roster={roster_status['has_roster']}, can_redistribute={roster_status['can_redistribute']}"
            )

            if roster_status["can_redistribute"]:
                # Execute redistribution
                logger.info(f"🔄 Starting auto-redistribution for ranking {ranking.id} ({ranking.sub_type_code})")
                try:
                    from app.services.matrix_distribution import MatrixDistributionService

                    matrix_service = MatrixDistributionService(self.db)
                    distribution_result = await matrix_service.execute_matrix_distribution(
                        ranking_id=ranking.id, executor_id=executor_id
                    )

                    allocated = distribution_result.get("total_allocated", 0)
                    total_allocated += allocated
                    successful_count += 1

                    ranking_result.update({"status": "success", "allocated": allocated})

                    logger.info(
                        f"✅ Redistributed ranking {ranking.id} ({ranking.sub_type_code}), " f"allocated: {allocated}"
                    )

                except Exception as e:
                    logger.error(
                        f"❌ Failed to redistribute ranking {ranking.id} ({ranking.sub_type_code}): {str(e)}",
                        exc_info=True,
                    )
                    ranking_result.update({"status": "failed", "error": str(e)})

            else:
                # Roster exists - cannot redistribute
                roster_code = (
                    roster_status.get("roster_info", {}).get("roster_code", "UNKNOWN")
                    if roster_status.get("roster_info")
                    else "NONE"
                )
                logger.info(
                    f"⚠️ Ranking {ranking.id} ({ranking.sub_type_code}) has active roster, "
                    f"skip auto-redistribution. Roster: {roster_code}"
                )
                ranking_result.update(
                    {
                        "status": "skipped",
                        "reason": "roster_exists",
                        "roster_code": roster_code,
                    }
                )

            redistribution_results.append(ranking_result)

        # Summary
        logger.info(
            f"📊 Auto-redistribution summary: {successful_count}/{len(rankings)} rankings redistributed, "
            f"total allocated: {total_allocated}"
        )

        return {
            "auto_redistributed": successful_count > 0,
            "total_allocated": total_allocated,
            "rankings_processed": len(rankings),
            "successful_count": successful_count,
            "results": redistribution_results,
            "reason": "status_changed",
        }

    @staticmethod
    def _normalize_semester_value(semester: Optional[Any]) -> Optional[str]:
        """Normalize semester representations to canonical string or None for yearly."""
        if semester is None:
            return None

        value = semester.value if hasattr(semester, "value") else str(semester).strip()
        lower = value.lower()

        if lower.startswith("semester."):
            lower = lower.split(".", 1)[1]

        if lower in {"", "none"}:
            return None

        if lower in {"yearly"}:
            return None

        try:
            return Semester(lower).value
        except ValueError:
            return None

    @staticmethod
    def _is_yearly_semester(semester: Optional[Any]) -> bool:
        """Return True if semester represents a yearly cycle."""
        if semester is None:
            return True

        value = semester.value if hasattr(semester, "value") else str(semester).strip()
        lower = value.lower()

        if lower.startswith("semester."):
            lower = lower.split(".", 1)[1]

        return lower in {"yearly"}

    # create_or_update_review() method removed - replaced by unified ApplicationReview system
    # Use ReviewService.create_review() instead for all review operations
    # Ranking functionality now handled by create_ranking() method

    async def get_applications_for_review(
        self,
        scholarship_type_id: Optional[int] = None,
        scholarship_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        reviewer_id: Optional[int] = None,
        academic_year: Optional[int] = None,
        semester: Optional[str] = None,
        college_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get applications that are ready for college review"""
        logger.info(
            f"Getting applications for college review with filters: type_id={scholarship_type_id}, type={scholarship_type}, sub_type={sub_type}, year={academic_year}, semester={semester}"
        )

        # Base query for applications in reviewable state with comprehensive eager loading
        stmt = (
            select(Application)
            .options(
                selectinload(Application.scholarship_type_ref),
                selectinload(Application.reviews).selectinload(
                    ApplicationReview.reviewer
                ),  # Unified review system with reviewer info
                selectinload(Application.files),
                selectinload(Application.student),  # Load student information
            )
            .where(
                or_(
                    Application.status == ApplicationStatus.recommended.value,
                    Application.status == ApplicationStatus.under_review.value,
                    Application.status == ApplicationStatus.approved.value,  # 包含已核准的申請
                    Application.status == ApplicationStatus.rejected.value,  # 包含已駁回的申請
                    Application.status == "college_reviewed",  # 向後兼容舊資料
                )
            )
        )
        logger.info(
            "Base query created, looking for status in [recommended, under_review, approved, rejected, college_reviewed]"
        )

        # Apply filters
        if scholarship_type_id:
            stmt = stmt.where(Application.scholarship_type_id == scholarship_type_id)

        # scholarship_type parameter deprecated - use scholarship_type_id instead

        if sub_type:
            stmt = stmt.where(func.upper(Application.sub_scholarship_type) == sub_type.upper())

        if academic_year:
            stmt = stmt.where(Application.academic_year == academic_year)

        if semester:
            # Handle special "YEARLY" semester option
            if semester == "YEARLY":
                stmt = stmt.where(Application.semester.is_(None))
            else:
                # Convert string to Semester enum if needed
                try:
                    if isinstance(semester, str):
                        semester_enum = Semester(semester)
                    else:
                        semester_enum = semester
                    # Include both semester-specific applications AND yearly applications (semester=NULL)
                    stmt = stmt.where(
                        or_(
                            Application.semester == semester_enum,
                            Application.semester.is_(None),  # Include yearly scholarships
                        )
                    )
                except ValueError:
                    # If invalid semester value, only show yearly scholarships
                    stmt = stmt.where(Application.semester.is_(None))

        # Apply college filter if provided (for college role users)
        if college_code:
            logger.info(f"Filtering applications by college_code={college_code}")
            # Use std_academyno which is the actual field name in student_data JSON from API
            stmt = stmt.where(sa_func.json_extract_path_text(Application.student_data, "std_academyno") == college_code)

        # Order by submission date (FIFO)
        stmt = stmt.order_by(asc(Application.submitted_at))

        result = await self.db.execute(stmt)
        applications = result.scalars().all()
        logger.info(f"Query executed, found {len(applications)} applications")
        for app in applications:
            logger.info(
                f"  App {app.id}: status={app.status}, type_id={app.scholarship_type_id}, year={app.academic_year}, semester={app.semester}"
            )

        # Note: CollegeReview removed - use Application.final_ranking_position instead
        # college_review_lookup logic removed - data now in Application model

        # Format response with additional review information
        formatted_applications = []
        for app in applications:
            student_payload = app.student_data if isinstance(app.student_data, dict) else {}
            student_id = (
                student_payload.get("std_stdcode")
                or student_payload.get("nycu_id")
                or student_payload.get("student_id")
                or student_payload.get("student_no")
            )
            student_name = (
                student_payload.get("std_cname") or student_payload.get("name") or student_payload.get("student_name")
            )

            app_data = {
                "id": app.id,
                "app_id": app.app_id,
                "student_id": student_id or "N/A",
                "student_name": student_name or "N/A",
                "scholarship_type_id": app.scholarship_type_id,
                "scholarship_type_zh": app.scholarship_type_ref.name if app.scholarship_type_ref else "未知獎學金",
                "sub_type": app.sub_scholarship_type,
                "academic_year": app.academic_year,
                "semester": app.semester.value if app.semester else None,
                "submitted_at": app.submitted_at,
                "status": app.status,
                "created_at": app.created_at,
                "student_data": student_payload,
                "is_renewal": app.is_renewal if hasattr(app, "is_renewal") else False,
                # Check if professor has reviewed (unified review system - check if any reviewer with professor role exists)
                "professor_review_completed": any(
                    review.reviewer.role == "professor" for review in app.reviews if hasattr(review, "reviewer")
                ),
                # college_review_completed replaced by checking ApplicationReview with college role
                "college_review_completed": any(
                    review.reviewer.role in ["college", "admin", "super_admin"]
                    for review in app.reviews
                    if hasattr(review, "reviewer")
                ),
                # Use Application.final_ranking_position instead of college_review.final_rank
                "final_ranking_position": app.final_ranking_position,
            }
            formatted_applications.append(app_data)

        return formatted_applications

    async def create_ranking(
        self,
        scholarship_type_id: int,
        sub_type_code: str,
        academic_year: int,
        semester: Optional[str],
        creator_id: int,
        ranking_name: Optional[str] = None,
        force_new: bool = False,
    ) -> CollegeRanking:
        """Create a new ranking for a scholarship sub-type with race condition protection"""

        # Normalize semester value; treat yearly cycles as NULL for storage
        normalized_semester = self._normalize_semester_value(semester)
        is_yearly_semester = self._is_yearly_semester(semester)

        if not force_new:
            # Check if an unfinished ranking already exists (reuse to prevent duplicates)
            existing_conditions = [
                CollegeRanking.scholarship_type_id == scholarship_type_id,
                CollegeRanking.sub_type_code == sub_type_code,
                CollegeRanking.academic_year == academic_year,
                CollegeRanking.is_finalized.is_(False),
            ]

            if normalized_semester is None:
                existing_conditions.append(
                    or_(CollegeRanking.semester.is_(None), CollegeRanking.semester == Semester.yearly.value)
                )
            else:
                existing_conditions.append(CollegeRanking.semester == normalized_semester)

            existing_stmt = select(CollegeRanking).where(and_(*existing_conditions)).limit(1)

            existing_result = await self.db.execute(existing_stmt)
            existing_ranking = existing_result.scalar_one_or_none()

            if existing_ranking:
                return existing_ranking

        # Get applications for this sub-type that have college reviews
        # Use the same semester filtering logic as in get_applications_for_review
        if is_yearly_semester:
            semester_filter = or_(
                Application.semester.is_(None),
                Application.semester == Semester.yearly.value,
            )
        elif normalized_semester:
            semester_enum = Semester(normalized_semester)
            semester_filter = or_(
                Application.semester == semester_enum,
                Application.semester.is_(None),
            )
        else:
            # If semester is None, get all applications
            semester_filter = True

        # Get creator's college code for filtering applications
        from app.models.user import User

        creator_stmt = select(User).where(User.id == creator_id)
        creator_result = await self.db.execute(creator_stmt)
        creator = creator_result.scalar_one_or_none()
        creator_college = creator.college_code if creator else None

        # Get all applications for the scholarship type (if sub_type_code is "default", include all sub-types)
        logger.debug(
            f"Building query for sub_type_code={sub_type_code}, semester_filter type={type(semester_filter)}, semester_filter={semester_filter}, creator_college={creator_college}"
        )

        if sub_type_code == "default":
            # Include all applications for this scholarship type, regardless of sub-type
            conditions = [
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.is_renewal.is_(False),  # Exclude renewal applications
                Application.deleted_at.is_(None),  # Exclude soft-deleted applications
                Application.status.in_(  # Whitelist valid statuses
                    [
                        ApplicationStatus.recommended.value,
                        ApplicationStatus.under_review.value,
                        ApplicationStatus.approved.value,
                        ApplicationStatus.rejected.value,
                        "college_reviewed",
                    ]
                ),
            ]
            logger.debug(f"Initial conditions count: {len(conditions)}")

            # Add semester filter only if it's an actual SQL expression
            if semester_filter is not True:
                logger.debug("Adding semester_filter to conditions")
                conditions.append(semester_filter)
            else:
                logger.debug("Skipping semester_filter (is True)")

            # Filter by creator's college if available
            if creator_college:
                logger.debug(f"Adding college filter for college_code={creator_college}")
                # Use std_academyno which is the actual field name in student_data JSON from API
                college_condition = (
                    sa_func.json_extract_path_text(Application.student_data, "std_academyno") == creator_college
                )
                conditions.append(college_condition)
                logger.debug("College condition added successfully")

            logger.debug(f"Final conditions count: {len(conditions)}, building query...")
            apps_stmt = select(Application).where(and_(*conditions))
            logger.debug("Query built successfully for default sub_type")
        else:
            # Only include applications for the specific sub-type
            logger.debug(f"Building query for specific sub_type_code={sub_type_code}")
            conditions = [
                Application.scholarship_type_id == scholarship_type_id,
                Application.sub_scholarship_type == sub_type_code,
                Application.academic_year == academic_year,
                Application.is_renewal.is_(False),  # Exclude renewal applications
                Application.deleted_at.is_(None),  # Exclude soft-deleted applications
                Application.status.in_(  # Whitelist valid statuses
                    [
                        ApplicationStatus.recommended.value,
                        ApplicationStatus.under_review.value,
                        ApplicationStatus.approved.value,
                        ApplicationStatus.rejected.value,
                        "college_reviewed",
                    ]
                ),
            ]
            logger.debug(f"Initial conditions count: {len(conditions)}")

            # Add semester filter only if it's an actual SQL expression
            if semester_filter is not True:
                logger.debug("Adding semester_filter to conditions")
                conditions.append(semester_filter)
            else:
                logger.debug("Skipping semester_filter (is True)")

            # Filter by creator's college if available
            if creator_college:
                logger.debug(f"Adding college filter for college_code={creator_college}")
                # Use std_academyno which is the actual field name in student_data JSON from API
                college_condition = (
                    sa_func.json_extract_path_text(Application.student_data, "std_academyno") == creator_college
                )
                conditions.append(college_condition)
                logger.debug("College condition added successfully")

            logger.debug(f"Final conditions count: {len(conditions)}, building query...")
            apps_stmt = select(Application).where(and_(*conditions))
            logger.debug("Query built successfully for specific sub_type")

        # Note: CollegeReview table removed - ranking data now stored in Application.final_ranking_position
        # Execute query to get applications
        apps_result = await self.db.execute(apps_stmt)
        applications = apps_result.scalars().all()

        # No need to create separate college reviews - ranking data stored in Application model
        # Applications will be sorted by final_ranking_position or other criteria

        # Get quota information from configuration
        config_stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                ScholarshipConfiguration.academic_year == academic_year,
                ScholarshipConfiguration.is_active.is_(True),
            )
        )

        if normalized_semester is not None:
            config_stmt = config_stmt.where(ScholarshipConfiguration.semester == normalized_semester)
        else:
            config_stmt = config_stmt.where(ScholarshipConfiguration.semester.is_(None))
        config_result = await self.db.execute(config_stmt)
        config = config_result.scalar_one_or_none()

        total_quota = None
        if config:
            if config.has_quota_limit:
                if sub_type_code == "default":
                    # For "default", use the total quota across all sub-types
                    total_quota = config.total_quota
                else:
                    # For specific sub-types, try to get sub-type specific quota
                    if config.has_college_quota:
                        total_quota = config.get_sub_type_total_quota(sub_type_code)
                    # Fallback to total quota if college quota not set or returns 0
                    if not total_quota:
                        total_quota = config.total_quota
            # If no quota limit set but total_quota exists, use it as a reference
            elif config.total_quota:
                total_quota = config.total_quota

        # Create ranking
        ranking = CollegeRanking(
            scholarship_type_id=scholarship_type_id,
            sub_type_code=sub_type_code,
            academic_year=academic_year,
            semester=normalized_semester,
            ranking_name=ranking_name or f"{sub_type_code} Ranking AY{academic_year}",
            total_applications=len(applications),
            total_quota=total_quota,
            created_by=creator_id,
        )

        self.db.add(ranking)
        await self.db.flush()  # Flush within transaction context
        await self.db.refresh(ranking)

        # Create ranking items - sort by final_ranking_position (if available), then by submission date
        def sort_key(app):
            # If application has final_ranking_position, use it; otherwise use a large number (lowest priority)
            # Lower rank number = higher priority (rank 1 is best)
            rank = app.final_ranking_position if app.final_ranking_position else 999999
            # Use submitted_at as secondary sort (earlier submissions get higher priority if same rank)
            submitted_at = app.submitted_at or app.created_at
            return (
                rank,  # Ascending order: lower rank number comes first
                submitted_at.timestamp(),  # Ascending: earlier submission comes first
            )

        applications.sort(key=sort_key, reverse=False)  # Ascending order

        for rank_position, app in enumerate(applications, 1):
            ranking_item = CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=app.id,
                rank_position=rank_position,
            )
            self.db.add(ranking_item)

        await self.db.flush()  # Flush changes within transaction

        return ranking

    async def get_ranking(self, ranking_id: int) -> Optional[CollegeRanking]:
        """Get a ranking with all its items and relationships using proper eager loading"""

        stmt = (
            select(CollegeRanking)
            .options(
                selectinload(CollegeRanking.items)
                .selectinload(CollegeRankingItem.application)
                .selectinload(Application.scholarship_type_ref),
                selectinload(CollegeRanking.items).selectinload(CollegeRankingItem.college_review),
                selectinload(CollegeRanking.scholarship_type).selectinload(ScholarshipType.sub_type_configs),
                selectinload(CollegeRanking.creator),
                selectinload(CollegeRanking.finalizer),
            )
            .where(CollegeRanking.id == ranking_id)
        )

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_ranking_order(self, ranking_id: int, new_order: List[Dict[str, Any]]) -> CollegeRanking:
        """Update the ranking order of applications with transaction safety"""

        try:
            # Get ranking with pessimistic locking
            ranking_stmt = (
                select(CollegeRanking)
                .options(selectinload(CollegeRanking.items).selectinload(CollegeRankingItem.application))
                .where(CollegeRanking.id == ranking_id)
                .with_for_update()
            )

            ranking_result = await self.db.execute(ranking_stmt)
            ranking = ranking_result.scalar_one_or_none()

            if not ranking:
                raise RankingNotFoundError(f"Ranking with ID {ranking_id} not found")

            if ranking.is_finalized:
                raise RankingModificationError(f"Cannot modify finalized ranking {ranking_id}")

            # Validate input
            if not new_order:
                raise InvalidRankingDataError("New order cannot be empty")

            positions = [item.get("position") for item in new_order]
            if len(positions) != len(set(positions)):
                raise InvalidRankingDataError("Duplicate positions found in ranking update")

            # Update rank positions with validation
            updated_count = 0
            for order_item in new_order:
                item_id = order_item.get("item_id")
                new_position = order_item.get("position")

                if not item_id or new_position is None:
                    continue

                # Find the ranking item
                ranking_item = next((item for item in ranking.items if item.id == item_id), None)

                if ranking_item and ranking_item.rank_position != new_position:
                    ranking_item.rank_position = new_position
                    # Also update the application's ranking position for consistency
                    if ranking_item.application:
                        ranking_item.application.final_ranking_position = new_position
                    updated_count += 1

            if updated_count == 0:
                raise InvalidRankingDataError("No valid position updates found in ranking data")

            ranking.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            await self.db.refresh(ranking)

            return ranking

        except Exception as e:
            raise e

    async def execute_quota_distribution(
        self,
        ranking_id: int,
        executor_id: int,
        distribution_rules: Optional[Dict[str, Any]] = None,
    ) -> QuotaDistribution:
        """Execute quota-based distribution for a ranking"""

        ranking = await self.get_ranking(ranking_id)
        if not ranking:
            raise NotFoundError("Ranking", str(ranking_id))

        if ranking.distribution_executed:
            raise BusinessLogicError("Distribution already executed for this ranking")

        # Sort ranking items by position
        sorted_items = sorted(ranking.items, key=lambda x: x.rank_position)

        # Apply quota allocation
        allocated_count = 0
        allocation_results = []

        for item in sorted_items:
            if ranking.total_quota and allocated_count >= ranking.total_quota:
                # No more quota available
                item.is_allocated = False
                item.status = "rejected"
                item.allocation_reason = "Quota exceeded"

                # Update application status
                item.application.quota_allocation_status = "rejected"
                item.application.status = "rejected"
            else:
                # Allocate quota
                item.is_allocated = True
                item.status = "allocated"
                item.allocation_reason = "Within quota limit"
                allocated_count += 1

                # Update application status
                item.application.quota_allocation_status = "allocated"
                item.application.status = "approved"

            allocation_results.append(
                {
                    "application_id": item.application_id,
                    "rank_position": item.rank_position,
                    "is_allocated": item.is_allocated,
                    "status": item.status,
                }
            )

        # Update ranking
        ranking.allocated_count = allocated_count
        ranking.distribution_executed = True
        ranking.distribution_date = datetime.now(timezone.utc)

        # Create distribution record
        distribution = QuotaDistribution(
            distribution_name=f"Distribution for {ranking.ranking_name}",
            academic_year=ranking.academic_year,
            semester=ranking.semester,
            total_applications=ranking.total_applications,
            total_quota=ranking.total_quota or ranking.total_applications,
            total_allocated=allocated_count,
            algorithm_version="v1.0",
            distribution_rules=distribution_rules or {},
            distribution_summary={
                ranking.sub_type_code: {
                    "total_applications": ranking.total_applications,
                    "total_quota": ranking.total_quota,
                    "allocated": allocated_count,
                    "rejected": ranking.total_applications - allocated_count,
                }
            },
            executed_by=executor_id,
        )

        self.db.add(distribution)
        await self.db.flush()  # Flush within transaction context
        await self.db.refresh(distribution)

        # 發送自動化通知 - Final results decided
        try:
            # Send result notifications for all applications in this ranking
            import logging

            logger = logging.getLogger(__name__)

            for item in sorted_items:
                application = item.application
                result_status = "獲得" if item.is_allocated else "未獲得"
                approved_amount = (
                    getattr(application.scholarship, "amount", "")
                    if item.is_allocated and application.scholarship
                    else ""
                )

                result_data = {
                    "result_status": result_status,
                    "approved_amount": str(approved_amount) if approved_amount else "",
                    "result_message": f"您的申請已完成審核程序，結果為：{result_status}",
                    "next_steps": "請查看系統通知了解後續步驟。" if item.is_allocated else "感謝您的申請。",
                }

                # Trigger email automation for final result
                await email_automation_service.trigger_final_result_decided(self.db, application.id, result_data)

        except Exception as e:
            logger.error(f"Failed to trigger automated result emails: {e}")

        return distribution

    async def finalize_ranking(self, ranking_id: int, finalizer_id: int) -> CollegeRanking:
        """Finalize a ranking (makes it read-only) with concurrent access protection"""

        try:
            # Get ranking with pessimistic locking to prevent concurrent modifications
            ranking_stmt = select(CollegeRanking).where(CollegeRanking.id == ranking_id).with_for_update()

            ranking_result = await self.db.execute(ranking_stmt)
            ranking = ranking_result.scalar_one_or_none()

            if not ranking:
                raise RankingNotFoundError(f"Ranking with ID {ranking_id} not found")

            if ranking.is_finalized:
                raise RankingModificationError("Ranking is already finalized")

            # Ensure only one ranking per scholarship/sub-type/term is finalized at a time
            semester_conditions = []
            if self._is_yearly_semester(ranking.semester):
                semester_conditions.append(CollegeRanking.semester.is_(None))
                semester_conditions.append(CollegeRanking.semester == Semester.yearly.value)
            else:
                normalized_semester = self._normalize_semester_value(ranking.semester)
                if normalized_semester:
                    semester_conditions.append(CollegeRanking.semester == normalized_semester)
                else:
                    semester_conditions.append(CollegeRanking.semester.is_(None))

            other_rankings_stmt = (
                select(CollegeRanking)
                .where(
                    CollegeRanking.id != ranking_id,
                    CollegeRanking.scholarship_type_id == ranking.scholarship_type_id,
                    CollegeRanking.sub_type_code == ranking.sub_type_code,
                    CollegeRanking.academic_year == ranking.academic_year,
                    or_(*semester_conditions),
                    CollegeRanking.is_finalized.is_(True),
                )
                .with_for_update()
            )

            other_rankings_result = await self.db.execute(other_rankings_stmt)
            other_rankings = other_rankings_result.scalars().all()

            for other in other_rankings:
                other.is_finalized = False
                other.finalized_at = None
                other.finalized_by = None
                other.ranking_status = "draft"

            ranking.is_finalized = True
            ranking.finalized_at = datetime.now(timezone.utc)
            ranking.finalized_by = finalizer_id
            ranking.ranking_status = "finalized"

            await self.db.flush()  # Flush within transaction context

            return ranking

        except (RankingNotFoundError, RankingModificationError):
            raise  # Re-raise specific exceptions
        except Exception as e:
            raise BusinessLogicError(f"Failed to finalize ranking {ranking_id}: {str(e)}")

    async def unfinalize_ranking(self, ranking_id: int) -> CollegeRanking:
        """Unfinalize a ranking (makes it editable again)"""

        try:
            # Get ranking with pessimistic locking
            ranking_stmt = select(CollegeRanking).where(CollegeRanking.id == ranking_id).with_for_update()

            ranking_result = await self.db.execute(ranking_stmt)
            ranking = ranking_result.scalar_one_or_none()

            if not ranking:
                raise RankingNotFoundError(f"Ranking with ID {ranking_id} not found")

            if not ranking.is_finalized:
                raise RankingModificationError("Ranking is not finalized")

            # Unfinalize the ranking
            ranking.is_finalized = False
            ranking.finalized_at = None
            ranking.finalized_by = None
            ranking.ranking_status = "draft"

            await self.db.flush()  # Flush within transaction context

            return ranking

        except (RankingNotFoundError, RankingModificationError):
            raise  # Re-raise specific exceptions
        except Exception as e:
            raise BusinessLogicError(f"Failed to unfinalize ranking {ranking_id}: {str(e)}")

    async def get_quota_status(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str] = None,
        college_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get quota status for a scholarship type

        Args:
            scholarship_type_id: Scholarship type ID
            academic_year: Academic year
            semester: Semester (optional)
            college_code: College code to calculate college-specific quota (optional)

        Returns:
            Dictionary with quota status including college_quota if college_code provided
        """

        # Normalize semester using existing helper (handles YEARLY -> None conversion)
        normalized_semester = self._normalize_semester_value(semester)

        # Get configuration
        config_stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                ScholarshipConfiguration.academic_year == academic_year,
                ScholarshipConfiguration.semester == normalized_semester,
                ScholarshipConfiguration.is_active.is_(True),
            )
        )
        config_result = await self.db.execute(config_stmt)
        config = config_result.scalar_one_or_none()

        if not config:
            return {"error": "No active configuration found"}

        # Get application counts by sub-type
        apps_stmt = (
            select(
                Application.sub_scholarship_type,
                func.count(Application.id).label("total"),
                func.sum(
                    case(
                        (Application.quota_allocation_status == "allocated", 1),
                        else_=0,
                    )
                ).label("allocated"),
            )
            .where(
                and_(
                    Application.scholarship_type_id == scholarship_type_id,
                    Application.academic_year == academic_year,
                    Application.semester == normalized_semester,
                )
            )
            .group_by(Application.sub_scholarship_type)
        )

        apps_result = await self.db.execute(apps_stmt)
        app_counts = apps_result.all()

        # Build quota status
        quota_status = {
            "total_quota": config.total_quota,
            "has_quota_limit": config.has_quota_limit,
            "has_college_quota": config.has_college_quota,
            "sub_types": {},
        }

        for sub_type, total, allocated in app_counts:
            # Normalize sub_type to lowercase to prevent duplicate keys
            # sub_type is always a string now (no longer enum)
            normalized_sub_type = (sub_type or "general").lower().strip()

            sub_quota = config.get_sub_type_total_quota(normalized_sub_type) if config.has_quota_limit else None

            # Merge data if key already exists (handles mixed case in database)
            if normalized_sub_type in quota_status["sub_types"]:
                existing = quota_status["sub_types"][normalized_sub_type]
                existing["total_applications"] += total
                existing["allocated"] = (existing["allocated"] or 0) + (allocated or 0)
                # Recalculate derived fields
                if sub_quota:
                    existing["remaining"] = sub_quota - existing["allocated"]
                    existing["utilization_rate"] = existing["allocated"] / sub_quota * 100
            else:
                quota_status["sub_types"][normalized_sub_type] = {
                    "total_applications": total,
                    "allocated": allocated or 0,
                    "quota": sub_quota,
                    "remaining": (sub_quota - (allocated or 0)) if sub_quota else None,
                    "utilization_rate": ((allocated or 0) / sub_quota * 100) if sub_quota else None,
                }

        # Calculate college-specific quota if college_code provided
        college_quota: Optional[int] = None
        college_quota_breakdown: Dict[str, int] = {}

        if college_code and config.has_college_quota and isinstance(config.quotas, dict):
            logger.info(f"Calculating college quota for college_code={college_code}")
            total_college_quota = 0

            for sub_type_code, college_quotas in config.quotas.items():
                if not isinstance(college_quotas, dict):
                    continue

                if college_code in college_quotas:
                    quota_value = college_quotas[college_code]
                    try:
                        numeric_quota = int(quota_value)
                        if numeric_quota > 0:
                            total_college_quota += numeric_quota
                            college_quota_breakdown[sub_type_code] = numeric_quota
                            logger.debug(
                                f"  Sub-type {sub_type_code}: {numeric_quota} quota for college {college_code}"
                            )
                    except (TypeError, ValueError) as e:
                        logger.warning(f"Invalid quota value for {sub_type_code}/{college_code}: {quota_value} ({e})")
                        pass

            if total_college_quota > 0:
                college_quota = total_college_quota
                logger.info(f"Total college quota for {college_code}: {college_quota}")
            else:
                logger.info(f"No college quota found for {college_code}")

        quota_status["college_quota"] = college_quota
        quota_status["college_quota_breakdown"] = college_quota_breakdown

        return quota_status


class QuotaDistributionService:
    """Service specifically for handling quota distribution algorithms"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def distribute_by_ranking(
        self,
        applications: List[Application],
        total_quota: int,
        distribution_rules: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Distribute quota based on ranking order"""

        # Note: college_ranking_score field removed - sort by final_ranking_position instead
        # Sort applications by ranking position (ascending - lower rank number is better)
        sorted_apps = sorted(
            applications,
            key=lambda x: (
                x.final_ranking_position if x.final_ranking_position else 999999,  # Unranked go to end
                x.submitted_at.timestamp() if x.submitted_at else 0,  # Tie-breaker: earlier submission
            ),
            reverse=False,  # Ascending order
        )

        # Allocate quota
        results = []
        for i, app in enumerate(sorted_apps):
            is_allocated = i < total_quota

            result = {
                "application_id": app.id,
                "rank_position": i + 1,
                "is_allocated": is_allocated,
                # Note: ranking_score field removed
                "final_ranking_position": app.final_ranking_position,
                "allocation_reason": "Within quota" if is_allocated else "Quota exceeded",
            }
            results.append(result)

        return results

    async def distribute_by_sub_type_matrix(
        self,
        applications: List[Application],
        quota_matrix: Dict[str, Dict[str, int]],  # {sub_type: {college: quota}}
        distribution_rules: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Distribute quota using sub-type and college matrix"""

        # Group applications by sub-type and college
        grouped_apps = {}
        for app in applications:
            sub_type = app.sub_scholarship_type
            student_payload = app.student_data if isinstance(app.student_data, dict) else {}
            college = (
                student_payload.get("college_code")
                or student_payload.get("std_college")
                or student_payload.get("academy_code")
                or "unknown"
            )

            if sub_type not in grouped_apps:
                grouped_apps[sub_type] = {}
            if college not in grouped_apps[sub_type]:
                grouped_apps[sub_type][college] = []

            grouped_apps[sub_type][college].append(app)

        # Distribute within each group
        results = []
        for sub_type, colleges in grouped_apps.items():
            sub_type_quota = quota_matrix.get(sub_type, {})

            for college, college_apps in colleges.items():
                college_quota = sub_type_quota.get(college, 0)

                # Note: college_ranking_score field removed - sort by final_ranking_position instead
                # Sort applications within this group by ranking position (ascending)
                sorted_apps = sorted(
                    college_apps,
                    key=lambda x: (
                        x.final_ranking_position if x.final_ranking_position else 999999,  # Unranked go to end
                        x.submitted_at.timestamp() if x.submitted_at else 0,
                    ),
                    reverse=False,  # Ascending order
                )

                # Allocate quota for this group
                for i, app in enumerate(sorted_apps):
                    is_allocated = i < college_quota

                    result = {
                        "application_id": app.id,
                        "sub_type": sub_type,
                        "college": college,
                        "rank_position": i + 1,
                        "is_allocated": is_allocated,
                        # Note: ranking_score field removed
                        "final_ranking_position": app.final_ranking_position,
                        "quota_available": college_quota,
                        "allocation_reason": f"Within {sub_type}-{college} quota"
                        if is_allocated
                        else f"{sub_type}-{college} quota exceeded",
                    }
                    results.append(result)

        return results

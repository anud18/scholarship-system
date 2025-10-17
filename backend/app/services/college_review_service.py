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
from app.models.application import Application, ApplicationStatus, ProfessorReview
from app.models.college_review import CollegeRanking, CollegeRankingItem, CollegeReview, QuotaDistribution
from app.models.enums import Semester
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

    async def create_or_update_review(
        self, application_id: int, reviewer_id: int, review_data: Dict[str, Any]
    ) -> CollegeReview:
        """Create or update a college review for an application"""

        # Check if review already exists with eager loading
        stmt = (
            select(CollegeReview)
            .options(
                selectinload(CollegeReview.application),
                selectinload(CollegeReview.reviewer),
            )
            .where(CollegeReview.application_id == application_id)
        )
        result = await self.db.execute(stmt)
        existing_review = result.scalar_one_or_none()

        # Verify application exists and is in reviewable state with eager loading
        app_stmt = (
            select(Application)
            .options(
                selectinload(Application.scholarship_type_ref),
                selectinload(Application.professor_reviews),
                selectinload(Application.files),
            )
            .where(Application.id == application_id)
        )
        app_result = await self.db.execute(app_stmt)
        application = app_result.scalar_one_or_none()

        if not application:
            raise NotFoundError("Application", str(application_id))

        # Allow reviewing applications in these states:
        # - recommended: initial state after professor review
        # - under_review: currently being reviewed
        # - approved: allow re-review of approved applications
        # - rejected: allow re-review of rejected applications
        # - college_reviewed: backward compatibility
        reviewable_states = [
            ApplicationStatus.recommended.value,
            ApplicationStatus.under_review.value,
            ApplicationStatus.approved.value,
            ApplicationStatus.rejected.value,
            "college_reviewed",
        ]

        if application.status not in reviewable_states:
            raise BusinessLogicError(
                f"Application {application_id} is not in reviewable state (current status: {application.status})"
            )

        # Calculate scores if not provided
        if not review_data.get("ranking_score"):
            ranking_score = self._calculate_ranking_score(review_data)
            review_data["ranking_score"] = ranking_score

        if existing_review:
            # Update existing review
            for key, value in review_data.items():
                if hasattr(existing_review, key):
                    setattr(existing_review, key, value)

            existing_review.updated_at = datetime.now(timezone.utc)
            existing_review.reviewed_at = datetime.now(timezone.utc)
            existing_review.review_status = "completed"

            college_review = existing_review
        else:
            # Create new review
            college_review = CollegeReview(
                application_id=application_id,
                reviewer_id=reviewer_id,
                review_started_at=datetime.now(timezone.utc),
                reviewed_at=datetime.now(timezone.utc),
                review_status="completed",
                **review_data,
            )
            self.db.add(college_review)

        # Update application's college review fields
        application.college_ranking_score = college_review.ranking_score

        # Set application status based on review recommendation
        recommendation = review_data.get("recommendation", "")
        if recommendation == "approve":
            application.status = ApplicationStatus.approved.value
        elif recommendation == "reject":
            application.status = ApplicationStatus.rejected.value
        elif recommendation == "conditional":
            application.status = ApplicationStatus.under_review.value  # 條件核准仍在審核中
        else:
            application.status = "college_reviewed"  # 預設狀態

        # Note: commit handled by transaction context manager
        await self.db.flush()  # Ensure changes are written to DB within transaction
        await self.db.refresh(college_review)

        # Update associated ranking items to reflect review status
        ranking_items_stmt = select(CollegeRankingItem).where(CollegeRankingItem.application_id == application_id)
        ranking_items_result = await self.db.execute(ranking_items_stmt)
        ranking_items = ranking_items_result.scalars().all()

        # Update ranking item status based on recommendation (use the same value from above)
        for ranking_item in ranking_items:
            if recommendation == "approve":
                ranking_item.status = "ranked"  # 核准的保持 ranked 狀態
                # Reset allocation fields to allow re-distribution
                ranking_item.allocated_sub_type = None
                ranking_item.is_allocated = False
                ranking_item.allocation_reason = None
                ranking_item.backup_position = None
            elif recommendation == "reject":
                ranking_item.status = "rejected"  # 駁回的標記為 rejected
                # Also reset allocation fields for rejected items
                ranking_item.allocated_sub_type = None
                ranking_item.is_allocated = False
                ranking_item.allocation_reason = None
                ranking_item.backup_position = None
            elif recommendation == "conditional":
                ranking_item.status = "ranked"  # 條件核准也保持 ranked
                # Reset allocation fields for conditional approval too
                ranking_item.allocated_sub_type = None
                ranking_item.is_allocated = False
                ranking_item.allocation_reason = None
                ranking_item.backup_position = None

        await self.db.flush()  # Flush ranking item updates

        # 觸發學院審查提交事件（會觸發自動化郵件規則）
        try:
            from app.models.user import User

            # Fetch reviewer and student info for email context
            stmt_reviewer = select(User).where(User.id == reviewer_id)
            result_reviewer = await self.db.execute(stmt_reviewer)
            reviewer = result_reviewer.scalar_one_or_none()

            stmt_student = select(User).where(User.id == application.user_id)
            result_student = await self.db.execute(stmt_student)
            student = result_student.scalar_one_or_none()

            await email_automation_service.trigger_college_review_submitted(
                db=self.db,
                application_id=application.id,
                review_data={
                    "app_id": application.app_id,
                    "student_name": student.name if student else "Unknown",
                    "student_email": student.email if student else "",
                    "college_name": reviewer.college if reviewer and hasattr(reviewer, "college") else "",
                    "ranking_score": college_review.ranking_score,
                    "recommendation": review_data.get("recommendation", ""),
                    "comments": review_data.get("comments", ""),
                    "reviewer_name": reviewer.name if reviewer else "Unknown",
                    "scholarship_type": application.scholarship_type_ref.name
                    if application.scholarship_type_ref
                    else "Unknown",
                    "scholarship_type_id": application.scholarship_type_id,
                    "review_date": college_review.reviewed_at.strftime("%Y-%m-%d")
                    if college_review.reviewed_at
                    else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                },
            )
        except Exception as e:
            logger.error(f"Failed to trigger college review automation: {e}")

        return college_review

    def _calculate_ranking_score(self, review_data: Dict[str, Any]) -> float:
        """Calculate overall ranking score based on component scores"""

        # Default scoring weights
        weights = {
            "academic": 0.30,
            "professor_review": 0.40,
            "college_criteria": 0.20,
            "special_circumstances": 0.10,
        }

        # Use custom weights if provided
        if "scoring_weights" in review_data:
            weights.update(review_data["scoring_weights"])

        # Extract component scores
        scores = {
            "academic": review_data.get("academic_score", 0),
            "professor_review": review_data.get("professor_review_score", 0),
            "college_criteria": review_data.get("college_criteria_score", 0),
            "special_circumstances": review_data.get("special_circumstances_score", 0),
        }

        # Calculate weighted total
        total_score = sum(scores[key] * weights[key] for key in scores)
        return round(total_score, 2)

    async def get_applications_for_review(
        self,
        scholarship_type_id: Optional[int] = None,
        scholarship_type: Optional[str] = None,
        sub_type: Optional[str] = None,
        reviewer_id: Optional[int] = None,
        academic_year: Optional[int] = None,
        semester: Optional[str] = None,
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
                selectinload(Application.professor_reviews).selectinload(ProfessorReview.professor),
                selectinload(Application.files),
                selectinload(Application.reviews),  # Load all application reviews
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

        # Filter by scholarship type code (case-insensitive)
        if scholarship_type:
            stmt = stmt.where(func.upper(Application.main_scholarship_type) == scholarship_type.upper())

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

        # Order by submission date (FIFO)
        stmt = stmt.order_by(asc(Application.submitted_at))

        result = await self.db.execute(stmt)
        applications = result.scalars().all()
        logger.info(f"Query executed, found {len(applications)} applications")
        for app in applications:
            logger.info(
                f"  App {app.id}: status={app.status}, type_id={app.scholarship_type_id}, year={app.academic_year}, semester={app.semester}"
            )

        # Get college review data for all applications in a single batch query
        application_ids = [app.id for app in applications]
        if application_ids:
            college_reviews_stmt = select(CollegeReview).where(CollegeReview.application_id.in_(application_ids))
            college_reviews_result = await self.db.execute(college_reviews_stmt)
            college_reviews = college_reviews_result.scalars().all()

            # Create lookup dictionary for college reviews
            college_review_lookup = {review.application_id: review for review in college_reviews}
        else:
            college_review_lookup = {}

        # Format response with additional review information
        formatted_applications = []
        for app in applications:
            # Get college review if exists
            college_review = college_review_lookup.get(app.id)

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
                "scholarship_type": app.main_scholarship_type,
                "scholarship_type_zh": app.scholarship_type_ref.name if app.scholarship_type_ref else "未知獎學金",
                "sub_type": app.sub_scholarship_type,
                "academic_year": app.academic_year,
                "semester": app.semester.value if app.semester else None,
                "submitted_at": app.submitted_at,
                "status": app.status,
                "created_at": app.created_at,
                "student_data": student_payload,
                "is_renewal": app.is_renewal if hasattr(app, "is_renewal") else False,
                "professor_review_completed": len(app.professor_reviews) > 0,
                "college_review_completed": college_review is not None,
                "college_review_score": college_review.ranking_score if college_review else None,
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
                college_condition = (
                    sa_func.json_extract_path_text(Application.student_data, "college_code") == creator_college
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
                college_condition = (
                    sa_func.json_extract_path_text(Application.student_data, "college_code") == creator_college
                )
                conditions.append(college_condition)
                logger.debug("College condition added successfully")

            logger.debug(f"Final conditions count: {len(conditions)}, building query...")
            apps_stmt = select(Application).where(and_(*conditions))
            logger.debug("Query built successfully for specific sub_type")

        # Get college reviews for the scholarship type
        if sub_type_code == "default":
            # Include college reviews for all applications of this scholarship type
            review_conditions = [
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
            # Add semester filter only if it's an actual SQL expression
            if semester_filter is not True:
                review_conditions.append(semester_filter)
            # Filter by creator's college if available
            if creator_college:
                review_conditions.append(
                    sa_func.json_extract_path_text(Application.student_data, "college_code") == creator_college
                )

            college_reviews_stmt = select(CollegeReview).join(Application).where(and_(*review_conditions))
        else:
            # Only include college reviews for the specific sub-type
            review_conditions = [
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
            # Add semester filter only if it's an actual SQL expression
            if semester_filter is not True:
                review_conditions.append(semester_filter)
            # Filter by creator's college if available
            if creator_college:
                review_conditions.append(
                    sa_func.json_extract_path_text(Application.student_data, "college_code") == creator_college
                )

            college_reviews_stmt = select(CollegeReview).join(Application).where(and_(*review_conditions))
        apps_result = await self.db.execute(apps_stmt)
        applications = apps_result.scalars().all()

        # Get college reviews for these applications
        college_reviews_result = await self.db.execute(college_reviews_stmt)
        college_reviews = college_reviews_result.scalars().all()

        # Ensure all applications have college reviews (create default ones if needed)
        college_review_lookup = {review.application_id: review for review in college_reviews}

        # Create default college reviews for applications that don't have them
        applications_with_reviews = []
        for app in applications:
            college_review = college_review_lookup.get(app.id)
            if not college_review:
                # Create a default college review for applications without one
                default_review = CollegeReview(
                    application_id=app.id,
                    reviewer_id=creator_id,  # Use the ranking creator as default reviewer
                    review_status="pending",
                    ranking_score=0.0,  # Default score
                    review_comments="Auto-created for ranking purposes",
                )
                self.db.add(default_review)
                await self.db.flush()  # Flush to get the ID
                await self.db.refresh(default_review)
                college_review = default_review

            applications_with_reviews.append((app, college_review))

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
            total_applications=len(applications_with_reviews),
            total_quota=total_quota,
            created_by=creator_id,
        )

        self.db.add(ranking)
        await self.db.flush()  # Flush within transaction context
        await self.db.refresh(ranking)

        # Create ranking items - sort by college review score (if available), then by submission date
        def sort_key(item):
            app, college_review = item
            # If college review exists, use its ranking score; otherwise use 0 (lowest priority)
            score = college_review.ranking_score if college_review else 0
            # Use submitted_at as secondary sort (earlier submissions get higher priority if same score)
            submitted_at = app.submitted_at or app.created_at
            return (
                score,
                -submitted_at.timestamp(),
            )  # Negative timestamp for descending order

        applications_with_reviews.sort(key=sort_key, reverse=True)

        for rank_position, (app, college_review) in enumerate(applications_with_reviews, 1):
            ranking_item = CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=app.id,
                college_review_id=college_review.id,  # Now guaranteed to exist
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
    ) -> Dict[str, Any]:
        """Get quota status for a scholarship type"""

        # Get configuration
        config_stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                ScholarshipConfiguration.academic_year == academic_year,
                ScholarshipConfiguration.semester == semester,
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
                        [(Application.quota_allocation_status == "allocated", 1)],
                        else_=0,
                    )
                ).label("allocated"),
            )
            .where(
                and_(
                    Application.scholarship_type_id == scholarship_type_id,
                    Application.academic_year == academic_year,
                    Application.semester == semester,
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
            sub_quota = config.get_sub_type_total_quota(sub_type) if config.has_quota_limit else None

            quota_status["sub_types"][sub_type] = {
                "total_applications": total,
                "allocated": allocated or 0,
                "quota": sub_quota,
                "remaining": (sub_quota - (allocated or 0)) if sub_quota else None,
                "utilization_rate": ((allocated or 0) / sub_quota * 100) if sub_quota else None,
            }

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

        # Sort applications by ranking score (descending)
        sorted_apps = sorted(
            applications,
            key=lambda x: (
                x.college_ranking_score or 0,
                -(x.submitted_at.timestamp() if x.submitted_at else 0),  # Tie-breaker: earlier submission
            ),
            reverse=True,
        )

        # Allocate quota
        results = []
        for i, app in enumerate(sorted_apps):
            is_allocated = i < total_quota

            result = {
                "application_id": app.id,
                "rank_position": i + 1,
                "is_allocated": is_allocated,
                "ranking_score": app.college_ranking_score,
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

                # Sort applications within this group
                sorted_apps = sorted(
                    college_apps,
                    key=lambda x: (
                        x.college_ranking_score or 0,
                        -(x.submitted_at.timestamp() if x.submitted_at else 0),
                    ),
                    reverse=True,
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
                        "ranking_score": app.college_ranking_score,
                        "quota_available": college_quota,
                        "allocation_reason": f"Within {sub_type}-{college} quota"
                        if is_allocated
                        else f"{sub_type}-{college} quota exceeded",
                    }
                    results.append(result)

        return results

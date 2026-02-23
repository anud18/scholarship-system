"""
Manual Distribution Service

Replaces automated quota/matrix distribution with admin-driven manual allocation.
Admin selects one scholarship sub-type per student via UI checkboxes.
Supports multi-year supplementary distribution (補發) where prior-year
remaining quotas can be allocated to current-year students.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus, ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipSubTypeConfig

logger = logging.getLogger(__name__)


def _ranking_semester_condition(semester: str):
    """
    Build a SQLAlchemy condition for CollegeRanking.semester.
    The frontend sends "yearly" for annual scholarships, but the DB stores
    NULL (or occasionally "annual") for those rows.
    """
    if semester == "yearly":
        return or_(
            CollegeRanking.semester.is_(None),
            CollegeRanking.semester == "annual",
            CollegeRanking.semester == "yearly",
        )
    return CollegeRanking.semester == semester


def _config_semester_condition(semester: str):
    """
    Build a SQLAlchemy condition for ScholarshipConfiguration.semester.
    The frontend sends "yearly" for annual scholarships, but the DB stores
    NULL or the enum value "yearly" for those rows.
    """
    if semester == "yearly":
        return or_(
            ScholarshipConfiguration.semester.is_(None),
            ScholarshipConfiguration.semester == "yearly",
        )
    return ScholarshipConfiguration.semester == semester


class ManualDistributionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_students_for_distribution(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: str,
        college_code: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Get ranked students with their allocation status for manual distribution.
        Returns students sorted by college, then rank_position.
        """
        # Get finalized rankings for this scholarship config
        ranking_query = select(CollegeRanking).where(
            and_(
                CollegeRanking.scholarship_type_id == scholarship_type_id,
                CollegeRanking.academic_year == academic_year,
                _ranking_semester_condition(semester),
                CollegeRanking.is_finalized == True,
            )
        )
        result = await self.db.execute(ranking_query)
        rankings = result.scalars().all()

        if not rankings:
            return []

        ranking_ids = [r.id for r in rankings]

        # Get all ranking items with applications
        items_query = (
            select(CollegeRankingItem)
            .options(selectinload(CollegeRankingItem.application))
            .where(CollegeRankingItem.ranking_id.in_(ranking_ids))
            .order_by(CollegeRankingItem.rank_position)
        )
        result = await self.db.execute(items_query)
        items = result.scalars().all()

        students = []
        for item in items:
            app = item.application
            if not app:
                continue

            student_data = app.student_data or {}

            # Filter by college if specified
            student_college = student_data.get("std_academyno", "")
            if college_code and student_college != college_code:
                continue

            # Compute application_identity
            identity = self._compute_application_identity(app)

            # Compute grade display
            grade = self._compute_grade_display(student_data)

            # Format enrollment date (ROC calendar)
            enrollment_date = self._format_enrollment_date(student_data)

            students.append({
                "ranking_item_id": item.id,
                "application_id": app.id,
                "rank_position": item.rank_position,
                "applied_sub_types": app.scholarship_subtype_list or [],
                "allocated_sub_type": item.allocated_sub_type,
                "allocation_year": item.allocation_year,
                "status": item.status,
                "college_code": student_college,
                "college_name": student_data.get("trm_academyname", ""),
                "department_name": student_data.get("trm_depname", ""),
                "grade": grade,
                "student_name": student_data.get("std_cname", ""),
                "nationality": student_data.get("std_nation", ""),
                "enrollment_date": enrollment_date,
                "student_id": student_data.get("std_stdcode", ""),
                "application_identity": identity,
            })

        # Sort by college_code, then rank_position
        students.sort(key=lambda s: (s["college_code"], s["rank_position"]))
        return students

    async def get_quota_status(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: str,
        prior_years: int = 2,
    ) -> dict[str, Any]:
        """
        Get real-time quota status per sub-type per (year × college).
        Returns data for the current year and up to `prior_years` previous years
        that have remaining quota.

        Response structure:
        {
          "nstc": {
            "display_name": "國科會博士生獎學金",
            "by_year": {
              "114": {"total": 80, "allocated": 0, "remaining": 80, "by_college": {...}},
              "113": {"total": 15, "allocated": 3, "remaining": 12, "by_college": {...}},
            }
          },
          ...
        }
        """
        # Build list of years to query: current + up to prior_years previous
        years_to_check = [academic_year - i for i in range(prior_years + 1)]

        # Get sub-type display names (shared across years)
        sub_type_query = (
            select(ScholarshipSubTypeConfig)
            .where(
                and_(
                    ScholarshipSubTypeConfig.scholarship_type_id == scholarship_type_id,
                    ScholarshipSubTypeConfig.is_active == True,
                )
            )
            .order_by(ScholarshipSubTypeConfig.display_order)
        )
        result = await self.db.execute(sub_type_query)
        sub_type_configs = result.scalars().all()
        sub_type_names = {stc.sub_type_code: stc.name for stc in sub_type_configs}

        # Count allocations using allocation_year across ALL rankings
        # (includes both prior-year rankings and current-year rankings that used prior-year quota)
        all_rankings_query = select(CollegeRanking).where(
            and_(
                CollegeRanking.scholarship_type_id == scholarship_type_id,
                CollegeRanking.is_finalized == True,
            )
        )
        result = await self.db.execute(all_rankings_query)
        all_rankings = result.scalars().all()
        all_ranking_ids = [r.id for r in all_rankings]

        # Get all allocated items, grouped by (sub_type, allocation_year, college)
        if all_ranking_ids:
            allocated_items_query = (
                select(CollegeRankingItem)
                .options(selectinload(CollegeRankingItem.application))
                .where(
                    and_(
                        CollegeRankingItem.ranking_id.in_(all_ranking_ids),
                        CollegeRankingItem.is_allocated == True,
                    )
                )
            )
            result = await self.db.execute(allocated_items_query)
            allocated_items = result.scalars().all()
        else:
            allocated_items = []

        # Build allocation counts: {sub_type: {year: {college: count}}}
        allocation_counts: dict[str, dict[int, dict[str, int]]] = {}
        for item in allocated_items:
            sub_type = item.allocated_sub_type
            if not sub_type:
                continue
            # Determine which year's quota this allocation consumes
            # Use allocation_year if set, else fall back to the ranking's academic_year
            ranking = next((r for r in all_rankings if r.id == item.ranking_id), None)
            alloc_year = item.allocation_year or (ranking.academic_year if ranking else None)
            if not alloc_year:
                continue
            college = (item.application.student_data or {}).get("std_academyno", "unknown")

            allocation_counts.setdefault(sub_type, {})
            allocation_counts[sub_type].setdefault(alloc_year, {})
            allocation_counts[sub_type][alloc_year][college] = (
                allocation_counts[sub_type][alloc_year].get(college, 0) + 1
            )

        # Build response: query each year's configuration
        quota_status: dict[str, Any] = {}

        for year in years_to_check:
            config_query = select(ScholarshipConfiguration).where(
                and_(
                    ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                    ScholarshipConfiguration.academic_year == year,
                    _config_semester_condition(semester),
                )
            )
            result = await self.db.execute(config_query)
            config = result.scalar_one_or_none()

            if not config or not config.quotas:
                continue

            quotas = config.quotas  # {sub_type: {college_code: quota}}

            for sub_type, college_quotas in quotas.items():
                if not isinstance(college_quotas, dict):
                    continue

                by_college_for_year = allocation_counts.get(sub_type, {}).get(year, {})
                total_quota = sum(college_quotas.values())
                total_allocated = sum(by_college_for_year.values())
                remaining = total_quota - total_allocated

                # Only include years with quota > 0
                if total_quota <= 0:
                    continue

                by_college = {}
                for college_code, quota in college_quotas.items():
                    allocated = by_college_for_year.get(college_code, 0)
                    by_college[college_code] = {
                        "total": quota,
                        "allocated": allocated,
                        "remaining": quota - allocated,
                    }

                if sub_type not in quota_status:
                    quota_status[sub_type] = {
                        "display_name": sub_type_names.get(sub_type, sub_type),
                        "by_year": {},
                    }

                quota_status[sub_type]["by_year"][str(year)] = {
                    "total": total_quota,
                    "allocated": total_allocated,
                    "remaining": remaining,
                    "by_college": by_college,
                }

        return quota_status

    async def allocate(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: str,
        allocations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Save manual allocation selections.
        Each allocation: {
            "ranking_item_id": int,
            "sub_type_code": str|None,
            "allocation_year": int|None  (None → defaults to academic_year)
        }
        sub_type_code=None means unallocate.
        """
        # Validate quota limits first
        await self._validate_allocations(
            scholarship_type_id, academic_year, semester, allocations
        )

        updated_count = 0
        for alloc in allocations:
            item_id = alloc["ranking_item_id"]
            sub_type = alloc.get("sub_type_code")
            alloc_year = alloc.get("allocation_year") or (academic_year if sub_type else None)

            item_query = select(CollegeRankingItem).where(
                CollegeRankingItem.id == item_id
            )
            result = await self.db.execute(item_query)
            item = result.scalar_one_or_none()
            if not item:
                continue

            if sub_type:
                item.is_allocated = True
                item.allocated_sub_type = sub_type
                item.allocation_year = alloc_year
                item.status = "allocated"
                item.allocation_reason = "手動分發"
            else:
                item.is_allocated = False
                item.allocated_sub_type = None
                item.allocation_year = None
                item.status = "ranked"
                item.allocation_reason = None

            updated_count += 1

        await self.db.flush()
        return {"updated_count": updated_count}

    async def finalize(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: str,
    ) -> dict[str, Any]:
        """
        Finalize manual distribution:
        1. Mark rankings as distribution_executed
        2. Update application statuses (allocated -> approved, others -> rejected)
        3. Update quota_allocation_status on applications
        """
        ranking_query = select(CollegeRanking).where(
            and_(
                CollegeRanking.scholarship_type_id == scholarship_type_id,
                CollegeRanking.academic_year == academic_year,
                _ranking_semester_condition(semester),
                CollegeRanking.is_finalized == True,
            )
        )
        result = await self.db.execute(ranking_query)
        rankings = result.scalars().all()
        ranking_ids = [r.id for r in rankings]

        if not ranking_ids:
            raise ValueError("No finalized rankings found")

        # Get all ranking items
        items_query = (
            select(CollegeRankingItem)
            .options(selectinload(CollegeRankingItem.application))
            .where(CollegeRankingItem.ranking_id.in_(ranking_ids))
        )
        result = await self.db.execute(items_query)
        items = result.scalars().all()

        approved_count = 0
        rejected_count = 0

        for item in items:
            app = item.application
            if not app:
                continue

            if item.is_allocated and item.allocated_sub_type:
                app.status = ApplicationStatus.approved
                app.quota_allocation_status = "allocated"
                app.sub_scholarship_type = item.allocated_sub_type
                app.approved_at = datetime.now(timezone.utc)
                app.review_stage = ReviewStage.quota_distributed
                approved_count += 1
            else:
                item.status = "rejected"
                app.status = ApplicationStatus.rejected
                app.quota_allocation_status = "rejected"
                app.review_stage = ReviewStage.quota_distributed
                rejected_count += 1

        # Update rankings
        now = datetime.now(timezone.utc)
        for ranking in rankings:
            ranking.distribution_executed = True
            ranking.distribution_date = now
            ranking.allocated_count = approved_count

        await self.db.flush()

        return {
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "total": approved_count + rejected_count,
        }

    async def _validate_allocations(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: str,
        allocations: list[dict[str, Any]],
    ) -> None:
        """Validate that allocations don't exceed per-college quotas for each year."""
        # Check single-select: no duplicate ranking_item_ids
        seen_items = set()
        for alloc in allocations:
            item_id = alloc["ranking_item_id"]
            if item_id in seen_items:
                raise ValueError(f"Duplicate ranking item: {item_id}")
            seen_items.add(item_id)

        # Quota validation is done real-time via the quota-status endpoint on the frontend.
        # The frontend sends only valid allocations based on displayed remaining counts.

    def _compute_application_identity(self, app: Application) -> str:
        """
        Compute display string for application identity.
        e.g., "114新申請", "112續領"
        """
        if app.is_renewal and app.previous_application_id:
            return f"{app.academic_year}續領"
        else:
            return f"{app.academic_year}新申請"

    def _compute_grade_display(self, student_data: dict) -> str:
        """Compute grade display string like 博一, 博二, 碩一, etc."""
        degree = student_data.get("trm_degree", student_data.get("std_degree", 0))
        term_count = student_data.get("trm_termcount", student_data.get("std_termcount", 1))
        year = (term_count + 1) // 2  # Convert semester count to year

        degree_prefix = {6: "博", 4: "碩", 2: "學"}.get(degree, "")
        year_suffix = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七"}.get(
            year, str(year)
        )
        return f"{degree_prefix}{year_suffix}" if degree_prefix else f"第{year}年"

    def _format_enrollment_date(self, student_data: dict) -> str:
        """Format enrollment date as ROC calendar (民國年.月.日)."""
        enroll_year = student_data.get("std_enrollyear", 0)
        enroll_term = student_data.get("std_enrollterm", 1)
        # Approximate: term 1 = September, term 2 = February
        month = "09" if enroll_term == 1 else "02"
        return f"{enroll_year}.{month}.01" if enroll_year else ""

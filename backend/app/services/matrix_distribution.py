"""
Matrix Distribution Service for College Rankings

This service implements the matrix-based quota distribution algorithm
where scholarships are allocated based on:
- Fixed sub-type priority order
- College-specific quotas
- Student ranking positions
- Student eligibility rules
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipRule

logger = logging.getLogger(__name__)

# Fixed sub-type priority order (NSTC → MOE_1W → MOE_2W → ...)
SUB_TYPE_PRIORITY = ["nstc", "moe_1w", "moe_2w", "general"]


class MatrixDistributionService:
    """Service for matrix-based quota distribution"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute_matrix_distribution(
        self,
        ranking_id: int,
        executor_id: int,
    ) -> Dict[str, Any]:
        """
        Execute matrix distribution for a ranking

        Algorithm:
        1. Get quota matrix from scholarship configuration
        2. Sort ranking items by rank_position
        3. For each sub-type (按優先順序):
           For each college:
             - Get students who applied for this sub-type
             - Check if student belongs to this college
             - Check if student hasn't been allocated yet
             - Check eligibility rules
             - Allocate (admitted) or backup based on quota
        4. Update CollegeRankingItem records with allocation results
        5. Return distribution summary
        """

        # Get ranking with all relationships
        ranking_stmt = (
            select(CollegeRanking)
            .options(
                selectinload(CollegeRanking.items).selectinload(CollegeRankingItem.application),
                selectinload(CollegeRanking.scholarship_type),
            )
            .where(CollegeRanking.id == ranking_id)
        )
        result = await self.db.execute(ranking_stmt)
        ranking = result.scalar_one_or_none()

        if not ranking:
            raise ValueError(f"Ranking {ranking_id} not found")

        # Get scholarship configuration for quota matrix
        config: Optional[ScholarshipConfiguration] = None

        # Prefer the exact configuration referenced by applications to avoid mismatch with inactive or archived configs
        config_ids = {
            item.application.scholarship_configuration_id
            for item in ranking.items
            if item.application and item.application.scholarship_configuration_id
        }

        if config_ids:
            if len(config_ids) > 1:
                logger.warning(
                    "Ranking %s references multiple scholarship configuration IDs: %s. Using the first one.",
                    ranking_id,
                    sorted(config_ids),
                )
            config_id = next(iter(config_ids))
            config = await self.db.get(ScholarshipConfiguration, config_id)

        if not config:
            normalized_semester: Optional[str] = None
            if ranking.semester:
                semester_value = str(ranking.semester).lower()
                if semester_value not in {"yearly", "year"}:
                    normalized_semester = semester_value

            config_stmt = select(ScholarshipConfiguration).where(
                and_(
                    ScholarshipConfiguration.scholarship_type_id == ranking.scholarship_type_id,
                    ScholarshipConfiguration.academic_year == ranking.academic_year,
                    ScholarshipConfiguration.is_active.is_(True),
                )
            )
            if normalized_semester is not None:
                config_stmt = config_stmt.where(ScholarshipConfiguration.semester == normalized_semester)
            else:
                config_stmt = config_stmt.where(ScholarshipConfiguration.semester.is_(None))

            config_result = await self.db.execute(config_stmt)
            config = config_result.scalar_one_or_none()

        if not config or not config.has_college_quota or not config.quotas:
            raise ValueError(f"No matrix quota configuration found for scholarship type {ranking.scholarship_type_id}")

        quota_matrix = config.quotas  # {"nstc": {"EE": 2, "EN": 3}, "moe_1w": {...}}

        # Get all scholarship rules for eligibility checking
        rules_stmt = select(ScholarshipRule).where(
            and_(
                ScholarshipRule.scholarship_type_id == ranking.scholarship_type_id,
                ScholarshipRule.is_active.is_(True),
            )
        )
        rules_result = await self.db.execute(rules_stmt)
        rules = rules_result.scalars().all()

        # Sort ranking items by rank_position
        sorted_items = sorted(ranking.items, key=lambda x: x.rank_position)

        # Distribution tracking
        distribution_summary = {}
        total_allocated = 0

        # Process each sub-type按優先順序
        for sub_type_code in SUB_TYPE_PRIORITY:
            if sub_type_code not in quota_matrix:
                continue

            college_quotas = quota_matrix[sub_type_code]
            distribution_summary[sub_type_code] = {"colleges": {}}

            # Process each college within this sub-type
            for college_code, college_quota in college_quotas.items():
                admitted_count = 0
                backup_count = 0
                college_summary = {
                    "quota": college_quota,
                    "admitted": [],
                    "backup": [],
                }

                # Filter students for this sub-type and college
                for item in sorted_items:
                    app = item.application

                    # Check if already allocated to another sub-type
                    if item.allocated_sub_type is not None:
                        continue

                    # Check if student applied for this sub-type
                    if not self._student_applied_for_sub_type(app, sub_type_code):
                        continue

                    # Check if student belongs to this college
                    if not self._student_belongs_to_college(app, college_code):
                        continue

                    # Check eligibility rules for this sub-type
                    is_eligible, rule_check_result = await self._check_eligibility(app, sub_type_code, rules)

                    if not is_eligible:
                        logger.info(f"Student {app.id} not eligible for {sub_type_code}: {rule_check_result}")
                        continue

                    # Allocate or backup
                    if admitted_count < college_quota:
                        # Admitted (正取)
                        item.allocated_sub_type = sub_type_code
                        item.is_allocated = True
                        item.backup_position = None
                        item.status = "allocated"
                        item.allocation_reason = f"正取 {sub_type_code}-{college_code}"
                        admitted_count += 1
                        total_allocated += 1

                        college_summary["admitted"].append(
                            {
                                "rank_position": item.rank_position,
                                "application_id": app.id,
                                "student_name": self._get_student_name(app),
                            }
                        )
                    else:
                        # Backup (備取)
                        backup_count += 1
                        item.allocated_sub_type = sub_type_code
                        item.is_allocated = False
                        item.backup_position = backup_count
                        item.status = "waitlisted"
                        item.allocation_reason = f"備取第{backup_count}名 {sub_type_code}-{college_code}"

                        college_summary["backup"].append(
                            {
                                "rank_position": item.rank_position,
                                "backup_position": backup_count,
                                "application_id": app.id,
                                "student_name": self._get_student_name(app),
                            }
                        )

                college_summary["admitted_count"] = admitted_count
                college_summary["backup_count"] = backup_count
                distribution_summary[sub_type_code]["colleges"][college_code] = college_summary

        # Mark items not allocated to any sub-type
        for item in sorted_items:
            if item.allocated_sub_type is None:
                item.is_allocated = False
                item.status = "rejected"
                item.allocation_reason = "無符合的子類別或超出配額"

        # Flush changes to database
        await self.db.flush()

        # Update ranking statistics
        ranking.allocated_count = total_allocated
        ranking.distribution_executed = True

        await self.db.flush()

        return {
            "ranking_id": ranking_id,
            "total_allocated": total_allocated,
            "total_applications": len(sorted_items),
            "distribution_summary": distribution_summary,
        }

    def _student_applied_for_sub_type(self, app: Application, sub_type_code: str) -> bool:
        """Check if student applied for this sub-type"""
        if not app.scholarship_subtype_list:
            return False

        # scholarship_subtype_list is a JSON array
        applied_subtypes = app.scholarship_subtype_list
        if isinstance(applied_subtypes, list):
            return sub_type_code.lower() in [st.lower() for st in applied_subtypes]

        return False

    def _student_belongs_to_college(self, app: Application, college_code: str) -> bool:
        """Check if student belongs to this college"""
        if not app.student_data or not isinstance(app.student_data, dict):
            return False

        student_college = (
            app.student_data.get("college_code")
            or app.student_data.get("std_college")
            or app.student_data.get("academy_code")
            or ""
        )

        return student_college.upper() == college_code.upper()

    async def _check_eligibility(
        self, app: Application, sub_type_code: str, rules: List[ScholarshipRule]
    ) -> Tuple[bool, str]:
        """
        Check if student meets eligibility rules for this sub-type

        Returns: (is_eligible, reason)
        """
        # Filter rules for this sub-type
        sub_type_rules = [r for r in rules if r.sub_type == sub_type_code or r.sub_type is None]

        if not sub_type_rules:
            # No rules defined, assume eligible
            return True, "No rules defined"

        # Check each rule
        for rule in sub_type_rules:
            # TODO: Implement actual rule checking logic
            # For now, assume all students are eligible
            # In future, implement rule evaluation based on:
            # - rule.field_name
            # - rule.operator
            # - rule.expected_value
            # - app.student_data or app.submitted_form_data
            pass

        return True, "All rules passed"

    def _get_student_name(self, app: Application) -> str:
        """Extract student name from application"""
        if not app.student_data or not isinstance(app.student_data, dict):
            return "Unknown"

        return (
            app.student_data.get("std_cname")
            or app.student_data.get("name")
            or app.student_data.get("student_name")
            or "Unknown"
        )

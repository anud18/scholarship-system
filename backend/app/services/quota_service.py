"""
Quota management service

Unified service for managing scholarship quotas based on ScholarshipConfiguration.
"""

from typing import Any, Dict, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.enums import QuotaManagementMode
from app.models.scholarship import ScholarshipConfiguration


class QuotaService:
    """Unified quota management service"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_config(
        self, scholarship_type_id: int, academic_year: int, semester: Optional[str]
    ) -> Optional[ScholarshipConfiguration]:
        """
        Get active scholarship configuration

        Args:
            scholarship_type_id: Scholarship type ID
            academic_year: Academic year (Taiwan calendar, e.g., 113)
            semester: Semester ('first', 'second', or None for annual)

        Returns:
            Active ScholarshipConfiguration or None if not found
        """
        query = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                ScholarshipConfiguration.academic_year == academic_year,
                ScholarshipConfiguration.is_active == True,
            )
        )

        # Handle semester filtering
        if semester:
            query = query.where(ScholarshipConfiguration.semester == semester)
        else:
            query = query.where(ScholarshipConfiguration.semester.is_(None))

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_scholarship_quota(
        self, scholarship_type_id: int, sub_type: str, academic_year: int, semester: Optional[str]
    ) -> Dict[str, Any]:
        """
        Get quota information from ScholarshipConfiguration

        Args:
            scholarship_type_id: Scholarship type ID
            sub_type: Sub-type code (e.g., 'nstc', 'general')
            academic_year: Academic year
            semester: Semester

        Returns:
            Dictionary containing quota information:
            - total_quota: Total quota number (None if unlimited)
            - mode: Quota management mode
            - by_college: College-wise quota breakdown (for matrix mode)
        """
        config = await self.get_active_config(scholarship_type_id, academic_year, semester)

        if not config:
            return {"total_quota": None, "mode": "no_config", "by_college": None}

        # Determine quota based on management mode
        if config.quota_management_mode == QuotaManagementMode.matrix_based:
            # Matrix mode: quotas[sub_type][college_code]
            total_quota = config.get_sub_type_total_quota(sub_type)
            by_college = config.quotas.get(sub_type, {}) if config.quotas else {}
            return {"total_quota": total_quota, "mode": "matrix", "by_college": by_college}

        elif config.quota_management_mode == QuotaManagementMode.simple:
            # Simple mode: use total_quota directly
            return {"total_quota": config.total_quota, "mode": "simple", "by_college": None}

        elif config.quota_management_mode == QuotaManagementMode.college_based:
            # College-based mode: quotas[college_code] (not sub-type specific)
            # For this mode, total_quota applies to all sub-types combined
            return {"total_quota": config.total_quota, "mode": "college_based", "by_college": config.quotas}

        else:
            # No quota limit (QuotaManagementMode.none)
            return {"total_quota": None, "mode": "unlimited", "by_college": None}

    async def get_quota_usage(
        self, scholarship_type_id: int, sub_type: str, academic_year: int, semester: Optional[str]
    ) -> Dict[str, int]:
        """
        Calculate quota usage statistics

        Args:
            scholarship_type_id: Scholarship type ID
            sub_type: Sub-type code
            academic_year: Academic year
            semester: Semester

        Returns:
            Dictionary containing usage statistics:
            - approved: Number of approved applications
            - pending: Number of pending applications
            - rejected: Number of rejected applications
            - total: Total number of applications
        """
        base_conditions = and_(
            Application.scholarship_type_id == scholarship_type_id,
            Application.sub_scholarship_type == sub_type,
            Application.academic_year == academic_year,
        )

        if semester:
            base_conditions = and_(base_conditions, Application.semester == semester)

        # Count approved applications
        approved_stmt = select(func.count(Application.id)).where(
            and_(base_conditions, Application.status == ApplicationStatus.approved.value)
        )
        approved_result = await self.db.execute(approved_stmt)
        approved_count = approved_result.scalar() or 0

        # Count pending applications (submitted, under_review, etc.)
        pending_stmt = select(func.count(Application.id)).where(
            and_(
                base_conditions,
                Application.status.in_(
                    [
                        ApplicationStatus.submitted.value,
                        ApplicationStatus.under_review.value,
                        ApplicationStatus.pending_recommendation.value,
                        ApplicationStatus.recommended.value,
                    ]
                ),
            )
        )
        pending_result = await self.db.execute(pending_stmt)
        pending_count = pending_result.scalar() or 0

        # Count rejected applications
        rejected_stmt = select(func.count(Application.id)).where(
            and_(base_conditions, Application.status == ApplicationStatus.rejected.value)
        )
        rejected_result = await self.db.execute(rejected_stmt)
        rejected_count = rejected_result.scalar() or 0

        # Count total applications
        total_stmt = select(func.count(Application.id)).where(base_conditions)
        total_result = await self.db.execute(total_stmt)
        total_count = total_result.scalar() or 0

        return {
            "approved": approved_count,
            "pending": pending_count,
            "rejected": rejected_count,
            "total": total_count,
        }

    async def get_quota_status(
        self, scholarship_type_id: int, sub_type: str, academic_year: int, semester: Optional[str]
    ) -> Dict[str, Any]:
        """
        Get comprehensive quota status (quota + usage)

        Args:
            scholarship_type_id: Scholarship type ID
            sub_type: Sub-type code
            academic_year: Academic year
            semester: Semester

        Returns:
            Complete quota status information
        """
        # Get quota information
        quota_info = await self.get_scholarship_quota(scholarship_type_id, sub_type, academic_year, semester)

        # Get usage statistics
        usage = await self.get_quota_usage(scholarship_type_id, sub_type, academic_year, semester)

        # Calculate availability
        total_quota = quota_info["total_quota"]
        if total_quota is not None:
            total_available = total_quota - usage["approved"]
            usage_percent = (usage["approved"] / total_quota * 100) if total_quota > 0 else 0
        else:
            total_available = None  # Unlimited
            usage_percent = 0

        return {
            "scholarship_type_id": scholarship_type_id,
            "sub_type": sub_type,
            "academic_year": academic_year,
            "semester": semester,
            "total_quota": total_quota,
            "quota_mode": quota_info["mode"],
            "by_college": quota_info["by_college"],
            "total_used": usage["approved"],
            "total_available": total_available,
            "pending": usage["pending"],
            "rejected": usage["rejected"],
            "total_applications": usage["total"],
            "usage_percent": usage_percent,
        }

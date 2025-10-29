"""
Alternate Promotion Service

This service handles finding and promoting alternate students when
primary allocated students lose eligibility during roster generation.

Key Functions:
- Find eligible alternate students from backup allocations
- Update CollegeRankingItem allocation status
- Apply scholarship-specific eligibility rules (e.g., PhD requirements)

Note: This service only modifies CollegeRankingItem, not PaymentRosterItem.
RosterItem creation is handled by RosterService.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.application import Application
from app.models.college_review import CollegeRankingItem
from app.models.scholarship import ScholarshipConfiguration
from app.services.plugins.phd_eligibility_plugin import check_phd_alternate_eligibility, is_phd_scholarship
from app.utils.application_helpers import get_snapshot_student_name

logger = logging.getLogger(__name__)


class AlternatePromotionService:
    """Service for finding and promoting alternate students"""

    def __init__(self, db: Session):
        self.db = db

    def find_and_promote_alternate(
        self,
        ranking_item: CollegeRankingItem,
        original_application: Application,
        scholarship_config: ScholarshipConfiguration,
        ineligible_reason: str,
        skip_eligibility_check: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Find eligible alternate and update CollegeRankingItem allocation status

        This method is called during roster generation when a primary allocated
        student loses eligibility. It finds the next eligible alternate and
        updates the database accordingly.

        Process:
        1. Mark original ranking_item as rejected
        2. Find eligible alternate from backup_allocations
        3. Update alternate ranking_item to allocated
        4. Return promotion result

        Note: This only modifies CollegeRankingItem. RosterItem creation
        is handled by the calling RosterService.

        Args:
            ranking_item: The original student's CollegeRankingItem (will be marked rejected)
            original_application: The original student's Application
            scholarship_config: Scholarship configuration
            ineligible_reason: Reason why original student lost eligibility
            skip_eligibility_check: Skip special eligibility checks (for manual override)

        Returns:
            {
                "promoted_item": CollegeRankingItem (the promoted alternate),
                "original_student": str,
                "promoted_student": str,
                "checked_count": int
            } or None if no eligible alternate found
        """
        try:
            # 1. Mark original ranking_item as rejected
            original_student_name = get_snapshot_student_name(original_application)

            ranking_item.status = "rejected"
            ranking_item.allocation_reason = ineligible_reason
            ranking_item.is_allocated = False
            self.db.add(ranking_item)

            logger.info(
                f"Marked ranking_item {ranking_item.id} as rejected: " f"{original_student_name} - {ineligible_reason}"
            )

            # 2. Get original student data for comparison
            original_student_data = original_application.student_data or {}

            # 3. Find eligible alternate
            eligible_result = self._find_eligible_alternate(
                ranking_id=ranking_item.ranking_id,
                sub_type=ranking_item.allocated_sub_type,
                original_student_data=original_student_data,
                scholarship_config=scholarship_config,
                skip_special_eligibility=skip_eligibility_check,
            )

            if not eligible_result or not eligible_result.get("ranking_item"):
                logger.warning(
                    f"No eligible alternate found for ranking_item {ranking_item.id}, "
                    f"checked {eligible_result.get('checked_count', 0) if eligible_result else 0} candidates"
                )
                return None

            alternate_item = eligible_result["ranking_item"]
            alternate_app = alternate_item.application
            alternate_student_name = get_snapshot_student_name(alternate_app)

            # 4. Update alternate ranking_item to allocated
            alternate_item.is_allocated = True
            alternate_item.status = "allocated"
            alternate_item.allocated_sub_type = ranking_item.allocated_sub_type
            alternate_item.allocation_reason = f"備取遞補（原學生 {original_student_name} 失格：{ineligible_reason}）"
            self.db.add(alternate_item)

            logger.info(
                f"Promoted alternate: {alternate_student_name} (ranking_item {alternate_item.id}) "
                f"to replace {original_student_name}"
            )

            # 5. Flush to database (will be committed by RosterService)
            self.db.flush()

            return {
                "promoted_item": alternate_item,
                "original_student": original_student_name,
                "promoted_student": alternate_student_name,
                "checked_count": eligible_result["checked_count"],
            }

        except Exception as e:
            logger.error(f"Error in find_and_promote_alternate: {e}")
            return None

    def _find_eligible_alternate(
        self,
        ranking_id: int,
        sub_type: Optional[str],
        original_student_data: Dict[str, Any],
        scholarship_config: ScholarshipConfiguration,
        skip_special_eligibility: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Find the next eligible alternate student from backup allocations

        Search Process:
        1. Get all CollegeRankingItem with backup_allocations for this ranking
        2. Filter by sub_type if specified
        3. Sort by backup_position (ascending)
        4. Apply whitelist checking
        5. Apply scholarship-specific eligibility rules (delegate to plugin if PhD)
        6. Return first eligible alternate

        Args:
            ranking_id: CollegeRanking ID
            sub_type: Scholarship sub-type to filter by
            original_student_data: Original student's data for comparison
            scholarship_config: Scholarship configuration
            skip_special_eligibility: Skip special eligibility checks

        Returns:
            {
                "ranking_item": CollegeRankingItem,
                "backup_position": int,
                "checked_count": int
            } or None
        """
        try:
            # Get all ranking items with backup allocations
            potential_alternates = (
                self.db.query(CollegeRankingItem)
                .filter(
                    and_(
                        CollegeRankingItem.ranking_id == ranking_id,
                        CollegeRankingItem.backup_allocations.isnot(None),
                        CollegeRankingItem.is_allocated.is_(False),  # Not already allocated
                        CollegeRankingItem.status != "rejected",  # Not rejected
                    )
                )
                .all()
            )

            logger.info(f"Found {len(potential_alternates)} potential alternates for ranking {ranking_id}")

            # Build a list of (ranking_item, backup_position) tuples
            candidates = []
            for item in potential_alternates:
                if not item.backup_allocations:
                    continue

                # Check each backup allocation for matching sub_type
                for backup in item.backup_allocations:
                    backup_sub_type = backup.get("sub_type")
                    backup_position = backup.get("backup_position", 999)

                    # Filter by sub_type if specified
                    if sub_type and backup_sub_type:
                        if backup_sub_type.lower() != sub_type.lower():
                            continue

                    candidates.append(
                        {"ranking_item": item, "backup_position": backup_position, "sub_type": backup_sub_type}
                    )

            # Sort by backup_position (ascending)
            candidates.sort(key=lambda x: x["backup_position"])

            logger.info(f"Found {len(candidates)} candidates after filtering by sub_type={sub_type}")

            # Check each candidate for eligibility
            checked_count = 0
            for candidate in candidates:
                checked_count += 1
                item = candidate["ranking_item"]
                application = item.application

                if not application:
                    logger.warning(f"CollegeRankingItem {item.id} has no application")
                    continue

                # Check whitelist if enabled
                if scholarship_config.scholarship_type.whitelist_enabled:
                    if not application.student or not application.student.nycu_id:
                        logger.info(f"Alternate student (app {application.id}) missing nycu_id")
                        continue

                    nycu_id = application.student.nycu_id
                    is_in_whitelist = scholarship_config.is_student_in_whitelist(nycu_id, sub_type)

                    if not is_in_whitelist:
                        logger.info(f"Alternate student {nycu_id} not in whitelist")
                        continue

                # Apply scholarship-specific eligibility rules
                if not skip_special_eligibility:
                    alternate_student_data = application.student_data or {}

                    # Check if PhD scholarship
                    if is_phd_scholarship(scholarship_config):
                        is_eligible, rejection_reason = check_phd_alternate_eligibility(
                            db=self.db,
                            student_data=alternate_student_data,
                            original_student_data=original_student_data,
                            scholarship_config=scholarship_config,
                            max_months=36,  # Can be configured from database in the future
                        )

                        if not is_eligible:
                            logger.info(
                                f"Alternate student (app {application.id}) failed PhD eligibility: {rejection_reason}"
                            )
                            continue

                # Found eligible alternate!
                logger.info(
                    f"Found eligible alternate: app {application.id}, "
                    f"backup_position={candidate['backup_position']}, checked={checked_count}"
                )

                return {
                    "ranking_item": item,
                    "backup_position": candidate["backup_position"],
                    "checked_count": checked_count,
                }

            # No eligible alternate found
            logger.info(f"No eligible alternate found after checking {checked_count} candidates")
            return {"ranking_item": None, "backup_position": None, "checked_count": checked_count}

        except Exception as e:
            logger.error(f"Error finding eligible alternate: {e}")
            return None

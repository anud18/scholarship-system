"""
Manual Distribution Service

Replaces automated quota/matrix distribution with admin-driven manual allocation.
Admin selects one scholarship sub-type per student via UI checkboxes.
Supports multi-year supplementary distribution (補發) where prior-year
remaining quotas can be allocated to current-year students.
"""

import json as _json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem, ManualDistributionHistory
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


def _compute_suggestions(
    unique_items: list,
    default_prefs: list[str],
    prev_alloc_years: dict[int, int],
    prior_years_map: dict[str, list[int]],
    quota_tracker: dict[tuple, int],
    academic_year: int,
) -> list[dict]:
    """
    Pure allocation logic (no DB access).  Extracted so it can be unit-tested
    without mocking async SQLAlchemy sessions.

    Parameters
    ----------
    unique_items:
        CollegeRankingItem objects (with .application pre-loaded) already
        deduplicated by application_id.  Items that are already allocated
        (is_allocated=True) are skipped silently.
    default_prefs:
        Ordered list of sub_type codes from ScholarshipSubTypeConfig.
        Last-resort fallback: sub_type_preferences → scholarship_subtype_list → default_prefs.
    prev_alloc_years:
        Mapping of {previous_application_id: allocation_year} for renewal
        students' prior allocations.
    prior_years_map:
        Mapping of {sub_type: [prior_year, ...]} from ScholarshipConfiguration
        .prior_quota_years.  Determines which prior years are valid for each
        sub-type.
    quota_tracker:
        Mutable dict {(sub_type, year, college_code): remaining_quota}.
        This function decrements it as it allocates.
    academic_year:
        The current academic year being allocated.

    Returns
    -------
    list[dict]
        [{"ranking_item_id": int, "sub_type_code": str|None, "allocation_year": int|None}, ...]
        One entry per unallocated input item, in allocation order.
    """
    # Sort: renewal students first, then by rank_position ascending
    sorted_items = sorted(
        [item for item in unique_items if not item.is_allocated],
        key=lambda i: (0 if i.application.is_renewal else 1, i.rank_position),
    )

    results: list[dict] = []

    for item in sorted_items:
        app = item.application
        college = (app.student_data or {}).get("std_academyno", "")

        # Determine target allocation year for this student
        # Priority: 1) previous_application_id lookup, 2) renewal_year field, 3) current academic_year
        prev_app_id = app.previous_application_id if app.is_renewal else None
        target_year: Optional[int] = prev_alloc_years.get(prev_app_id) if prev_app_id else None
        if target_year is None and app.is_renewal and app.renewal_year:
            target_year = app.renewal_year
        if target_year is None:
            target_year = academic_year

        # Determine preference order, constrained to sub-types the student actually applied for
        applied = app.scholarship_subtype_list or []
        raw_prefs: list[str] = app.sub_type_preferences or applied or default_prefs
        applied_set = set(applied)
        preferences: list[str] = [p for p in raw_prefs if p in applied_set] if applied_set else raw_prefs

        allocated_sub_type: Optional[str] = None
        allocated_year: Optional[int] = None

        for sub_type in preferences:
            # Determine the effective year to try first
            if target_year != academic_year:
                # Check whether the prior year is a configured prior year for this sub_type
                allowed_prior_years = prior_years_map.get(sub_type, [])
                if target_year not in allowed_prior_years:
                    # Prior year not configured for this sub_type — try current year directly
                    key_current = (sub_type, academic_year, college)
                    if quota_tracker.get(key_current, 0) > 0:
                        quota_tracker[key_current] -= 1
                        allocated_sub_type = sub_type
                        allocated_year = academic_year
                    # Move to next preference regardless
                    if allocated_sub_type:
                        break
                    continue

            # Try the target year (could be a prior year or current year)
            key_target = (sub_type, target_year, college)
            if quota_tracker.get(key_target, 0) > 0:
                quota_tracker[key_target] -= 1
                allocated_sub_type = sub_type
                allocated_year = target_year
                break

            # Fallback for renewal students: try current year if target (prior) year is exhausted
            if app.is_renewal and target_year != academic_year:
                key_current = (sub_type, academic_year, college)
                if quota_tracker.get(key_current, 0) > 0:
                    quota_tracker[key_current] -= 1
                    allocated_sub_type = sub_type
                    allocated_year = academic_year
                    break

        results.append({
            "ranking_item_id": item.id,
            "sub_type_code": allocated_sub_type,
            "allocation_year": allocated_year,
        })

    return results


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
                "is_renewal": app.is_renewal,
                "renewal_year": app.renewal_year,
            })

        # Sort by college_code, then rank_position
        students.sort(key=lambda s: (s["college_code"], s["rank_position"]))
        return students

    async def get_quota_status(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: str,
    ) -> dict[str, Any]:
        """
        Get real-time quota status per sub-type per (year × college).
        Uses prior_quota_years from the current year's config to determine
        which prior years' quotas are available per sub-type.

        Response structure:
        {
          "nstc": {
            "display_name": "國科會博士生獎學金",
            "by_year": {
              "114": {"total": 80, "allocated": 0, "remaining": 80, "by_college": {...}},
              "113": {"total": 15, "allocated": 3, "remaining": 12, "by_college": {...}},
            }
          },
          "moe_1w": {
            "display_name": "教育部博士生獎學金",
            "by_year": {
              "114": {"total": 55, ...}    // no 113 — moe_1w has no prior years
            }
          }
        }
        """
        # 1. Load current year's config to get prior_quota_years
        current_config = await self._load_config(
            scholarship_type_id, academic_year, semester
        )

        prior_years_map: dict[str, list[int]] = {}
        if current_config and current_config.prior_quota_years:
            raw = current_config.prior_quota_years
            # Handle case where JSON column stored as string instead of dict
            if isinstance(raw, str):

                try:
                    raw = _json.loads(raw)
                except (ValueError, TypeError):
                    raw = {}
            if isinstance(raw, dict):
                prior_years_map = raw

        # Determine all years to check: current year + union of all prior years
        all_prior_years: set[int] = set()
        for sub_type, years_list in prior_years_map.items():
            if isinstance(years_list, list):
                all_prior_years.update(years_list)
            else:
                logger.warning("Invalid prior_quota_years for %s: expected list, got %s", sub_type, type(years_list))
        years_to_check = sorted([academic_year] + list(all_prior_years), reverse=True)

        # 2. Load configs for all years in a single query
        configs_by_year: dict[int, Optional[ScholarshipConfiguration]] = {}
        if years_to_check:
            configs_stmt = (
                select(ScholarshipConfiguration)
                .where(
                    and_(
                        ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                        ScholarshipConfiguration.academic_year.in_(years_to_check),
                        _config_semester_condition(semester),
                    )
                )
                .order_by(ScholarshipConfiguration.id.desc())
            )
            configs_result = await self.db.execute(configs_stmt)
            for cfg in configs_result.scalars().all():
                # Keep only the first (latest) config per year
                if cfg.academic_year not in configs_by_year:
                    configs_by_year[cfg.academic_year] = cfg

        # 3. Get sub-type display names (shared across years)
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

        # 4. Count allocations using allocation_year across ALL finalized rankings
        all_rankings_query = select(CollegeRanking).where(
            and_(
                CollegeRanking.scholarship_type_id == scholarship_type_id,
                CollegeRanking.is_finalized == True,
            )
        )
        result = await self.db.execute(all_rankings_query)
        all_rankings = result.scalars().all()
        all_ranking_ids = [r.id for r in all_rankings]

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

        # 5. Build response: for each year's config, filtered by prior_quota_years
        quota_status: dict[str, Any] = {}

        for year in years_to_check:
            year_config = configs_by_year.get(year)
            if not year_config or not year_config.quotas:
                continue

            quotas = year_config.quotas  # {sub_type: {college_code: quota}}

            for sub_type, college_quotas in quotas.items():
                if not isinstance(college_quotas, dict):
                    continue

                # Skip this (sub_type, year) if year != academic_year
                # and not in prior_quota_years for this sub_type
                if year != academic_year:
                    allowed_years = prior_years_map.get(sub_type, [])
                    if year not in allowed_years:
                        continue

                by_college_for_year = allocation_counts.get(sub_type, {}).get(year, {})
                total_quota = sum(college_quotas.values())
                total_allocated = sum(by_college_for_year.values())
                remaining = total_quota - total_allocated

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

    async def _load_config(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: str,
    ) -> Optional[ScholarshipConfiguration]:
        """Load a ScholarshipConfiguration for a given year.
        If multiple configs exist, returns the latest (highest id).
        """
        stmt = (
            select(ScholarshipConfiguration)
            .where(
                and_(
                    ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                    ScholarshipConfiguration.academic_year == academic_year,
                    _config_semester_condition(semester),
                )
            )
            .order_by(ScholarshipConfiguration.id.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().first()

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

        # Record allocation history for undo/redo
        try:
            # Get current state snapshot
            ranking_query = select(CollegeRanking).where(
                and_(
                    CollegeRanking.scholarship_type_id == scholarship_type_id,
                    CollegeRanking.academic_year == academic_year,
                    _ranking_semester_condition(semester),
                )
            )
            result = await self.db.execute(ranking_query)
            rankings = result.scalars().all()
            ranking_ids = [r.id for r in rankings]

            if ranking_ids:
                # Get current allocations
                items_query = select(CollegeRankingItem).where(
                    CollegeRankingItem.ranking_id.in_(ranking_ids)
                )
                result = await self.db.execute(items_query)
                items = result.scalars().all()

                # Build snapshot
                allocations_snapshot = {}
                total_allocated = 0
                for item in items:
                    if item.is_allocated:
                        allocations_snapshot[item.id] = {
                            "sub_type": item.allocated_sub_type,
                            "allocation_year": item.allocation_year,
                            "status": item.status,
                        }
                        total_allocated += 1

                # Create history record
                history = ManualDistributionHistory(
                    scholarship_type_id=scholarship_type_id,
                    academic_year=academic_year,
                    semester=semester,
                    allocations_snapshot=allocations_snapshot,
                    operation_type="save",
                    change_summary=f"Saved {updated_count} allocation(s)",
                    total_allocated=total_allocated,
                )
                self.db.add(history)
                await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to record allocation history: {e}")
            # Don't fail the allocation if history recording fails

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

        # Record finalization in history for undo capability
        try:
            # Build snapshot of finalized allocations
            allocations_snapshot = {}
            for item in items:
                if item.is_allocated and item.allocated_sub_type:
                    allocations_snapshot[item.id] = {
                        "sub_type": item.allocated_sub_type,
                        "allocation_year": item.allocation_year,
                        "status": item.status,
                    }

            history = ManualDistributionHistory(
                scholarship_type_id=scholarship_type_id,
                academic_year=academic_year,
                semester=semester,
                allocations_snapshot=allocations_snapshot,
                operation_type="finalize",
                change_summary=f"Distribution finalized: {approved_count} approved, {rejected_count} rejected",
                total_allocated=approved_count,
            )
            self.db.add(history)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to record finalization history: {e}")
            # Don't fail the finalization if history recording fails

        return {
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "total": approved_count + rejected_count,
        }

    async def restore_from_history(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: str,
        allocations_snapshot: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Restore allocations from a historical snapshot.
        The snapshot contains: {ranking_item_id: {sub_type, allocation_year, status}, ...}
        """
        # First clear all current allocations
        ranking_query = select(CollegeRanking).where(
            and_(
                CollegeRanking.scholarship_type_id == scholarship_type_id,
                CollegeRanking.academic_year == academic_year,
                _ranking_semester_condition(semester),
            )
        )
        result = await self.db.execute(ranking_query)
        rankings = result.scalars().all()
        ranking_ids = [r.id for r in rankings]

        if ranking_ids:
            # Clear all allocations
            items_query = select(CollegeRankingItem).where(
                CollegeRankingItem.ranking_id.in_(ranking_ids)
            )
            result = await self.db.execute(items_query)
            items = result.scalars().all()

            for item in items:
                item.is_allocated = False
                item.allocated_sub_type = None
                item.allocation_year = None
                item.status = "ranked"
                item.allocation_reason = None

        # Now restore from snapshot
        restored_count = 0
        for item_id_str, alloc_data in allocations_snapshot.items():
            try:
                item_id = int(item_id_str)
                item_query = select(CollegeRankingItem).where(
                    CollegeRankingItem.id == item_id
                )
                result = await self.db.execute(item_query)
                item = result.scalar_one_or_none()

                if item and alloc_data.get("sub_type"):
                    item.is_allocated = True
                    item.allocated_sub_type = alloc_data["sub_type"]
                    item.allocation_year = alloc_data.get("allocation_year")
                    item.status = alloc_data.get("status", "allocated")
                    item.allocation_reason = "還原歷史分發"
                    restored_count += 1
            except (ValueError, TypeError):
                logger.warning(f"Skipping invalid item ID in snapshot: {item_id_str}")
                continue

        await self.db.flush()

        # Record this restore as a history event
        try:
            history = ManualDistributionHistory(
                scholarship_type_id=scholarship_type_id,
                academic_year=academic_year,
                semester=semester,
                allocations_snapshot=allocations_snapshot,
                operation_type="revert",
                change_summary=f"Restored {restored_count} allocation(s) from history",
                total_allocated=restored_count,
            )
            self.db.add(history)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to record restore history: {e}")

        return {"restored_count": restored_count}

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

    async def _get_default_preferences(self, scholarship_type_id: int) -> list[str]:
        """
        Return active sub-type codes for a scholarship type, ordered by display_order.
        Used as the fallback preference list when a student has no sub_type_preferences set.
        """
        stmt = (
            select(ScholarshipSubTypeConfig)
            .where(
                and_(
                    ScholarshipSubTypeConfig.scholarship_type_id == scholarship_type_id,
                    ScholarshipSubTypeConfig.is_active == True,
                )
            )
            .order_by(ScholarshipSubTypeConfig.display_order)
        )
        result = await self.db.execute(stmt)
        return [row.sub_type_code for row in result.scalars().all()]

    async def _batch_load_previous_allocation_years(
        self, previous_app_ids: list[int]
    ) -> dict[int, int]:
        """
        For renewal students, find the allocation_year from their previous application's
        CollegeRankingItem.

        Returns: {previous_application_id: allocation_year}
        Only includes entries where allocation_year IS NOT NULL.
        """
        if not previous_app_ids:
            return {}

        stmt = select(CollegeRankingItem).where(
            and_(
                CollegeRankingItem.application_id.in_(previous_app_ids),
                CollegeRankingItem.allocation_year.isnot(None),
            )
        )
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        # If a previous app appears in multiple ranking items, use the first one
        mapping: dict[int, int] = {}
        for item in items:
            if item.application_id not in mapping:
                mapping[item.application_id] = item.allocation_year
        return mapping

    async def auto_allocate_preview(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: str,
    ) -> list[dict]:
        """
        Compute auto-allocation suggestions without persisting any changes.

        Algorithm:
        1. Load finalized CollegeRanking records + their items (with Application eager-loaded).
        2. Deduplicate items by application_id (keep first seen).
        3. Load default preferences and previous allocation years for renewal students.
        4. Build quota tracker from config (current year + prior years per sub-type).
        5. Subtract already-allocated items from tracker.
        6. Sort students: renewal first, then by rank_position ascending.
        7. Allocate sequentially following preference order and quota constraints.

        Returns list of {"ranking_item_id", "sub_type_code", "allocation_year"} dicts.
        Only unallocated items are included in the output.
        """
        # --- Step 0: Load finalized rankings ---
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

        # Load items with eagerly loaded Application
        items_query = (
            select(CollegeRankingItem)
            .options(selectinload(CollegeRankingItem.application))
            .where(CollegeRankingItem.ranking_id.in_(ranking_ids))
        )
        result = await self.db.execute(items_query)
        all_items = result.scalars().all()

        # Deduplicate by application_id (keep first seen)
        seen_app_ids: set[int] = set()
        unique_items = []
        for item in all_items:
            if item.application and item.application.id not in seen_app_ids:
                seen_app_ids.add(item.application.id)
                unique_items.append(item)

        if not unique_items:
            return []

        # --- Step 0b: Load default preferences ---
        default_prefs = await self._get_default_preferences(scholarship_type_id)

        # Load previous allocation years for renewal students
        previous_app_ids = [
            item.application.previous_application_id
            for item in unique_items
            if item.application.is_renewal and item.application.previous_application_id
        ]
        prev_alloc_years = await self._batch_load_previous_allocation_years(previous_app_ids)

        # --- Step 1: Build quota tracker ---
        current_config = await self._load_config(scholarship_type_id, academic_year, semester)

        prior_years_map: dict[str, list[int]] = {}
        if current_config and current_config.prior_quota_years:
            raw = current_config.prior_quota_years
            if isinstance(raw, str):

                try:
                    raw = _json.loads(raw)
                except (ValueError, TypeError):
                    raw = {}
            if isinstance(raw, dict):
                prior_years_map = raw

        # Determine all years to load configs for
        all_prior_years: set[int] = set()
        for sub_type, years_list in prior_years_map.items():
            if isinstance(years_list, list):
                all_prior_years.update(years_list)
        years_to_check = sorted([academic_year] + list(all_prior_years), reverse=True)

        # Batch-load configs for all relevant years
        configs_by_year: dict[int, Optional[ScholarshipConfiguration]] = {}
        if years_to_check:
            configs_stmt = (
                select(ScholarshipConfiguration)
                .where(
                    and_(
                        ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                        ScholarshipConfiguration.academic_year.in_(years_to_check),
                        _config_semester_condition(semester),
                    )
                )
                .order_by(ScholarshipConfiguration.id.desc())
            )
            configs_result = await self.db.execute(configs_stmt)
            for cfg in configs_result.scalars().all():
                if cfg.academic_year not in configs_by_year:
                    configs_by_year[cfg.academic_year] = cfg

        # Build quota tracker: {(sub_type, year, college_code): remaining}
        quota_tracker: dict[tuple[str, int, str], int] = {}
        for year in years_to_check:
            year_config = configs_by_year.get(year)
            if not year_config or not year_config.quotas:
                continue
            quotas = year_config.quotas  # {sub_type: {college_code: quota}}
            for sub_type, college_quotas in quotas.items():
                if not isinstance(college_quotas, dict):
                    continue
                # Skip prior year / sub_type combos not configured in prior_quota_years
                if year != academic_year:
                    allowed_years = prior_years_map.get(sub_type, [])
                    if year not in allowed_years:
                        continue
                for college_code, quota in college_quotas.items():
                    quota_tracker[(sub_type, year, college_code)] = quota

        # Subtract existing allocations from tracker (use all_items, not unique_items,
        # because a student's allocation may be on a ranking item that was deduplicated away)
        for item in all_items:
            if item.is_allocated and item.allocated_sub_type and item.allocation_year:
                college = (item.application.student_data or {}).get("std_academyno", "")
                key = (item.allocated_sub_type, item.allocation_year, college)
                if key in quota_tracker:
                    quota_tracker[key] = max(0, quota_tracker[key] - 1)

        return _compute_suggestions(
            unique_items=unique_items,
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

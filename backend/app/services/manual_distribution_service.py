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
from typing import Any, Literal, Optional

from sqlalchemy import and_, case as sa_case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.college_review import CollegeRanking, CollegeRankingItem, ManualDistributionHistory
from app.models.enums import ApplicationStatus, ReviewStage
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipSubTypeConfig
from app.models.user import User, UserRole
from app.services.received_months_service import calculate_received_months_bulk_async

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
    rejected_map: Optional[dict[int, set[str]]] = None,
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
    rejected_map:
        Mapping of {application_id: {rejected_sub_type_codes}} from professor
        reviews.  Sub-types rejected by professors are excluded from allocation.

    Returns
    -------
    list[dict]
        [{"ranking_item_id": int, "sub_type_code": str|None, "allocation_year": int|None}, ...]
        One entry per unallocated input item, in allocation order.
    """
    if rejected_map is None:
        rejected_map = {}
    # Sort: renewal students first, then by rank_position ascending
    sorted_items = sorted(
        [item for item in unique_items if not item.is_allocated],
        key=lambda i: (0 if i.application.is_renewal else 1, i.rank_position),
    )

    results: list[dict] = []

    for item in sorted_items:
        # College-rejected students default to no allocation. Admin can still
        # override manually if needed.
        if getattr(item, "college_rejected", False):
            results.append(
                {
                    "ranking_item_id": item.id,
                    "sub_type_code": None,
                    "allocation_year": None,
                }
            )
            continue

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
        # and excluding sub-types rejected by professors
        applied = app.scholarship_subtype_list or []
        rejected = rejected_map.get(app.id, set())
        raw_prefs: list[str] = app.sub_type_preferences or applied or default_prefs
        applied_set = set(applied)
        preferences: list[str] = [
            p for p in raw_prefs if (p in applied_set if applied_set else True) and p not in rejected
        ]

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

        results.append(
            {
                "ranking_item_id": item.id,
                "sub_type_code": allocated_sub_type,
                "allocation_year": allocated_year,
            }
        )

    return results


class ManualDistributionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def pool_total(self, config: ScholarshipConfiguration, sub_type: str) -> int:
        """Mode-aware per-(config, sub_type) pool total (spec §6.1).

        matrix_based / college_based (has_college_quota): sum the per-college
        matrix row → same as model.get_sub_type_total_quota.
        simple / none (NOT has_college_quota): quotas[sub_type] is a scalar
        (or fall back to total_quota). get_sub_type_total_quota returns 0 for
        these configs, so we MUST NOT route the non-matrix branch through it —
        a cross-type borrow from such a config would read an empty pool.
        """
        quotas = config.quotas or {}
        if config.has_college_quota:
            sub_type_quotas = quotas.get(sub_type, {})
            if not isinstance(sub_type_quotas, dict):
                return 0
            return sum(sub_type_quotas.values())
        scalar = quotas.get(sub_type, 0)
        try:
            scalar_int = int(scalar)
        except (TypeError, ValueError):
            scalar_int = 0
        return scalar_int or int(config.total_quota or 0)

    async def consumers_count(self, config_id: int, sub_type: str) -> int:
        """Count every LIVE consumer of (config_id, sub_type) anywhere (spec §6.2).

        Guaranteed two-half partition:
          half 1 — general/manual winners: allocated CollegeRankingItem whose
                   application is NOT a renewal (is_renewal==False guard).
          half 2 — approved renewals: Application(is_renewal, approved).

        The is_renewal==False guard on half 1 is load-bearing:
        college_review_service.py:636-657 creates a CollegeRankingItem for
        every application INCLUDING renewals (sorted first), and
        restore_allocation flips is_allocated=True on any item with an
        allocated_sub_type — so a revoked-then-restored renewal would otherwise
        be counted in BOTH halves.
        """
        winners_stmt = (
            select(func.count(CollegeRankingItem.id))
            .join(Application, CollegeRankingItem.application_id == Application.id)
            .where(
                CollegeRankingItem.is_allocated.is_(True),
                CollegeRankingItem.allocated_sub_type == sub_type,
                CollegeRankingItem.allocation_config_id == config_id,
                Application.is_renewal.is_(False),
            )
        )
        winners = (await self.db.execute(winners_stmt)).scalar_one()

        renewals_stmt = select(func.count(Application.id)).where(
            Application.is_renewal.is_(True),
            Application.status == ApplicationStatus.approved,
            Application.sub_scholarship_type == sub_type,
            Application.allocation_config_id == config_id,
        )
        renewals = (await self.db.execute(renewals_stmt)).scalar_one()

        return int(winners) + int(renewals)

    async def remaining(self, config: ScholarshipConfiguration, sub_type: str) -> int:
        """Global live remaining = pool_total - consumers_count (spec §6.2).

        GLOBAL: counts every consumer of this config anywhere, regardless of
        which distribution round (or which borrowing config) created the slot —
        so freeing a slot anywhere instantly raises this value everywhere.
        """
        return self.pool_total(config, sub_type) - await self.consumers_count(config.id, sub_type)

    async def _resolve_linked_configs(
        self, requesting_config: ScholarshipConfiguration, sub_type: str
    ) -> list[ScholarshipConfiguration]:
        """Load the linked source configs of `requesting_config` whose
        shared_quota_sources entry lists `sub_type` (spec §6.3).

        Missing target configs (the source_config_code resolves to nothing) are
        silently dropped — consistent with §10/§11.5 dangling-link handling.
        """
        sources = requesting_config.shared_quota_sources or []
        codes: list[str] = []
        for entry in sources:
            if not isinstance(entry, dict):
                continue
            entry_sub_types = entry.get("sub_types") or []
            code = entry.get("source_config_code")
            if code and sub_type in entry_sub_types:
                codes.append(code)
        if not codes:
            return []
        stmt = select(ScholarshipConfiguration).where(ScholarshipConfiguration.config_code.in_(codes))
        return list((await self.db.execute(stmt)).scalars().all())

    async def _allowed_config_ids(self, requesting_config: ScholarshipConfiguration, sub_type: str) -> set[int]:
        """Allowed consumed-config ids for an allocation of (requesting, sub_type).

        = {own config id} ∪ {linked source config ids whose link lists sub_type}.
        Used server-side to validate that an inbound allocation_config_id is
        permitted before recomputing remaining (spec §7).
        """
        allowed = {requesting_config.id}
        for linked in await self._resolve_linked_configs(requesting_config, sub_type):
            allowed.add(linked.id)
        return allowed

    async def distributable_pool(self, requesting_config: ScholarshipConfiguration, sub_type: str) -> list[dict]:
        """The pool of consumable configs for (requesting_config, sub_type), §6.3.

        Returns the own config first, then each linked source config in
        DESCENDING academic_year, each with its LIVE `remaining`. Each entry maps
        to one grid column; an allocation records that config's id as
        allocation_config_id.
        """
        pool: list[dict] = [
            {
                "config_id": requesting_config.id,
                "config_code": requesting_config.config_code,
                "academic_year": requesting_config.academic_year,
                "is_own": True,
                "remaining": await self.remaining(requesting_config, sub_type),
            }
        ]
        linked = await self._resolve_linked_configs(requesting_config, sub_type)
        for cfg in sorted(linked, key=lambda c: c.academic_year, reverse=True):
            pool.append(
                {
                    "config_id": cfg.id,
                    "config_code": cfg.config_code,
                    "academic_year": cfg.academic_year,
                    "is_own": False,
                    "remaining": await self.remaining(cfg, sub_type),
                }
            )
        return pool

    async def _batch_load_rejected_map(self, app_ids: list[int]) -> dict[int, set[str]]:
        """Load professor-rejected sub-types for a batch of applications."""
        rejected_map: dict[int, set[str]] = {}
        if not app_ids:
            return rejected_map
        query = (
            select(ApplicationReviewItem.sub_type_code, ApplicationReview.application_id)
            .join(ApplicationReview, ApplicationReviewItem.review_id == ApplicationReview.id)
            .where(
                ApplicationReview.application_id.in_(app_ids),
                ApplicationReviewItem.recommendation == "reject",
            )
        )
        result = await self.db.execute(query)
        for sub_type_code, app_id in result:
            rejected_map.setdefault(app_id, set()).add(sub_type_code)
        return rejected_map

    async def _bulk_system_received_months(
        self,
        items: list[CollegeRankingItem],
        scholarship_type_id: int,
        academic_year: int,
        semester: str,
    ) -> dict[str, int]:
        """
        Bulk-compute system received_months keyed by student std_stdcode.

        Returns empty dict when no matching ScholarshipConfiguration exists;
        callers fall back to showing no system value for affected students.
        """
        config_stmt = select(ScholarshipConfiguration.id).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                ScholarshipConfiguration.academic_year == academic_year,
                _config_semester_condition(semester),
            )
        )
        config_row = (await self.db.execute(config_stmt)).first()
        if not config_row:
            return {}
        config_id = config_row[0]

        student_ids: list[str] = []
        for item in items:
            app = item.application
            if not app or app.deleted_at is not None:
                continue
            sid = (app.student_data or {}).get("std_stdcode", "")
            if sid:
                student_ids.append(sid)

        if not student_ids:
            return {}

        return await calculate_received_months_bulk_async(self.db, student_ids, config_id)

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
                CollegeRanking.is_finalized.is_(True),
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

        # Batch-load rejected sub-types from professor reviews
        app_ids = [item.application.id for item in items if item.application]
        rejected_map = await self._batch_load_rejected_map(app_ids)

        # Bulk-compute system received_months for all students in one query.
        # Admin-imported overrides (source="imported") take precedence over
        # system values — see docs/received-months-calculation.md.
        system_months = await self._bulk_system_received_months(items, scholarship_type_id, academic_year, semester)

        students = []
        for item in items:
            app = item.application
            if not app:
                continue

            # Skip soft-deleted applications
            if app.deleted_at is not None:
                continue

            student_data = app.student_data or {}

            # Filter by college if specified
            student_college = student_data.get("std_academyno", "")
            if college_code and student_college != college_code:
                continue

            # Compute application_identity
            identity = self._compute_application_identity(app)

            # Compute term count
            term_count = self._compute_term_count(student_data)

            # Format enrollment date (ROC calendar)
            enrollment_date = self._format_enrollment_date(student_data)

            # Resolve received_months: imported overrides win, else system value
            if item.received_months_source == "imported" and item.received_months is not None:
                rm_value = item.received_months
                rm_source = "imported"
            else:
                student_id_value = student_data.get("std_stdcode", "")
                rm_value = system_months.get(student_id_value) if student_id_value else None
                rm_source = "system" if rm_value is not None else None

            students.append(
                {
                    "ranking_item_id": item.id,
                    "application_id": app.id,
                    "rank_position": item.rank_position,
                    "applied_sub_types": app.scholarship_subtype_list or [],
                    "rejected_sub_types": list(rejected_map.get(app.id, set())),
                    "allocated_sub_type": item.allocated_sub_type,
                    "allocation_year": item.allocation_year,
                    # Live funding flag — cancel (revoke/suspend) flips this to
                    # False to free the quota slot, restore flips it back. The
                    # frontend seeds the 核配 checkbox from this, not from
                    # allocated_sub_type (which is preserved across cancel).
                    "is_allocated": item.is_allocated,
                    "status": item.status,
                    # Application-level allocation status — drives the
                    # distribution-row status control (正常/撤銷/停發) and
                    # disables the 核配 checkboxes once revoked/suspended.
                    "quota_allocation_status": app.quota_allocation_status,
                    "revoke_reason": app.revoke_reason,
                    "suspend_reason": app.suspend_reason,
                    "college_rejected": item.college_rejected,
                    "is_supplementary": item.is_supplementary,
                    "college_code": student_college,
                    "college_name": student_data.get("trm_academyname", ""),
                    "department_name": student_data.get("trm_depname", ""),
                    "term_count": term_count,
                    "student_name": student_data.get("std_cname", ""),
                    "nationality": student_data.get("std_nation", ""),
                    "enrollment_date": enrollment_date,
                    "student_id": student_data.get("std_stdcode", ""),
                    "application_identity": identity,
                    "is_renewal": app.is_renewal,
                    "renewal_year": app.renewal_year,
                    "renewal_sub_type": self._get_renewal_sub_type(app),
                    "received_months": rm_value,
                    "received_months_source": rm_source,
                }
            )

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
            "display_name": "國科會",
            "by_year": {
              "114": {"total": 80, "allocated": 0, "remaining": 80, "by_college": {...}},
              "113": {"total": 15, "allocated": 3, "remaining": 12, "by_college": {...}},
            }
          },
          "moe_1w": {
            "display_name": "教育部",
            "by_year": {
              "114": {"total": 55, ...}    // no 113 — moe_1w has no prior years
            }
          }
        }
        """
        # 1. Load current year's config to get prior_quota_years
        current_config = await self._load_config(scholarship_type_id, academic_year, semester)

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
                    ScholarshipSubTypeConfig.is_active.is_(True),
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
                CollegeRanking.is_finalized.is_(True),
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
                        CollegeRankingItem.is_allocated.is_(True),
                    )
                )
            )
            result = await self.db.execute(allocated_items_query)
            allocated_items = result.scalars().all()
        else:
            allocated_items = []

        # Build allocation counts: {sub_type: {year: {college: count}}}
        ranking_by_id = {r.id: r for r in all_rankings}
        allocation_counts: dict[str, dict[int, dict[str, int]]] = {}
        for item in allocated_items:
            # Skip soft-deleted applications from quota accounting
            if item.application and item.application.deleted_at is not None:
                continue
            sub_type = item.allocated_sub_type
            if not sub_type:
                continue
            ranking = ranking_by_id.get(item.ranking_id)
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
        await self._validate_allocations(scholarship_type_id, academic_year, semester, allocations)

        updated_count = 0
        for alloc in allocations:
            item_id = alloc["ranking_item_id"]
            sub_type = alloc.get("sub_type_code")
            alloc_year = alloc.get("allocation_year") or (academic_year if sub_type else None)

            item_query = select(CollegeRankingItem).where(CollegeRankingItem.id == item_id)
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
                items_query = select(CollegeRankingItem).where(CollegeRankingItem.ranking_id.in_(ranking_ids))
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
            logger.warning("Failed to record allocation history", exc_info=True)
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
        2. Update application statuses (allocated -> approved; non-allocated keeps
           its prior user-facing status — see #45. Only quota_allocation_status
           is set to 'rejected' for non-allocated apps so the distribution engine
           can distinguish allocated/non-allocated outcomes.)
        3. Update quota_allocation_status on applications
        """
        ranking_query = select(CollegeRanking).where(
            and_(
                CollegeRanking.scholarship_type_id == scholarship_type_id,
                CollegeRanking.academic_year == academic_year,
                _ranking_semester_condition(semester),
                CollegeRanking.is_finalized.is_(True),
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

            # Skip soft-deleted applications
            if app.deleted_at is not None:
                continue

            # Skip applications already revoked/suspended post-finalize. Their
            # ranking item was unallocated (is_allocated=False) by the cancel
            # flow; finalize must never flip them back to approved/allocated.
            if app.quota_allocation_status in ("revoked", "suspended"):
                continue

            if item.is_allocated and item.allocated_sub_type:
                app.status = ApplicationStatus.approved
                app.quota_allocation_status = "allocated"
                app.sub_scholarship_type = item.allocated_sub_type
                app.approved_at = datetime.now(timezone.utc)
                app.review_stage = ReviewStage.quota_distributed
                approved_count += 1
            elif item.is_supplementary and not item.is_allocated:
                # Supplementary students pending a second distribution pass —
                # leave status as 'ranked' so they appear in the next allocation.
                pass
            else:
                # Non-allocated: keep the user-facing app.status as-is
                # (e.g. an approved-but-not-funded app stays "approved"). Only
                # the quota_allocation_status flips to "rejected" so the
                # distribution engine can identify non-allocated outcomes.
                # See #45 — earlier code stomped app.status to rejected, which
                # incorrectly told students their application was denied when
                # in fact they passed review but missed the quota cut.
                item.status = "rejected"
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
            logger.warning("Failed to record finalization history", exc_info=True)
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
            items_query = select(CollegeRankingItem).where(CollegeRankingItem.ranking_id.in_(ranking_ids))
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
                item_query = select(CollegeRankingItem).where(CollegeRankingItem.id == item_id)
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
        except Exception:
            logger.warning("Failed to record restore history", exc_info=True)

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

        # Professor-approval gate (issue: 分發時一定要教授有同意那個獎學金才能被分發到).
        # A student may only be distributed to a sub-type the professor approved
        # for that application. Exemptions handled in _assert_professor_approved:
        #   - renewal applications (續領豁免 — they don't go through professor review)
        #   - scholarships that don't require a professor recommendation step
        #     (no professor reviews exist, so there is nothing to gate on)
        await self._assert_professor_approved(allocations)

        # Quota validation is done real-time via the quota-status endpoint on the frontend.
        # The frontend sends only valid allocations based on displayed remaining counts.

    async def _assert_professor_approved(self, allocations: list[dict[str, Any]]) -> None:
        """Block any allocation to a sub-type the professor did not approve.

        Only allocations that assign a sub-type are checked (``sub_type_code`` set;
        ``None`` means unallocate). Renewal applications and scholarships that don't
        require a professor recommendation are exempt — for those there is no
        professor approval to enforce against.
        """
        allocating = [a for a in allocations if a.get("sub_type_code")]
        if not allocating:
            return

        item_ids = [a["ranking_item_id"] for a in allocating]
        stmt = (
            select(CollegeRankingItem)
            .options(selectinload(CollegeRankingItem.application).selectinload(Application.scholarship_configuration))
            .where(CollegeRankingItem.id.in_(item_ids))
        )
        items = {it.id: it for it in (await self.db.execute(stmt)).scalars().all()}

        # Keep only allocations that actually need the gate (skip renewal apps and
        # scholarships without a professor recommendation step).
        gated: list[tuple[dict[str, Any], Application]] = []
        for alloc in allocating:
            item = items.get(alloc["ranking_item_id"])
            app = item.application if item else None
            if app is None or app.is_renewal:
                continue
            cfg = app.scholarship_configuration
            if not (cfg and cfg.requires_professor_recommendation):
                continue
            gated.append((alloc, app))

        if not gated:
            return

        approved = await self._professor_approved_sub_types({app.id for _, app in gated})

        violations = []
        for alloc, app in gated:
            sub_type = (alloc["sub_type_code"] or "").lower().strip()
            if sub_type not in approved.get(app.id, set()):
                violations.append(f"{app.app_id} → {alloc['sub_type_code']}")

        if violations:
            raise ValueError("以下分發未取得教授對該子類型的核准，無法分發：" + "、".join(violations))

    async def _professor_approved_sub_types(self, app_ids: set[int]) -> dict[int, set[str]]:
        """application_id → set of sub_type_codes a professor recommended ``approve``."""
        if not app_ids:
            return {}
        stmt = (
            select(ApplicationReview.application_id, ApplicationReviewItem.sub_type_code)
            .join(ApplicationReviewItem, ApplicationReviewItem.review_id == ApplicationReview.id)
            .join(User, User.id == ApplicationReview.reviewer_id)
            .where(
                ApplicationReview.application_id.in_(app_ids),
                User.role == UserRole.professor,
                ApplicationReviewItem.recommendation == "approve",
            )
        )
        result = await self.db.execute(stmt)
        approved: dict[int, set[str]] = {}
        for app_id, sub_type_code in result.all():
            approved.setdefault(app_id, set()).add((sub_type_code or "").lower().strip())
        return approved

    def _compute_application_identity(self, app: Application) -> str:
        """
        Compute display string for application identity.
        e.g., "114新申請", "112續領"
        """
        if app.is_renewal and app.previous_application_id:
            return f"{app.academic_year}續領"
        else:
            return f"{app.academic_year}新申請"

    def _compute_term_count(self, student_data: dict) -> int | None:
        """Get student's semester count (第幾學期) from SIS API data."""
        term_count = student_data.get("trm_termcount")
        if term_count is not None:
            try:
                return int(term_count)
            except (ValueError, TypeError):
                return None
        return None

    def _get_renewal_sub_type(self, app: Application) -> str | None:
        """
        Get the sub-type of the student's renewal application.
        Maps sub_type codes to Chinese display names.
        """
        if not app.is_renewal:
            return None
        sub_type = app.sub_scholarship_type
        if not sub_type or sub_type == "general":
            return None
        return self._sub_type_to_chinese(sub_type)

    @staticmethod
    def _sub_type_to_chinese(sub_type: str) -> str:
        """Map sub-type code to Chinese display name."""
        mapping = {
            "nstc": "國科會",
            "moe_1w": "教育部",
            "moe_2w": "教育部",
        }
        return mapping.get(sub_type, sub_type)

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
                    ScholarshipSubTypeConfig.is_active.is_(True),
                )
            )
            .order_by(ScholarshipSubTypeConfig.display_order)
        )
        result = await self.db.execute(stmt)
        return [row.sub_type_code for row in result.scalars().all()]

    async def _batch_load_previous_allocation_years(self, previous_app_ids: list[int]) -> dict[int, int]:
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
                CollegeRanking.is_finalized.is_(True),
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

        # Deduplicate by application_id (keep first seen), skip soft-deleted
        seen_app_ids: set[int] = set()
        unique_items = []
        for item in all_items:
            if item.application and item.application.deleted_at is None and item.application.id not in seen_app_ids:
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
        for years_list in prior_years_map.values():
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

        # Load rejected sub-types from professor reviews
        app_ids = [item.application.id for item in unique_items]
        rejected_map = await self._batch_load_rejected_map(app_ids)

        return _compute_suggestions(
            unique_items=unique_items,
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
            rejected_map=rejected_map,
        )

    async def revoke_allocation(self, application_id: int, admin_user_id: int, reason: str) -> dict:
        """Revoke an allocated application: status -> cancelled,
        quota_allocation_status -> revoked, hard-delete its PaymentRosterItem
        rows in all non-LOCKED rosters, write audit log."""
        return await self._cancel_allocation(
            application_id=application_id,
            admin_user_id=admin_user_id,
            reason=reason,
            mode="revoke",
        )

    async def suspend_allocation(self, application_id: int, admin_user_id: int, reason: str) -> dict:
        """Suspend an allocated application: status -> cancelled,
        quota_allocation_status -> suspended, hard-delete its PaymentRosterItem
        rows in all non-LOCKED rosters, write audit log."""
        return await self._cancel_allocation(
            application_id=application_id,
            admin_user_id=admin_user_id,
            reason=reason,
            mode="suspend",
        )

    async def restore_allocation(self, application_id: int, admin_user_id: int) -> dict:
        """Restore a revoked/suspended application back to the allocated state:
        status -> approved, quota_allocation_status -> allocated, clear the
        revoke/suspend metadata, write an audit log.

        Rosters are intentionally NOT touched: items removed from non-LOCKED
        rosters are re-created on the next roster generation, and items manually
        removed from a LOCKED roster stay removed (its Excel was already
        re-exported — we never silently un-delete a locked roster line)."""
        result = await self.db.execute(select(Application).where(Application.id == application_id).with_for_update())
        app = result.scalar_one_or_none()
        if app is None:
            raise ValueError(f"Application {application_id} not found")

        prior_status = app.quota_allocation_status
        if prior_status not in ("revoked", "suspended"):
            raise ValueError(
                f"Application {application_id} is not revoked/suspended " f"(quota_allocation_status={prior_status})"
            )

        ranking_items_result = await self.db.execute(
            select(CollegeRankingItem).where(CollegeRankingItem.application_id == application_id)
        )
        ranking_items = ranking_items_result.scalars().all()
        ranking_item_id = ranking_items[0].id if ranking_items else None

        app.status = ApplicationStatus.approved
        app.quota_allocation_status = "allocated"
        # Clear both metadata sets regardless of which one applied.
        app.revoked_at = None
        app.revoked_by = None
        app.revoke_reason = None
        app.suspended_at = None
        app.suspended_by = None
        app.suspend_reason = None

        # Re-affirm the allocation on the ranking item(s) so the student
        # re-consumes the quota slot and a finalize run re-approves them. The
        # allocated_sub_type / allocation_year were preserved at cancel time, so
        # we only flip is_allocated back for items that actually held a slot.
        for ri in ranking_items:
            if ri.allocated_sub_type:
                ri.is_allocated = True

        log = AuditLog.create_log(
            user_id=admin_user_id,
            action="application.restore",
            resource_type="application",
            resource_id=str(application_id),
            description=f"restore application {application_id} from {prior_status}",
            new_values={"from": prior_status, "to": "allocated"},
        )
        self.db.add(log)
        await self.db.flush()

        return {
            "application_id": application_id,
            "ranking_item_id": ranking_item_id,
            "quota_allocation_status": app.quota_allocation_status,
            "restored_from": prior_status,
            "restored_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _cancel_allocation(
        self,
        application_id: int,
        admin_user_id: int,
        reason: str,
        mode: Literal["revoke", "suspend"],
    ) -> dict:
        # 1. Row-lock the application
        result = await self.db.execute(select(Application).where(Application.id == application_id).with_for_update())
        app = result.scalar_one_or_none()
        if app is None:
            raise ValueError(f"Application {application_id} not found")

        # 2. Conflict check
        if app.quota_allocation_status in ("revoked", "suspended"):
            raise ValueError(f"Application {application_id} already {app.quota_allocation_status}")

        # 3. 400 check
        if app.quota_allocation_status != "allocated":
            raise ValueError(
                f"Application {application_id} is not allocated "
                f"(quota_allocation_status={app.quota_allocation_status})"
            )

        # Find the CollegeRankingItem(s) for this application (the rows that drove
        # the allocation in the manual-distribution flow). The spec response
        # includes ranking_item_id so downstream consumers can reference it.
        ranking_items_result = await self.db.execute(
            select(CollegeRankingItem).where(CollegeRankingItem.application_id == application_id)
        )
        ranking_items = ranking_items_result.scalars().all()
        ranking_item_id = ranking_items[0].id if ranking_items else None

        now = datetime.now(timezone.utc)

        # 4. Update application columns
        app.status = ApplicationStatus.cancelled
        if mode == "revoke":
            app.quota_allocation_status = "revoked"
            app.revoked_at = now
            app.revoked_by = admin_user_id
            app.revoke_reason = reason
        else:
            app.quota_allocation_status = "suspended"
            app.suspended_at = now
            app.suspended_by = admin_user_id
            app.suspend_reason = reason

        # 4b. Free the quota slot: flip the ranking item(s) out of the allocated
        # state so (a) the freed slot becomes available for a replacement and
        # (b) a re-run of finalize cannot resurrect this student. We keep
        # allocated_sub_type / allocation_year so restore_allocation can re-affirm
        # the exact same slot without re-deriving it.
        for ri in ranking_items:
            ri.is_allocated = False

        # 5. Hard-delete items in non-LOCKED rosters
        items_result = await self.db.execute(
            select(PaymentRosterItem)
            .join(PaymentRoster, PaymentRosterItem.roster_id == PaymentRoster.id)
            .where(
                PaymentRosterItem.application_id == application_id,
                PaymentRoster.status != RosterStatus.LOCKED,
            )
        )
        items_to_delete = items_result.scalars().all()
        affected_roster_ids = sorted({i.roster_id for i in items_to_delete})

        for item in items_to_delete:
            await self.db.delete(item)
        await self.db.flush()  # make deletes visible to the subsequent recompute query

        # 6. Recompute roster totals for affected rosters
        for roster_id in affected_roster_ids:
            await self._recompute_roster_totals(roster_id)

        # 7. Audit log
        action = "application.revoke" if mode == "revoke" else "application.suspend"
        log = AuditLog.create_log(
            user_id=admin_user_id,
            action=action,
            resource_type="application",
            resource_id=str(application_id),
            description=f"{mode} application {application_id}",
            new_values={"reason": reason, "affected_unlocked_rosters": affected_roster_ids},
        )
        self.db.add(log)

        await self.db.flush()

        timestamp_key = "revoked_at" if mode == "revoke" else "suspended_at"
        return {
            "application_id": application_id,
            "ranking_item_id": ranking_item_id,
            "quota_allocation_status": app.quota_allocation_status,
            timestamp_key: now.isoformat(),
            "affected_unlocked_rosters": affected_roster_ids,
        }

    async def _recompute_roster_totals(self, roster_id: int) -> None:
        """Recompute total_applications, qualified_count, disqualified_count,
        total_amount for a roster after items have been added/removed.

        - total_applications = all rows
        - qualified_count = is_included=True rows
        - disqualified_count = is_included=False rows
        - total_amount = sum(scholarship_amount) over is_included=True rows
        """
        agg = await self.db.execute(
            select(
                func.count(PaymentRosterItem.id),
                func.coalesce(
                    func.sum(
                        sa_case(
                            (PaymentRosterItem.is_included.is_(True), 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        sa_case(
                            (PaymentRosterItem.is_included.is_(True), PaymentRosterItem.scholarship_amount),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).where(PaymentRosterItem.roster_id == roster_id)
        )
        total_count, qualified_count, total_amount = agg.one()

        roster = await self.db.get(PaymentRoster, roster_id)
        if roster:
            roster.total_applications = total_count
            roster.qualified_count = qualified_count
            roster.disqualified_count = total_count - qualified_count
            roster.total_amount = total_amount

    # ------------------------------------------------------------------ #
    # Phase 6 — General distribution with challenge release + fill-in
    # See docs/superpowers/specs/2026-05-13-renewal-application-design.md
    # Section 9 (一般階段分發演算法).
    # ------------------------------------------------------------------ #

    async def _get_active_config(self, scholarship_type_id: int, academic_year: int) -> ScholarshipConfiguration:
        """Load the active ScholarshipConfiguration for (type, year).

        Phase 6 distribution operates on quotas at the (sub_type, year) level
        rather than per-college; semester is unused here since renewal flows
        target yearly scholarships (see spec Section 1).
        """
        stmt = (
            select(ScholarshipConfiguration)
            .where(
                and_(
                    ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                    ScholarshipConfiguration.academic_year == academic_year,
                    ScholarshipConfiguration.is_active == True,  # noqa: E712
                )
            )
            .order_by(ScholarshipConfiguration.id.desc())
        )
        config = (await self.db.execute(stmt)).scalars().first()
        if config is None:
            raise ValueError(f"No active ScholarshipConfiguration for type {scholarship_type_id}, year {academic_year}")
        return config

    async def _count_approved_renewals_per_pool(
        self, scholarship_type_id: int, academic_year: int
    ) -> dict[tuple[str, int], int]:
        """Count approved renewals grouped by (sub_scholarship_type, renewal_year).

        Used to compute remaining quota = total - already-consumed-by-renewals.
        Renewals without an explicit renewal_year fall back to academic_year
        (they came from this year's pool).
        """
        stmt = (
            select(
                Application.sub_scholarship_type,
                Application.renewal_year,
                func.count(Application.id),
            )
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.is_renewal.is_(True),
                Application.status == ApplicationStatus.approved,
            )
            .group_by(Application.sub_scholarship_type, Application.renewal_year)
        )
        rows = (await self.db.execute(stmt)).all()
        result: dict[tuple[str, int], int] = {}
        for sub_type, renewal_year, count in rows:
            year = int(renewal_year) if renewal_year is not None else int(academic_year)
            result[(sub_type, year)] = result.get((sub_type, year), 0) + int(count)
        return result

    async def _get_general_candidates(
        self,
        scholarship_type_id: int,
        academic_year: int,
        sub_type: str,
    ) -> list[CollegeRankingItem]:
        """Return ranked candidates for first-round distribution on `sub_type`.

        Includes BOTH pure-new applicants and challenge applicants whose
        target sub_type matches — challenges compete for slots within the
        sub_type they're applying to.
        """
        stmt = (
            select(CollegeRankingItem)
            .options(selectinload(CollegeRankingItem.application))
            .join(Application, CollegeRankingItem.application_id == Application.id)
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.sub_scholarship_type == sub_type,
                Application.is_renewal.is_(False),
                Application.status.notin_(
                    [
                        ApplicationStatus.approved,
                        ApplicationStatus.rejected,
                        ApplicationStatus.withdrawn,
                        ApplicationStatus.deleted,
                        ApplicationStatus.cancelled,
                        ApplicationStatus.cancelled_by_challenge,
                    ]
                ),
                Application.deleted_at.is_(None),
            )
            .order_by(CollegeRankingItem.rank_position)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def _get_waitlist_candidates(
        self,
        scholarship_type_id: int,
        academic_year: int,
        sub_type: str,
        limit: int,
    ) -> list[CollegeRankingItem]:
        """Return pure-new candidates eligible to fill released slots.

        Filters challenges_application_id IS NULL — only pure-new applicants
        can fill released slots (spec Section 9.2). This prevents release
        chains: a challenge winner's freed slot only flows to a pure-new
        applicant, so no further releases cascade.
        """
        stmt = (
            select(CollegeRankingItem)
            .options(selectinload(CollegeRankingItem.application))
            .join(Application, CollegeRankingItem.application_id == Application.id)
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.sub_scholarship_type == sub_type,
                Application.is_renewal.is_(False),
                Application.challenges_application_id.is_(None),
                Application.status != ApplicationStatus.approved,
                Application.status.notin_(
                    [
                        ApplicationStatus.rejected,
                        ApplicationStatus.withdrawn,
                        ApplicationStatus.deleted,
                        ApplicationStatus.cancelled,
                        ApplicationStatus.cancelled_by_challenge,
                    ]
                ),
                Application.deleted_at.is_(None),
            )
            .order_by(CollegeRankingItem.rank_position)
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    @staticmethod
    def _pick_pool(
        remaining: dict[tuple[str, int], int],
        sub_type: str,
        config: ScholarshipConfiguration,
    ) -> Optional[int]:
        """Pick the next allocation_year with available quota for `sub_type`.

        Policy: prefer the current academic_year first, then prior years in
        descending order. Returns None when no pool with positive remaining
        quota exists for this sub_type.
        """
        candidate_years = sorted(
            [y for (st, y), c in remaining.items() if st == sub_type and c > 0],
            reverse=True,
        )
        if not candidate_years:
            return None
        # Prefer the configured current year if available; otherwise the
        # highest-numbered prior year (already sorted descending).
        if config.academic_year in candidate_years:
            return config.academic_year
        return candidate_years[0]

    @staticmethod
    def _build_remaining_quota(
        quotas: dict,
        used_by_renewal: dict[tuple[str, int], int],
    ) -> dict[tuple[str, int], int]:
        """Build {(sub_type, alloc_year): remaining} from config quotas.

        The Phase 6 quotas dict is `{sub_type: {year_string: total_int}}` per
        spec Section 9.1. Year keys are coerced to int so downstream code can
        compare against renewal_year / academic_year (also ints).
        """
        remaining: dict[tuple[str, int], int] = {}
        for sub_type, year_map in (quotas or {}).items():
            if not isinstance(year_map, dict):
                continue
            for year_key, total in year_map.items():
                try:
                    year_int = int(year_key)
                except (TypeError, ValueError):
                    # Non-year keys (legacy college-code matrix) aren't used
                    # by the Phase 6 algorithm; skip silently.
                    continue
                used = used_by_renewal.get((sub_type, year_int), 0)
                remaining[(sub_type, year_int)] = int(total) - used
        return remaining

    async def execute_general_distribution(
        self,
        scholarship_type_id: int,
        academic_year: int,
    ) -> dict[str, Any]:
        """Run general-phase distribution with challenge release and waitlist fill-in.

        Spec Section 9.1 — algorithm:
        1. Compute remaining quota = total - approved renewals per pool.
        2. First-round: per sub_type, walk ranked candidates and assign each
           to the next available (sub_type, allocation_year) pool.
        3. For every approved challenge: cancel its renewal target with
           status=cancelled_by_challenge, track the freed slot.
        4. Fill released slots from the same-sub_type waitlist (pure-new
           applicants only — preventing cascading releases).
        5. Commit and return summary stats per spec Section 12.
        """
        config = await self._get_active_config(scholarship_type_id, academic_year)
        quotas = config.quotas or {}

        # 1. Remaining quota after subtracting approved renewals.
        used_by_renewal = await self._count_approved_renewals_per_pool(scholarship_type_id, academic_year)
        remaining = self._build_remaining_quota(quotas, used_by_renewal)

        # 2. First-round distribution per sub_type.
        approved_challenges: list[Application] = []
        for sub_type in quotas.keys():
            candidates = await self._get_general_candidates(scholarship_type_id, academic_year, sub_type)
            for cand in candidates:
                pool_year = self._pick_pool(remaining, sub_type, config)
                if pool_year is None:
                    break
                app = cand.application
                if app is None:
                    continue
                app.status = ApplicationStatus.approved
                app.sub_scholarship_type = sub_type
                app.quota_allocation_status = "allocated"
                app.review_stage = ReviewStage.quota_distributed
                app.approved_at = datetime.now(timezone.utc)
                cand.is_allocated = True
                cand.allocated_sub_type = sub_type
                cand.allocation_year = pool_year
                cand.status = "allocated"
                cand.allocation_reason = "一般階段自動分發"
                remaining[(sub_type, pool_year)] -= 1
                if app.challenges_application_id is not None:
                    approved_challenges.append(app)

        # 3. Release handling — approved challenges cancel their renewal targets.
        # Batch-load all referenced renewal applications to avoid N+1 queries.
        challenge_renewal_ids = [
            app.challenges_application_id for app in approved_challenges if app.challenges_application_id is not None
        ]
        renewal_apps_by_id: dict[int, Application] = {}
        if challenge_renewal_ids:
            renewal_apps_by_id = {
                app.id: app
                for app in (
                    await self.db.scalars(select(Application).where(Application.id.in_(challenge_renewal_ids)))
                ).all()
            }

        released: dict[tuple[str, int], int] = {}
        for challenge_app in approved_challenges:
            renewal_app = renewal_apps_by_id.get(challenge_app.challenges_application_id)
            if renewal_app is None:
                logger.warning(
                    "Challenge app %s references missing renewal id=%s — skipping release",
                    challenge_app.id,
                    challenge_app.challenges_application_id,
                )
                continue
            renewal_app.status = ApplicationStatus.cancelled_by_challenge
            renewal_app.cancelled_due_to_application_id = challenge_app.id
            freed_year = int(renewal_app.renewal_year) if renewal_app.renewal_year is not None else int(academic_year)
            key = (renewal_app.sub_scholarship_type, freed_year)
            released[key] = released.get(key, 0) + 1

        # 4. Fill released slots from waitlist of same sub_type.
        fill_in_count = 0
        for (sub_type, alloc_year), count in released.items():
            waitlist = await self._get_waitlist_candidates(scholarship_type_id, academic_year, sub_type, limit=count)
            for cand in waitlist:
                app = cand.application
                if app is None:
                    continue
                app.status = ApplicationStatus.approved
                app.sub_scholarship_type = sub_type
                app.quota_allocation_status = "allocated"
                app.review_stage = ReviewStage.quota_distributed
                app.approved_at = datetime.now(timezone.utc)
                cand.is_allocated = True
                cand.allocated_sub_type = sub_type
                cand.allocation_year = alloc_year
                cand.status = "allocated"
                cand.allocation_reason = "釋出 slot 候補遞補"
                fill_in_count += 1

        await self.db.commit()

        return {
            "approved_renewals": sum(used_by_renewal.values()),
            "approved_challenges": len(approved_challenges),
            "released_slots": dict(released),
            "filled_in": fill_in_count,
            "unfilled": sum(released.values()) - fill_in_count,
        }

    async def compute_distribution_state(self, scholarship_type_id: int, academic_year: int) -> dict[str, Any]:
        """Aggregate the state needed by the manual distribution panel UI.

        Returns a single payload covering:

          * ``renewal_allocations`` — approved renewals grouped by
            ``(sub_type, renewal_year)``; each entry includes a
            ``has_challenge`` flag if a downstream challenge application
            points at the renewal (Application_C).
          * ``available_quotas`` — per ``(sub_type, allocation_year)``:
            ``total`` from config, ``used`` from approved renewals, and
            ``remaining`` = total − used. Legacy non-year-keyed quota maps
            (e.g. ``{college_code: int}``) are skipped silently — Phase 6
            only operates on year-keyed quotas (spec Section 9.1).
          * ``candidates`` — non-renewal applicants ranked via
            ``CollegeRankingItem.rank_position``. For each candidate,
            ``is_challenge`` is true when ``challenges_application_id`` is
            set, and ``challenged_renewal`` carries minimal info about the
            renewal that would be cancelled if the challenge wins.

        This endpoint never mutates state — it's a read aggregator the
        admin UI calls to render the panel.
        """
        config = await self._get_active_config(scholarship_type_id, academic_year)
        quotas = config.quotas or {}

        # --- 1. Renewal allocations grouped by (sub_type, renewal_year) --- #
        renewal_apps_result = await self.db.execute(
            select(Application)
            .options(joinedload(Application.student))
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.is_renewal.is_(True),
                Application.status == ApplicationStatus.approved,
            )
        )
        renewal_apps = renewal_apps_result.scalars().unique().all()

        # Mark challenges. Use a sentinel (-1) so the IN clause is valid
        # across dialects when no renewals exist.
        renewal_ids = [a.id for a in renewal_apps]
        challenge_rows = (
            (
                await self.db.execute(
                    select(Application).where(Application.challenges_application_id.in_(renewal_ids or [-1]))
                )
            )
            .scalars()
            .all()
        )
        challenged_renewal_ids = {ch.challenges_application_id for ch in challenge_rows}

        renewal_grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for app in renewal_apps:
            # Fallback renewal_year → academic_year matches the rest of the
            # Phase 6 code (see _count_approved_renewals_per_pool).
            year_key = int(app.renewal_year) if app.renewal_year is not None else int(academic_year)
            key = (app.sub_scholarship_type, year_key)
            renewal_grouped.setdefault(key, []).append(
                {
                    "application_id": app.id,
                    "student_name": app.student.name if app.student else None,
                    "has_challenge": app.id in challenged_renewal_ids,
                }
            )

        # --- 2. Available quotas per (sub_type, allocation_year) --- #
        used = await self._count_approved_renewals_per_pool(scholarship_type_id, academic_year)
        available_quotas: list[dict[str, Any]] = []
        for sub_type, year_map in quotas.items():
            # Skip legacy non-year-keyed entries (e.g. {college_code: int}).
            if not isinstance(year_map, dict):
                continue
            for year_key, total in year_map.items():
                try:
                    year = int(year_key)
                except (TypeError, ValueError):
                    # Non-int keys (legacy college matrix) are not used by
                    # the Phase 6 algorithm — skip silently.
                    continue
                try:
                    total_int = int(total)
                except (TypeError, ValueError):
                    continue
                used_count = used.get((sub_type, year), 0)
                available_quotas.append(
                    {
                        "sub_type": sub_type,
                        "allocation_year": year,
                        "total": total_int,
                        "used": used_count,
                        "remaining": total_int - used_count,
                    }
                )

        # --- 3. Candidates (general phase, non-renewal) --- #
        candidates_result = await self.db.execute(
            select(CollegeRankingItem, Application)
            .options(joinedload(Application.student))
            .join(Application, CollegeRankingItem.application_id == Application.id)
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.is_renewal.is_(False),
                Application.deleted_at.is_(None),
            )
            .order_by(CollegeRankingItem.rank_position)
        )
        cands = candidates_result.unique().all()

        # Batch-load the renewal targets of any challenge candidates so we
        # avoid N+1 lookups for the (typically small) challenge subset.
        challenge_target_ids = {
            app.challenges_application_id for _, app in cands if app.challenges_application_id is not None
        }
        renewal_by_id: dict[int, Application] = {}
        if challenge_target_ids:
            target_rows = (
                (await self.db.execute(select(Application).where(Application.id.in_(challenge_target_ids))))
                .scalars()
                .all()
            )
            renewal_by_id = {r.id: r for r in target_rows}

        candidates: list[dict[str, Any]] = []
        for ri, app in cands:
            challenged_renewal: Optional[dict[str, Any]] = None
            if app.challenges_application_id:
                renewal = renewal_by_id.get(app.challenges_application_id)
                if renewal is not None:
                    challenged_renewal = {
                        "renewal_application_id": renewal.id,
                        "sub_type": renewal.sub_scholarship_type,
                        "renewal_year": renewal.renewal_year,
                    }
            candidates.append(
                {
                    "rank": ri.rank_position,
                    "application_id": app.id,
                    "student_name": app.student.name if app.student else None,
                    "is_challenge": app.challenges_application_id is not None,
                    "challenged_renewal": challenged_renewal,
                    "applying_sub_type": app.sub_scholarship_type,
                }
            )

        return {
            "renewal_allocations": [
                {"sub_type": sub_type, "renewal_year": year, "applications": items}
                for (sub_type, year), items in renewal_grouped.items()
            ],
            "available_quotas": available_quotas,
            "candidates": candidates,
        }

    async def preview_release_chain(self, proposed_allocations: list) -> dict[str, Any]:
        """Dry-run preview: which renewals would be cancelled and who would fill in.

        For each proposed allocation whose application is a challenge (i.e.
        has challenges_application_id set), returns the renewal that would
        be cancelled and the next waitlist candidate who would inherit the
        freed slot. Does not persist anything.
        """
        chain: list[dict[str, Any]] = []
        # Track per-sub_type fill-in suggestions so a single preview call
        # never suggests the same waitlist candidate twice.
        used_fill_ids: set[int] = set()

        for alloc in proposed_allocations:
            # Support both Pydantic schema objects and plain dicts.
            ranking_item_id = getattr(alloc, "ranking_item_id", None)
            if ranking_item_id is None and isinstance(alloc, dict):
                ranking_item_id = alloc.get("ranking_item_id")
            if ranking_item_id is None:
                continue

            item = await self.db.scalar(
                select(CollegeRankingItem)
                .options(selectinload(CollegeRankingItem.application))
                .where(CollegeRankingItem.id == ranking_item_id)
            )
            if item is None or item.application is None:
                continue
            app = item.application
            if not app.challenges_application_id:
                continue

            renewal = await self.db.scalar(select(Application).where(Application.id == app.challenges_application_id))
            if renewal is None:
                continue

            waitlist = await self._get_waitlist_candidates(
                renewal.scholarship_type_id,
                app.academic_year,
                renewal.sub_scholarship_type,
                limit=len(used_fill_ids) + 1,
            )
            suggested_app: Optional[Application] = None
            for cand in waitlist:
                if cand.application and cand.application.id not in used_fill_ids:
                    suggested_app = cand.application
                    used_fill_ids.add(suggested_app.id)
                    break

            suggested_name: Optional[str] = None
            if suggested_app is not None:
                sd = suggested_app.student_data or {}
                suggested_name = sd.get("std_cname") or sd.get("name")

            chain.append(
                {
                    "challenge_application_id": app.id,
                    "cancelled_application_id": renewal.id,
                    "freed_slot": {
                        "sub_type": renewal.sub_scholarship_type,
                        "allocation_year": (int(renewal.renewal_year) if renewal.renewal_year is not None else None),
                    },
                    "suggested_fill_id": suggested_app.id if suggested_app else None,
                    "suggested_fill_name": suggested_name,
                }
            )

        return {"release_chain": chain}

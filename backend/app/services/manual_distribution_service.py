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
from app.models.audit_log import AuditAction, AuditLog
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
    prev_alloc_configs: dict[int, int],
    allowed_configs_by_sub_type: dict[str, list[int]],
    quota_tracker: dict[tuple, int],
    own_config_id: int,
    rejected_map: Optional[dict[int, set[str]]] = None,
) -> list[dict]:
    """
    Pure allocation logic (no DB access).  Extracted so it can be unit-tested
    without mocking async SQLAlchemy sessions.

    Parameters
    ----------
    unique_items:
        CollegeRankingItem objects (with .application pre-loaded) already
        deduplicated by application_id.  Already-allocated items are skipped.
    default_prefs:
        Ordered sub_type codes; last-resort preference fallback.
    prev_alloc_configs:
        {previous_application_id: allocation_config_id} for renewal students'
        prior allocations — the config that prior slot consumed.
    allowed_configs_by_sub_type:
        {sub_type: [config_id, ...]} own-config-first, then linked source
        configs by descending year. Defines which configs a sub_type may draw.
    quota_tracker:
        Mutable {(config_id, sub_type, college_code): remaining}. Decremented
        as it allocates. The pool cap is already baked into these counts
        (seeded from remaining(config, sub_type) split per college).
    own_config_id:
        The requesting config id (default target when no prior slot applies).
    rejected_map:
        {application_id: {rejected_sub_type_codes}} — excluded from allocation.

    Returns
    -------
    list[dict]
        [{"ranking_item_id", "sub_type_code", "allocation_config_id"}, ...]
        One entry per unallocated input item, in allocation order.
    """
    if rejected_map is None:
        rejected_map = {}
    sorted_items = sorted(
        [item for item in unique_items if not item.is_allocated],
        key=lambda i: (0 if i.application.is_renewal else 1, i.rank_position),
    )

    results: list[dict] = []

    for item in sorted_items:
        if getattr(item, "college_rejected", False):
            results.append({"ranking_item_id": item.id, "sub_type_code": None, "allocation_config_id": None})
            continue

        app = item.application
        college = (app.student_data or {}).get("std_academyno", "")

        # Preferred target config for a renewal: the config its prior slot consumed.
        prev_app_id = app.previous_application_id if app.is_renewal else None
        target_config: Optional[int] = prev_alloc_configs.get(prev_app_id) if prev_app_id else None

        applied = app.scholarship_subtype_list or []
        rejected = rejected_map.get(app.id, set())
        raw_prefs: list[str] = app.sub_type_preferences or applied or default_prefs
        applied_set = set(applied)
        preferences: list[str] = [
            p for p in raw_prefs if (p in applied_set if applied_set else True) and p not in rejected
        ]

        allocated_sub_type: Optional[str] = None
        allocated_config: Optional[int] = None

        for sub_type in preferences:
            allowed = allowed_configs_by_sub_type.get(sub_type, [own_config_id])
            # Try the renewal's prior config first (if it is an allowed source),
            # then walk the allowed configs in order (own-first, linked by year).
            candidate_order: list[int] = []
            if target_config is not None and target_config in allowed:
                candidate_order.append(target_config)
            candidate_order.extend(cid for cid in allowed if cid not in candidate_order)

            for cid in candidate_order:
                key = (cid, sub_type, college)
                if quota_tracker.get(key, 0) > 0:
                    quota_tracker[key] -= 1
                    allocated_sub_type = sub_type
                    allocated_config = cid
                    break
            if allocated_sub_type:
                break

        results.append(
            {
                "ranking_item_id": item.id,
                "sub_type_code": allocated_sub_type,
                "allocation_config_id": allocated_config,
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
            return sum(self._matrix_row(config, sub_type).values())
        scalar = quotas.get(sub_type, 0)
        try:
            scalar_int = int(scalar)
        except (TypeError, ValueError):
            scalar_int = 0
        return scalar_int or int(config.total_quota or 0)

    @staticmethod
    def _matrix_row(config: ScholarshipConfiguration, sub_type: str) -> dict[str, int]:
        """Normalized per-college quota row for one sub_type.

        Single owner of the quotas-matrix parsing tolerance: a non-dict row
        yields {}, and malformed cell values coerce to 0 — so pool_total and
        _college_breakdown can never disagree about the same row.
        """
        row = (config.quotas or {}).get(sub_type, {})
        if not isinstance(row, dict):
            return {}
        normalized: dict[str, int] = {}
        for code, value in row.items():
            try:
                normalized[code] = int(value or 0)
            except (TypeError, ValueError):
                normalized[code] = 0
        return normalized

    @staticmethod
    def _winner_filters(config_id: int, sub_type: str) -> tuple:
        """Shared half-1 predicates: allocated non-renewal winners."""
        return (
            CollegeRankingItem.is_allocated.is_(True),
            CollegeRankingItem.allocated_sub_type == sub_type,
            CollegeRankingItem.allocation_config_id == config_id,
            Application.is_renewal.is_(False),
        )

    @staticmethod
    def _renewal_filters(config_id: int, sub_type: str) -> tuple:
        """Shared half-2 predicates: approved renewals."""
        return (
            Application.is_renewal.is_(True),
            Application.status == ApplicationStatus.approved,
            Application.sub_scholarship_type == sub_type,
            Application.allocation_config_id == config_id,
        )

    async def consumers_count(self, config_id: int, sub_type: str) -> int:
        """Count every LIVE consumer of (config_id, sub_type) anywhere (spec §6.2).

        Guaranteed two-half partition (predicates shared with
        consumers_by_college via _winner_filters/_renewal_filters):
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
            .where(*self._winner_filters(config_id, sub_type))
        )
        winners = (await self.db.execute(winners_stmt)).scalar_one()

        renewals_stmt = select(func.count(Application.id)).where(*self._renewal_filters(config_id, sub_type))
        renewals = (await self.db.execute(renewals_stmt)).scalar_one()

        return int(winners) + int(renewals)

    async def consumers_by_college(self, config_id: int, sub_type: str) -> dict[str, int]:
        """Per-college split of consumers_count — SAME two-half partition.

        Attribution: application.student_data["std_academyno"]; a missing or
        empty academyno lands in the "" bucket (rendered 未知 in the UI).
        Invariant (tripwire-tested): sum(values) == consumers_count(config_id,
        sub_type) — both methods build their where-clauses from the shared
        _winner_filters/_renewal_filters helpers, so the predicates cannot
        drift.
        """
        winners_stmt = (
            select(Application.student_data)
            .join(CollegeRankingItem, CollegeRankingItem.application_id == Application.id)
            .where(*self._winner_filters(config_id, sub_type))
        )
        renewals_stmt = select(Application.student_data).where(*self._renewal_filters(config_id, sub_type))
        counts: dict[str, int] = {}
        for stmt in (winners_stmt, renewals_stmt):
            for student_data in (await self.db.execute(stmt)).scalars():
                college = (student_data or {}).get("std_academyno", "") or ""
                counts[college] = counts.get(college, 0) + 1
        return counts

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
        seen_app_ids: set[int] = set()
        for item in items:
            app = item.application
            if not app:
                continue

            # Skip soft-deleted applications
            if app.deleted_at is not None:
                continue

            # Deduplicate by application_id (keep first seen) — mirrors
            # get_auto_allocation_suggestions. Normally each application belongs to
            # exactly one college's single finalized ranking, but a NULL-college
            # (admin/global) or "default" sub-type ranking finalized alongside a
            # per-college one could otherwise list the same student twice.
            if app.id in seen_app_ids:
                continue
            seen_app_ids.add(app.id)

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
                    # Config whose quota this slot consumes — the frontend grid
                    # seeds the checked column from (allocated_sub_type,
                    # allocation_config_id). Superseded the legacy allocation_year.
                    "allocation_config_id": item.allocation_config_id,
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
        """Real-time quota grid per sub-type, keyed by **config** (spec §6.3, §12).

        Response:
        {
          "nstc": {
            "display_name": "國科會",
            "by_config": [
              {"config_id", "config_code", "academic_year", "is_own", "total",
               "remaining", "by_college"},  # by_college: {code: {total, allocated,
                                            # remaining}} for matrix configs, else None
              ...  # own config first, then linked source configs by descending year
            ]
          },
          ...
        }
        remaining is the LIVE global value (pool_total − every consumer of that
        config anywhere, INCLUDING approved renewals — see §17.1 behavior change).
        """
        current_config = await self._load_config(scholarship_type_id, academic_year, semester)
        if current_config is None:
            return {}

        # Sub-type display names.
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
        sub_type_configs = (await self.db.execute(sub_type_query)).scalars().all()
        sub_type_names = {stc.sub_type_code: stc.name for stc in sub_type_configs}

        # Drive columns off the requesting config's own quota sub_types.
        own_quotas = current_config.quotas or {}

        quota_status: dict[str, Any] = {}
        for sub_type in own_quotas.keys():
            if self.pool_total(current_config, sub_type) <= 0:
                continue
            # Resolve linked configs once so we can look up pool_total per linked config.
            linked_configs = await self._resolve_linked_configs(current_config, sub_type)
            linked_by_code: dict[str, ScholarshipConfiguration] = {cfg.config_code: cfg for cfg in linked_configs}
            by_config = []
            for col in await self.distributable_pool(current_config, sub_type):
                cfg = current_config if col["is_own"] else linked_by_code.get(col["config_code"])
                total = self.pool_total(cfg, sub_type) if cfg is not None else 0
                by_config.append(
                    {
                        "config_id": col["config_id"],
                        "config_code": col["config_code"],
                        "academic_year": col["academic_year"],
                        "is_own": col["is_own"],
                        "total": total,
                        "remaining": col["remaining"],
                        "by_college": await self._college_breakdown(cfg, sub_type),
                    }
                )
            quota_status[sub_type] = {
                "display_name": sub_type_names.get(sub_type, sub_type),
                "by_config": by_config,
            }

        return quota_status

    async def _college_breakdown(
        self,
        cfg: ScholarshipConfiguration | None,
        sub_type: str,
    ) -> dict[str, dict[str, int]] | None:
        """Per-college quota grid for one (config, sub_type) column (advisory).

        None for non-matrix configs (no per-college split exists). Colleges
        appear when they have quota > 0 in the matrix OR live consumers;
        remaining is NOT clamped — negative flags over-allocation in the UI.
        The enforced gate stays the global per-(config, sub_type) recount in
        _assert_round_not_oversubscribed.
        """
        if cfg is None or not cfg.has_college_quota:
            return None
        matrix = self._matrix_row(cfg, sub_type)
        allocated_by_college = await self.consumers_by_college(cfg.id, sub_type)

        breakdown: dict[str, dict[str, int]] = {}
        for code in sorted(set(matrix) | set(allocated_by_college)):
            college_total = matrix.get(code, 0)
            allocated = allocated_by_college.get(code, 0)
            if college_total <= 0 and allocated <= 0:
                continue
            breakdown[code] = {
                "total": college_total,
                "allocated": allocated,
                "remaining": college_total - allocated,
            }
        return breakdown

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
        admin_user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Save manual allocation selections.
        Each allocation: {
            "ranking_item_id": int,
            "sub_type_code": str|None,
            "allocation_config_id": int|None  (None → defaults to the requesting config)
        }
        sub_type_code=None means unallocate.
        """
        # Validate quota limits first
        await self._validate_allocations(scholarship_type_id, academic_year, semester, allocations)

        updated_count = 0
        requesting_config = await self._load_config(scholarship_type_id, academic_year, semester)
        if requesting_config is None:
            raise ValueError("No active configuration for this distribution round")

        for alloc in allocations:
            item_id = alloc["ranking_item_id"]
            sub_type = alloc.get("sub_type_code")
            alloc_config_id = alloc.get("allocation_config_id") or (requesting_config.id if sub_type else None)

            item_query = select(CollegeRankingItem).where(CollegeRankingItem.id == item_id)
            result = await self.db.execute(item_query)
            item = result.scalar_one_or_none()
            if not item:
                continue

            # G3 (#965): capture the prior slot state — 「誰把哪個名額配給誰」
            # must be reconstructable from audit_logs, not only from the
            # undo-oriented ManualDistributionHistory snapshot.
            prior_state = {
                "is_allocated": item.is_allocated,
                "allocated_sub_type": item.allocated_sub_type,
                "allocation_config_id": item.allocation_config_id,
            }

            if sub_type:
                allowed = await self._allowed_config_ids(requesting_config, sub_type)
                if alloc_config_id not in allowed:
                    code = await self._config_code_by_id(requesting_config, sub_type, alloc_config_id)
                    raise ValueError(f"分發目標配置不在允許範圍：{code} (sub_type={sub_type})")
                item.is_allocated = True
                item.allocated_sub_type = sub_type
                item.allocation_config_id = alloc_config_id
                item.status = "allocated"
                item.allocation_reason = "手動分發"
            else:
                item.is_allocated = False
                item.allocated_sub_type = None
                item.allocation_config_id = None
                item.status = "ranked"
                item.allocation_reason = None

            if admin_user_id is not None and item.application_id is not None:
                self.db.add(
                    AuditLog.create_log(
                        user_id=admin_user_id,
                        action=AuditAction.execute_distribution.value,
                        resource_type="application",
                        resource_id=str(item.application_id),
                        description=(
                            f"manual allocation: ranking_item {item.id} -> "
                            f"{sub_type or 'unallocated'} (config {alloc_config_id})"
                        ),
                        old_values=prior_state,
                        new_values={
                            "is_allocated": item.is_allocated,
                            "allocated_sub_type": item.allocated_sub_type,
                            "allocation_config_id": item.allocation_config_id,
                        },
                        meta_data={"ranking_item_id": item.id},
                    )
                )

            updated_count += 1

        # §10 server-side quota gate: lock the consumed config rows, recount,
        # reject if any is oversubscribed.
        await self._assert_round_not_oversubscribed(requesting_config)

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
                            "allocation_config_id": item.allocation_config_id,
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
                    created_by=admin_user_id,
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
        admin_user_id: Optional[int] = None,
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

            prior_app_state = {
                "status": app.status.value if hasattr(app.status, "value") else str(app.status),
                "quota_allocation_status": app.quota_allocation_status,
            }
            if item.is_allocated and item.allocated_sub_type:
                app.status = ApplicationStatus.approved
                app.quota_allocation_status = "allocated"
                app.sub_scholarship_type = item.allocated_sub_type
                app.approved_at = datetime.now(timezone.utc)
                app.review_stage = ReviewStage.quota_distributed
                # Backfill: an approved renewal must NEVER have NULL allocation_config_id
                # (spec §9 — NULL would inflate §6.2 pool counts). Prefer the ranking
                # item's consumed config; fall back to the app's own config.
                if app.allocation_config_id is None:
                    app.allocation_config_id = item.allocation_config_id or app.scholarship_configuration_id
                if admin_user_id is not None:
                    self.db.add(
                        AuditLog.create_log(
                            user_id=admin_user_id,
                            action=AuditAction.execute_distribution.value,
                            resource_type="application",
                            resource_id=str(app.id),
                            description=f"distribution finalized: {app.app_id} approved ({item.allocated_sub_type})",
                            old_values=prior_app_state,
                            new_values={
                                "status": "approved",
                                "quota_allocation_status": "allocated",
                                "sub_scholarship_type": item.allocated_sub_type,
                                "allocation_config_id": app.allocation_config_id,
                            },
                            meta_data={"app_id": app.app_id, "ranking_item_id": item.id},
                        )
                    )
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
                if admin_user_id is not None:
                    self.db.add(
                        AuditLog.create_log(
                            user_id=admin_user_id,
                            action=AuditAction.execute_distribution.value,
                            resource_type="application",
                            resource_id=str(app.id),
                            description=f"distribution finalized: {app.app_id} not allocated (quota rejected)",
                            old_values=prior_app_state,
                            new_values={
                                "status": prior_app_state["status"],
                                "quota_allocation_status": "rejected",
                            },
                            meta_data={"app_id": app.app_id, "ranking_item_id": item.id},
                        )
                    )
                rejected_count += 1

        # §10 quota gate — recount under SELECT FOR UPDATE before committing the
        # finalize. Reject if any consumed config is oversubscribed.
        requesting_config = await self._load_config(scholarship_type_id, academic_year, semester)
        if requesting_config is not None:
            await self._assert_round_not_oversubscribed(requesting_config)

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
                        "allocation_config_id": item.allocation_config_id,
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
                created_by=admin_user_id,
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
        admin_user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        """
        Restore allocations from a historical snapshot.
        The snapshot contains: {ranking_item_id: {sub_type, allocation_config_id, status}, ...}
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
                item.allocation_config_id = None
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
                    item.allocation_config_id = alloc_data.get("allocation_config_id")
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
                created_by=admin_user_id,
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

        # Server-side quota enforcement is net-new (spec §10): the lock gate in
        # allocate/finalize (_assert_round_not_oversubscribed) recounts remaining
        # under SELECT FOR UPDATE on the consumed config rows and rejects
        # oversubscription. The frontend remaining counts are advisory.

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
        For renewal students, find the allocation_config_id from their previous
        application's CollegeRankingItem (the config that prior slot consumed).

        Returns: {previous_application_id: allocation_config_id}
        Only includes entries where allocation_config_id IS NOT NULL.
        """
        if not previous_app_ids:
            return {}

        stmt = select(CollegeRankingItem).where(
            and_(
                CollegeRankingItem.application_id.in_(previous_app_ids),
                CollegeRankingItem.allocation_config_id.isnot(None),
            )
        )
        result = await self.db.execute(stmt)
        items = result.scalars().all()

        # If a previous app appears in multiple ranking items, use the first one
        mapping: dict[int, int] = {}
        for item in items:
            if item.application_id not in mapping:
                mapping[item.application_id] = item.allocation_config_id
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

        Returns list of {"ranking_item_id", "sub_type_code", "allocation_config_id"} dicts.
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

        # Previous allocation CONFIG for renewal students (the config prior slot consumed).
        previous_app_ids = [
            item.application.previous_application_id
            for item in unique_items
            if item.application.is_renewal and item.application.previous_application_id
        ]
        prev_alloc_configs = await self._batch_load_previous_allocation_years(previous_app_ids)

        # --- Step 1: Resolve requesting config + its distributable configs ---
        requesting_config = await self._load_config(scholarship_type_id, academic_year, semester)
        if requesting_config is None:
            return []
        # Configs reachable for any sub_type: own + every linked source,
        # seeded per real sub_type below (a bare resolve("") matches nothing).
        all_configs: dict[int, ScholarshipConfiguration] = {requesting_config.id: requesting_config}

        # Build all linked configs across all sub_types
        sub_types = set((requesting_config.quotas or {}).keys())
        for entry in requesting_config.shared_quota_sources or []:
            sub_types.update(entry.get("sub_types") or [])
        for st in sub_types:
            for cfg in await self._resolve_linked_configs(requesting_config, st):
                all_configs[cfg.id] = cfg

        # allowed_configs_by_sub_type: own-first then linked by descending year.
        allowed_configs_by_sub_type: dict[str, list[int]] = {}
        for st in sub_types:
            allowed_configs_by_sub_type[st] = [
                c["config_id"] for c in await self.distributable_pool(requesting_config, st)
            ]

        # --- Step 2: Build the per-(config, sub_type, college) tracker ---
        # Seed from each consumed config's matrix so per-college caps survive,
        # then subtract every existing global consumer of that config so the
        # tracker reflects live remaining (honors the cross-config pool cap).
        quota_tracker: dict[tuple[str, int, str], int] = {}
        for cid, cfg in all_configs.items():
            if not cfg.has_college_quota or not cfg.quotas:
                continue
            for sub_type, college_quotas in cfg.quotas.items():
                if not isinstance(college_quotas, dict):
                    continue
                for college_code, quota in college_quotas.items():
                    quota_tracker[(cid, sub_type, college_code)] = int(quota)

        # Subtract every already-allocated ranking item pointing at these configs
        # (across ALL rankings, not just this round — global pool).
        existing_stmt = (
            select(CollegeRankingItem)
            .options(selectinload(CollegeRankingItem.application))
            .where(
                CollegeRankingItem.is_allocated.is_(True),
                CollegeRankingItem.allocation_config_id.in_(list(all_configs.keys())),
            )
        )
        existing_items = (await self.db.execute(existing_stmt)).scalars().all()
        for ex in existing_items:
            if not ex.allocated_sub_type or ex.application is None:
                continue
            college = (ex.application.student_data or {}).get("std_academyno", "")
            key = (ex.allocation_config_id, ex.allocated_sub_type, college)
            if key in quota_tracker:
                quota_tracker[key] = max(0, quota_tracker[key] - 1)

        # Subtract approved renewals consuming these configs (Application half).
        renewal_stmt = select(Application).where(
            Application.is_renewal.is_(True),
            Application.status == ApplicationStatus.approved,
            Application.allocation_config_id.in_(list(all_configs.keys())),
            Application.deleted_at.is_(None),
        )
        renewal_rows = (await self.db.execute(renewal_stmt)).scalars().all()
        for ra in renewal_rows:
            if not ra.sub_scholarship_type:
                continue
            college = (ra.student_data or {}).get("std_academyno", "")
            key = (ra.allocation_config_id, ra.sub_scholarship_type, college)
            if key in quota_tracker:
                quota_tracker[key] = max(0, quota_tracker[key] - 1)

        # Load rejected sub-types from professor reviews.
        app_ids = [item.application.id for item in unique_items]
        rejected_map = await self._batch_load_rejected_map(app_ids)

        return _compute_suggestions(
            unique_items=unique_items,
            default_prefs=default_prefs,
            prev_alloc_configs=prev_alloc_configs,
            allowed_configs_by_sub_type=allowed_configs_by_sub_type,
            quota_tracker=quota_tracker,
            own_config_id=requesting_config.id,
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
        # Capture the original cancellation reason BEFORE clearing it below —
        # the endpoint's audit log preserves it as old_values (G18/G9).
        prior_reason = app.revoke_reason if prior_status == "revoked" else app.suspend_reason

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

        # Audit logging moved to the endpoint (ApplicationAuditService.
        # log_application_restore) so the row carries the acting User +
        # request IP/UA and the action lives in the AuditAction enum (G18).
        await self.db.flush()

        return {
            "application_id": application_id,
            "app_id": app.app_id,
            "ranking_item_id": ranking_item_id,
            "quota_allocation_status": app.quota_allocation_status,
            "restored_from": prior_status,
            "restored_reason": prior_reason,
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

        # 7. Audit logging moved to the endpoint (ApplicationAuditService.
        # log_application_revoke / log_application_suspend) so the row carries
        # the acting User + request IP/UA and the action lives in the
        # AuditAction enum instead of an ad-hoc string (G18).
        await self.db.flush()

        timestamp_key = "revoked_at" if mode == "revoke" else "suspended_at"
        return {
            "application_id": application_id,
            "app_id": app.app_id,
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

    async def _pick_config(
        self,
        requesting_config: ScholarshipConfiguration,
        sub_type: str,
        working_remaining: dict[int, int],
    ) -> Optional[int]:
        """Pick the next config id with positive working remaining for sub_type.

        Replaces the year-keyed `_pick_pool` (spec §6.3). Policy: prefer the OWN
        config first, then linked source configs by DESCENDING academic_year.
        `working_remaining` is keyed by config id and supplied (and decremented)
        by the caller so a multi-assign loop need not re-query the DB. Returns
        None when no candidate config has positive remaining.
        """
        if working_remaining.get(requesting_config.id, 0) > 0:
            return requesting_config.id
        linked = await self._resolve_linked_configs(requesting_config, sub_type)
        for cfg in sorted(linked, key=lambda c: c.academic_year, reverse=True):
            if working_remaining.get(cfg.id, 0) > 0:
                return cfg.id
        return None

    async def _config_code_by_id(
        self, requesting_config: ScholarshipConfiguration, sub_type: str, config_id: Optional[int]
    ) -> str:
        """Human-readable config_code for an id (own, linked, or any other config),
        for error messages. Falls back to a direct lookup so a disallowed-but-real
        config still names itself, and to the raw id only if it does not exist."""
        if config_id == requesting_config.id:
            return requesting_config.config_code
        for cfg in await self._resolve_linked_configs(requesting_config, sub_type):
            if cfg.id == config_id:
                return cfg.config_code
        if config_id is not None:
            code = await self.db.scalar(
                select(ScholarshipConfiguration.config_code).where(ScholarshipConfiguration.id == config_id)
            )
            if code:
                return code
        return str(config_id)

    async def _assert_round_not_oversubscribed(self, requesting_config: ScholarshipConfiguration) -> None:
        """§10 quota gate: SELECT FOR UPDATE the consumed config rows for this
        round (own + every linked source across every sub_type), recount remaining
        via §6.2, and reject if any consumed config is oversubscribed.

        Flushes pending allocation writes FIRST so the recount sees them (autoflush
        is off on this session, so the just-written items would otherwise be
        invisible to the count queries)."""
        await self.db.flush()

        consumed_ids = {requesting_config.id}
        for sub_type in (requesting_config.quotas or {}).keys():
            for cfg in await self._resolve_linked_configs(requesting_config, sub_type):
                consumed_ids.add(cfg.id)

        locked_rows = (
            (
                await self.db.execute(
                    select(ScholarshipConfiguration)
                    .where(ScholarshipConfiguration.id.in_(consumed_ids))
                    .order_by(ScholarshipConfiguration.id)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

        for cfg in locked_rows:
            for sub_type in (cfg.quotas or {}).keys():
                if await self.remaining(cfg, sub_type) < 0:
                    raise ValueError(f"配額超額：{cfg.config_code} / {sub_type} 的核配數已超過總配額，請調整分發")

    async def execute_general_distribution(
        self,
        scholarship_type_id: int,
        academic_year: int,
    ) -> dict[str, Any]:
        """Run general-phase distribution with challenge release and waitlist fill-in.

        Rebuilt onto the live shared pool (spec §6.3):
        1. Per sub_type, seed working_remaining{config_id} from distributable_pool.
        2. First-round: assign each ranked candidate to the next config with
           positive working remaining (own first, then linked by year).
        3. Each approved challenge cancels its renewal target; track the freed
           slot keyed on the cancelled renewal's allocation_config_id.
        4. Fill released slots from the same-sub_type waitlist, re-deriving
           remaining(freed_config, st) rather than trusting a raw release count.
        """
        config = await self._get_active_config(scholarship_type_id, academic_year)
        sub_types = list((config.quotas or {}).keys())

        # 1+2. First-round distribution per sub_type.
        approved_challenges: list[Application] = []
        for sub_type in sub_types:
            pool = await self.distributable_pool(config, sub_type)
            working_remaining: dict[int, int] = {c["config_id"]: c["remaining"] for c in pool}
            candidates = await self._get_general_candidates(scholarship_type_id, academic_year, sub_type)
            for cand in candidates:
                picked = await self._pick_config(config, sub_type, working_remaining)
                if picked is None:
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
                cand.allocation_config_id = picked
                cand.status = "allocated"
                cand.allocation_reason = "一般階段自動分發"
                working_remaining[picked] -= 1
                if app.challenges_application_id is not None:
                    approved_challenges.append(app)

        # 3. Release handling — approved challenges cancel their renewal targets.
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

        # released keyed on (sub_type, freed_config_id) from the cancelled renewal.
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
            freed_config_id = renewal_app.allocation_config_id
            if freed_config_id is None:
                logger.warning(
                    "Cancelled renewal id=%s has no allocation_config_id — cannot release a slot",
                    renewal_app.id,
                )
                continue
            key = (renewal_app.sub_scholarship_type, freed_config_id)
            released[key] = released.get(key, 0) + 1

        # 4. Fill released slots from waitlist of same sub_type, re-deriving
        # remaining(freed_config, st) after the cancellations above were flushed.
        await self.db.flush()
        fill_in_count = 0
        all_configs = {config.id: config}
        for st in sub_types:
            for c in await self._resolve_linked_configs(config, st):
                all_configs[c.id] = c
        for (sub_type, freed_config_id), _count in released.items():
            freed_config = all_configs.get(freed_config_id)
            if freed_config is None:
                freed_config = (
                    await self.db.execute(
                        select(ScholarshipConfiguration).where(ScholarshipConfiguration.id == freed_config_id)
                    )
                ).scalar_one_or_none()
                if freed_config is None:
                    continue
            available = await self.remaining(freed_config, sub_type)
            if available <= 0:
                continue
            waitlist = await self._get_waitlist_candidates(
                scholarship_type_id, academic_year, sub_type, limit=available
            )
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
                cand.allocation_config_id = freed_config_id
                cand.status = "allocated"
                cand.allocation_reason = "釋出 slot 候補遞補"
                fill_in_count += 1

        await self.db.commit()

        return {
            "approved_challenges": len(approved_challenges),
            "released_slots": {f"{st}:{cid}": n for (st, cid), n in released.items()},
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
            # renewal accounting (consumers_count owns approved-renewal counts).
            year_key = int(app.renewal_year) if app.renewal_year is not None else int(academic_year)
            key = (app.sub_scholarship_type, year_key)
            renewal_grouped.setdefault(key, []).append(
                {
                    "application_id": app.id,
                    "student_name": app.student.name if app.student else None,
                    "has_challenge": app.id in challenged_renewal_ids,
                }
            )

        # --- 2. Available quotas per (sub_type, config) — live shared pool --- #
        available_quotas: list[dict[str, Any]] = []
        # Collect all sub_types (own + linked sources) to build pool columns.
        sub_types = set((config.quotas or {}).keys())
        for entry in config.shared_quota_sources or []:
            sub_types.update(entry.get("sub_types") or [])

        # Build a lookup of all reachable configs (own + any linked source).
        # We call _resolve_linked_configs per sub_type since it filters by sub_type.
        all_configs: dict[int, ScholarshipConfiguration] = {config.id: config}
        for sub_type in sub_types:
            for linked_cfg in await self._resolve_linked_configs(config, sub_type):
                all_configs[linked_cfg.id] = linked_cfg

        for sub_type in sub_types:
            for col in await self.distributable_pool(config, sub_type):
                cfg = all_configs.get(col["config_id"])
                if cfg is None:
                    continue
                total = self.pool_total(cfg, sub_type)
                if total <= 0:
                    continue
                remaining = col["remaining"]
                available_quotas.append(
                    {
                        "sub_type": sub_type,
                        "config_id": col["config_id"],
                        "config_code": col["config_code"],
                        "academic_year": col["academic_year"],
                        "is_own": col["is_own"],
                        "total": total,
                        "used": total - remaining,
                        "remaining": remaining,
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

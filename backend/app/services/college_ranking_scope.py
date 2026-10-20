"""Ranking-scope rules for college rankings (同步申請名單 / 確認排名 collapse).

A ranking's scope is (scholarship type, sub-type, academic year, semester, college).
A college may keep several draft rankings per scope; finalizing one deletes the
others, so a scope holds at most one finalized ranking (partial unique index
uq_college_rankings_finalized_per_college). This module holds the pieces those rules
share — the per-scope advisory lock, the settled / roster-referenced guards, the
diff against the application list and the sync — as a mixin of CollegeReviewService.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import and_, delete
from sqlalchemy import func as sa_func
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import (
    CANCELLED_ALLOCATION_STATUSES,
    REVIEWABLE_APPLICATION_STATUSES,
    ApplicationStatus,
    Semester,
)
from app.models.payment_roster import PaymentRoster
from app.services.college_review_errors import RankingModificationError, RankingNotFoundError, RankingScopeConflictError
from app.services.ranking_groups import ranking_group

# int4 namespace for pg_advisory_xact_lock(int4, int4) — ASCII "RANK". The second
# key is hashtext() of the ranking scope, so create / finalize / delete of one
# scope serialise while other scopes never wait on each other.
RANKING_SCOPE_LOCK_NAMESPACE = 0x52414E4B

# Ranking-item statuses that carry no distribution outcome. Anything else
# ('allocated' / 'rejected' / 'waitlisted') is written by manual distribution.
_UNDISTRIBUTED_ITEM_STATUSES = (None, "ranked")

# Application statuses that take an application out of the ranking pool only for a
# while: staff move it back to under_review, or the student resubmits. A sync keeps
# such an application's ranking item (and its rank) instead of removing it.
_REVERSIBLE_INELIGIBLE_STATUSES = frozenset(
    {
        ApplicationStatus.pending_documents.value,
        ApplicationStatus.returned.value,
        ApplicationStatus.manual_excluded.value,
    }
)


def _status_value(status: Any) -> Any:
    return status.value if hasattr(status, "value") else status


def _has_allocation_state(item: Any) -> bool:
    """True when a ranking item (ORM row or column tuple) carries distribution state.

    These are exactly the columns manual distribution writes: allocate() / finalize()
    set is_allocated, allocated_sub_type, allocation_config_id and status
    ('allocated' / 'rejected'); 撤銷/停發 clear is_allocated but keep
    allocated_sub_type so 復發 can re-affirm the slot; backup_position /
    backup_allocations hold 備取 data. Rosters, quota counters and history
    snapshots depend on them, so such items are never removed or deleted.
    """
    return bool(
        item.is_allocated
        or item.allocated_sub_type is not None
        or item.allocation_config_id is not None
        or item.backup_position is not None
        or item.backup_allocations
        or item.status not in _UNDISTRIBUTED_ITEM_STATUSES
    )


def _is_reversibly_ineligible(app: Optional[Application]) -> bool:
    """True when the application left the ranking pool in a state that can be undone."""
    if app is None or app.deleted_at is not None:
        return False
    status = _status_value(app.status)
    if status in _REVERSIBLE_INELIGIBLE_STATUSES:
        return True
    # 撤銷 / 停發 park an application at status=cancelled until 復發 (restore_allocation).
    return status == ApplicationStatus.cancelled.value and app.quota_allocation_status in CANCELLED_ALLOCATION_STATUSES


@dataclass(frozen=True)
class RankingDiff:
    """How a ranking differs from the applications it should hold right now."""

    # Eligible applications not in the ranking, in _ranking_sort_key order.
    pending_application_ids: List[int]
    # Ranked applications that are no longer eligible (withdrawn, deleted, sub-type /
    # college / term changed), in rank order. Excludes items carrying allocation state
    # and applications parked in a reversible state.
    stale_application_ids: List[int]

    @property
    def has_changes(self) -> bool:
        return bool(self.pending_application_ids or self.stale_application_ids)


@dataclass(frozen=True)
class RankingSyncResult:
    """Outcome of sync_ranking (同步申請名單)."""

    ranking: CollegeRanking
    added_application_ids: List[int]
    removed_application_ids: List[int]
    # str(application_id) -> rank_position before the sync, read under the row lock
    # (the audit trail's 「同步前的名次」).
    previous_rank_positions: Dict[str, int]


@dataclass(frozen=True)
class DeletedRankingInfo:
    """Snapshot of a deleted ranking for the audit trail (its order is otherwise lost)."""

    id: int
    ranking_name: Optional[str]
    total_applications: int
    # str(application_id) -> rank_position at deletion time.
    rank_positions: Dict[str, int]


@dataclass(frozen=True)
class RankingFinalizeResult:
    """Outcome of finalize_ranking: the locked ranking and the drafts it superseded."""

    ranking: CollegeRanking
    deleted_rankings: List[DeletedRankingInfo]


class RankingScopeMixin:
    """Scope / diff / sync / collapse helpers of CollegeReviewService (needs ``self.db``)."""

    db: AsyncSession

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

    def _dialect_name(self) -> str:
        """Dialect of the session's bind ("" for a stub session without one)."""
        get_bind = getattr(self.db, "get_bind", None)
        if get_bind is None:
            return ""
        name = getattr(getattr(get_bind(), "dialect", None), "name", None)
        return name if isinstance(name, str) else ""

    async def _lock_ranking_scope(
        self,
        scholarship_type_id: int,
        sub_type_code: str,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
    ) -> None:
        """Serialise create / finalize / delete for one ranking scope (PostgreSQL only).

        Row locks cannot stop a concurrent INSERT of a new draft, so a transaction
        advisory lock keyed on the scope is taken instead; it is released at
        commit/rollback. SQLite (tests) has no concurrent writers, so it is skipped.
        """
        if self._dialect_name() != "postgresql":
            return
        normalized_semester = self._normalize_semester_value(semester)
        scope_key = (
            f"{scholarship_type_id}:{sub_type_code}:{academic_year}:"
            f"{normalized_semester or 'yearly'}:{college_code or ''}"
        )
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, hashtext(:scope_key))"),
            {"namespace": RANKING_SCOPE_LOCK_NAMESPACE, "scope_key": scope_key},
        )

    @classmethod
    def _scope_conditions(
        cls,
        scholarship_type_id: int,
        sub_type_code: str,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
    ) -> list:
        """WHERE conditions selecting every ranking of a scope.

        Matches uq_college_rankings_finalized_per_college, which coalesces a NULL
        semester to 'yearly' and a NULL college_code to '' (admin global ranking).
        """
        normalized_semester = cls._normalize_semester_value(semester)
        conditions = [
            CollegeRanking.scholarship_type_id == scholarship_type_id,
            CollegeRanking.sub_type_code == sub_type_code,
            CollegeRanking.academic_year == academic_year,
        ]
        if normalized_semester is None:
            conditions.append(or_(CollegeRanking.semester.is_(None), CollegeRanking.semester == Semester.yearly.value))
        else:
            conditions.append(CollegeRanking.semester == normalized_semester)
        if college_code:
            conditions.append(CollegeRanking.college_code == college_code)
        else:
            conditions.append(or_(CollegeRanking.college_code.is_(None), CollegeRanking.college_code == ""))
        return conditions

    async def list_scope_rankings(
        self,
        scholarship_type_id: int,
        sub_type_code: str,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
        *,
        exclude_id: Optional[int] = None,
        for_update: bool = False,
    ) -> List[CollegeRanking]:
        """Every ranking of a scope, ordered by id (fresh from the DB, not the identity map)."""
        conditions = self._scope_conditions(scholarship_type_id, sub_type_code, academic_year, semester, college_code)
        if exclude_id is not None:
            conditions.append(CollegeRanking.id != exclude_id)
        stmt = (
            select(CollegeRanking)
            .where(and_(*conditions))
            .order_by(CollegeRanking.id)
            .execution_options(populate_existing=True)
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _select_ranking_for_update(self, ranking_id: int) -> Optional[CollegeRanking]:
        """Row-lock a ranking and re-read it (None when a concurrent request deleted it)."""
        stmt = (
            select(CollegeRanking)
            .where(CollegeRanking.id == ranking_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _load_settled_ids(self, ranking_ids: Iterable[int]) -> Set[int]:
        """Rankings whose distribution was executed or that hold any item with allocation state.

        Such rankings feed rosters, quota counters and history snapshots, so they are
        never deleted and only ever appended to (see _has_allocation_state).
        """
        ids = {ranking_id for ranking_id in ranking_ids if ranking_id is not None}
        if not ids:
            return set()

        executed_result = await self.db.execute(
            select(CollegeRanking.id).where(
                CollegeRanking.id.in_(ids),
                CollegeRanking.distribution_executed.is_(True),
            )
        )
        settled = set(executed_result.scalars().all())

        remaining = ids - settled
        if not remaining:
            return settled

        # SQL pre-filter is a superset of _has_allocation_state (JSON emptiness is
        # dialect-specific), the exact predicate runs in Python.
        item_rows = await self.db.execute(
            select(
                CollegeRankingItem.ranking_id,
                CollegeRankingItem.is_allocated,
                CollegeRankingItem.allocated_sub_type,
                CollegeRankingItem.allocation_config_id,
                CollegeRankingItem.backup_position,
                CollegeRankingItem.backup_allocations,
                CollegeRankingItem.status,
            ).where(
                CollegeRankingItem.ranking_id.in_(remaining),
                or_(
                    CollegeRankingItem.is_allocated.is_(True),
                    CollegeRankingItem.allocated_sub_type.isnot(None),
                    CollegeRankingItem.allocation_config_id.isnot(None),
                    CollegeRankingItem.backup_position.isnot(None),
                    CollegeRankingItem.backup_allocations.isnot(None),
                    and_(CollegeRankingItem.status.isnot(None), CollegeRankingItem.status != "ranked"),
                ),
            )
        )
        settled.update(row.ranking_id for row in item_rows.all() if _has_allocation_state(row))
        return settled

    async def _load_roster_referenced_ids(self, ranking_ids: Iterable[int]) -> Set[int]:
        """Rankings referenced by a payment roster (payment_rosters.ranking_id).

        On PostgreSQL the column carries two FKs (NO ACTION and ON DELETE SET NULL);
        whichever trigger fires first wins, so deleting such a ranking either fails or
        silently unlinks the roster (a pg_restore'd DB). Whole-period rosters also
        resolve their members through it, so such rankings are never deleted.
        """
        ids = {ranking_id for ranking_id in ranking_ids if ranking_id is not None}
        if not ids:
            return set()
        result = await self.db.execute(
            select(PaymentRoster.ranking_id).where(PaymentRoster.ranking_id.in_(ids)).distinct()
        )
        return set(result.scalars().all())

    async def _application_ids_ranked_elsewhere(
        self, application_ids: Iterable[int], excluded_ranking_ids: Iterable[int]
    ) -> Set[int]:
        """Applications still held by a ranking outside ``excluded_ranking_ids``.

        Application.final_ranking_position is a single value, yet an application can
        also sit in rankings of other scopes (a sub-type ranking and the "default"
        one, a college ranking and an admin global one) whose positions may coincide.
        A matching value therefore does not prove which ranking wrote it, so it is
        never cleared while another ranking still holds the application.
        """
        ids = set(application_ids)
        if not ids:
            return set()
        result = await self.db.execute(
            select(CollegeRankingItem.application_id)
            .where(
                CollegeRankingItem.application_id.in_(ids),
                CollegeRankingItem.ranking_id.notin_(set(excluded_ranking_ids)),
            )
            .distinct()
        )
        return set(result.scalars().all())

    async def load_ranking_protection(self, ranking_ids: Iterable[int]) -> Tuple[Set[int], Set[int]]:
        """(settled ids, roster-referenced ids) among ``ranking_ids``, for the ranking list.

        A settled ranking blocks creating another ranking in its scope; neither kind
        is ever deleted, by 刪除 or by another ranking's lock. The list exposes both
        so the UI disables those actions instead of inviting a certain 409.
        """
        ids = list(ranking_ids)
        return await self._load_settled_ids(ids), await self._load_roster_referenced_ids(ids)

    async def _is_settled(self, ranking: CollegeRanking) -> bool:
        return ranking.id in await self._load_settled_ids([ranking.id])

    @staticmethod
    def _ranking_label(ranking: CollegeRanking) -> str:
        return ranking.ranking_name or f"排名 #{ranking.id}"

    @staticmethod
    def _ranking_sort_key(app: Application) -> tuple:
        """Renewals first, then each 申請梯次 in round order; inside a group by
        professor rank, then earlier submission."""
        sort_group = ranking_group(app)  # 0 = renewal (top), 1 = 第一梯次, 2 = 第二梯次 ...
        # If application has final_ranking_position, use it; otherwise use a large number (lowest priority)
        rank = app.final_ranking_position if app.final_ranking_position else 999999
        # Use submitted_at as secondary sort (earlier submissions get higher priority if same rank)
        submitted_at = app.submitted_at or app.created_at
        return (sort_group, rank, submitted_at.timestamp())

    async def _eligible_applications(
        self,
        scholarship_type_id: int,
        sub_type_code: str,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
    ) -> List[Application]:
        """Applications a college ranking of this key should contain right now.

        Same semester logic as get_applications_for_review; ``sub_type_code == "default"``
        spans every sub-type. ``college_code`` restricts to the college's own students via
        the SIS snapshot (std_academyno); None (admin global ranking) means all colleges.
        """
        normalized_semester = self._normalize_semester_value(semester)

        conditions = [
            Application.scholarship_type_id == scholarship_type_id,
            Application.academic_year == academic_year,
            Application.deleted_at.is_(None),  # Exclude soft-deleted applications
            # Valid statuses for ranking: the same reviewed/approved states the
            # review listings surface (shared constant keeps the sites in sync).
            Application.status.in_(REVIEWABLE_APPLICATION_STATUSES),
        ]

        if sub_type_code != "default":
            conditions.append(Application.sub_scholarship_type == sub_type_code)

        if self._is_yearly_semester(semester):
            conditions.append(or_(Application.semester.is_(None), Application.semester == Semester.yearly.value))
        elif normalized_semester:
            conditions.append(
                or_(Application.semester == Semester(normalized_semester), Application.semester.is_(None))
            )

        if college_code:
            # std_academyno is the college field in the student_data SIS snapshot
            conditions.append(sa_func.json_extract_path_text(Application.student_data, "std_academyno") == college_code)

        result = await self.db.execute(select(Application).where(and_(*conditions)))
        return list(result.scalars().all())

    async def _load_item_rows(self, ranking_id: int) -> List[Tuple[CollegeRankingItem, Optional[Application]]]:
        """(item, application) pairs of a ranking in rank order — explicit query, no lazy loads."""
        result = await self.db.execute(
            select(CollegeRankingItem, Application)
            .outerjoin(Application, CollegeRankingItem.application_id == Application.id)
            .where(CollegeRankingItem.ranking_id == ranking_id)
            .order_by(CollegeRankingItem.rank_position, CollegeRankingItem.id)
        )
        return [(item, app) for item, app in result.all()]

    async def _diff_against_applications(
        self, ranking: CollegeRanking, *, append_only: bool
    ) -> Tuple[RankingDiff, List[Tuple[CollegeRankingItem, Optional[Application]]], Dict[int, Application]]:
        """Diff a ranking against ONE _eligible_applications result.

        Pending and stale come from the same eligible set, so a sync can never remove
        an application that the next diff would report as pending again. With
        ``append_only`` (a settled ranking) nothing is ever reported as stale.
        """
        item_rows = await self._load_item_rows(ranking.id)
        eligible = await self._eligible_applications(
            ranking.scholarship_type_id,
            ranking.sub_type_code,
            ranking.academic_year,
            ranking.semester,
            ranking.college_code,
        )
        eligible_by_id = {app.id: app for app in eligible}
        ranked_ids = {item.application_id for item, _app in item_rows}

        pending = [
            app.id for app in sorted((app for app in eligible if app.id not in ranked_ids), key=self._ranking_sort_key)
        ]
        stale: List[int] = []
        if not append_only:
            stale = list(
                dict.fromkeys(
                    item.application_id
                    for item, app in item_rows
                    if item.application_id not in eligible_by_id
                    and not _has_allocation_state(item)
                    and not _is_reversibly_ineligible(app)
                )
            )
        diff = RankingDiff(pending_application_ids=pending, stale_application_ids=stale)
        return diff, item_rows, eligible_by_id

    async def compute_ranking_diff(self, ranking: CollegeRanking) -> RankingDiff:
        """What 「同步申請名單」 would change, without writing (drives the UI reminder).

        - finalized AND settled (distributed): empty — historic, no reminder noise;
        - settled but unlocked (the 補充匯入 window): pending only, sync is append-only;
        - finalized but not settled: both lists, so the UI can ask to unlock first;
        - draft: both lists.
        """
        settled = await self._is_settled(ranking)
        if ranking.is_finalized and settled:
            return RankingDiff(pending_application_ids=[], stale_application_ids=[])
        diff, _item_rows, _eligible = await self._diff_against_applications(ranking, append_only=settled)
        return diff

    def _add_ranking_item(self, ranking_id: int, app: Application, rank_position: int) -> None:
        self.db.add(CollegeRankingItem(ranking_id=ranking_id, application_id=app.id, rank_position=rank_position))
        app.final_ranking_position = rank_position

    def _append_new_items(
        self,
        ranking: CollegeRanking,
        item_rows: List[Tuple[CollegeRankingItem, Optional[Application]]],
        new_apps: List[Application],
    ) -> int:
        """Append after the current last position; existing items keep their positions."""
        last_position = max((item.rank_position or 0 for item, _app in item_rows), default=0)
        for offset, app in enumerate(new_apps, 1):
            self._add_ranking_item(ranking.id, app, last_position + offset)
        return len(item_rows) + len(new_apps)

    async def _rebuild_draft_items(
        self,
        ranking: CollegeRanking,
        item_rows: List[Tuple[CollegeRankingItem, Optional[Application]]],
        new_apps: List[Application],
        stale_ids: Set[int],
    ) -> int:
        """Drop stale items, slot new applications in, renumber 1..n.

        A new application goes right after the last ranked one of its own or an earlier
        group (續領 → 第一梯次 → 第二梯次 …; at the top when there is none), so the result
        still satisfies update_ranking_order's group-order rule: renewals before new
        applications, a later 梯次 behind the earlier ones. Rows the college rejected
        ('N' in the Excel import, parked at the end) stay behind every new applicant.
        """
        ranked_elsewhere = await self._application_ids_ranked_elsewhere(stale_ids, [ranking.id])
        kept: List[Tuple[Optional[CollegeRankingItem], Optional[Application]]] = []
        for item, app in item_rows:
            if item.application_id not in stale_ids:
                kept.append((item, app))
                continue
            await self.db.delete(item)
            # Leave no rank behind on an application no ranking holds any more —
            # unless a ranking since gone wrote a different value there.
            if app is not None and app.id not in ranked_elsewhere and app.final_ranking_position == item.rank_position:
                app.final_ranking_position = None

        rejected_from = len(kept)
        while rejected_from > 0 and kept[rejected_from - 1][0].college_rejected:
            rejected_from -= 1
        ranked, rejected_tail = kept[:rejected_from], kept[rejected_from:]

        ordered = list(ranked)
        for app in sorted(new_apps, key=ranking_group):  # stable: keeps the pending order inside a group
            group = ranking_group(app)
            cut = 1 + max(
                (index for index, (_item, ranked_app) in enumerate(ordered) if ranking_group(ranked_app) <= group),
                default=-1,
            )
            ordered.insert(cut, (None, app))
        ordered += rejected_tail

        for position, (item, app) in enumerate(ordered, 1):
            if item is None:
                self._add_ranking_item(ranking.id, app, position)
            elif item.rank_position != position:
                item.rank_position = position
                if app is not None:
                    app.final_ranking_position = position
        return len(ordered)

    async def sync_ranking(self, ranking_id: int) -> RankingSyncResult:
        """同步申請名單: add pending applications to a non-finalized ranking, drop stale ones.

        A settled ranking (distribution executed — reachable only while unlocked for
        補充匯入) is append-only: new applications go after the current last position
        and nothing is removed or renumbered, so allocated items keep their positions.
        A plain draft loses its stale items, gains the new ones and is renumbered.
        Every new or moved position is mirrored into Application.final_ranking_position.
        """
        ranking = await self._select_ranking_for_update(ranking_id)
        if not ranking:
            raise RankingNotFoundError(f"Ranking with ID {ranking_id} not found")
        if ranking.is_finalized:
            raise RankingModificationError("排名已鎖定，請先解除鎖定再同步申請名單")

        append_only = await self._is_settled(ranking)
        diff, item_rows, eligible_by_id = await self._diff_against_applications(ranking, append_only=append_only)
        previous_rank_positions = {str(item.application_id): item.rank_position for item, _app in item_rows}
        new_apps = [eligible_by_id[app_id] for app_id in diff.pending_application_ids]

        if append_only:
            total = self._append_new_items(ranking, item_rows, new_apps)
        else:
            total = await self._rebuild_draft_items(ranking, item_rows, new_apps, set(diff.stale_application_ids))

        ranking.total_applications = total
        ranking.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        return RankingSyncResult(
            ranking=ranking,
            added_application_ids=list(diff.pending_application_ids),
            removed_application_ids=list(diff.stale_application_ids),
            previous_rank_positions=previous_rank_positions,
        )

    async def _assert_scope_accepts_new_ranking(
        self,
        scholarship_type_id: int,
        sub_type_code: str,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
    ) -> None:
        """409 while the scope holds a finalized or a settled (distributed) ranking."""
        scope_rankings = await self.list_scope_rankings(
            scholarship_type_id, sub_type_code, academic_year, semester, college_code
        )
        finalized = next((ranking for ranking in scope_rankings if ranking.is_finalized), None)
        if finalized:
            raise RankingScopeConflictError(
                f"本學院此學年度／學期已有鎖定（已確認）的排名「{self._ranking_label(finalized)}」，"
                "無法再新增排名；如需重新排名請先解除鎖定"
            )

        settled_ids = await self._load_settled_ids(ranking.id for ranking in scope_rankings)
        settled = next((ranking for ranking in scope_rankings if ranking.id in settled_ids), None)
        if settled:
            raise RankingScopeConflictError(
                f"排名「{self._ranking_label(settled)}」已執行分發，無法再新增排名；"
                "如需加入新申請請在該排名按「同步申請名單」"
            )

    async def _delete_rankings(self, rankings: List[CollegeRanking]) -> List[DeletedRankingInfo]:
        """Hard-delete rankings and their items; return a rank snapshot of each.

        college_ranking_items.ranking_id is a NO ACTION FK and the ORM cascade only
        fires for session.delete(), so the items are bulk-deleted first. Callers must
        have checked the rankings are neither settled nor roster-referenced.
        """
        if not rankings:
            return []
        ids = [ranking.id for ranking in rankings]

        position_rows = await self.db.execute(
            select(
                CollegeRankingItem.ranking_id,
                CollegeRankingItem.application_id,
                CollegeRankingItem.rank_position,
            ).where(CollegeRankingItem.ranking_id.in_(ids))
        )
        rank_positions: Dict[int, Dict[str, int]] = {ranking_id: {} for ranking_id in ids}
        for ranking_id, application_id, rank_position in position_rows.all():
            rank_positions[ranking_id][str(application_id)] = rank_position

        infos = [
            DeletedRankingInfo(
                id=ranking.id,
                ranking_name=ranking.ranking_name,
                total_applications=(
                    ranking.total_applications
                    if ranking.total_applications is not None
                    else len(rank_positions[ranking.id])
                ),
                rank_positions=rank_positions[ranking.id],
            )
            for ranking in rankings
        ]

        await self.db.execute(delete(CollegeRankingItem).where(CollegeRankingItem.ranking_id.in_(ids)))
        await self.db.execute(delete(CollegeRanking).where(CollegeRanking.id.in_(ids)))
        return infos

    def _assert_siblings_confirmed(self, siblings: List[CollegeRanking], expected_sibling_ids: Iterable[int]) -> None:
        """409 when the scope holds a ranking the user did not confirm deleting.

        The confirm dialog lists the siblings of the user's last ranking-list load;
        another reviewer may have created a draft since. Siblings deleted meanwhile
        are fine (fewer deletions than confirmed).
        """
        confirmed = set(expected_sibling_ids)
        unconfirmed = [sibling for sibling in siblings if sibling.id not in confirmed]
        if unconfirmed:
            names = "、".join(f"「{self._ranking_label(sibling)}」" for sibling in unconfirmed)
            raise RankingScopeConflictError(
                f"此學年度／學期有新的排名 {names} 尚未列入確認，鎖定會將其刪除；請重新整理後再確認排名"
            )

    async def _assert_siblings_removable(self, siblings: List[CollegeRanking]) -> None:
        """409 unless every sibling is a plain draft that finalize may delete."""
        finalized = next((sibling for sibling in siblings if sibling.is_finalized), None)
        if finalized:
            raise RankingScopeConflictError(
                f"此學年度／學期已有鎖定的排名「{self._ranking_label(finalized)}」，無法再確認另一份排名"
            )

        sibling_ids = [sibling.id for sibling in siblings]
        protected_ids = await self._load_settled_ids(sibling_ids) | await self._load_roster_referenced_ids(sibling_ids)
        protected = next((sibling for sibling in siblings if sibling.id in protected_ids), None)
        if protected:
            raise RankingScopeConflictError(
                f"排名「{self._ranking_label(protected)}」已執行分發或已用於造冊，無法自動刪除；"
                "請聯絡管理員處理後再確認排名"
            )

    async def _mirror_final_ranking_positions(
        self, ranking_id: int, superseded: Iterable[DeletedRankingInfo] = ()
    ) -> None:
        """Copy the ranking's positions into Application.final_ranking_position.

        The confirmed ranking is the source of truth; a deleted draft may have
        written its own order there (update_ranking_order mirrors every reorder).
        Applications only the ``superseded`` drafts held lose the rank they wrote
        (see _clear_superseded_positions).
        """
        for item, app in await self._load_item_rows(ranking_id):
            if app is not None and app.final_ranking_position != item.rank_position:
                app.final_ranking_position = item.rank_position
        await self._clear_superseded_positions(superseded)

    async def _clear_superseded_positions(self, superseded: Iterable[DeletedRankingInfo]) -> None:
        """Clear the rank deleted rankings wrote on applications no ranking holds any more.

        Without this the review listing keeps showing such an application as ranked.
        An application another ranking still holds (the confirmed one, or another
        scope's) keeps its value; see _application_ids_ranked_elsewhere.
        """
        superseded = list(superseded)
        orphan_positions: Dict[int, Set[int]] = {}
        for info in superseded:
            for application_id, rank_position in info.rank_positions.items():
                orphan_positions.setdefault(int(application_id), set()).add(rank_position)
        ranked_elsewhere = await self._application_ids_ranked_elsewhere(
            orphan_positions, [info.id for info in superseded]
        )
        orphan_ids = set(orphan_positions) - ranked_elsewhere
        if not orphan_ids:
            return
        result = await self.db.execute(select(Application).where(Application.id.in_(orphan_ids)))
        for app in result.scalars().all():
            if app.final_ranking_position in orphan_positions[app.id]:
                app.final_ranking_position = None

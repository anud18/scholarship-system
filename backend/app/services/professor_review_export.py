"""指導教授審核意見 for the exports.

One home for loading the professor's per-sub-type verdicts and turning them
into display text, shared by the 學生資料彙整表 columns
(CollegeRankingExportService) and the 指導教授評語 page of the per-student
申請資料合併檔 (professor_review_pdf), so the two surfaces never disagree:
both read one ProfessorReviewData built by load_professor_review_data.

Kept free of reportlab/openpyxl and of the endpoint/service layers so any
export module can import it without cycles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.scholarship import ScholarshipConfiguration
from app.models.user import User, UserRole

PROFESSOR_RESULT_LABELS: Dict[str, str] = {"approve": "推薦", "reject": "不推薦"}
# Applied for the sub-type, but no professor verdict on it.
NOT_REVIEWED_LABEL = "未審核"
# The student did not apply for the sub-type — nothing for the professor to review.
NOT_APPLIED_LABEL = "未申請"
# The verdict of an application without real sub-types is stored under this
# code (ReviewService / the professor UI's fallback); a scholarship without
# real sub-types gets one unprefixed column pair for it.
DEFAULT_SUB_TYPE = "default"
# Display name of DEFAULT_SUB_TYPE where a category must be named — the
# professor UI's label for the same item.
DEFAULT_SUB_TYPE_LABEL = "整體推薦"
# Placeholder sub-type of a scholarship without sub-types; same as DEFAULT_SUB_TYPE.
_GENERAL_SUB_TYPE = "general"

RESULT_HEADER = "指導教授審核結果"
COMMENT_HEADER = "指導教授評語"
# Joins several professors' verdicts on one sub-type (co-advisors) in one cell.
_MULTI_SEPARATOR = "；"


@dataclass(frozen=True)
class ProfessorReviewEntry:
    """One professor's verdict on one sub-type of an application."""

    sub_type_code: str  # review_code(): normalized, 'general' folded into 'default'
    recommendation: str  # 'approve' | 'reject'
    comments: Optional[str]
    reviewer_name: Optional[str]
    reviewed_at: Optional[datetime]


def normalize_sub_type(code: Optional[str]) -> str:
    """Sub-types are free-form admin strings; compare them lower/stripped."""
    return (code or "").lower().strip()


def review_code(code: Optional[str]) -> str:
    """normalize_sub_type, with the 'general' placeholder folded into DEFAULT_SUB_TYPE
    (both mean "no real sub-type")."""
    normalized = normalize_sub_type(code)
    return DEFAULT_SUB_TYPE if normalized in ("", _GENERAL_SUB_TYPE) else normalized


def applied_sub_types(application: Any) -> List[str]:
    """review_code()s the professor reviews for this application — mirrors
    ReviewService._normalized_subtypes, including its fallback for no sub-types."""
    raw = getattr(application, "scholarship_subtype_list", None) or []
    codes = [review_code(c) for c in raw if isinstance(c, str) and c.strip()]
    return codes or [DEFAULT_SUB_TYPE]


def recommendation_label(recommendation: Optional[str]) -> str:
    return PROFESSOR_RESULT_LABELS.get(recommendation or "", recommendation or "")


def sub_type_display_name(code: str, sub_type_labels: Dict[str, str]) -> Optional[str]:
    """Chinese name of a sub-type, or None for DEFAULT_SUB_TYPE (no sub-type to name)."""
    if code == DEFAULT_SUB_TYPE:
        return None
    for raw_code, label in sub_type_labels.items():
        if normalize_sub_type(raw_code) == code:
            return label
    return code


@dataclass(frozen=True)
class ProfessorReviewData:
    """Everything the exports need to show professor verdicts for a batch of applications.

    ``sub_types`` is the column set: the scholarship's own sub-types in its
    order, plus any other code a verdict was stored under (so no verdict is
    ever dropped from the table).
    """

    sub_types: Tuple[str, ...] = ()
    entries_by_app: Dict[int, List[ProfessorReviewEntry]] = field(default_factory=dict)
    # Applications whose flow requires a professor verdict (renewal-aware).
    review_required_app_ids: FrozenSet[int] = frozenset()

    def entries(self, application: Any) -> List[ProfessorReviewEntry]:
        return self.entries_by_app.get(getattr(application, "id", None), [])

    def is_review_required(self, application: Any) -> bool:
        return getattr(application, "id", None) in self.review_required_app_ids

    def headers(self, sub_type_labels: Dict[str, str]) -> List[str]:
        """Every sub-type's 審核結果 column first, then every 評語 column."""

        def _header(code: str, suffix: str) -> str:
            name = sub_type_display_name(code, sub_type_labels)
            return f"{name}-{suffix}" if name else suffix

        return [_header(c, RESULT_HEADER) for c in self.sub_types] + [
            _header(c, COMMENT_HEADER) for c in self.sub_types
        ]

    def missing_label(self, application: Any, sub_type_code: str) -> str:
        """Status text for a sub-type without any professor verdict."""
        if sub_type_code in applied_sub_types(application):
            return NOT_REVIEWED_LABEL
        return NOT_APPLIED_LABEL

    def cell_pair(self, application: Any, sub_type_code: str) -> Tuple[str, str]:
        """(審核結果, 評語) cell text for one sub-type.

        With several professors on the same sub-type (co-advisors) each part is
        prefixed with the professor's name so no verdict is silently dropped.
        """
        matching = [e for e in self.entries(application) if e.sub_type_code == sub_type_code]
        if not matching:
            return self.missing_label(application, sub_type_code), ""
        if len(matching) == 1:
            only = matching[0]
            return recommendation_label(only.recommendation), only.comments or ""
        results = _MULTI_SEPARATOR.join(
            f"{e.reviewer_name or '指導教授'}：{recommendation_label(e.recommendation)}" for e in matching
        )
        comments = _MULTI_SEPARATOR.join(
            f"{e.reviewer_name or '指導教授'}：{e.comments}" for e in matching if e.comments
        )
        return results, comments

    def cells(self, application: Any) -> List[str]:
        """Row cells matching headers(): all results, then all comments."""
        pairs = [self.cell_pair(application, code) for code in self.sub_types]
        return [result for result, _ in pairs] + [comment for _, comment in pairs]


def review_sub_type_columns(
    scholarship_type: Any, entries_by_app: Optional[Dict[int, List[ProfessorReviewEntry]]] = None
) -> Tuple[str, ...]:
    """Column set: the scholarship's sub-types in its own order — a listed
    'general' (alone or mixed with real sub-types) becomes DEFAULT_SUB_TYPE, which
    is also the column when the list is empty — then any other code a loaded
    verdict carries."""
    codes: List[str] = []
    for raw in getattr(scholarship_type, "sub_type_list", None) or []:
        code = review_code(raw) if isinstance(raw, str) and raw.strip() else ""
        if code and code not in codes:
            codes.append(code)
    if not codes:
        codes.append(DEFAULT_SUB_TYPE)
    for entries in (entries_by_app or {}).values():
        for entry in entries:
            if entry.sub_type_code not in codes:
                codes.append(entry.sub_type_code)
    return tuple(codes)


async def load_professor_reviews(db: AsyncSession, app_ids: Iterable[int]) -> Dict[int, List[ProfessorReviewEntry]]:
    """{application_id: [entry, ...]} of professor verdicts, oldest review first.

    Only professors' reviews: the college recommends through its ranking and
    the admin through the distribution grid, neither leaves review items.
    Codes are plain normalize_sub_type() here (the manual-distribution grid
    matches them against quota keys); the exports fold them via review_code().
    """
    ids = list(app_ids)
    review_map: Dict[int, List[ProfessorReviewEntry]] = {}
    if not ids:
        return review_map
    query = (
        select(
            ApplicationReview.application_id,
            ApplicationReviewItem.sub_type_code,
            ApplicationReviewItem.recommendation,
            ApplicationReviewItem.comments,
            User.name,
            ApplicationReview.reviewed_at,
        )
        .join(ApplicationReviewItem, ApplicationReviewItem.review_id == ApplicationReview.id)
        .join(User, User.id == ApplicationReview.reviewer_id)
        .where(
            ApplicationReview.application_id.in_(ids),
            User.role == UserRole.professor,
        )
        .order_by(ApplicationReview.reviewed_at, ApplicationReviewItem.id)
    )
    for app_id, sub_type_code, recommendation, comments, reviewer_name, reviewed_at in await db.execute(query):
        review_map.setdefault(app_id, []).append(
            ProfessorReviewEntry(
                sub_type_code=normalize_sub_type(sub_type_code),
                recommendation=recommendation,
                comments=comments,
                reviewer_name=reviewer_name,
                reviewed_at=reviewed_at,
            )
        )
    return review_map


async def _review_required_app_ids(db: AsyncSession, applications: Sequence[Any]) -> FrozenSet[int]:
    """Applications whose configuration requires a professor verdict for their
    kind (new vs renewal) — ScholarshipConfiguration.requires_professor_review_for."""
    config_ids = {a.scholarship_configuration_id for a in applications if a.scholarship_configuration_id}
    if not config_ids:
        return frozenset()
    rows = await db.execute(select(ScholarshipConfiguration).where(ScholarshipConfiguration.id.in_(config_ids)))
    configs = {cfg.id: cfg for cfg in rows.scalars()}
    return frozenset(
        a.id
        for a in applications
        if (cfg := configs.get(a.scholarship_configuration_id))
        and cfg.requires_professor_review_for(bool(a.is_renewal))
    )


async def load_professor_review_data(
    db: AsyncSession, *, scholarship_type: Any, applications: Sequence[Any]
) -> ProfessorReviewData:
    """Bulk-load the professor verdicts, column set and review requirement for an export."""
    loaded = await load_professor_reviews(db, [a.id for a in applications])
    entries_by_app = {
        app_id: [
            ProfessorReviewEntry(
                sub_type_code=review_code(e.sub_type_code),
                recommendation=e.recommendation,
                comments=e.comments,
                reviewer_name=e.reviewer_name,
                reviewed_at=e.reviewed_at,
            )
            for e in entries
        ]
        for app_id, entries in loaded.items()
    }
    return ProfessorReviewData(
        sub_types=review_sub_type_columns(scholarship_type, entries_by_app),
        entries_by_app=entries_by_app,
        review_required_app_ids=await _review_required_app_ids(db, applications),
    )

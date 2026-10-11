"""指導教授審核意見 for the exports.

One home for loading the professor's per-sub-type verdicts and turning them
into display text, shared by the 學生資料彙整表 columns
(CollegeRankingExportService) and the 指導教授評語 page of the per-student
申請資料合併檔 (professor_review_pdf), so the two surfaces never disagree.

Kept free of reportlab/openpyxl and of the endpoint/service layers so any
export module can import it without cycles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.user import User, UserRole

PROFESSOR_RESULT_LABELS: Dict[str, str] = {"approve": "推薦", "reject": "不推薦"}
# Applied for the sub-type, but no professor verdict on it (pending, or a flow
# without a professor step such as most renewals).
NOT_REVIEWED_LABEL = "未審核"
# Did not apply for the sub-type at all — nothing for the professor to review.
NOT_APPLIED_LABEL = "—"
# ReviewService stores the verdict of an application without sub-types under
# this code; a scholarship without real sub-types gets one column pair for it.
DEFAULT_SUB_TYPE = "default"
# ScholarshipType.sub_type_list's placeholder for "no sub-types".
_GENERAL_SUB_TYPE = "general"

RESULT_HEADER = "指導教授審核結果"
COMMENT_HEADER = "指導教授評語"
# Joins several professors' verdicts on one sub-type (co-advisors) in one cell.
_MULTI_SEPARATOR = "；"


@dataclass(frozen=True)
class ProfessorReviewEntry:
    """One professor's verdict on one sub-type of an application."""

    sub_type_code: str  # normalized with normalize_sub_type
    recommendation: str  # 'approve' | 'reject'
    comments: Optional[str]
    reviewer_name: Optional[str]
    reviewed_at: Optional[datetime]


def normalize_sub_type(code: Optional[str]) -> str:
    """Sub-type codes are free-form admin strings; compare them lower/stripped."""
    return (code or "").lower().strip()


async def load_professor_reviews(db: AsyncSession, app_ids: Iterable[int]) -> Dict[int, List[ProfessorReviewEntry]]:
    """{application_id: [entry, ...]} of professor verdicts, oldest review first.

    Only professors' reviews: the college recommends through its ranking and
    the admin through the distribution grid, neither leaves review items.
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


def sub_type_labels_of(scholarship_type: Any) -> Dict[str, str]:
    """sub_type_code → 中文名稱 from the scholarship's sub_type_configs (must be loaded)."""
    labels: Dict[str, str] = {}
    for cfg in getattr(scholarship_type, "sub_type_configs", None) or []:
        if cfg.sub_type_code and cfg.name:
            labels[cfg.sub_type_code] = cfg.name
    return labels


def review_sub_type_columns(scholarship_type: Any) -> List[str]:
    """Sub-types that get a 審核結果/評語 column pair, in the scholarship's own order.

    A scholarship without real sub-types gets a single pair for DEFAULT_SUB_TYPE.
    """
    codes: List[str] = []
    for raw in getattr(scholarship_type, "sub_type_list", None) or []:
        code = normalize_sub_type(raw) if isinstance(raw, str) else ""
        if code and code != _GENERAL_SUB_TYPE and code not in codes:
            codes.append(code)
    return codes or [DEFAULT_SUB_TYPE]


def applied_sub_types(application: Any) -> List[str]:
    """The sub-types the professor reviews for this application — mirrors
    ReviewService._normalized_subtypes, including its "default" fallback."""
    raw = getattr(application, "scholarship_subtype_list", None) or []
    codes = [normalize_sub_type(c) for c in raw if isinstance(c, str) and c.strip()]
    return codes or [DEFAULT_SUB_TYPE]


def sub_type_display_name(code: str, sub_type_labels: Dict[str, str]) -> Optional[str]:
    """Chinese name of a sub-type, or None for DEFAULT_SUB_TYPE (no sub-type to name)."""
    if code == DEFAULT_SUB_TYPE:
        return None
    for raw_code, label in sub_type_labels.items():
        if normalize_sub_type(raw_code) == code:
            return label
    return code


def review_headers(sub_types: Sequence[str], sub_type_labels: Dict[str, str]) -> List[str]:
    """Every sub-type's 審核結果 column first, then every 評語 column."""

    def _header(code: str, suffix: str) -> str:
        name = sub_type_display_name(code, sub_type_labels)
        return f"{name}-{suffix}" if name else suffix

    return [_header(c, RESULT_HEADER) for c in sub_types] + [_header(c, COMMENT_HEADER) for c in sub_types]


def recommendation_label(recommendation: Optional[str]) -> str:
    return PROFESSOR_RESULT_LABELS.get(recommendation or "", recommendation or "")


def review_cell_pair(application: Any, entries: Sequence[ProfessorReviewEntry], sub_type_code: str) -> Tuple[str, str]:
    """(審核結果, 評語) cell text for one sub-type.

    With several professors on the same sub-type (co-advisors) each part is
    prefixed with the professor's name so no verdict is silently dropped.
    """
    matching = [e for e in entries if e.sub_type_code == sub_type_code]
    if not matching:
        status = NOT_REVIEWED_LABEL if sub_type_code in applied_sub_types(application) else NOT_APPLIED_LABEL
        return status, ""
    if len(matching) == 1:
        only = matching[0]
        return recommendation_label(only.recommendation), only.comments or ""
    results = _MULTI_SEPARATOR.join(
        f"{e.reviewer_name or '指導教授'}：{recommendation_label(e.recommendation)}" for e in matching
    )
    comments = _MULTI_SEPARATOR.join(f"{e.reviewer_name or '指導教授'}：{e.comments}" for e in matching if e.comments)
    return results, comments


def review_cells(application: Any, entries: Sequence[ProfessorReviewEntry], sub_types: Sequence[str]) -> List[str]:
    """Row cells matching review_headers: all results, then all comments."""
    pairs = [review_cell_pair(application, entries, code) for code in sub_types]
    return [result for result, _ in pairs] + [comment for _, comment in pairs]

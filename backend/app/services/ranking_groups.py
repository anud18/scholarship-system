"""College-ranking order groups: 續領 → 第一梯次 → 第二梯次 → ...

A college ranking lists renewals first, then each 申請梯次 in round order, so a
later round's applicants always rank behind the earlier rounds' (多梯次申請).
The college orders freely inside a group. Rows the college rejected ('N') are
parked at the end of the ranking and are exempt from the group order.
"""

from typing import Any, Iterable, Optional, Tuple

from sqlalchemy import case, func

from app.models.application_round import FIRST_APPLICATION_ROUND

RENEWAL_GROUP = 0

RENEWAL_ORDER_ERROR = "續領學生的排名必須在所有新申請學生之前"

_CHINESE_NUMERALS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]


def round_label(round_number: int) -> str:
    """第一梯次 / 第二梯次 / ... (Arabic digits past 十)."""
    if 0 < round_number < len(_CHINESE_NUMERALS):
        return f"第{_CHINESE_NUMERALS[round_number]}梯次"
    return f"第{round_number}梯次"


def application_round_of(app: Any) -> int:
    """The application's 梯次 (missing / NULL → round 1)."""
    return getattr(app, "application_round", None) or FIRST_APPLICATION_ROUND


def ranking_group(app: Any) -> int:
    """Sort group of an application in a college ranking (lower ranks first)."""
    if app is None:
        return FIRST_APPLICATION_ROUND
    if getattr(app, "is_renewal", False):
        return RENEWAL_GROUP
    return application_round_of(app)


def ranking_group_sql(application_cls):
    """SQL twin of ranking_group for ORDER BY on an Application query."""
    return case(
        (application_cls.is_renewal.is_(True), RENEWAL_GROUP),
        else_=func.coalesce(application_cls.application_round, FIRST_APPLICATION_ROUND),
    )


def distribution_order_key(app: Any, rank_position: int, ranking_item_id: int) -> Tuple[int, int, int]:
    """Order of a college's ranked students on the admin distribution page and in 預設分發:
    續領 → 第一梯次 → 第二梯次 …, then the college's rank, then the ranking item."""
    return (ranking_group(app), rank_position, ranking_item_id)


def round_order_error(earlier_group: int, later_group: int) -> str:
    """Message for an application of ``later_group`` ranked above one of ``earlier_group``."""
    if earlier_group == RENEWAL_GROUP:
        return RENEWAL_ORDER_ERROR
    return f"{round_label(later_group)}申請學生的排名必須在{round_label(earlier_group)}之後"


def find_group_order_violation(apps_in_rank_order: Iterable[Any]) -> Optional[str]:
    """First group-order violation in a ranking, or None when the order is valid.

    ``apps_in_rank_order`` are the applications of the non-rejected rows, sorted by
    their (new) rank position.
    """
    highest_group: Optional[int] = None
    for app in apps_in_rank_order:
        group = ranking_group(app)
        if highest_group is not None and group < highest_group:
            return round_order_error(group, highest_group)
        highest_group = group if highest_group is None else max(highest_group, group)
    return None

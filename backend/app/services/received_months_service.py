"""
Received-months calculation service.

Shared source of truth for "已領月份數" used by:
- PhD eligibility plugin (36-month cap check)
- Manual distribution panel (display column)

Counts months a student has received under a scholarship_configuration
across all sub_types (nstc, moe_1w, moe_2w combined). Each distinct
(academic_year, period_label, sub_type) roster contributes months based
on its roster_cycle:

    MONTHLY       -> 1 month
    SEMI_YEARLY   -> 6 months
    YEARLY        -> 12 months

Only rosters with PaymentRosterItem.is_included=True are counted.

See docs/received-months-calculation.md for full specification.
"""

from typing import Iterable

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterCycle

_CYCLE_MONTHS: dict[RosterCycle, int] = {
    RosterCycle.MONTHLY: 1,
    RosterCycle.SEMI_YEARLY: 6,
    RosterCycle.YEARLY: 12,
}


def _months_for_cycle(cycle: RosterCycle) -> int:
    return _CYCLE_MONTHS.get(cycle, 1)


def _single_stmt(student_nycu_id: str, scholarship_config_id: int) -> Select:
    return (
        select(PaymentRoster.roster_cycle, func.count(PaymentRosterItem.id))
        .join(PaymentRosterItem, PaymentRosterItem.roster_id == PaymentRoster.id)
        .where(
            and_(
                PaymentRoster.scholarship_configuration_id == scholarship_config_id,
                PaymentRosterItem.student_id_number == student_nycu_id,
                PaymentRosterItem.is_included.is_(True),
            )
        )
        .group_by(PaymentRoster.roster_cycle)
    )


def _bulk_stmt(student_nycu_ids: list[str], scholarship_config_id: int) -> Select:
    return (
        select(
            PaymentRosterItem.student_id_number,
            PaymentRoster.roster_cycle,
            func.count(PaymentRosterItem.id),
        )
        .join(PaymentRoster, PaymentRoster.id == PaymentRosterItem.roster_id)
        .where(
            and_(
                PaymentRoster.scholarship_configuration_id == scholarship_config_id,
                PaymentRosterItem.student_id_number.in_(student_nycu_ids),
                PaymentRosterItem.is_included.is_(True),
            )
        )
        .group_by(PaymentRosterItem.student_id_number, PaymentRoster.roster_cycle)
    )


def calculate_received_months(
    db: Session, student_nycu_id: str, scholarship_config_id: int
) -> int:
    """
    Total months a single student has received under the given scholarship config.

    Returns 0 when the student has no included roster items under this config.
    """
    total = 0
    for cycle, count in db.execute(_single_stmt(student_nycu_id, scholarship_config_id)).all():
        total += _months_for_cycle(cycle) * count
    return total


def calculate_received_months_bulk(
    db: Session, student_nycu_ids: Iterable[str], scholarship_config_id: int
) -> dict[str, int]:
    """
    Bulk version for callers listing many students at once (e.g. distribution panel).

    Returns a dict from student_nycu_id to month count. Students with no
    matching items are included with value 0.
    """
    ids = list(student_nycu_ids)
    result: dict[str, int] = {sid: 0 for sid in ids}
    if not ids:
        return result

    for student_id, cycle, count in db.execute(_bulk_stmt(ids, scholarship_config_id)).all():
        result[student_id] = result.get(student_id, 0) + _months_for_cycle(cycle) * count
    return result


async def calculate_received_months_bulk_async(
    db: AsyncSession, student_nycu_ids: Iterable[str], scholarship_config_id: int
) -> dict[str, int]:
    """Async variant for callers using AsyncSession (e.g. FastAPI endpoints)."""
    ids = list(student_nycu_ids)
    result: dict[str, int] = {sid: 0 for sid in ids}
    if not ids:
        return result

    rows = (await db.execute(_bulk_stmt(ids, scholarship_config_id))).all()
    for student_id, cycle, count in rows:
        result[student_id] = result.get(student_id, 0) + _months_for_cycle(cycle) * count
    return result

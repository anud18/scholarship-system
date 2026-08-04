"""
Received-months calculation service.

Shared source of truth for "已領月份數" used by:
- PhD eligibility plugin (36-month cap check)
- Manual distribution panel (display column)
- Student scholarship history page (學生領獎紀錄查詢)

已領月份數 has two halves that are ADDED together:

    已領月份數 = 匯入月份數 + 系統月份數

匯入月份數 is a lifetime baseline imported from 國科會's
「獲獎生已領月份統計表」, stored in student_received_month_records and keyed by
(學號, scholarship_type). 系統月份數 is computed live from this system's own
rosters, below.

Addition is only correct because the imported file records months paid BEFORE
this system took over roster generation — the two never cover the same month.
See docs/adr/0001-received-months-are-additive.md.

The system half counts months under a scholarship_configuration across all
sub_types (nstc, moe_1w, moe_2w combined). Each distinct
(academic_year, period_label, sub_type) roster contributes months based
on its roster_cycle:

    MONTHLY       -> 1 month
    SEMI_YEARLY   -> 6 months
    YEARLY        -> 12 months

Only rosters with PaymentRosterItem.is_included=True are counted.

Students are matched on PaymentRosterItem.student_number (學號 / std_stdcode),
the canonical student identifier. NOT student_id_number — that column holds the
national ID (身分證字號 / std_pid) for the Excel payment column and is unsuitable
for identity matching (e.g. foreign students may lack a national ID).

See docs/received-months-calculation.md for full specification.
"""

from typing import Iterable

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterCycle
from app.models.received_months import StudentReceivedMonthRecord

_CYCLE_MONTHS: dict[RosterCycle, int] = {
    RosterCycle.MONTHLY: 1,
    RosterCycle.SEMI_YEARLY: 6,
    RosterCycle.YEARLY: 12,
}


def _months_for_cycle(cycle: RosterCycle) -> int:
    return _CYCLE_MONTHS.get(cycle, 1)


def months_for_cycle_value(cycle_value: str) -> int:
    """Months contributed by one roster, from its cycle's string value.

    For callers holding the serialised cycle ("monthly") rather than the enum
    member — keeps the 1/6/12 mapping defined in exactly one place.
    """
    try:
        return _months_for_cycle(RosterCycle(cycle_value))
    except ValueError:
        return 1


def _single_stmt(student_nycu_id: str, scholarship_config_id: int) -> Select:
    return (
        select(PaymentRoster.roster_cycle, func.count(PaymentRosterItem.id))
        .join(PaymentRosterItem, PaymentRosterItem.roster_id == PaymentRoster.id)
        .where(
            and_(
                PaymentRoster.scholarship_configuration_id == scholarship_config_id,
                PaymentRosterItem.student_number == student_nycu_id,
                PaymentRosterItem.is_included.is_(True),
            )
        )
        .group_by(PaymentRoster.roster_cycle)
    )


def _bulk_stmt(student_nycu_ids: list[str], scholarship_config_id: int) -> Select:
    return (
        select(
            PaymentRosterItem.student_number,
            PaymentRoster.roster_cycle,
            func.count(PaymentRosterItem.id),
        )
        .join(PaymentRoster, PaymentRoster.id == PaymentRosterItem.roster_id)
        .where(
            and_(
                PaymentRoster.scholarship_configuration_id == scholarship_config_id,
                PaymentRosterItem.student_number.in_(student_nycu_ids),
                PaymentRosterItem.is_included.is_(True),
            )
        )
        .group_by(PaymentRosterItem.student_number, PaymentRoster.roster_cycle)
    )


def calculate_received_months(db: Session, student_nycu_id: str, scholarship_config_id: int) -> int:
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


# --------------------------------------------------------------------------
# 匯入月份數 — the lifetime baseline imported from 國科會's file.
# --------------------------------------------------------------------------


def _imported_stmt(student_nycu_ids: list[str], scholarship_type_id: int) -> Select:
    return select(StudentReceivedMonthRecord.student_number, StudentReceivedMonthRecord.months).where(
        and_(
            StudentReceivedMonthRecord.scholarship_type_id == scholarship_type_id,
            StudentReceivedMonthRecord.student_number.in_(student_nycu_ids),
        )
    )


def get_imported_months(db: Session, student_nycu_id: str, scholarship_type_id: int) -> int:
    """Imported baseline for one student. 0 when nothing has been imported."""
    row = db.execute(_imported_stmt([student_nycu_id], scholarship_type_id)).first()
    return int(row[1]) if row and row[1] is not None else 0


def get_imported_months_bulk(db: Session, student_nycu_ids: Iterable[str], scholarship_type_id: int) -> dict[str, int]:
    """Bulk imported baselines, keyed by 學號. Missing students map to 0."""
    ids = list(student_nycu_ids)
    result: dict[str, int] = {sid: 0 for sid in ids}
    if not ids:
        return result
    for student_id, months in db.execute(_imported_stmt(ids, scholarship_type_id)).all():
        result[student_id] = int(months or 0)
    return result


async def get_imported_months_bulk_async(
    db: AsyncSession, student_nycu_ids: Iterable[str], scholarship_type_id: int
) -> dict[str, int]:
    """Async variant of :func:`get_imported_months_bulk`."""
    ids = list(student_nycu_ids)
    result: dict[str, int] = {sid: 0 for sid in ids}
    if not ids:
        return result
    rows = (await db.execute(_imported_stmt(ids, scholarship_type_id))).all()
    for student_id, months in rows:
        result[student_id] = int(months or 0)
    return result


# --------------------------------------------------------------------------
# The composed number every caller should read.
# --------------------------------------------------------------------------


def calculate_total_received_months(
    db: Session, student_nycu_id: str, scholarship_config_id: int, scholarship_type_id: int
) -> int:
    """已領月份數 = 匯入月份數 (lifetime) + 系統月份數 (this config's year)."""
    return get_imported_months(db, student_nycu_id, scholarship_type_id) + calculate_received_months(
        db, student_nycu_id, scholarship_config_id
    )

from collections import defaultdict
from typing import Any, Dict, List, Mapping, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.application import Application
from app.models.payment_roster import PaymentRoster, PaymentRosterItem
from app.models.roster_audit import RosterAuditAction, RosterAuditLog
from app.models.user import User
from app.services.staff_form_edit import (
    ROSTER_ACCOUNT_ACTIONS,
    RosterAccountAction,
    RosterAccountSync,
    RosterItemRef,
)
from app.utils.bank_account_fields import submitted_bank_account

ROSTER_SYNC_SOURCE = "staff_form_edit"


async def sync_roster_bank_account(
    db: AsyncSession,
    application: Application,
    previous_form_data: Optional[Mapping[str, Any]],
    actor: User,
    client_ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> RosterAccountSync:
    """Point the application's 造冊 items at the account its edited form now holds.

    Adds the item updates and their RosterAuditLog rows to the caller's
    transaction; the caller commits.
    """
    account = submitted_bank_account(application.submitted_form_data)
    if account == submitted_bank_account(previous_form_data):
        return RosterAccountSync()

    refs: Dict[RosterAccountAction, List[RosterItemRef]] = defaultdict(list)
    for item in await _lock_roster_items(db, application.id):
        if (item.bank_account or "") == account:
            continue
        action = ROSTER_ACCOUNT_ACTIONS[item.roster.status]
        refs[action].append(RosterItemRef(item.roster_id, item.roster.roster_code, item.id))
        if action is RosterAccountAction.SYNCED:
            db.add(_point_item_at(item, account, application, actor, client_ip, user_agent))
    return RosterAccountSync(items={action: tuple(found) for action, found in refs.items()})


async def _lock_roster_items(db: AsyncSession, application_id: int) -> Sequence[PaymentRosterItem]:
    # Lock the rosters first, in id order: 重新生成 deletes and re-inserts a
    # roster's items while holding its row, and a single locking query would
    # keep the snapshot it took before waiting, missing the re-inserted rows.
    holding = select(PaymentRosterItem.roster_id).where(PaymentRosterItem.application_id == application_id)
    await db.execute(
        select(PaymentRoster.id).where(PaymentRoster.id.in_(holding)).order_by(PaymentRoster.id).with_for_update()
    )
    result = await db.execute(
        select(PaymentRosterItem)
        .where(PaymentRosterItem.application_id == application_id)
        .options(joinedload(PaymentRosterItem.roster))
        .order_by(PaymentRosterItem.id)
        .with_for_update(of=PaymentRosterItem)
    )
    return result.scalars().all()


def _point_item_at(
    item: PaymentRosterItem,
    account: str,
    application: Application,
    actor: User,
    client_ip: Optional[str],
    user_agent: Optional[str],
) -> RosterAuditLog:
    """Swap in the new account and drop the bank review that described the old one; returns the audit row."""
    old_values = {
        "bank_account": item.bank_account,
        "bank_account_number_status": item.bank_account_number_status,
        "bank_verification_details": item.bank_verification_details,
    }
    item.bank_account = account
    item.bank_account_number_status = None
    item.bank_verification_details = None
    item.roster.excel_stale = True
    return RosterAuditLog.for_item(
        roster_id=item.roster_id,
        action=RosterAuditAction.ITEM_UPDATE,
        item=item,
        user_id=actor.id,
        user=actor,
        source=ROSTER_SYNC_SOURCE,
        reason=f"申請 {application.app_id} 的郵局帳號經審核人員修改",
        student_id=(application.student_data or {}).get("std_stdcode"),
        client_ip=client_ip,
        user_agent=user_agent,
        old_values=old_values,
        new_values={"bank_account": account, "bank_account_number_status": None, "bank_verification_details": None},
    )

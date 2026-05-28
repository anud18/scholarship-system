"""backfill payment_roster_items.student_id_number with decrypted std_pid

Historically student_id_number stored std_stdcode (student number) instead
of std_pid (national ID).  The Excel payment template column is 身分證字號 so
this field must hold the real national ID.

This migration iterates existing rows, loads the decrypted std_pid from
applications.student_data (StudentDataJSON ORM TypeDecorator handles
decryption), and writes it into student_id_number.

Revision ID: backfill_roster_nat_id_001
Revises: merge_renewal_main_001
"""

from __future__ import annotations

import logging
from typing import Union

from alembic import op
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger("alembic.runtime.migration")

revision: str = "backfill_roster_nat_id_001"
down_revision: Union[str, None] = "merge_renewal_main_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        # Import models — TypeDecorators fire during ORM load/flush
        from app.models.payment_roster import PaymentRosterItem
        from app.models.application import Application

        row_count = session.execute(text("SELECT COUNT(*) FROM payment_roster_items")).scalar()
        logger.info(f"Backfilling national ID for {row_count} payment_roster_items")

        items = session.query(PaymentRosterItem).options(joinedload(PaymentRosterItem.application)).all()
        updated = 0
        skipped_no_app = 0
        skipped_no_pid = 0

        for item in items:
            app = item.application
            if not app or not app.student_data:
                skipped_no_app += 1
                continue

            std_pid = app.student_data.get("std_pid", "")
            if not std_pid:
                skipped_no_pid += 1
                continue

            if item.student_id_number != std_pid:
                item.student_id_number = std_pid
                updated += 1

        session.flush()
        logger.info(
            f"Backfill complete: updated={updated}, "
            f"skipped_no_app={skipped_no_app}, skipped_no_pid={skipped_no_pid}"
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    # No safe reverse: we don't know which rows held std_stdcode vs std_pid.
    pass

"""add payment_roster_items.student_number (學號) and backfill from std_stdcode

PaymentRosterItem.student_id_number was repurposed to hold the national ID
(身分證字號 / std_pid) for the Excel payment column (see backfill_roster_nat_id_001),
which overwrote the 學號 it used to carry. But cross-roster student matching —
the received-months cumulative count (已領月份數), the PhD 36-month cap, and the
scholarship-history lookup — keys off the 學號 (std_stdcode), the system's
canonical student identifier.

This migration adds a dedicated student_number (學號) snapshot column and
backfills it from applications.student_data->>'std_stdcode'. It iterates rows
via the ORM so the StudentDataJSON TypeDecorator decrypts student_data, mirroring
backfill_roster_nat_id_001.

Revision ID: add_roster_student_number_001
Revises: merge_20260608_sq_audit
"""

from __future__ import annotations

import logging
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session, joinedload

logger = logging.getLogger("alembic.runtime.migration")

revision: str = "add_roster_student_number_001"
down_revision: Union[str, None] = "merge_20260608_sq_audit"
branch_labels = None
depends_on = None

_TABLE = "payment_roster_items"
_COLUMN = "student_number"
_INDEX = "ix_payment_roster_items_student_number"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN not in existing_columns:
        op.add_column(_TABLE, sa.Column(_COLUMN, sa.String(length=20), nullable=True))

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _INDEX not in existing_indexes:
        op.create_index(_INDEX, _TABLE, [_COLUMN])

    _backfill(bind)


def _backfill(bind) -> None:
    """Populate student_number from each item's application std_stdcode."""
    session = Session(bind=bind)
    try:
        # Import models — TypeDecorators fire during ORM load (decrypt student_data).
        from app.models.application import Application  # noqa: F401
        from app.models.payment_roster import PaymentRosterItem

        items = session.query(PaymentRosterItem).options(joinedload(PaymentRosterItem.application)).all()
        updated = 0
        skipped_no_app = 0
        skipped_no_stdcode = 0

        for item in items:
            app = item.application
            if not app or not app.student_data:
                skipped_no_app += 1
                continue

            std_stdcode = app.student_data.get("std_stdcode", "")
            if not std_stdcode:
                skipped_no_stdcode += 1
                continue

            if item.student_number != std_stdcode:
                item.student_number = std_stdcode
                updated += 1

        session.flush()
        logger.info(
            f"Backfill student_number complete: updated={updated}, "
            f"skipped_no_app={skipped_no_app}, skipped_no_stdcode={skipped_no_stdcode}"
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_indexes = {ix["name"] for ix in inspector.get_indexes(_TABLE)}
    if _INDEX in existing_indexes:
        op.drop_index(_INDEX, table_name=_TABLE)

    existing_columns = {c["name"] for c in inspector.get_columns(_TABLE)}
    if _COLUMN in existing_columns:
        op.drop_column(_TABLE, _COLUMN)

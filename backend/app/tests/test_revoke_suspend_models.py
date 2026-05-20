"""Pin: applications + payment_rosters expose the revoke/suspend metadata
columns at the ORM layer so service code can read/write them."""

from app.models.application import Application
from app.models.payment_roster import PaymentRoster


def test_application_has_revoke_metadata_columns():
    cols = {c.name for c in Application.__table__.columns}
    assert {"revoked_at", "revoked_by", "revoke_reason"}.issubset(cols)


def test_application_has_suspend_metadata_columns():
    cols = {c.name for c in Application.__table__.columns}
    assert {"suspended_at", "suspended_by", "suspend_reason"}.issubset(cols)


def test_payment_roster_has_excel_stale_column():
    cols = {c.name for c in PaymentRoster.__table__.columns}
    assert "excel_stale" in cols

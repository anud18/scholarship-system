"""cycle-status 造冊列表 row builder (`_roster_period_entry`).

Every cycle branch (monthly / semi-yearly / yearly / distribution-generated)
goes through this one helper, so a renewal-bearing roster generated from the
matrix carries the same shape as a scheduled one: 造冊期間 dates plus the
included-續領 count the list uses to mark it.
"""

from datetime import datetime
from types import SimpleNamespace

from app.api.v1.endpoints.payment_rosters import RENEWAL_IDENTITY_SUFFIX, _roster_period_entry
from app.models.payment_roster import RosterStatus


def _roster(status=RosterStatus.COMPLETED, **overrides):
    base = dict(
        id=7,
        roster_code="ROSTER-115-nstc-phd_114-phd_115",
        status=status,
        excel_stale=False,
        sub_type="nstc",
        allocation_year=114,
        project_number="114R000001",
        completed_at=datetime(2026, 9, 1, 8, 0, 0),
        total_amount=80000,
        qualified_count=2,
        notes=None,
    )
    return SimpleNamespace(**{**base, **overrides})


PERIOD_DATES = {"start_date": datetime(2026, 9, 1), "end_date": datetime(2027, 8, 31)}


def test_completed_entry_carries_dates_and_renewal_count():
    entry = _roster_period_entry(_roster(), "115", PERIOD_DATES, renewal_count=2)

    assert entry["label"] == "115"
    assert entry["roster_id"] == 7
    assert entry["status"] == "completed"
    assert entry["roster_status"] == "completed"
    assert entry["sub_type"] == "nstc"
    assert entry["allocation_year"] == 114
    assert entry["project_number"] == "114R000001"
    assert entry["renewal_count"] == 2
    assert entry["period_start_date"] == "2026-09-01T00:00:00"
    assert entry["period_end_date"] == "2027-08-31T00:00:00"
    assert entry["total_amount"] == 80000.0
    assert entry["qualified_count"] == 2


def test_locked_collapses_to_completed_but_keeps_roster_status():
    entry = _roster_period_entry(_roster(RosterStatus.LOCKED), "115", PERIOD_DATES, 0)
    assert entry["status"] == "completed"
    assert entry["roster_status"] == "locked"
    assert entry["renewal_count"] == 0


def test_failed_entry_surfaces_notes_as_error_message():
    entry = _roster_period_entry(_roster(RosterStatus.FAILED, notes="boom"), "115", PERIOD_DATES, 0)
    assert entry["status"] == "failed"
    assert entry["error_message"] == "boom"


def test_processing_and_draft_statuses():
    assert _roster_period_entry(_roster(RosterStatus.PROCESSING), "115", None, 0)["status"] == "processing"
    assert _roster_period_entry(_roster(RosterStatus.DRAFT), "115", None, 0)["status"] == "draft"


def test_missing_period_dates_omits_date_keys_instead_of_crashing():
    entry = _roster_period_entry(_roster(), "115", None, 0)
    assert "period_start_date" not in entry
    assert "period_end_date" not in entry


def test_identity_suffix_matches_roster_item_snapshot_format():
    """_create_roster_item writes f"{year}續領"; the count query LIKEs on this suffix."""
    assert f"115{RENEWAL_IDENTITY_SUFFIX}" == "115續領"

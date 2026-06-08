"""Regression tests for the 造冊 distribution-list display year.

The 查看名單 student table renders "{allocation_year}年 {allocated_sub_type}"
per row. PaymentRosterItem.allocation_year is only snapshotted by the manual
DISTRIBUTION path (where it records the consumed/borrowed prior-year quota);
the monthly/legacy generation path leaves it NULL. Without a fallback those
rows show no year at all.

`_roster_item_dict_with_display_year` (app/api/v1/endpoints/payment_rosters.py)
resolves the displayed year: the per-item snapshot when set, else the roster's
own academic_year — so every row shows which year's quota it draws from, while
shared-quota rows keep their explicit borrowed year.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.api.v1.endpoints.payment_rosters import _roster_item_dict_with_display_year
from app.models.payment_roster import StudentVerificationStatus


def _item(**overrides):
    """Duck-typed object with every field app.schemas.roster.RosterItemResponse
    requires (from_attributes round-trip)."""
    base = dict(
        id=1,
        roster_id=1,
        application_id=1,
        student_id_number="A123456789",
        student_name="王小明",
        scholarship_amount=Decimal("40000"),
        verification_status=StudentVerificationStatus.VERIFIED,
        is_included=True,
        created_at=datetime(2026, 6, 8, tzinfo=timezone.utc),
        allocated_sub_type="nstc",
        allocation_year=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_falls_back_to_roster_academic_year_when_item_year_null():
    # Monthly/legacy roster: item has no allocation_year snapshot, so the row
    # must show the roster's own academic_year (114年) instead of nothing.
    out = _roster_item_dict_with_display_year(_item(allocation_year=None), SimpleNamespace(academic_year=114))
    assert out["allocation_year"] == 114
    assert out["allocated_sub_type"] == "nstc"


def test_keeps_borrowed_snapshot_over_roster_year():
    # Shared quota: a 115 roster item consuming 114's quota snapshots
    # allocation_year=114; the fallback must NOT overwrite it with 115.
    out = _roster_item_dict_with_display_year(_item(allocation_year=114), SimpleNamespace(academic_year=115))
    assert out["allocation_year"] == 114

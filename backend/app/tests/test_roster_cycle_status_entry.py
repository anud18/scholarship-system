"""cycle-status 造冊列表 row builder (`_roster_period_entry`).

Every cycle branch (monthly / semi-yearly / yearly / distribution-generated)
goes through this one helper, so a renewal-bearing roster generated from the
matrix carries the same shape as a scheduled one: 造冊期間 dates plus the
included-續領 count the list uses to mark it.
"""

from datetime import datetime
from types import SimpleNamespace

from app.api.v1.endpoints.payment_rosters import (
    _period_label_year,
    _period_specs,
    _roster_period_entry,
    _segment_fields,
    _segment_years,
)
from app.models.payment_roster import AWARD_TERM_YEARS, RosterStatus


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
    assert _roster_period_entry(_roster(RosterStatus.PROCESSING), "115", PERIOD_DATES, 0)["status"] == "processing"
    assert _roster_period_entry(_roster(RosterStatus.DRAFT), "115", PERIOD_DATES, 0)["status"] == "draft"


def test_segment_years_extends_to_latest_payable_year():
    """A 補發 recipient still drawing on the slots in 118 extends the list to 118."""
    assert _segment_years(114, AWARD_TERM_YEARS, {}, latest_payable_year=118) == [114, 115, 116, 117, 118]
    assert _segment_years(114, AWARD_TERM_YEARS, {}, latest_payable_year=113) == [114, 115, 116]


# ─── year segments: 第一年新申請 + 兩年續領，全在同一個配置底下 ─────────────


def test_segment_years_fixed_term_from_config_year():
    assert _segment_years(114, AWARD_TERM_YEARS, {}) == [114, 115, 116]


def test_segment_years_single_year_when_renewal_disabled():
    assert _segment_years(114, 1, {}) == [114]


def test_segment_years_extends_to_later_rosters_but_not_earlier():
    """A 補發 recipient's renewal can sit past the cohort's third year; a stray
    earlier-labelled roster does not add a segment before the config year."""
    groups = {"117-09": [object()], "113": [object()], "not-a-year": [object()]}
    assert _segment_years(114, AWARD_TERM_YEARS, groups) == [114, 115, 116, 117]


def test_segment_fields_mark_first_year_as_new_and_later_as_renewal():
    assert _segment_fields(114, 114) == {"academic_year": 114, "year_offset": 0, "segment": "新申請"}
    assert _segment_fields(116, 114) == {"academic_year": 116, "year_offset": 2, "segment": "續領"}


def test_period_label_year_parses_leading_roc_year():
    assert _period_label_year("115-09") == 115
    assert _period_label_year("115") == 115
    assert _period_label_year("H1") is None


def test_monthly_specs_for_yearly_scholarship_run_september_to_august():
    specs = _period_specs("monthly", 115, True, None)
    assert [s["label"] for s in specs][:4] == ["115-09", "115-10", "115-11", "115-12"]
    assert [s["label"] for s in specs][-1] == "115-08"
    assert all(s["semester_filter"] is None for s in specs)
    assert specs[0]["extra"] == {"western_date": "2026-09", "display_label": "115-09 (2026年9月)"}
    assert specs[-1]["extra"]["western_date"] == "2027-08"


def test_monthly_specs_for_semester_scholarship_map_months_to_semesters():
    specs = _period_specs("monthly", 115, False, "first")
    assert [s["label"] for s in specs][:2] == ["115-01", "115-02"]
    by_label = {s["label"]: s["semester_filter"] for s in specs}
    assert by_label["115-01"] == "first"
    assert by_label["115-03"] == "second"
    assert by_label["115-09"] == "first"


def test_semi_yearly_and_yearly_specs():
    semi = _period_specs("semi_yearly", 116, True, None)
    assert [(s["label"], s["semester_filter"]) for s in semi] == [("116-H1", None), ("116-H2", None)]
    semi_sem = _period_specs("semi_yearly", 116, False, "first")
    assert [s["semester_filter"] for s in semi_sem] == ["first", "second"]
    assert _period_specs("yearly", 116, True, None) == [{"label": "116", "semester_filter": None, "extra": {}}]

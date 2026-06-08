"""
Pin test: the roster display-year snapshot lives on PaymentRoster /
PaymentRosterItem.allocation_year and is KEPT (spec §8 — denormalized snapshot
= consumed config's academic_year). The excel export and student-history
readers must continue to read `item.allocation_year` off a roster ITEM, never
off a CollegeRankingItem. This guards against an over-eager drop of the kept
snapshot column when CollegeRankingItem.allocation_year is removed.
"""

from pathlib import Path

SERVICES = Path(__file__).resolve().parents[2] / "app" / "services"
EXCEL = SERVICES / "excel_export_service.py"
HISTORY = SERVICES / "student_scholarship_history_service.py"


def test_excel_export_reads_item_allocation_year_snapshot():
    source = EXCEL.read_text(encoding="utf-8")
    # Both the _format_allocation_display helper and the remarks builder read
    # the kept PaymentRosterItem snapshot.
    assert "item.allocation_year" in source


def test_student_history_reads_item_allocation_year_snapshot():
    source = HISTORY.read_text(encoding="utf-8")
    assert "allocation_year=item.allocation_year" in source

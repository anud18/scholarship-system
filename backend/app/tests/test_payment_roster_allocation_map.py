"""
Source-invariant test: after the shared-pool migration `CollegeRankingItem`
no longer has an `allocation_year` column, so the payment-roster
`allocation_map` builder must read `allocation_config_id`. A stale
`ri.allocation_year` read would raise AttributeError at request time
(the roster-validation endpoint builds this map for every allocated item).
"""

from pathlib import Path

ENDPOINT = Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints" / "payment_rosters.py"


def test_allocation_map_reads_allocation_config_id_not_year():
    source = ENDPOINT.read_text(encoding="utf-8")
    # The dropped column must not be read off a CollegeRankingItem row alias.
    assert "ri.allocation_year" not in source
    # The map must now carry the consumed-config id.
    assert "ri.allocation_config_id" in source
    assert '"allocation_config_id": ri.allocation_config_id' in source


def test_student_info_exposes_allocation_config_id():
    source = ENDPOINT.read_text(encoding="utf-8")
    assert 'allocation_map.get(application.id, {}).get("allocation_config_id")' in source
    assert 'allocation_map.get(application.id, {}).get("allocation_year")' not in source

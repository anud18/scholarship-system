"""Source-invariant guard: preview_roster_students must NOT self-select a single
ranking. It must defer ranking resolution to
RosterService._get_eligible_applications, which (after the all-college fix)
aggregates ALL executed rankings — so the preview matches what generate_roster
produces. Same technique as test_payment_roster_allocation_map.py, used because
preview_roster_students opens its own SessionLocal and is awkward to drive
through the DI test client. Behavioural coverage lives in
test_roster_matrix_aggregate_all_colleges.py."""

from pathlib import Path

ENDPOINT = Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints" / "payment_rosters.py"


def test_preview_does_not_self_select_single_ranking():
    source = ENDPOINT.read_text(encoding="utf-8")
    # The divergent single-ranking auto-detect (ordered by created_at) must be gone.
    assert "CollegeRanking.created_at.desc()" not in source


def test_preview_delegates_ranking_resolution_to_service():
    source = ENDPOINT.read_text(encoding="utf-8")
    # preview still hands ranking_id (None when unspecified) to the shared selector.
    assert "_get_eligible_applications(" in source

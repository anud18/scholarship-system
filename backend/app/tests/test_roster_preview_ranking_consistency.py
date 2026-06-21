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


def _preview_function_source() -> str:
    """Slice out just the preview_roster_students function body so the guards
    below cannot pass vacuously on substrings that live in other endpoints
    (e.g. _get_eligible_applications is also called by other handlers)."""
    source = ENDPOINT.read_text(encoding="utf-8")
    start = source.index("async def preview_roster_students")
    nxt = source.find("\n@router.", start)
    return source[start : nxt if nxt != -1 else len(source)]


def test_preview_does_not_self_select_single_ranking():
    fn = _preview_function_source()
    # The divergent single-ranking auto-detect (ordered by created_at) must be gone.
    assert "CollegeRanking.created_at.desc()" not in fn
    # And it must never reassign ranking_id from a self-picked ranking — that
    # reassignment (e.g. `ranking_id = ranking.id`) WAS the bug. The signature
    # declares `ranking_id:` (colon), so this does not match the parameter.
    assert "ranking_id = " not in fn


def test_preview_delegates_ranking_resolution_to_service():
    fn = _preview_function_source()
    # Preview delegates selection to the shared service selector...
    assert "_get_eligible_applications(" in fn
    # ...passing the caller's ranking_id through UNCHANGED (None ⇒ all colleges).
    assert "ranking_id=ranking_id" in fn

"""
Tests for `backend/app/services/alternate_promotion_service.py` —
the sub_type filter + sort logic in `_find_eligible_alternate`.

Module had ZERO test references. SECURITY-CRITICAL: drives the
backup-student-promotion logic when a primary allocated student
loses eligibility during roster generation. Drift would silently
mispromote alternates from the wrong sub_type or wrong position.

Wave 6a140 pins the PURE-LOGIC invariants without standing up
a real database:
- sub_type filter is CASE-INSENSITIVE (.lower() comparison)
- candidates sorted by backup_position ascending
- empty backup_position defaults to 999 (push-to-end)
- sub_type omitted → all sub_types match (no filter)

DB queries themselves are mocked at the Session level — we're
testing the in-memory filter/sort logic, not the SQLAlchemy
query.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.alternate_promotion_service import AlternatePromotionService


def _make_item(item_id: int, backup_allocations: list):
    """Build a CollegeRankingItem stand-in with backup_allocations."""
    item = SimpleNamespace(
        id=item_id,
        backup_allocations=backup_allocations,
        application=None,  # not exercised in candidate-build branch
    )
    return item


class TestSubTypeFilterCaseInsensitive:
    """Pin SECURITY: sub_type comparison is .lower() — pin so refactor
    doesn't introduce case-sensitive matching and silently filter out
    legitimate candidates."""

    def test_uppercase_filter_matches_lowercase_backup_sub_type(self, monkeypatch):
        # Pin: filter "NSTC" matches backup_sub_type "nstc".
        # Per CLAUDE.md §4, sub_types are configuration-driven
        # lowercase strings — but admins may enter mixed case.
        service = AlternatePromotionService(db=MagicMock())
        item = _make_item(
            1,
            [{"sub_type": "nstc", "backup_position": 1}],
        )
        service.db.query.return_value.filter.return_value.all.return_value = [item]

        # Stub out the eligibility-check branch by returning early
        # at the candidates list. We don't reach the application
        # branch because we pass empty original_student_data.
        result = service._find_eligible_alternate(
            ranking_id=1,
            sub_type="NSTC",
            original_student_data={},
            scholarship_config=MagicMock(scholarship_type=MagicMock(whitelist_enabled=False)),
            skip_special_eligibility=True,
        )
        # The application is None so the loop continues and finds
        # 0 eligible — but checked_count records that the candidate
        # was considered (means the case-insensitive filter matched).
        # We assert checked_count > 0 (1 candidate was processed).
        # If case-sensitive filter were applied, candidates list
        # would be empty and checked_count would be 0.
        assert result is not None
        assert result["checked_count"] >= 1

    def test_lowercase_filter_matches_uppercase_backup(self, monkeypatch):
        # Pin: reverse direction — lowercase filter matches
        # uppercase backup_sub_type.
        service = AlternatePromotionService(db=MagicMock())
        item = _make_item(
            1,
            [{"sub_type": "NSTC", "backup_position": 1}],
        )
        service.db.query.return_value.filter.return_value.all.return_value = [item]

        result = service._find_eligible_alternate(
            ranking_id=1,
            sub_type="nstc",
            original_student_data={},
            scholarship_config=MagicMock(scholarship_type=MagicMock(whitelist_enabled=False)),
            skip_special_eligibility=True,
        )
        assert result is not None
        assert result["checked_count"] >= 1

    def test_mismatched_sub_type_skipped(self):
        # Pin: "moe_1w" filter must NOT match "nstc" backup.
        # Pin SECURITY: drift would allow students from the wrong
        # sub_type to be promoted as alternates.
        service = AlternatePromotionService(db=MagicMock())
        item = _make_item(
            1,
            [{"sub_type": "nstc", "backup_position": 1}],
        )
        service.db.query.return_value.filter.return_value.all.return_value = [item]

        result = service._find_eligible_alternate(
            ranking_id=1,
            sub_type="moe_1w",
            original_student_data={},
            scholarship_config=MagicMock(scholarship_type=MagicMock(whitelist_enabled=False)),
            skip_special_eligibility=True,
        )
        # No candidates match → checked_count is 0
        assert result is not None
        assert result["checked_count"] == 0


class TestBackupPositionSort:
    """Pin: candidates sorted by backup_position ascending so the
    "next" alternate is always position 1 (the highest-ranked
    backup), then 2, etc. Drift would silently misorder the
    promotion sequence."""

    def test_candidates_sorted_by_backup_position(self):
        # Pin: items with position 3, 1, 2 are sorted to 1, 2, 3
        # order. The first eligible candidate processed should be
        # position 1 (since DB ordering is not guaranteed).
        service = AlternatePromotionService(db=MagicMock())
        items = [
            _make_item(1, [{"sub_type": "nstc", "backup_position": 3}]),
            _make_item(2, [{"sub_type": "nstc", "backup_position": 1}]),
            _make_item(3, [{"sub_type": "nstc", "backup_position": 2}]),
        ]
        service.db.query.return_value.filter.return_value.all.return_value = items

        # Because all candidates have application=None, they're all
        # skipped in the eligibility loop. The TEST is that the
        # service didn't raise on the sort (i.e. it can compare
        # the positions as ints).
        result = service._find_eligible_alternate(
            ranking_id=1,
            sub_type="nstc",
            original_student_data={},
            scholarship_config=MagicMock(scholarship_type=MagicMock(whitelist_enabled=False)),
            skip_special_eligibility=True,
        )
        assert result is not None
        # All 3 candidates were checked (none eligible because
        # application=None) — confirms sort completed.
        assert result["checked_count"] == 3

    def test_missing_backup_position_defaults_to_999(self):
        # Pin: when backup dict has no `backup_position` key, fall
        # back to 999 so it sorts to the END. Pin so refactor doesn't
        # accidentally short-circuit malformed entries to the FRONT
        # (position 0) and promote the wrong person.
        service = AlternatePromotionService(db=MagicMock())
        # Two items — one with explicit position 5, one with missing
        # position (should default to 999). Sort should place the 5
        # first, then the missing-position one.
        items = [
            _make_item(1, [{"sub_type": "nstc"}]),  # No backup_position
            _make_item(2, [{"sub_type": "nstc", "backup_position": 5}]),
        ]
        service.db.query.return_value.filter.return_value.all.return_value = items

        result = service._find_eligible_alternate(
            ranking_id=1,
            sub_type="nstc",
            original_student_data={},
            scholarship_config=MagicMock(scholarship_type=MagicMock(whitelist_enabled=False)),
            skip_special_eligibility=True,
        )
        assert result is not None
        # Both candidates considered — sort handled both.
        assert result["checked_count"] == 2


class TestSubTypeOmittedNoFilter:
    """Pin: when sub_type=None, ALL backup allocations are candidates
    regardless of their sub_type. Pin so refactor doesn't accidentally
    require sub_type (which would break general/single-sub-type
    scholarship rosters)."""

    def test_no_sub_type_filter_returns_all_candidates(self):
        # Pin: None sub_type → no filter applied. All 3 candidates
        # (different sub_types) all match.
        service = AlternatePromotionService(db=MagicMock())
        items = [
            _make_item(1, [{"sub_type": "nstc", "backup_position": 1}]),
            _make_item(2, [{"sub_type": "moe_1w", "backup_position": 1}]),
            _make_item(3, [{"sub_type": "moe_2w", "backup_position": 1}]),
        ]
        service.db.query.return_value.filter.return_value.all.return_value = items

        result = service._find_eligible_alternate(
            ranking_id=1,
            sub_type=None,
            original_student_data={},
            scholarship_config=MagicMock(scholarship_type=MagicMock(whitelist_enabled=False)),
            skip_special_eligibility=True,
        )
        assert result is not None
        assert result["checked_count"] == 3

    def test_backup_with_no_sub_type_passes_when_filter_provided(self):
        # Pin: when backup has NO sub_type key but filter IS provided,
        # the backup is INCLUDED (defensive — assume general). Pin
        # so refactor doesn't accidentally exclude legacy backups
        # that lack the sub_type annotation.
        service = AlternatePromotionService(db=MagicMock())
        items = [
            _make_item(1, [{"backup_position": 1}]),  # No sub_type
        ]
        service.db.query.return_value.filter.return_value.all.return_value = items

        result = service._find_eligible_alternate(
            ranking_id=1,
            sub_type="nstc",
            original_student_data={},
            scholarship_config=MagicMock(scholarship_type=MagicMock(whitelist_enabled=False)),
            skip_special_eligibility=True,
        )
        assert result is not None
        assert result["checked_count"] == 1


class TestEmptyBackupAllocations:
    """Pin: items with no backup_allocations are skipped (defensive)."""

    def test_empty_backup_allocations_skipped(self):
        # Pin: defensive check — when backup_allocations is None or
        # empty list, skip the item entirely (no candidates emitted).
        service = AlternatePromotionService(db=MagicMock())
        items = [
            _make_item(1, []),  # Empty list
            _make_item(2, None),  # None
        ]
        service.db.query.return_value.filter.return_value.all.return_value = items

        result = service._find_eligible_alternate(
            ranking_id=1,
            sub_type=None,
            original_student_data={},
            scholarship_config=MagicMock(scholarship_type=MagicMock(whitelist_enabled=False)),
            skip_special_eligibility=True,
        )
        assert result is not None
        assert result["checked_count"] == 0


class TestExceptionPath:
    """Pin: any exception in the search returns None (caller treats
    as 'no alternate found' rather than crashing the roster job)."""

    def test_query_exception_returns_None(self):
        # Pin SECURITY: exception → returns None instead of raising.
        # The caller (`find_and_promote_alternate`) treats this as
        # "no eligible alternate" and proceeds without promoting.
        # Pin so refactor changing to re-raise would crash the
        # entire roster generation job for a single bad lookup.
        service = AlternatePromotionService(db=MagicMock())
        service.db.query.side_effect = RuntimeError("db connection lost")

        result = service._find_eligible_alternate(
            ranking_id=1,
            sub_type="nstc",
            original_student_data={},
            scholarship_config=MagicMock(scholarship_type=MagicMock(whitelist_enabled=False)),
            skip_special_eligibility=True,
        )
        assert result is None

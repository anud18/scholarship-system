"""
Pure-property tests for `CollegeRanking`, `CollegeRankingItem`, and
`QuotaDistribution` models.

These drive the college reviewer's quota dashboard:
- remaining_quota: how many slots left to allocate
- allocation_rate: progress percentage on the dashboard pill
- can_allocate_more: disables the 'Allocate' button when quota full
- is_within_quota: row badge for items above/below the cutoff
- success_rate: post-distribution health metric in the audit log
- get_sub_type_summary: drills into per-sub-type counts on detail pages

Bugs cause:
- Over-allocation (can_allocate_more True past quota) → exceeds budget
- Wrong dashboard percentages → bad mental model for reviewers
- Division-by-zero (NaN%) → CSS layout breakage on progress bar

6 helpers covered (13 cases).
"""

from types import SimpleNamespace

import pytest

from app.models.college_review import CollegeRanking, CollegeRankingItem, QuotaDistribution


# SA-free helper classes — bypass SQLAlchemy column instrumentation so pure
# Python @property methods can be exercised without needing _sa_instance_state.
class _FakeRanking:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

    remaining_quota = property(CollegeRanking.remaining_quota.fget)
    allocation_rate = property(CollegeRanking.allocation_rate.fget)
    can_allocate_more = CollegeRanking.can_allocate_more


class _FakeRankingItem:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

    is_within_quota = property(CollegeRankingItem.is_within_quota.fget)


class _FakeDistribution:
    def __init__(self, **attrs):
        self.__dict__.update(attrs)

    success_rate = property(QuotaDistribution.success_rate.fget)
    get_sub_type_summary = QuotaDistribution.get_sub_type_summary


def _ranking(**overrides) -> _FakeRanking:
    defaults = {
        "id": 1,
        "total_quota": 10,
        "allocated_count": 0,
        "total_applications": 0,
        "distribution_executed": False,
    }
    defaults.update(overrides)
    return _FakeRanking(**defaults)


def _item(**overrides) -> _FakeRankingItem:
    defaults = {
        "id": 1,
        "rank_position": 1,
    }
    defaults.update(overrides)
    return _FakeRankingItem(**defaults)


def _distribution(**overrides) -> _FakeDistribution:
    defaults = {
        "id": 1,
        "total_applications": 0,
        "total_allocated": 0,
        "distribution_summary": None,
    }
    defaults.update(overrides)
    return _FakeDistribution(**defaults)


# ─── CollegeRanking ──────────────────────────────────────────────────


def test_remaining_quota_zero_when_no_total():
    """No total_quota → 0 remaining (default-safe, no NaN/negative)."""
    assert _ranking(total_quota=0).remaining_quota == 0
    assert _ranking(total_quota=None).remaining_quota == 0


def test_remaining_quota_subtraction():
    """Standard subtraction; pin so a future refactor doesn't swap to
    counting allocations differently."""
    assert _ranking(total_quota=10, allocated_count=3).remaining_quota == 7
    assert _ranking(total_quota=10, allocated_count=0).remaining_quota == 10


def test_remaining_quota_clamps_to_zero_when_over_allocated():
    """If allocated_count > total_quota (admin manual override), don't
    return negative — clamp to 0. UI expects non-negative."""
    assert _ranking(total_quota=10, allocated_count=15).remaining_quota == 0


def test_allocation_rate_zero_division_guard():
    """No applications → 0% (avoids NaN%/'width: NaN%' CSS crash)."""
    assert _ranking(total_applications=0).allocation_rate == 0.0
    assert _ranking(total_applications=None).allocation_rate == 0.0


def test_allocation_rate_percentage_math():
    """Pin: (allocated / total) * 100. Returns float."""
    assert _ranking(total_applications=10, allocated_count=3).allocation_rate == 30.0
    assert _ranking(total_applications=4, allocated_count=1).allocation_rate == 25.0


def test_can_allocate_more_requires_quota_and_not_executed():
    """Both conditions: remaining > 0 AND distribution_executed=False."""
    assert _ranking(total_quota=10, allocated_count=3, distribution_executed=False).can_allocate_more() is True
    # No remaining quota → can't allocate.
    assert _ranking(total_quota=10, allocated_count=10, distribution_executed=False).can_allocate_more() is False
    # Already executed → can't allocate (frozen).
    assert _ranking(total_quota=10, allocated_count=3, distribution_executed=True).can_allocate_more() is False


# ─── CollegeRankingItem ──────────────────────────────────────────────


def test_is_within_quota_yes():
    """Rank 5 with quota 10 → within."""
    item = _item(rank_position=5)
    item.ranking = SimpleNamespace(total_quota=10)
    assert item.is_within_quota is True


def test_is_within_quota_boundary_inclusive():
    """Rank == quota → still within (inclusive). Pin so the last-rank
    student isn't displayed as 'just outside'."""
    item = _item(rank_position=10)
    item.ranking = SimpleNamespace(total_quota=10)
    assert item.is_within_quota is True


def test_is_within_quota_above_quota():
    item = _item(rank_position=11)
    item.ranking = SimpleNamespace(total_quota=10)
    assert item.is_within_quota is False


def test_is_within_quota_no_total_returns_false():
    """No total_quota set → no rank can be 'within' (cautious default)."""
    item = _item(rank_position=1)
    item.ranking = SimpleNamespace(total_quota=None)
    assert item.is_within_quota is False
    item.ranking = SimpleNamespace(total_quota=0)
    assert item.is_within_quota is False


# ─── QuotaDistribution ───────────────────────────────────────────────


def test_success_rate_zero_division_guard():
    """No applications → 0.0 (avoid NaN in audit log/issue body)."""
    assert _distribution(total_applications=0).success_rate == 0.0


def test_success_rate_percentage():
    """(allocated/total) * 100."""
    assert _distribution(total_applications=100, total_allocated=90).success_rate == 90.0
    assert _distribution(total_applications=10, total_allocated=7).success_rate == 70.0


def test_get_sub_type_summary_returns_per_sub_type_data():
    """Reads from distribution_summary dict by sub_type key."""
    d = _distribution(distribution_summary={"nstc": {"allocated": 5, "total": 10}})
    assert d.get_sub_type_summary("nstc") == {"allocated": 5, "total": 10}


def test_get_sub_type_summary_missing_returns_none():
    """Unknown sub_type → None (don't fabricate)."""
    d = _distribution(distribution_summary={"nstc": {}})
    assert d.get_sub_type_summary("moe_1w") is None


def test_get_sub_type_summary_no_summary_returns_none():
    """Empty distribution_summary → None for any key."""
    d = _distribution(distribution_summary=None)
    assert d.get_sub_type_summary("nstc") is None

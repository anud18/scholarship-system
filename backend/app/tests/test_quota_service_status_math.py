"""
Tests for `QuotaService.get_quota_status` quota-availability math.

This method composes get_scholarship_quota + get_quota_usage and
computes the values the admin quota dashboard renders:
- `total_available = total_quota - approved` (clamped to None when
  unlimited)
- `usage_percent = approved / total_quota * 100`

Bugs cause:
- Negative total_available shown to admin (math wrong → confusing UI)
- Division-by-zero crash when total_quota=0 (we display 0% for that case)
- usage_percent at 100% but admin sees applications still being
  approved (the gate is enforced elsewhere; this is dashboard-only)

Mocks the two DB-backed sub-methods via AsyncMock and tests only the
arithmetic + shape contract.

6 cases. Pure async, no real DB.
"""

from unittest.mock import AsyncMock

import pytest

from app.services.quota_service import QuotaService


def _service() -> QuotaService:
    """Construct without invoking __init__ (which requires a DB session).
    Sub-methods will be replaced with AsyncMocks."""
    svc = object.__new__(QuotaService)
    svc.db = None  # type: ignore[assignment]
    return svc


def _patch_sub_methods(svc: QuotaService, quota: dict, usage: dict) -> None:
    """Replace get_scholarship_quota + get_quota_usage with AsyncMocks
    so the math path runs without DB."""
    svc.get_scholarship_quota = AsyncMock(return_value=quota)
    svc.get_quota_usage = AsyncMock(return_value=usage)


# ─── total_available math ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_total_available_subtracts_approved_from_total():
    """Pin: total_available = total_quota - approved. The dashboard
    'remaining slots' counter relies on this."""
    svc = _service()
    _patch_sub_methods(
        svc,
        quota={"total_quota": 10, "mode": "simple", "by_college": {}},
        usage={"approved": 3, "pending": 2, "rejected": 1, "total": 6},
    )
    result = await svc.get_quota_status(1, "nstc", 113, "first")
    assert result["total_quota"] == 10
    assert result["total_used"] == 3
    assert result["total_available"] == 7  # 10 - 3


@pytest.mark.asyncio
async def test_unlimited_quota_signals_none_available():
    """Pin: total_quota=None (unlimited) → total_available=None,
    usage_percent=0. The frontend renders 'unlimited' for None."""
    svc = _service()
    _patch_sub_methods(
        svc,
        quota={"total_quota": None, "mode": "none", "by_college": {}},
        usage={"approved": 5, "pending": 0, "rejected": 0, "total": 5},
    )
    result = await svc.get_quota_status(1, "nstc", 113, None)
    assert result["total_available"] is None
    assert result["usage_percent"] == 0


@pytest.mark.asyncio
async def test_zero_quota_avoids_division_by_zero():
    """SECURITY/UX: total_quota=0 → usage_percent=0 (no ZeroDivisionError).
    Caller might configure 'closed scholarship' with quota=0 and we
    must not crash the dashboard."""
    svc = _service()
    _patch_sub_methods(
        svc,
        quota={"total_quota": 0, "mode": "simple", "by_college": {}},
        usage={"approved": 0, "pending": 1, "rejected": 0, "total": 1},
    )
    result = await svc.get_quota_status(1, "nstc", 113, "first")
    assert result["total_quota"] == 0
    assert result["usage_percent"] == 0


# ─── usage_percent math ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_usage_percent_calculation():
    """Pin: usage_percent = approved / total_quota * 100."""
    svc = _service()
    _patch_sub_methods(
        svc,
        quota={"total_quota": 20, "mode": "simple", "by_college": {}},
        usage={"approved": 5, "pending": 3, "rejected": 2, "total": 10},
    )
    result = await svc.get_quota_status(1, "nstc", 113, "first")
    assert result["usage_percent"] == 25.0  # 5/20 * 100


@pytest.mark.asyncio
async def test_usage_percent_can_exceed_100():
    """Pin: if approved > total_quota (over-allocation, possibly due
    to mid-cycle quota reduction), usage_percent reports >100 rather
    than capping. The admin needs to see the over-allocation to act."""
    svc = _service()
    _patch_sub_methods(
        svc,
        quota={"total_quota": 5, "mode": "simple", "by_college": {}},
        usage={"approved": 7, "pending": 0, "rejected": 0, "total": 7},
    )
    result = await svc.get_quota_status(1, "nstc", 113, "first")
    assert result["usage_percent"] == 140.0  # 7/5 * 100
    # total_available is negative in this case — admin sees the
    # over-allocation
    assert result["total_available"] == -2


# ─── Response shape contract ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_response_shape_contains_all_dashboard_fields():
    """Pin: response includes every field the admin quota dashboard
    component reads. A refactor that renames a key would break the UI."""
    svc = _service()
    _patch_sub_methods(
        svc,
        quota={"total_quota": 10, "mode": "simple", "by_college": {"EE": 5, "EN": 5}},
        usage={"approved": 3, "pending": 2, "rejected": 1, "total": 6},
    )
    result = await svc.get_quota_status(42, "moe_1w", 114, "second")
    # Identity / scope
    assert result["scholarship_type_id"] == 42
    assert result["sub_type"] == "moe_1w"
    assert result["academic_year"] == 114
    assert result["semester"] == "second"
    # Quota config
    assert result["total_quota"] == 10
    assert result["quota_mode"] == "simple"
    assert result["by_college"] == {"EE": 5, "EN": 5}
    # Usage breakdown
    assert result["total_used"] == 3
    assert result["pending"] == 2
    assert result["rejected"] == 1
    assert result["total_applications"] == 6
    # Derived
    assert result["total_available"] == 7
    assert result["usage_percent"] == 30.0

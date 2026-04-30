"""
Unit tests for the auto_allocate_preview algorithm.

Tests focus on the pure allocation logic via _compute_suggestions(),
which is extracted from the async DB layer for clean unit testing.

TDD: Tests written BEFORE implementation.
"""

import importlib.util
import os
import sys
from types import SimpleNamespace
from typing import Optional
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fixture-based module isolation: mock only when not already imported,
# and restore on teardown to avoid poisoning other test modules.
# ---------------------------------------------------------------------------

_SERVICE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "app", "services", "manual_distribution_service.py")
)

_MOCK_MODULES = [
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
    "app",
    "app.models",
    "app.models.application",
    "app.models.college_review",
    "app.models.enums",
    "app.models.scholarship",
]


@pytest.fixture(scope="module")
def _compute_suggestions():
    """
    Import _compute_suggestions with mocked dependencies, then clean up
    sys.modules on teardown to avoid poisoning other test files.
    """
    originals = {}
    for mod_name in _MOCK_MODULES:
        originals[mod_name] = sys.modules.get(mod_name)
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()

    # Ensure sub-packages resolve correctly via their parents
    sys.modules["sqlalchemy"].ext = sys.modules["sqlalchemy.ext"]
    sys.modules["sqlalchemy.ext"].asyncio = sys.modules["sqlalchemy.ext.asyncio"]
    sys.modules["sqlalchemy.ext.asyncio"].AsyncSession = object

    sys.modules["sqlalchemy.orm"].selectinload = MagicMock()

    sys.modules["app.models.enums"].ApplicationStatus = MagicMock()
    sys.modules["app.models.enums"].ReviewStage = MagicMock()

    sys.modules["app.models.college_review"].CollegeRanking = MagicMock()
    sys.modules["app.models.college_review"].CollegeRankingItem = MagicMock()
    sys.modules["app.models.college_review"].ManualDistributionHistory = MagicMock()

    sys.modules["app.models.scholarship"].ScholarshipConfiguration = MagicMock()
    sys.modules["app.models.scholarship"].ScholarshipSubTypeConfig = MagicMock()

    sys.modules["app.models.application"].Application = MagicMock()

    spec = importlib.util.spec_from_file_location("manual_distribution_service_direct", _SERVICE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    yield module._compute_suggestions

    # Restore original sys.modules state
    for mod_name in _MOCK_MODULES:
        if originals[mod_name] is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = originals[mod_name]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app(
    app_id: int,
    college: str = "A",
    is_renewal: bool = False,
    prev_app_id: Optional[int] = None,
    sub_type_preferences: Optional[list] = None,
    renewal_year: Optional[int] = None,
    scholarship_subtype_list: Optional[list] = None,
) -> SimpleNamespace:
    """Build a minimal Application-like object."""
    return SimpleNamespace(
        id=app_id,
        is_renewal=is_renewal,
        renewal_year=renewal_year,
        previous_application_id=prev_app_id,
        sub_type_preferences=sub_type_preferences,
        student_data={"std_academyno": college},
        scholarship_subtype_list=scholarship_subtype_list or [],
    )


def _make_item(
    item_id: int,
    rank_position: int,
    app: SimpleNamespace,
    is_allocated: bool = False,
    allocated_sub_type: Optional[str] = None,
    allocation_year: Optional[int] = None,
) -> SimpleNamespace:
    """Build a minimal CollegeRankingItem-like object."""
    return SimpleNamespace(
        id=item_id,
        rank_position=rank_position,
        application=app,
        is_allocated=is_allocated,
        allocated_sub_type=allocated_sub_type,
        allocation_year=allocation_year,
    )


def _build_quota_tracker(entries: dict) -> dict:
    """
    Build a quota tracker dict.
    entries: {(sub_type, year, college): count}
    """
    return dict(entries)


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestNewApplicantsAllocatedToCurrentYearNstcFirst:
    """Test 1: 2 new applicants with prefs ["nstc", "moe_1w"], both get nstc at current year."""

    def test_new_applicants_allocated_to_current_year_nstc_first(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc", "moe_1w"]
        prior_years_map = {"nstc": [113], "moe_1w": []}
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 114, "A"): 5,
                ("moe_1w", 114, "A"): 3,
            }
        )
        prev_alloc_years: dict[int, int] = {}

        app1 = _make_app(1, college="A", sub_type_preferences=["nstc", "moe_1w"])
        app2 = _make_app(2, college="A", sub_type_preferences=["nstc", "moe_1w"])
        item1 = _make_item(101, rank_position=1, app=app1)
        item2 = _make_item(102, rank_position=2, app=app2)

        results = _compute_suggestions(
            unique_items=[item1, item2],
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        assert len(results) == 2
        assert results[0] == {"ranking_item_id": 101, "sub_type_code": "nstc", "allocation_year": 114}
        assert results[1] == {"ranking_item_id": 102, "sub_type_code": "nstc", "allocation_year": 114}


class TestRenewalStudentsSortedBeforeNew:
    """Test 2: 1 renewal + 1 new, both rank 1, verify renewal processed first."""

    def test_renewal_students_sorted_before_new(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc", "moe_1w"]
        prior_years_map = {"nstc": [113], "moe_1w": []}
        # Only 1 slot for nstc in college A
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 114, "A"): 1,
                ("moe_1w", 114, "A"): 5,
            }
        )
        prev_alloc_years: dict[int, int] = {}

        renewal_app = _make_app(1, college="A", is_renewal=True)
        new_app = _make_app(2, college="A", is_renewal=False)
        # Both at rank_position=1 to test sorting
        renewal_item = _make_item(101, rank_position=1, app=renewal_app)
        new_item = _make_item(102, rank_position=1, app=new_app)

        results = _compute_suggestions(
            unique_items=[new_item, renewal_item],  # new passed first, renewal should win
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        assert len(results) == 2
        # Renewal gets nstc, new gets moe_1w (nstc exhausted)
        renewal_result = next(r for r in results if r["ranking_item_id"] == 101)
        new_result = next(r for r in results if r["ranking_item_id"] == 102)
        assert renewal_result["sub_type_code"] == "nstc"
        assert new_result["sub_type_code"] == "moe_1w"


class TestRenewalTargetsPreviousAllocationYear:
    """Test 3: Renewal student with prev alloc year 113, verify suggestion is (nstc, 113)."""

    def test_renewal_targets_previous_allocation_year(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc", "moe_1w"]
        prior_years_map = {"nstc": [113], "moe_1w": []}
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 113, "A"): 2,  # Prior year quota available
                ("nstc", 114, "A"): 5,
                ("moe_1w", 114, "A"): 3,
            }
        )
        # Renewal student's previous app (id=99) was allocated to year 113
        prev_alloc_years = {99: 113}

        renewal_app = _make_app(1, college="A", is_renewal=True, prev_app_id=99)
        item = _make_item(101, rank_position=1, app=renewal_app)

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        assert len(results) == 1
        assert results[0] == {"ranking_item_id": 101, "sub_type_code": "nstc", "allocation_year": 113}


class TestRenewalFallbackToCurrentYearWhenPriorExhausted:
    """Test 4: Prior year quota = 0, verify falls back to current year."""

    def test_renewal_fallback_to_current_year_when_prior_exhausted(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc", "moe_1w"]
        prior_years_map = {"nstc": [113], "moe_1w": []}
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 113, "A"): 0,  # Prior year exhausted
                ("nstc", 114, "A"): 5,  # Current year available
                ("moe_1w", 114, "A"): 3,
            }
        )
        prev_alloc_years = {99: 113}

        renewal_app = _make_app(1, college="A", is_renewal=True, prev_app_id=99)
        item = _make_item(101, rank_position=1, app=renewal_app)

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        assert len(results) == 1
        # Falls back to current year since 113 is exhausted
        assert results[0] == {"ranking_item_id": 101, "sub_type_code": "nstc", "allocation_year": 114}


class TestQuotaExhaustedFallsToNextPreference:
    """Test 5: nstc quota = 0, verify student gets moe_1w."""

    def test_quota_exhausted_falls_to_next_preference(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc", "moe_1w"]
        prior_years_map = {"nstc": [113], "moe_1w": []}
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 114, "A"): 0,  # Exhausted
                ("moe_1w", 114, "A"): 3,
            }
        )
        prev_alloc_years: dict[int, int] = {}

        app = _make_app(1, college="A", sub_type_preferences=["nstc", "moe_1w"])
        item = _make_item(101, rank_position=1, app=app)

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        assert len(results) == 1
        assert results[0] == {"ranking_item_id": 101, "sub_type_code": "moe_1w", "allocation_year": 114}


class TestAllQuotasExhaustedReturnsNull:
    """Test 6: No quota remaining, verify null suggestion."""

    def test_all_quotas_exhausted_returns_null(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc", "moe_1w"]
        prior_years_map = {"nstc": [113], "moe_1w": []}
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 114, "A"): 0,
                ("moe_1w", 114, "A"): 0,
            }
        )
        prev_alloc_years: dict[int, int] = {}

        app = _make_app(1, college="A", sub_type_preferences=["nstc", "moe_1w"])
        item = _make_item(101, rank_position=1, app=app)

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        assert len(results) == 1
        assert results[0] == {"ranking_item_id": 101, "sub_type_code": None, "allocation_year": None}


class TestNullPreferencesUsesConfigDefaults:
    """Test 7: sub_type_preferences is None, verify uses ScholarshipSubTypeConfig order."""

    def test_null_preferences_uses_config_defaults(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc", "moe_1w"]  # Config-driven defaults
        prior_years_map = {"nstc": [113], "moe_1w": []}
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 114, "A"): 0,  # nstc exhausted
                ("moe_1w", 114, "A"): 5,
            }
        )
        prev_alloc_years: dict[int, int] = {}

        app = _make_app(1, college="A", sub_type_preferences=None)  # No preferences set
        item = _make_item(101, rank_position=1, app=app)

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        assert len(results) == 1
        # Uses default prefs: nstc exhausted, falls to moe_1w
        assert results[0] == {"ranking_item_id": 101, "sub_type_code": "moe_1w", "allocation_year": 114}


class TestAlreadyAllocatedStudentsSkipped:
    """Test 8: Student with existing allocation, verify skipped."""

    def test_already_allocated_students_skipped(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc", "moe_1w"]
        prior_years_map = {"nstc": [113], "moe_1w": []}
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 114, "A"): 5,
                ("moe_1w", 114, "A"): 3,
            }
        )
        prev_alloc_years: dict[int, int] = {}

        app = _make_app(1, college="A")
        # Item already has an allocation
        item = _make_item(
            101,
            rank_position=1,
            app=app,
            is_allocated=True,
            allocated_sub_type="nstc",
            allocation_year=114,
        )

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        # Already allocated items are not re-suggested; quota not consumed
        # The item should not appear in the results (it's already handled)
        assert len(results) == 0
        # Quota should NOT have been decremented by this already-allocated item
        assert quota_tracker[("nstc", 114, "A")] == 5


class TestPerCollegeQuotaRespected:
    """Test 9: College A quota=1, 2 students from college A, only 1 gets allocated."""

    def test_per_college_quota_respected(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc", "moe_1w"]
        prior_years_map = {"nstc": [113], "moe_1w": []}
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 114, "A"): 1,  # Only 1 slot for college A
                ("moe_1w", 114, "A"): 0,  # No moe_1w for college A either
            }
        )
        prev_alloc_years: dict[int, int] = {}

        app1 = _make_app(1, college="A", sub_type_preferences=["nstc", "moe_1w"])
        app2 = _make_app(2, college="A", sub_type_preferences=["nstc", "moe_1w"])
        item1 = _make_item(101, rank_position=1, app=app1)
        item2 = _make_item(102, rank_position=2, app=app2)

        results = _compute_suggestions(
            unique_items=[item1, item2],
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        assert len(results) == 2
        # First student gets nstc (rank 1)
        assert results[0] == {"ranking_item_id": 101, "sub_type_code": "nstc", "allocation_year": 114}
        # Second student gets nothing (quota exhausted for both sub-types in college A)
        assert results[1] == {"ranking_item_id": 102, "sub_type_code": None, "allocation_year": None}


class TestRenewalWithPriorYearNotConfigured:
    """Bonus test: Renewal targets prior year not in prior_years_map, should try current year."""

    def test_renewal_with_prior_year_not_in_config_uses_current(self, _compute_suggestions):
        """
        Renewal student's prev alloc year is 112, but prior_years_map only has 113.
        Should try current year (114) as fallback.
        """
        academic_year = 114
        default_prefs = ["nstc"]
        prior_years_map = {"nstc": [113]}  # Only 113, not 112
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 114, "A"): 3,  # Current year available
                ("nstc", 113, "A"): 2,  # 113 available but not target
            }
        )
        prev_alloc_years = {99: 112}  # Previous year was 112

        renewal_app = _make_app(1, college="A", is_renewal=True, prev_app_id=99)
        item = _make_item(101, rank_position=1, app=renewal_app)

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        assert len(results) == 1
        # Since 112 not in prior_years_map for nstc, falls back to current year
        assert results[0] == {"ranking_item_id": 101, "sub_type_code": "nstc", "allocation_year": 114}


class TestNoDedupInComputeSuggestions:
    """Verify _compute_suggestions does not re-deduplicate (caller's responsibility)."""

    def test_both_items_get_suggestions(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc"]
        prior_years_map = {"nstc": [113]}
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 114, "A"): 5,
            }
        )
        prev_alloc_years: dict[int, int] = {}

        app = _make_app(1, college="A")
        # Same application appears twice (from different rankings)
        item1 = _make_item(101, rank_position=1, app=app)
        item2 = _make_item(102, rank_position=2, app=app)  # Same app.id=1

        results = _compute_suggestions(
            unique_items=[item1, item2],  # Pre-deduplicated list passed in
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        # Both items passed in; _compute_suggestions does not re-deduplicate
        # (deduplication is done before calling this function)
        # So both get their own result
        assert len(results) == 2


class TestEmptyItemsList:
    """Empty input returns empty output."""

    def test_empty_items_returns_empty(self, _compute_suggestions):
        results = _compute_suggestions(
            unique_items=[],
            default_prefs=["nstc"],
            prev_alloc_years={},
            prior_years_map={},
            quota_tracker={},
            academic_year=114,
        )
        assert results == []


class TestRenewalWithNoPreviousApplicationId:
    """Renewal student with no previous_application_id uses current year."""

    def test_renewal_no_prev_app_id_uses_current_year(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc"]
        prior_years_map = {"nstc": [113]}
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 114, "A"): 5,
            }
        )
        prev_alloc_years: dict[int, int] = {}

        # is_renewal=True but prev_app_id=None
        app = _make_app(1, college="A", is_renewal=True, prev_app_id=None)
        item = _make_item(101, rank_position=1, app=app)

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        assert len(results) == 1
        assert results[0] == {"ranking_item_id": 101, "sub_type_code": "nstc", "allocation_year": 114}


class TestUnknownCollegeGetsNoAllocation:
    """Student from college not in quota tracker gets null allocation."""

    def test_unknown_college_no_allocation(self, _compute_suggestions):
        academic_year = 114
        default_prefs = ["nstc"]
        prior_years_map = {}
        # Only college A has quota
        quota_tracker = _build_quota_tracker(
            {
                ("nstc", 114, "A"): 5,
            }
        )
        prev_alloc_years: dict[int, int] = {}

        app = _make_app(1, college="B")  # College B not in tracker
        item = _make_item(101, rank_position=1, app=app)

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=default_prefs,
            prev_alloc_years=prev_alloc_years,
            prior_years_map=prior_years_map,
            quota_tracker=quota_tracker,
            academic_year=academic_year,
        )

        assert len(results) == 1
        assert results[0] == {"ranking_item_id": 101, "sub_type_code": None, "allocation_year": None}


class TestPreferenceOrderRespected:
    """Bug fix: students with sub_type_preferences should be allocated
    according to their preference order, not default_prefs."""

    def test_moe_preferred_over_nstc(self, _compute_suggestions):
        """Student applied for both nstc and moe_1w but prefers moe_1w.
        Should be allocated to moe_1w even though default_prefs has nstc first."""
        app = _make_app(
            1,
            college="C",
            sub_type_preferences=["moe_1w", "nstc"],
            scholarship_subtype_list=["moe_1w", "nstc"],
        )
        item = _make_item(1, rank_position=1, app=app)

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=["nstc", "moe_1w"],  # System default: nstc first
            prev_alloc_years={},
            prior_years_map={},
            quota_tracker={
                ("nstc", 114, "C"): 5,
                ("moe_1w", 114, "C"): 5,
            },
            academic_year=114,
        )

        assert len(results) == 1
        assert results[0]["sub_type_code"] == "moe_1w"
        assert results[0]["allocation_year"] == 114

    def test_no_preferences_uses_subtype_list_order(self, _compute_suggestions):
        """Student has no sub_type_preferences but scholarship_subtype_list
        is ['moe_1w', 'nstc']. Should use subtype_list order as fallback,
        not default_prefs."""
        app = _make_app(
            1,
            college="C",
            sub_type_preferences=None,
            scholarship_subtype_list=["moe_1w", "nstc"],
        )
        item = _make_item(1, rank_position=1, app=app)

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=["nstc", "moe_1w"],
            prev_alloc_years={},
            prior_years_map={},
            quota_tracker={
                ("nstc", 114, "C"): 5,
                ("moe_1w", 114, "C"): 5,
            },
            academic_year=114,
        )

        assert len(results) == 1
        assert results[0]["sub_type_code"] == "moe_1w"

    def test_only_moe_applied_not_allocated_to_nstc(self, _compute_suggestions):
        """Student only applied for moe_1w. Must NOT be allocated to nstc."""
        app = _make_app(
            1,
            college="C",
            sub_type_preferences=None,
            scholarship_subtype_list=["moe_1w"],
        )
        item = _make_item(1, rank_position=1, app=app)

        results = _compute_suggestions(
            unique_items=[item],
            default_prefs=["nstc", "moe_1w"],
            prev_alloc_years={},
            prior_years_map={},
            quota_tracker={
                ("nstc", 114, "C"): 5,
                ("moe_1w", 114, "C"): 5,
            },
            academic_year=114,
        )

        assert len(results) == 1
        assert results[0]["sub_type_code"] == "moe_1w"

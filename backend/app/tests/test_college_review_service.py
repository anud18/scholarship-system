"""
Test cases for College Review Service

Tests critical functionality including:
- Ranking operations with concurrent access protection
- Error handling and validation
- Permission checks and data integrity
"""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.services.college_review_service import (
    CollegeReviewError,
    CollegeReviewService,
    InvalidRankingDataError,
    RankingModificationError,
    RankingNotFoundError,
    ReviewPermissionError,
)


def _ranking_key_queries(statements):
    """Select statements whose WHERE targets the college_rankings key (the reuse lookup)."""
    return [
        s
        for s in statements
        if getattr(s, "whereclause", None) is not None and "college_rankings.sub_type_code" in str(s.whereclause)
    ]


class TestCollegeReviewService:
    """Test suite for CollegeReviewService"""

    @pytest.fixture
    def service(self):
        """Create service instance with a mock database session."""
        db = MagicMock()
        db.execute = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()
        return CollegeReviewService(db)

    @pytest.fixture
    def sample_ranking(self):
        """Sample ranking for testing"""
        return CollegeRanking(
            id=1,
            scholarship_type_id=1,
            sub_type_code="phd_research",
            academic_year=113,
            semester="FIRST",
            created_by=2001,
            is_finalized=False,
            ranking_status="draft",
        )

    async def test_ranking_finalization_concurrent_protection(self, service, sample_ranking):
        """Test that ranking finalization calls the DB with locking queries"""
        # Mock ranking query results
        result = MagicMock()
        result.scalar_one_or_none.return_value = sample_ranking
        service.db.execute = AsyncMock(side_effect=[result])

        await service.finalize_ranking(ranking_id=1, finalizer_id=2001)

        # finalize_ranking issues exactly one SELECT: the target ranking with a
        # FOR UPDATE lock. There is no sibling-conflict query any more because a
        # college owns a single ranking per period.
        assert service.db.execute.call_count == 1
        service.db.flush.assert_called_once()

    async def test_finalize_already_finalized_ranking(self, service):
        """Test finalizing an already finalized ranking"""
        finalized_ranking = CollegeRanking(id=1, is_finalized=True, ranking_status="finalized")

        result = MagicMock()
        result.scalar_one_or_none.return_value = finalized_ranking
        service.db.execute = AsyncMock(return_value=result)

        with pytest.raises(RankingModificationError):
            await service.finalize_ranking(ranking_id=1, finalizer_id=2001)

    async def test_update_ranking_order_validation(self, service, sample_ranking):
        """Test ranking order update with validation"""
        sample_ranking.items = [
            CollegeRankingItem(id=1, application_id=101, rank_position=1),
            CollegeRankingItem(id=2, application_id=102, rank_position=2),
        ]

        result = MagicMock()
        result.scalar_one_or_none.return_value = sample_ranking
        service.db.execute = AsyncMock(return_value=result)

        new_order = [{"item_id": 1, "position": 2}, {"item_id": 2, "position": 1}]

        ranking = await service.update_ranking_order(ranking_id=1, new_order=new_order)

        assert ranking is not None
        service.db.flush.assert_called_once()
        service.db.refresh.assert_called_once()

    async def test_update_ranking_duplicate_positions(self, service, sample_ranking):
        """Test ranking order update with duplicate positions"""
        new_order = [
            {"item_id": 1, "position": 1},
            {"item_id": 2, "position": 1},  # Duplicate position
        ]

        result = MagicMock()
        result.scalar_one_or_none.return_value = sample_ranking
        service.db.execute = AsyncMock(return_value=result)

        with pytest.raises(InvalidRankingDataError):
            await service.update_ranking_order(ranking_id=1, new_order=new_order)

    async def test_create_ranking_reuse_is_scoped_by_college(self, service):
        """Regression: the reuse-existing-unfinalized-ranking lookup must be scoped by
        college_code, otherwise one college's unfinalized ranking is handed to other
        colleges creating a ranking for the same (type, sub_type, year). Those colleges
        could not see it (get_rankings is also college-scoped) and their applications
        were never ranked, so only one college survived into admin distribution.
        Reproduced live; see issue #1034.
        """
        captured = []

        def _record(stmt, *args, **kwargs):
            captured.append(stmt)
            result = MagicMock()
            # First query is the creator lookup → return a college reviewer; the
            # subsequent existence / apps queries return nothing.
            if len(captured) == 1:
                creator = MagicMock()
                creator.college_code = "E"
                result.scalar_one_or_none.return_value = creator
            else:
                result.scalar_one_or_none.return_value = None
            scalars = MagicMock()
            scalars.all.return_value = []
            result.scalars.return_value = scalars
            return result

        service.db.execute = AsyncMock(side_effect=_record)

        await service.create_ranking(
            scholarship_type_id=2,
            sub_type_code="default",
            academic_year=114,
            semester="yearly",
            creator_id=52,
        )

        # The reuse-existence check is the statement whose WHERE filters on the ranking key.
        # Render with literal binds so we assert the EXACT predicate (operator + value),
        # not just the substring "college_code" — a substring check would also pass for an
        # inverted `!=` or an unconditional `IS NULL`, which would be wrong.
        existence = _ranking_key_queries(captured)
        assert existence, "expected a reuse-existence query on the college_rankings key"
        where_sql = str(existence[0].whereclause.compile(compile_kwargs={"literal_binds": True}))
        assert "college_code = 'E'" in where_sql, (
            "reuse must be scoped to the creator's college (equality), so each college "
            f"shares one ranking and colleges stay isolated; got WHERE: {where_sql}"
        )
        assert "college_code !=" not in where_sql, f"reuse must use equality, not !=; got: {where_sql}"
        assert "created_by" not in where_sql, (
            "reuse must NOT be scoped by created_by (that breaks multi-reviewer-per-college "
            f"sharing); got WHERE: {where_sql}"
        )
        assert "is_finalized" not in where_sql, (
            "a college owns ONE ranking per period, finalized or not — reuse must not skip "
            f"finalized rankings (that re-opens the multi-ranking loophole); got WHERE: {where_sql}"
        )

    async def test_create_ranking_reuse_admin_uses_null_college(self, service):
        """A creator with no college (admin/super_admin → college_code None) reuses the
        global ranking via `college_code IS NULL`, not an equality on an empty value."""
        captured = []

        def _record(stmt, *args, **kwargs):
            captured.append(stmt)
            result = MagicMock()
            if len(captured) == 1:
                creator = MagicMock()
                creator.college_code = None  # admin-like creator
                result.scalar_one_or_none.return_value = creator
            else:
                result.scalar_one_or_none.return_value = None
            scalars = MagicMock()
            scalars.all.return_value = []
            result.scalars.return_value = scalars
            return result

        service.db.execute = AsyncMock(side_effect=_record)

        await service.create_ranking(
            scholarship_type_id=2,
            sub_type_code="default",
            academic_year=114,
            semester="yearly",
            creator_id=1,
        )

        existence = _ranking_key_queries(captured)
        assert existence, "expected a reuse-existence query"
        where_sql = str(existence[0].whereclause.compile(compile_kwargs={"literal_binds": True}))
        assert "college_code IS NULL" in where_sql, f"admin/global reuse must match IS NULL; got: {where_sql}"

    async def test_create_ranking_returns_existing_even_when_finalized(self, service):
        """Single-ranking rule: when the college already owns a ranking for this period
        (here a finalized one) create_ranking hands it back and creates nothing."""
        existing = CollegeRanking(
            id=7,
            scholarship_type_id=2,
            sub_type_code="default",
            academic_year=114,
            semester=None,
            college_code="E",
            is_finalized=True,
            ranking_status="finalized",
        )
        captured = []

        def _record(stmt, *args, **kwargs):
            captured.append(stmt)
            result = MagicMock()
            if len(captured) == 1:
                creator = MagicMock()
                creator.college_code = "E"
                result.scalar_one_or_none.return_value = creator
            else:
                result.scalar_one_or_none.return_value = existing
            return result

        service.db.execute = AsyncMock(side_effect=_record)

        ranking = await service.create_ranking(
            scholarship_type_id=2,
            sub_type_code="default",
            academic_year=114,
            semester="yearly",
            creator_id=52,
        )

        assert ranking is existing
        service.db.add.assert_not_called()
        # creator lookup + existence check only — no application query, no insert
        assert len(captured) == 2

    async def test_finalize_touches_only_the_target_ranking(self, service):
        """A college owns exactly one ranking per period, so finalize must not run any
        sibling "un-finalize others" query — it locks and flips the target row only.
        (Another college's ranking must never be affected: issue #1034.)"""
        captured = []
        target = MagicMock()
        target.id = 6
        target.college_code = "E"
        target.semester = "yearly"
        target.scholarship_type_id = 2
        target.sub_type_code = "default"
        target.academic_year = 114
        target.is_finalized = False

        def _record(stmt, *args, **kwargs):
            captured.append(stmt)
            result = MagicMock()
            result.scalar_one_or_none.return_value = target
            return result

        service.db.execute = AsyncMock(side_effect=_record)
        service.db.flush = AsyncMock()

        await service.finalize_ranking(ranking_id=6, finalizer_id=99)

        assert target.is_finalized is True
        assert target.ranking_status == "finalized"
        assert target.finalized_by == 99
        assert len(captured) == 1, f"finalize must issue only the target lock query; got {len(captured)}"
        where_sql = str(captured[0].whereclause.compile(compile_kwargs={"literal_binds": True}))
        assert "college_rankings.id = 6" in where_sql
        assert "is_finalized" not in where_sql

    def test_exception_hierarchy(self):
        """Test that custom exceptions inherit properly"""
        assert issubclass(RankingNotFoundError, CollegeReviewError)
        assert issubclass(RankingModificationError, CollegeReviewError)
        assert issubclass(InvalidRankingDataError, CollegeReviewError)
        assert issubclass(ReviewPermissionError, CollegeReviewError)
        assert issubclass(CollegeReviewError, Exception)


class TestAssertCanManageRanking:
    """assert_can_manage_ranking: a college's reviewers (or admins) may act on that
    college's ranking; other colleges may not. Keeps the ranking write/read-by-id
    endpoints consistent with the college-scoped create/list (issue #1034)."""

    @staticmethod
    def _user(*, is_admin=False, is_super_admin=False, college_code=None):
        u = MagicMock()
        u.is_admin.return_value = is_admin
        u.is_super_admin.return_value = is_super_admin
        u.college_code = college_code
        return u

    @staticmethod
    def _ranking(college_code):
        r = MagicMock()
        r.college_code = college_code
        return r

    def _assert(self):
        from app.api.v1.endpoints.college_review._helpers import assert_can_manage_ranking

        return assert_can_manage_ranking

    def test_admin_can_manage_any(self):
        self._assert()(self._ranking("E"), self._user(is_admin=True, college_code=None))

    def test_super_admin_can_manage_any(self):
        self._assert()(self._ranking(None), self._user(is_super_admin=True, college_code=None))

    def test_same_college_reviewer_allowed(self):
        # Second reviewer of college E (not the creator) may manage E's ranking.
        self._assert()(self._ranking("E"), self._user(college_code="E"))

    def test_different_college_reviewer_forbidden(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._assert()(self._ranking("E"), self._user(college_code="B"))
        assert exc.value.status_code == 403

    def test_college_user_cannot_manage_global_null_ranking(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._assert()(self._ranking(None), self._user(college_code="E"))
        assert exc.value.status_code == 403

    def test_null_college_user_does_not_match_null_ranking(self):
        # Guard against NULL == NULL accidentally granting access.
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._assert()(self._ranking(None), self._user(college_code=None))
        assert exc.value.status_code == 403

    def test_empty_string_college_codes_are_not_a_match(self):
        # "" is not a valid college; two empty-coded actors must not share access
        # (aligns with the defensive strip-and-reject in export/supplementary-import).
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._assert()(self._ranking(""), self._user(college_code=""))
        assert exc.value.status_code == 403


# Integration tests that would require database setup
class TestCollegeReviewServiceIntegration:
    """Integration tests for CollegeReviewService with real database operations"""

    @pytest.mark.integration
    async def test_full_review_workflow(self, db):
        """Test complete review workflow from creation to finalization"""
        # Placeholder — full DB-backed workflow test not yet implemented
        pass

    @pytest.mark.integration
    async def test_concurrent_ranking_modifications(self, db):
        """Test concurrent access protection in real database scenario"""
        # Placeholder — concurrent access test not yet implemented
        pass

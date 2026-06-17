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
        # second execute (conflict check) returns empty list of other finalized rankings
        conflict_result = MagicMock()
        conflict_result.scalars.return_value.all.return_value = []
        service.db.execute = AsyncMock(side_effect=[result, conflict_result])

        await service.finalize_ranking(ranking_id=1, finalizer_id=2001)

        # finalize_ranking issues two SELECT statements: one for the target ranking
        # (with FOR UPDATE lock) and one to check for conflicting finalized rankings.
        assert service.db.execute.call_count == 2
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

    async def test_create_ranking_reuse_is_scoped_by_creator(self, service):
        """Regression: the reuse-existing-unfinalized-ranking lookup must be scoped
        by created_by, otherwise one college's unfinalized ranking is handed to every
        other college creating a ranking for the same (type, sub_type, year) — those
        colleges cannot see it (get_rankings filters by created_by) and their
        applications are never ranked. Reproduced live; see the multi-college flow.
        """
        captured = []

        def _record(stmt, *args, **kwargs):
            captured.append(stmt)
            result = MagicMock()
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

        # First statement is the reuse-existence check; its WHERE clause (not the
        # SELECT column list) must filter on created_by. Inspecting whereclause only
        # avoids a false positive from select(CollegeRanking) listing every column.
        assert captured, "expected create_ranking to issue at least one query"
        where_sql = str(captured[0].whereclause)
        assert "created_by" in where_sql, (
            "reuse-existence check WHERE must be scoped by created_by to keep each "
            f"college's ranking distinct; got WHERE: {where_sql}"
        )

    def test_exception_hierarchy(self):
        """Test that custom exceptions inherit properly"""
        assert issubclass(RankingNotFoundError, CollegeReviewError)
        assert issubclass(RankingModificationError, CollegeReviewError)
        assert issubclass(InvalidRankingDataError, CollegeReviewError)
        assert issubclass(ReviewPermissionError, CollegeReviewError)
        assert issubclass(CollegeReviewError, Exception)


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

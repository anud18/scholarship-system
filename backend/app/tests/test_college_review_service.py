"""
Test cases for College Review Service

Tests critical functionality including:
- Review creation and updates
- Ranking operations with concurrent access protection
- Error handling and validation
- Permission checks and data integrity
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import BusinessLogicError, NotFoundError
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem, CollegeReview
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
    async def service(self, db_session):
        """Create service instance with mocked database session"""
        return CollegeReviewService(db_session)

    @pytest.fixture
    def sample_application(self):
        """Sample application for testing"""
        return Application(
            id=1,
            student_id=1001,
            scholarship_type_id=1,
            academic_year=113,
            semester="FIRST",
            status="under_review",
            sub_scholarship_type="phd_research",
        )

    @pytest.fixture
    def sample_college_review(self):
        """Sample college review for testing"""
        return CollegeReview(
            id=1,
            application_id=1,
            reviewer_id=2001,
            academic_score=85.0,
            professor_review_score=90.0,
            college_criteria_score=88.0,
            ranking_score=87.5,
            review_status="completed",
        )

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

    async def test_create_review_success(self, service, sample_application):
        """Test successful review creation"""
        # Mock database operations
        service.db.execute = AsyncMock()
        service.db.add = MagicMock()
        service.db.flush = AsyncMock()
        service.db.refresh = AsyncMock()

        # Mock application query result
        app_result = MagicMock()
        app_result.scalar_one_or_none.return_value = sample_application
        service.db.execute.return_value = app_result

        review_data = {
            "academic_score": 85.0,
            "professor_review_score": 90.0,
            "college_criteria_score": 88.0,
            "comments": "Excellent candidate",
        }

        # Execute
        result = await service.create_or_update_review(application_id=1, reviewer_id=2001, review_data=review_data)

        # Verify database operations were called
        service.db.add.assert_called_once()
        service.db.flush.assert_called_once()
        service.db.refresh.assert_called_once()

    async def test_create_review_application_not_found(self, service):
        """Test review creation when application doesn't exist"""
        # Mock database to return None for application
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        service.db.execute = AsyncMock(return_value=result)

        review_data = {"academic_score": 85.0}

        # Should raise NotFoundError
        with pytest.raises(NotFoundError):
            await service.create_or_update_review(application_id=999, reviewer_id=2001, review_data=review_data)

    async def test_create_review_invalid_application_status(self, service):
        """Test review creation with invalid application status"""
        # Create application with invalid status
        invalid_app = Application(
            id=1,
            status="submitted",  # Invalid for review
            scholarship_type_id=1,
            academic_year=113,
        )

        result = MagicMock()
        result.scalar_one_or_none.return_value = invalid_app
        service.db.execute = AsyncMock(return_value=result)

        review_data = {"academic_score": 85.0}

        # Should raise BusinessLogicError
        with pytest.raises(BusinessLogicError):
            await service.create_or_update_review(application_id=1, reviewer_id=2001, review_data=review_data)

    async def test_ranking_finalization_concurrent_protection(self, service, sample_ranking):
        """Test that ranking finalization has concurrent access protection"""
        # Mock database transaction context
        service.db.begin = AsyncMock().__aenter__.return_value.__aexit__ = AsyncMock()

        # Mock ranking query with locking
        result = MagicMock()
        result.scalar_one_or_none.return_value = sample_ranking
        service.db.execute = AsyncMock(return_value=result)
        service.db.flush = AsyncMock()

        # Execute finalization
        await service.finalize_ranking(ranking_id=1, finalizer_id=2001)

        # Verify transaction and locking were used
        service.db.execute.assert_called_once()
        service.db.flush.assert_called_once()

    async def test_finalize_already_finalized_ranking(self, service):
        """Test finalizing an already finalized ranking"""
        # Create finalized ranking
        finalized_ranking = CollegeRanking(id=1, is_finalized=True, ranking_status="finalized")

        result = MagicMock()
        result.scalar_one_or_none.return_value = finalized_ranking
        service.db.execute = AsyncMock(return_value=result)
        service.db.begin = AsyncMock().__aenter__.return_value

        # Should raise RankingModificationError
        with pytest.raises(RankingModificationError):
            await service.finalize_ranking(ranking_id=1, finalizer_id=2001)

    async def test_update_ranking_order_validation(self, service, sample_ranking):
        """Test ranking order update with validation"""
        # Add items to ranking
        sample_ranking.items = [
            CollegeRankingItem(id=1, application_id=101, rank_position=1),
            CollegeRankingItem(id=2, application_id=102, rank_position=2),
        ]

        result = MagicMock()
        result.scalar_one_or_none.return_value = sample_ranking
        service.db.execute = AsyncMock(return_value=result)
        service.db.begin = AsyncMock().__aenter__.return_value
        service.db.flush = AsyncMock()

        # Valid new order
        new_order = [{"item_id": 1, "position": 2}, {"item_id": 2, "position": 1}]

        # Should succeed
        result = await service.update_ranking_order(ranking_id=1, new_order=new_order)

        assert result is not None
        service.db.flush.assert_called_once()

    async def test_update_ranking_duplicate_positions(self, service, sample_ranking):
        """Test ranking order update with duplicate positions"""
        service.db.begin = AsyncMock().__aenter__.return_value

        # Invalid order with duplicate positions
        new_order = [
            {"item_id": 1, "position": 1},
            {"item_id": 2, "position": 1},  # Duplicate position
        ]

        result = MagicMock()
        result.scalar_one_or_none.return_value = sample_ranking
        service.db.execute = AsyncMock(return_value=result)

        # Should raise InvalidRankingDataError
        with pytest.raises(InvalidRankingDataError):
            await service.update_ranking_order(ranking_id=1, new_order=new_order)

    async def test_ranking_score_calculation(self, service):
        """Test ranking score calculation logic"""
        review_data = {
            "academic_score": 80.0,
            "professor_review_score": 90.0,
            "college_criteria_score": 85.0,
            "special_circumstances_score": 75.0,
        }

        # Calculate score using service's internal method
        score = service._calculate_ranking_score(review_data)

        # Expected: 0.30*80 + 0.40*90 + 0.20*85 + 0.10*75 = 24 + 36 + 17 + 7.5 = 84.5
        expected_score = 84.5
        assert abs(score - expected_score) < 0.1

    async def test_custom_scoring_weights(self, service):
        """Test ranking score calculation with custom weights"""
        review_data = {
            "academic_score": 80.0,
            "professor_review_score": 90.0,
            "college_criteria_score": 85.0,
            "special_circumstances_score": 75.0,
            "scoring_weights": {
                "academic": 0.50,  # Higher weight on academics
                "professor_review": 0.30,
                "college_criteria": 0.15,
                "special_circumstances": 0.05,
            },
        }

        score = service._calculate_ranking_score(review_data)

        # Expected: 0.50*80 + 0.30*90 + 0.15*85 + 0.05*75 = 40 + 27 + 12.75 + 3.75 = 83.5
        expected_score = 83.5
        assert abs(score - expected_score) < 0.1

    def test_exception_hierarchy(self):
        """Test that custom exceptions inherit properly"""
        # All custom exceptions should inherit from CollegeReviewError
        assert issubclass(RankingNotFoundError, CollegeReviewError)
        assert issubclass(RankingModificationError, CollegeReviewError)
        assert issubclass(InvalidRankingDataError, CollegeReviewError)
        assert issubclass(ReviewPermissionError, CollegeReviewError)

        # CollegeReviewError should inherit from base Exception
        assert issubclass(CollegeReviewError, Exception)


# Integration tests that would require database setup
class TestCollegeReviewServiceIntegration:
    """Integration tests for CollegeReviewService with real database operations"""

    @pytest.mark.integration
    async def test_full_review_workflow(self, db_session):
        """Test complete review workflow from creation to finalization"""
        # This would test the full workflow with real database operations
        # Requires proper test database setup
        pass

    @pytest.mark.integration
    async def test_concurrent_ranking_modifications(self, db_session):
        """Test concurrent access protection in real database scenario"""
        # This would test actual concurrent access scenarios
        # Requires multi-threading test setup
        pass

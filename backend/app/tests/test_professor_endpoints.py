"""
Unit tests for professor review endpoints
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

# Import test dependencies
from app.api.v1.endpoints.professor import (
    get_application_sub_types,
    get_professor_applications,
    get_professor_review,
    get_professor_review_stats,
    submit_professor_review,
)
from app.models.user import User, UserRole
from app.schemas.application import ApplicationListResponse, ProfessorReviewCreate, ProfessorReviewItemCreate
from app.schemas.common import PaginatedResponse


class TestProfessorApplicationsEndpoint:
    """Test professor applications listing endpoint"""

    @pytest.fixture
    def mock_professor(self):
        """Mock professor user"""
        professor = Mock(spec=User)
        professor.id = 1
        professor.role = UserRole.professor
        professor.name = "Dr. Test Professor"
        professor.nycu_id = "prof001"
        return professor

    @pytest.fixture
    def mock_db_session(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def mock_request(self):
        """Mock FastAPI request object"""
        request = Mock()
        request.client.host = "127.0.0.1"
        return request

    @pytest.fixture
    def sample_applications(self):
        """Sample application responses"""
        return [
            ApplicationListResponse(
                id=1,
                app_id="APP-2024-001",
                user_id=10,
                student_id="312551001",
                scholarship_type="phd",
                scholarship_type_id=1,
                scholarship_type_zh="博士生獎學金",
                scholarship_name="PhD Scholarship AY113",
                amount=50000,
                currency="TWD",
                status="submitted",
                status_name="已提交",
                academic_year=113,
                semester="first",
                student_data={"cname": "Test Student", "stdNo": "312551001"},
                submitted_form_data={},
                agree_terms=True,
                professor_id=1,
                reviewer_id=None,
                final_approver_id=None,
                review_score=None,
                review_comments=None,
                rejection_reason=None,
                submitted_at=datetime.now(timezone.utc),
                reviewed_at=None,
                approved_at=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                meta_data=None,
                student_name="Test Student",
                student_no="312551001",
            )
        ]

    @pytest.mark.asyncio
    async def test_get_professor_applications_success(
        self, mock_professor, mock_db_session, mock_request, sample_applications
    ):
        """Test successful retrieval of professor applications"""
        # Mock the service call and rate limiting
        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class, patch(
            "app.core.rate_limiting.get_rate_limiter"
        ) as mock_get_limiter:
            mock_service = mock_service_class.return_value
            mock_service.get_professor_applications_paginated = AsyncMock(return_value=(sample_applications, 1))

            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 10))
            mock_get_limiter.return_value = mock_limiter

            # Call the endpoint
            result = await get_professor_applications(
                request=mock_request,
                status_filter=None,
                page=1,
                size=20,
                current_user=mock_professor,
                db=mock_db_session,
            )

            # Assertions
            assert isinstance(result, PaginatedResponse)
            assert result.items == sample_applications
            assert result.total == 1
            assert result.page == 1
            assert result.size == 20
            assert result.pages == 1

            # Verify service was called correctly
            mock_service.get_professor_applications_paginated.assert_called_once_with(
                professor_id=mock_professor.id, status_filter=None, page=1, size=20
            )

    @pytest.mark.asyncio
    async def test_get_professor_applications_with_filters(
        self, mock_professor, mock_db_session, mock_request, sample_applications
    ):
        """Test applications retrieval with status filter"""
        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class, patch(
            "app.core.rate_limiting.get_rate_limiter"
        ) as mock_get_limiter:
            mock_service = mock_service_class.return_value
            mock_service.get_professor_applications_paginated = AsyncMock(return_value=(sample_applications, 1))

            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 10))
            mock_get_limiter.return_value = mock_limiter

            result = await get_professor_applications(
                request=mock_request,
                status_filter="pending",
                page=2,
                size=10,
                current_user=mock_professor,
                db=mock_db_session,
            )

            assert isinstance(result, PaginatedResponse)
            assert result.page == 2
            assert result.size == 10

            mock_service.get_professor_applications_paginated.assert_called_once_with(
                professor_id=mock_professor.id, status_filter="pending", page=2, size=10
            )

    @pytest.mark.asyncio
    async def test_get_professor_applications_empty_result(self, mock_professor, mock_db_session, mock_request):
        """Test applications retrieval with no results"""
        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class, patch(
            "app.core.rate_limiting.get_rate_limiter"
        ) as mock_get_limiter:
            mock_service = mock_service_class.return_value
            mock_service.get_professor_applications_paginated = AsyncMock(return_value=([], 0))

            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 10))
            mock_get_limiter.return_value = mock_limiter

            result = await get_professor_applications(
                request=mock_request,
                status_filter=None,
                page=1,
                size=20,
                current_user=mock_professor,
                db=mock_db_session,
            )

            assert isinstance(result, PaginatedResponse)
            assert result.items == []
            assert result.total == 0
            assert result.pages == 0

    @pytest.mark.asyncio
    async def test_get_professor_applications_service_error(self, mock_professor, mock_db_session, mock_request):
        """Test applications retrieval when service throws error"""
        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class, patch(
            "app.core.rate_limiting.get_rate_limiter"
        ) as mock_get_limiter:
            mock_service = mock_service_class.return_value
            mock_service.get_professor_applications_paginated.side_effect = Exception("Database error")

            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 10))
            mock_get_limiter.return_value = mock_limiter

            with pytest.raises(HTTPException) as exc_info:
                await get_professor_applications(
                    request=mock_request,
                    status_filter=None,
                    page=1,
                    size=20,
                    current_user=mock_professor,
                    db=mock_db_session,
                )

            assert exc_info.value.status_code == 500
            assert "Failed to fetch applications" in str(exc_info.value.detail)


class TestProfessorReviewEndpoints:
    """Test professor review CRUD endpoints"""

    @pytest.fixture
    def mock_professor(self):
        professor = Mock(spec=User)
        professor.id = 1
        professor.role = UserRole.professor
        return professor

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_request(self):
        request = Mock()
        request.client.host = "127.0.0.1"
        return request

    @pytest.fixture
    def sample_review_create(self):
        """Sample review creation data"""
        return ProfessorReviewCreate(
            recommendation="Student demonstrates excellent academic performance",
            items=[
                ProfessorReviewItemCreate(
                    sub_type_code="nstc",
                    is_recommended=True,
                    comments="Highly recommended for NSTC scholarship",
                ),
                ProfessorReviewItemCreate(
                    sub_type_code="moe_1w",
                    is_recommended=False,
                    comments="Does not meet MOE requirements",
                ),
            ],
        )

    @pytest.mark.asyncio
    async def test_get_professor_review_success(self, mock_professor, mock_db_session, mock_request):
        """Test successful retrieval of existing review"""
        from app.schemas.application import ProfessorReviewResponse

        mock_review = ProfessorReviewResponse(
            id=1,
            application_id=10,
            professor_id=1,
            recommendation="Test recommendation",
            review_status="approved",
            reviewed_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            items=[],
        )

        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class:
            mock_service = mock_service_class.return_value
            mock_service.get_professor_review = AsyncMock(return_value=mock_review)

            result = await get_professor_review(
                request=mock_request,
                application_id=10,
                current_user=mock_professor,
                db=mock_db_session,
            )

            assert result == mock_review
            mock_service.get_professor_review.assert_called_once_with(application_id=10, professor_id=1)

    @pytest.mark.asyncio
    async def test_get_professor_review_not_found(self, mock_professor, mock_db_session, mock_request):
        """Test retrieval of non-existent review returns empty structure"""
        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class:
            mock_service = mock_service_class.return_value
            mock_service.get_professor_review = AsyncMock(return_value=None)

            result = await get_professor_review(
                request=mock_request,
                application_id=10,
                current_user=mock_professor,
                db=mock_db_session,
            )

            # Should return empty review structure for new reviews
            assert result.id == 0
            assert result.application_id == 10
            assert result.professor_id == 1
            assert result.items == []

    @pytest.mark.asyncio
    async def test_submit_professor_review_success(
        self, mock_professor, mock_db_session, mock_request, sample_review_create
    ):
        """Test successful review submission"""
        from app.schemas.application import ProfessorReviewResponse

        mock_application = Mock()
        mock_application.id = 10

        mock_review_response = ProfessorReviewResponse(
            id=1,
            application_id=10,
            professor_id=1,
            recommendation=sample_review_create.recommendation,
            review_status="submitted",
            reviewed_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            items=[],
        )

        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class:
            mock_service = mock_service_class.return_value
            mock_service.get_application_by_id = AsyncMock(return_value=mock_application)
            mock_service.can_professor_submit_review = AsyncMock(return_value=True)
            mock_service.submit_professor_review = AsyncMock(return_value=mock_review_response)

            # Mock the TESTING environment variable and rate limiting
            with patch("os.getenv", return_value="true"), patch(
                "app.core.rate_limiting.get_rate_limiter"
            ) as mock_get_limiter:
                mock_limiter = Mock()
                mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 10))
                mock_get_limiter.return_value = mock_limiter

                result = await submit_professor_review(
                    request=mock_request,
                    review_data=sample_review_create,
                    application_id=10,
                    current_user=mock_professor,
                    db=mock_db_session,
                )

            assert result == mock_review_response
            mock_service.submit_professor_review.assert_called_once_with(
                application_id=10,
                professor_id=1,
                review_data=sample_review_create.dict(),
            )

    @pytest.mark.asyncio
    async def test_submit_professor_review_application_not_found(
        self, mock_professor, mock_db_session, mock_request, sample_review_create
    ):
        """Test review submission for non-existent application"""
        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class, patch(
            "app.core.rate_limiting.get_rate_limiter"
        ) as mock_get_limiter:
            mock_service = mock_service_class.return_value
            mock_service.get_application_by_id = AsyncMock(return_value=None)

            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 10))
            mock_get_limiter.return_value = mock_limiter

            with pytest.raises(HTTPException) as exc_info:
                await submit_professor_review(
                    request=mock_request,
                    review_data=sample_review_create,
                    application_id=10,
                    current_user=mock_professor,
                    db=mock_db_session,
                )

            assert exc_info.value.status_code == 404
            assert "Application not found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_submit_professor_review_authorization_failed(
        self, mock_professor, mock_db_session, mock_request, sample_review_create
    ):
        """Test review submission when professor not authorized"""
        mock_application = Mock()
        mock_application.id = 10

        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class, patch(
            "app.core.rate_limiting.get_rate_limiter"
        ) as mock_get_limiter:
            mock_service = mock_service_class.return_value
            mock_service.get_application_by_id = AsyncMock(return_value=mock_application)
            mock_service.can_professor_submit_review = AsyncMock(return_value=False)

            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 10))
            mock_get_limiter.return_value = mock_limiter

            # Mock the TESTING environment variable as false
            with patch("os.getenv", return_value="false"):
                with pytest.raises(HTTPException) as exc_info:
                    await submit_professor_review(
                        request=mock_request,
                        review_data=sample_review_create,
                        application_id=10,
                        current_user=mock_professor,
                        db=mock_db_session,
                    )

                assert exc_info.value.status_code == 403
                assert "Professor not authorized to submit review" in str(exc_info.value.detail)


class TestProfessorSubTypesEndpoint:
    """Test application sub-types endpoint"""

    @pytest.fixture
    def mock_professor(self):
        professor = Mock(spec=User)
        professor.id = 1
        professor.role = UserRole.professor
        return professor

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_request(self):
        request = Mock()
        request.client.host = "127.0.0.1"
        return request

    @pytest.fixture
    def sample_sub_types(self):
        """Sample sub-types response"""
        return [
            {"value": "nstc", "label": "科技部獎學金", "label_en": "NSTC Scholarship"},
            {
                "value": "moe_1w",
                "label": "教育部獎學金 (一年級)",
                "label_en": "MOE Scholarship (1st Year)",
            },
        ]

    @pytest.mark.asyncio
    async def test_get_application_sub_types_success(
        self, mock_professor, mock_db_session, mock_request, sample_sub_types
    ):
        """Test successful retrieval of sub-types"""
        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class:
            mock_service = mock_service_class.return_value
            mock_service.get_application_available_sub_types = AsyncMock(return_value=sample_sub_types)

            result = await get_application_sub_types(
                request=mock_request,
                application_id=10,
                current_user=mock_professor,
                db=mock_db_session,
            )

            assert result == sample_sub_types
            mock_service.get_application_available_sub_types.assert_called_once_with(10)

    @pytest.mark.asyncio
    async def test_get_application_sub_types_service_error(self, mock_professor, mock_db_session, mock_request):
        """Test sub-types retrieval when service throws error"""
        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class:
            mock_service = mock_service_class.return_value
            mock_service.get_application_available_sub_types = AsyncMock(side_effect=Exception("Service error"))

            with pytest.raises(HTTPException) as exc_info:
                await get_application_sub_types(
                    request=mock_request,
                    application_id=10,
                    current_user=mock_professor,
                    db=mock_db_session,
                )

            assert exc_info.value.status_code == 500
            assert "Failed to fetch sub-types" in str(exc_info.value.detail)


class TestProfessorStatsEndpoint:
    """Test professor statistics endpoint"""

    @pytest.fixture
    def mock_professor(self):
        professor = Mock(spec=User)
        professor.id = 1
        professor.role = UserRole.professor
        return professor

    @pytest.fixture
    def mock_db_session(self):
        return AsyncMock()

    @pytest.fixture
    def mock_request(self):
        request = Mock()
        request.client.host = "127.0.0.1"
        return request

    @pytest.fixture
    def sample_stats(self):
        """Sample statistics response"""
        return {"pending_reviews": 5, "completed_reviews": 12, "overdue_reviews": 2}

    @pytest.mark.asyncio
    async def test_get_professor_review_stats_success(
        self, mock_professor, mock_db_session, mock_request, sample_stats
    ):
        """Test successful retrieval of statistics"""
        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class, patch(
            "app.core.rate_limiting.get_rate_limiter"
        ) as mock_get_limiter:
            mock_service = mock_service_class.return_value
            mock_service.get_professor_review_stats = AsyncMock(return_value=sample_stats)

            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 10))
            mock_get_limiter.return_value = mock_limiter

            result = await get_professor_review_stats(
                request=mock_request, current_user=mock_professor, db=mock_db_session
            )

            assert result == {
                "pending_reviews": 5,
                "completed_reviews": 12,
                "overdue_reviews": 2,
            }
            mock_service.get_professor_review_stats.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_get_professor_review_stats_service_error(self, mock_professor, mock_db_session, mock_request):
        """Test statistics retrieval when service throws error"""
        with patch("app.api.v1.endpoints.professor.ApplicationService") as mock_service_class, patch(
            "app.core.rate_limiting.get_rate_limiter"
        ) as mock_get_limiter:
            mock_service = mock_service_class.return_value
            mock_service.get_professor_review_stats = AsyncMock(side_effect=Exception("Database connection failed"))

            mock_limiter = Mock()
            mock_limiter.is_rate_limited = AsyncMock(return_value=(False, 10))
            mock_get_limiter.return_value = mock_limiter

            with pytest.raises(HTTPException) as exc_info:
                await get_professor_review_stats(
                    request=mock_request,
                    current_user=mock_professor,
                    db=mock_db_session,
                )

            assert exc_info.value.status_code == 500
            assert "Failed to fetch statistics" in str(exc_info.value.detail)

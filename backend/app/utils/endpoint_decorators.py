"""
Endpoint Error Handling Decorators

This module provides reusable error handling decorators for API endpoints
to reduce code duplication and ensure consistent error responses.
"""

import functools
import logging
from typing import Callable

from fastapi import HTTPException, status
from sqlalchemy.exc import DatabaseError, IntegrityError

from app.services.college_review_service import RankingModificationError, RankingNotFoundError, ReviewPermissionError

logger = logging.getLogger(__name__)


def handle_college_review_errors(func: Callable) -> Callable:
    """
    Decorator for handling common college review API errors.

    Converts exceptions to appropriate HTTP responses:
    - ReviewPermissionError → 403 Forbidden
    - RankingNotFoundError → 404 Not Found
    - RankingModificationError → 400 Bad Request
    - ValueError → 400 Bad Request
    - IntegrityError → 409 Conflict
    - DatabaseError → 503 Service Unavailable
    - Exception → 500 Internal Server Error

    Usage:
        @router.post("/endpoint")
        @handle_college_review_errors
        async def my_endpoint(...):
            # endpoint logic
            pass
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)

        except ReviewPermissionError as e:
            logger.warning(f"Permission denied: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e),
            )

        except RankingNotFoundError as e:
            logger.warning(f"Ranking not found: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e),
            )

        except RankingModificationError as e:
            logger.warning(f"Ranking modification error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

        except ValueError as e:
            logger.warning(f"Invalid value: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid request data: {str(e)}",
            )

        except IntegrityError as e:
            logger.error(f"Database integrity error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The request conflicts with existing data",
            )

        except DatabaseError as e:
            logger.error(f"Database error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service temporarily unavailable",
            )

        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred",
            )

    return wrapper

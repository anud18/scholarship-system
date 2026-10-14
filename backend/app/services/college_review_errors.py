"""Exceptions raised by the college review / ranking services.

Kept in their own module so CollegeReviewService and RankingScopeMixin can both
raise them without an import cycle; college_review_service re-exports them.
"""


# Custom exceptions for college review operations
class CollegeReviewError(Exception):
    """Base exception for college review operations"""

    pass


class RankingNotFoundError(CollegeReviewError):
    """Raised when a ranking is not found"""

    pass


class RankingModificationError(CollegeReviewError):
    """Raised when attempting to modify a finalized ranking"""

    pass


class InvalidRankingDataError(CollegeReviewError):
    """Raised when ranking data is invalid"""

    pass


class ReviewPermissionError(CollegeReviewError):
    """Raised when user lacks permission for review operation"""

    pass


class RankingScopeConflictError(CollegeReviewError):
    """Raised when the ranking's scope forbids the operation (HTTP 409).

    E.g. creating a ranking while the scope holds a finalized or distributed one, or
    finalizing while a sibling ranking cannot be removed. Messages are user-facing.
    """

    pass

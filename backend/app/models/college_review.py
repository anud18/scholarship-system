"""
College review and ranking models for scholarship applications

This module defines the database models for college-level review processes,
including ranking, quota distribution, and final allocation decisions.
"""

from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

# Import types only for type checking to avoid circular imports
if TYPE_CHECKING:
    pass


def get_json_type():
    """Get appropriate JSON type based on database dialect"""
    try:
        from app.core.config import settings

        if "postgresql" in settings.database_url.lower():
            return JSONB
        else:
            return JSON
    except Exception:
        return JSON  # Fallback to standard JSON


class CollegeReview(Base):
    """
    College review model for scholarship applications

    Stores college-level review data including ranking scores,
    review comments, and final recommendations for each application.
    """

    __tablename__ = "college_reviews"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, unique=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Ranking and scoring
    ranking_score = Column(Numeric(8, 2))  # Overall ranking score (0-100)
    academic_score = Column(Numeric(5, 2))  # Academic performance score (0-100)
    professor_review_score = Column(Numeric(5, 2))  # Weighted professor review score (0-100)
    college_criteria_score = Column(Numeric(5, 2))  # College-specific criteria score (0-100)
    special_circumstances_score = Column(Numeric(5, 2))  # Special circumstances score (0-100)

    # Review details
    review_comments = Column(Text)  # Detailed review comments
    recommendation = Column(String(20))  # 'approve', 'reject', 'conditional'
    decision_reason = Column(Text)  # Reason for the recommendation

    # Ranking information
    preliminary_rank = Column(Integer)  # Initial ranking within sub-type
    final_rank = Column(Integer)  # Final ranking after adjustments
    sub_type_group = Column(String(50))  # Sub-type group for ranking

    # Review metadata
    review_status = Column(String(20), default="pending")  # 'pending', 'completed', 'revised'
    is_priority = Column(Boolean, default=False)  # Priority application flag
    needs_special_attention = Column(Boolean, default=False)  # Flag for special review

    # Scoring weights used (for audit trail)
    scoring_weights = Column(get_json_type())  # Store the weights used for this review

    # Time tracking
    review_started_at = Column(DateTime(timezone=True))
    reviewed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Database-level constraints for data integrity
    __table_args__ = (
        CheckConstraint(
            "academic_score IS NULL OR (academic_score >= 0 AND academic_score <= 100)",
            name="check_academic_score_range",
        ),
        CheckConstraint(
            "professor_review_score IS NULL OR (professor_review_score >= 0 AND professor_review_score <= 100)",
            name="check_professor_score_range",
        ),
        CheckConstraint(
            "college_criteria_score IS NULL OR (college_criteria_score >= 0 AND college_criteria_score <= 100)",
            name="check_college_score_range",
        ),
        CheckConstraint(
            "special_circumstances_score IS NULL OR (special_circumstances_score >= 0 AND special_circumstances_score <= 100)",
            name="check_special_score_range",
        ),
        CheckConstraint(
            "ranking_score IS NULL OR (ranking_score >= 0 AND ranking_score <= 100)",
            name="check_ranking_score_range",
        ),
    )

    # Relationships using string references to avoid circular dependencies
    application = relationship("Application", lazy="select", foreign_keys=[application_id])
    reviewer = relationship("User", lazy="select", foreign_keys=[reviewer_id])

    def __repr__(self):
        return (
            f"<CollegeReview(id={self.id}, application_id={self.application_id}, ranking_score={self.ranking_score})>"
        )

    @property
    def is_completed(self) -> bool:
        """Check if the review is completed"""
        return self.review_status == "completed"

    @property
    def is_recommended(self) -> bool:
        """Check if the application is recommended for approval"""
        return self.recommendation == "approve"

    def calculate_total_score(self, weights: Optional[Dict[str, float]] = None) -> float:
        """
        Calculate total weighted score based on individual component scores

        Args:
            weights: Dictionary of scoring weights. If None, uses default weights.

        Returns:
            Total weighted score (0-100)
        """
        if not weights:
            weights = {
                "academic": 0.30,
                "professor_review": 0.40,
                "college_criteria": 0.20,
                "special_circumstances": 0.10,
            }

        scores = {
            "academic": self.academic_score or 0,
            "professor_review": self.professor_review_score or 0,
            "college_criteria": self.college_criteria_score or 0,
            "special_circumstances": self.special_circumstances_score or 0,
        }

        total_score = sum(scores[key] * weights.get(key, 0) for key in scores)
        return round(total_score, 2)


class CollegeRanking(Base):
    """
    College ranking model for managing ranked lists of applications

    This model maintains the ranked order of applications within each
    scholarship sub-type group for quota distribution purposes.
    """

    __tablename__ = "college_rankings"

    id = Column(Integer, primary_key=True, index=True)
    scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=False)
    sub_type_code = Column(String(50), nullable=False)
    academic_year = Column(Integer, nullable=False)
    semester = Column(String(20))  # Can be null for yearly scholarships

    # Ranking metadata
    ranking_name = Column(String(200))  # Descriptive name for this ranking
    total_applications = Column(Integer, default=0)
    total_quota = Column(Integer)  # Available quota for this sub-type
    allocated_count = Column(Integer, default=0)  # Number of applications allocated

    # Ranking status
    is_finalized = Column(Boolean, default=False)
    ranking_status = Column(String(20), default="draft")  # 'draft', 'review', 'finalized'

    # Distribution information
    distribution_executed = Column(Boolean, default=False)
    distribution_date = Column(DateTime(timezone=True))
    github_issue_url = Column(String(500))  # Link to generated GitHub issue

    # Time tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    finalized_at = Column(DateTime(timezone=True))
    created_by = Column(Integer, ForeignKey("users.id"))
    finalized_by = Column(Integer, ForeignKey("users.id"))

    # Relationships using string references to avoid circular imports
    scholarship_type = relationship("ScholarshipType", lazy="select")
    items = relationship("CollegeRankingItem", back_populates="ranking", cascade="all, delete-orphan")
    creator = relationship("User", foreign_keys=[created_by], lazy="select")
    finalizer = relationship("User", foreign_keys=[finalized_by], lazy="select")

    def __repr__(self):
        return f"<CollegeRanking(id={self.id}, sub_type={self.sub_type_code}, total={self.total_applications})>"

    @property
    def remaining_quota(self) -> int:
        """Calculate remaining quota"""
        if not self.total_quota:
            return 0
        return max(0, self.total_quota - self.allocated_count)

    @property
    def allocation_rate(self) -> float:
        """Calculate allocation rate percentage"""
        if not self.total_applications:
            return 0.0
        return (self.allocated_count / self.total_applications) * 100

    def can_allocate_more(self) -> bool:
        """Check if more applications can be allocated"""
        return self.remaining_quota > 0 and not self.distribution_executed


class CollegeRankingItem(Base):
    """
    Individual ranking item within a college ranking

    Represents a single application's position within a ranked list
    for quota distribution.
    """

    __tablename__ = "college_ranking_items"

    id = Column(Integer, primary_key=True, index=True)
    ranking_id = Column(Integer, ForeignKey("college_rankings.id"), nullable=False)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    college_review_id = Column(Integer, ForeignKey("college_reviews.id"), nullable=False)

    # Ranking position
    rank_position = Column(Integer, nullable=False)  # 1-based ranking position
    is_allocated = Column(Boolean, default=False)  # Whether quota was allocated
    allocation_reason = Column(Text)  # Reason for allocation/rejection

    # Scoring information (cached from college review)
    total_score = Column(Numeric(8, 2))
    tie_breaker_applied = Column(Boolean, default=False)
    tie_breaker_reason = Column(Text)

    # Status tracking
    status = Column(String(20), default="ranked")  # 'ranked', 'allocated', 'rejected', 'waitlisted'

    # Time tracking
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships using string references to avoid circular imports
    ranking = relationship("CollegeRanking", back_populates="items")
    application = relationship("Application", lazy="select", foreign_keys=[application_id])
    college_review = relationship("CollegeReview", lazy="select", foreign_keys=[college_review_id])

    def __repr__(self):
        return f"<CollegeRankingItem(id={self.id}, rank={self.rank_position}, allocated={self.is_allocated})>"

    @property
    def is_within_quota(self) -> bool:
        """Check if this rank position is within the available quota"""
        if not self.ranking.total_quota:
            return False
        return self.rank_position <= self.ranking.total_quota


class QuotaDistribution(Base):
    """
    Quota distribution record for audit and tracking purposes

    Maintains a historical record of all quota distribution executions
    including the algorithms used and results achieved.
    """

    __tablename__ = "quota_distributions"

    id = Column(Integer, primary_key=True, index=True)
    distribution_name = Column(String(200), nullable=False)
    academic_year = Column(Integer, nullable=False)
    semester = Column(String(20))

    # Distribution parameters
    total_applications = Column(Integer)
    total_quota = Column(Integer)
    total_allocated = Column(Integer)

    # Algorithm information
    algorithm_version = Column(String(50))  # Version of distribution algorithm used
    scoring_weights = Column(get_json_type())  # Weights used for scoring
    distribution_rules = Column(get_json_type())  # Rules and constraints applied

    # Results summary
    distribution_summary = Column(get_json_type())  # Summary statistics by sub-type
    exceptions = Column(get_json_type())  # Any exceptions or manual interventions

    # GitHub integration
    github_issue_number = Column(Integer)
    github_issue_url = Column(String(500))

    # Time tracking
    executed_at = Column(DateTime(timezone=True), server_default=func.now())
    executed_by = Column(Integer, ForeignKey("users.id"))

    # Relationships using string references to avoid circular imports
    executor = relationship("User", lazy="select", foreign_keys=[executed_by])

    def __repr__(self):
        return f"<QuotaDistribution(id={self.id}, name={self.distribution_name}, executed_at={self.executed_at})>"

    @property
    def success_rate(self) -> float:
        """Calculate the success rate of the distribution"""
        if not self.total_applications:
            return 0.0
        return (self.total_allocated / self.total_applications) * 100

    def get_sub_type_summary(self, sub_type: str) -> Optional[Dict[str, Any]]:
        """Get distribution summary for a specific sub-type"""
        if not self.distribution_summary:
            return None
        return self.distribution_summary.get(sub_type)


# PostgreSQL-optimized indexes for college review tables
# These indexes will be automatically created when using PostgreSQL

# Index for efficient college review lookups
Index(
    "ix_college_reviews_application_reviewer",
    CollegeReview.application_id,
    CollegeReview.reviewer_id,
)
Index("ix_college_reviews_ranking_score", CollegeReview.ranking_score.desc())  # For ranking queries
Index(
    "ix_college_reviews_recommendation_status",
    CollegeReview.recommendation,
    CollegeReview.review_status,
)
Index(
    "ix_college_reviews_priority_attention",
    CollegeReview.is_priority,
    CollegeReview.needs_special_attention,
)

# Index for ranking queries
Index(
    "ix_college_rankings_lookup",
    CollegeRanking.scholarship_type_id,
    CollegeRanking.sub_type_code,
    CollegeRanking.academic_year,
    CollegeRanking.semester,
)
Index(
    "ix_college_rankings_status_finalized",
    CollegeRanking.ranking_status,
    CollegeRanking.is_finalized,
)

# Index for ranking items
Index(
    "ix_college_ranking_items_position",
    CollegeRankingItem.ranking_id,
    CollegeRankingItem.rank_position,
)
Index(
    "ix_college_ranking_items_allocation",
    CollegeRankingItem.is_allocated,
    CollegeRankingItem.status,
)
Index("ix_college_ranking_items_score", CollegeRankingItem.total_score.desc())

# Index for quota distribution tracking
Index(
    "ix_quota_distributions_academic_year",
    QuotaDistribution.academic_year,
    QuotaDistribution.semester,
)
Index(
    "ix_quota_distributions_execution",
    QuotaDistribution.executed_at,
    QuotaDistribution.executed_by,
)

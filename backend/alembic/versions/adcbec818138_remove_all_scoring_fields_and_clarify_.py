"""remove_all_scoring_fields_and_clarify_student_data

Revision ID: adcbec818138
Revises: 07e9ece93d90
Create Date: 2025-10-22 19:34:23.063970

Removes all scoring/rating fields from Application, ApplicationReview, and CollegeReview models.
Clarifies that student_data should contain only SIS API data snapshot.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "adcbec818138"
down_revision: Union[str, None] = "07e9ece93d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove all scoring fields from review tables"""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    # === Application Table ===
    application_columns = {col["name"] for col in inspector.get_columns("applications")}

    # Drop scoring fields from applications table
    if "review_score" in application_columns:
        op.drop_column("applications", "review_score")
    if "review_comments" in application_columns:
        op.drop_column("applications", "review_comments")
    if "rejection_reason" in application_columns:
        op.drop_column("applications", "rejection_reason")
    if "priority_score" in application_columns:
        op.drop_column("applications", "priority_score")
    if "college_ranking_score" in application_columns:
        op.drop_column("applications", "college_ranking_score")

    # === ApplicationReview Table ===
    review_columns = {col["name"] for col in inspector.get_columns("application_reviews")}

    # Drop scoring fields from application_reviews table
    if "score" in review_columns:
        op.drop_column("application_reviews", "score")
    if "criteria_scores" in review_columns:
        op.drop_column("application_reviews", "criteria_scores")

    # === CollegeReview Table ===
    # Skip if college_reviews table doesn't exist
    if "college_reviews" not in tables:
        print("⊘ Skipping college_reviews modifications: table does not exist")
        return

    college_review_columns = {col["name"] for col in inspector.get_columns("college_reviews")}

    # Drop constraints first (PostgreSQL specific)
    constraints = [
        "check_academic_score_range",
        "check_professor_score_range",
        "check_college_score_range",
        "check_special_score_range",
        "check_ranking_score_range",
    ]

    try:
        existing_constraints = [c["name"] for c in inspector.get_check_constraints("college_reviews")]
        for constraint_name in constraints:
            if constraint_name in existing_constraints:
                op.drop_constraint(constraint_name, "college_reviews", type_="check")
    except Exception:
        # SQLite doesn't support dropping constraints
        pass

    # Drop index (PostgreSQL specific)
    try:
        existing_indexes = [idx["name"] for idx in inspector.get_indexes("college_reviews")]
        if "ix_college_reviews_ranking_score" in existing_indexes:
            op.drop_index("ix_college_reviews_ranking_score", "college_reviews")
    except Exception:
        # SQLite may not have this index
        pass

    # Drop scoring fields from college_reviews table
    if "ranking_score" in college_review_columns:
        op.drop_column("college_reviews", "ranking_score")
    if "academic_score" in college_review_columns:
        op.drop_column("college_reviews", "academic_score")
    if "professor_review_score" in college_review_columns:
        op.drop_column("college_reviews", "professor_review_score")
    if "college_criteria_score" in college_review_columns:
        op.drop_column("college_reviews", "college_criteria_score")
    if "special_circumstances_score" in college_review_columns:
        op.drop_column("college_reviews", "special_circumstances_score")
    if "scoring_weights" in college_review_columns:
        op.drop_column("college_reviews", "scoring_weights")


def downgrade() -> None:
    """Restore scoring fields (not recommended)"""
    # Application table
    op.add_column("applications", sa.Column("review_score", sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column("applications", sa.Column("review_comments", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("priority_score", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("applications", sa.Column("college_ranking_score", sa.Numeric(precision=8, scale=2), nullable=True))

    # ApplicationReview table
    op.add_column("application_reviews", sa.Column("score", sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column("application_reviews", sa.Column("criteria_scores", sa.JSON(), nullable=True))

    # CollegeReview table - add columns
    op.add_column("college_reviews", sa.Column("ranking_score", sa.Numeric(precision=8, scale=2), nullable=True))
    op.add_column("college_reviews", sa.Column("academic_score", sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column(
        "college_reviews", sa.Column("professor_review_score", sa.Numeric(precision=5, scale=2), nullable=True)
    )
    op.add_column(
        "college_reviews", sa.Column("college_criteria_score", sa.Numeric(precision=5, scale=2), nullable=True)
    )
    op.add_column(
        "college_reviews", sa.Column("special_circumstances_score", sa.Numeric(precision=5, scale=2), nullable=True)
    )
    op.add_column("college_reviews", sa.Column("scoring_weights", sa.JSON(), nullable=True))

    # CollegeReview table - add constraints (PostgreSQL only)
    try:
        op.create_check_constraint(
            "check_academic_score_range",
            "college_reviews",
            "academic_score IS NULL OR (academic_score >= 0 AND academic_score <= 100)",
        )
        op.create_check_constraint(
            "check_professor_score_range",
            "college_reviews",
            "professor_review_score IS NULL OR (professor_review_score >= 0 AND professor_review_score <= 100)",
        )
        op.create_check_constraint(
            "check_college_score_range",
            "college_reviews",
            "college_criteria_score IS NULL OR (college_criteria_score >= 0 AND college_criteria_score <= 100)",
        )
        op.create_check_constraint(
            "check_special_score_range",
            "college_reviews",
            "special_circumstances_score IS NULL OR (special_circumstances_score >= 0 AND special_circumstances_score <= 100)",
        )
        op.create_check_constraint(
            "check_ranking_score_range",
            "college_reviews",
            "ranking_score IS NULL OR (ranking_score >= 0 AND ranking_score <= 100)",
        )

        # Add index
        op.create_index("ix_college_reviews_ranking_score", "college_reviews", ["ranking_score"], unique=False)
    except Exception:
        # SQLite doesn't support check constraints in alembic
        pass

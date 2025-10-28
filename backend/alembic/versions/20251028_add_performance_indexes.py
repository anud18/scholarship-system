"""add performance indexes for unified review system

Revision ID: 20251028_add_indexes
Revises: 20251028_drop_college
Create Date: 2025-10-28

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20251028_add_indexes"
down_revision: Union[str, None] = "20251028_drop_college"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Indexes for ApplicationReview (unified review system)
    op.create_index(
        "ix_application_reviews_application_reviewer",
        "application_reviews",
        ["application_id", "reviewer_id"],
    )
    op.create_index(
        "ix_application_reviews_reviewed_at",
        "application_reviews",
        ["reviewed_at"],
    )

    # Indexes for ApplicationReviewItem (sub-type specific reviews)
    op.create_index(
        "ix_application_review_items_review_subtype",
        "application_review_items",
        ["review_id", "sub_type"],
    )
    op.create_index(
        "ix_application_review_items_recommendation",
        "application_review_items",
        ["recommendation"],
    )
    op.create_index(
        "ix_application_review_items_subtype_recommendation",
        "application_review_items",
        ["sub_type", "recommendation"],
    )

    # Indexes for Application (enhanced queries)
    op.create_index(
        "ix_applications_final_ranking_position",
        "applications",
        ["final_ranking_position"],
    )
    op.create_index(
        "ix_applications_review_stage",
        "applications",
        ["review_stage"],
    )
    op.create_index(
        "ix_applications_status_stage",
        "applications",
        ["status", "review_stage"],
    )
    op.create_index(
        "ix_applications_scholarship_academic_semester",
        "applications",
        ["scholarship_type_id", "academic_year", "semester"],
    )


def downgrade() -> None:
    # Drop Application indexes
    op.drop_index("ix_applications_scholarship_academic_semester", table_name="applications")
    op.drop_index("ix_applications_status_stage", table_name="applications")
    op.drop_index("ix_applications_review_stage", table_name="applications")
    op.drop_index("ix_applications_final_ranking_position", table_name="applications")

    # Drop ApplicationReviewItem indexes
    op.drop_index("ix_application_review_items_subtype_recommendation", table_name="application_review_items")
    op.drop_index("ix_application_review_items_recommendation", table_name="application_review_items")
    op.drop_index("ix_application_review_items_review_subtype", table_name="application_review_items")

    # Drop ApplicationReview indexes
    op.drop_index("ix_application_reviews_reviewed_at", table_name="application_reviews")
    op.drop_index("ix_application_reviews_application_reviewer", table_name="application_reviews")

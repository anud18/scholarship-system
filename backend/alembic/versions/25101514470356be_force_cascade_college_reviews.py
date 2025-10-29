"""
Force cascade deletes for college review foreign keys

Revision ID: 25101514470356be
Revises: d5e18b9d8e3a
Create Date: 2025-10-15 14:47:03.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "25101514470356be"
down_revision: Union[str, None] = "7b3f6d9c894f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # College ranking items -> college reviews
    op.execute(
        """
        ALTER TABLE college_ranking_items
        DROP CONSTRAINT IF EXISTS college_ranking_items_college_review_id_fkey;
        """
    )
    op.execute(
        """
        ALTER TABLE college_ranking_items
        ADD CONSTRAINT college_ranking_items_college_review_id_fkey
        FOREIGN KEY (college_review_id)
        REFERENCES college_reviews(id)
        ON DELETE CASCADE;
        """
    )

    # College reviews -> applications
    op.execute(
        """
        ALTER TABLE college_reviews
        DROP CONSTRAINT IF EXISTS college_reviews_application_id_fkey;
        """
    )
    op.execute(
        """
        ALTER TABLE college_reviews
        ADD CONSTRAINT college_reviews_application_id_fkey
        FOREIGN KEY (application_id)
        REFERENCES applications(id)
        ON DELETE CASCADE;
        """
    )


def downgrade() -> None:
    # Revert college reviews -> applications
    op.execute(
        """
        ALTER TABLE college_reviews
        DROP CONSTRAINT IF EXISTS college_reviews_application_id_fkey;
        """
    )
    op.execute(
        """
        ALTER TABLE college_reviews
        ADD CONSTRAINT college_reviews_application_id_fkey
        FOREIGN KEY (application_id)
        REFERENCES applications(id);
        """
    )

    # Revert college ranking items -> college reviews
    op.execute(
        """
        ALTER TABLE college_ranking_items
        DROP CONSTRAINT IF EXISTS college_ranking_items_college_review_id_fkey;
        """
    )
    op.execute(
        """
        ALTER TABLE college_ranking_items
        ADD CONSTRAINT college_ranking_items_college_review_id_fkey
        FOREIGN KEY (college_review_id)
        REFERENCES college_reviews(id);
        """
    )

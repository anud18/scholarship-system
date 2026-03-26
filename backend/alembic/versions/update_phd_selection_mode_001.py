"""Change PhD scholarship sub_type_selection_mode from hierarchical to multiple

Students can now apply for MOE without first selecting NSTC.

Revision ID: update_phd_sel_mode_001
Revises: add_sub_type_prefs_001
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

revision = "update_phd_sel_mode_001"
down_revision = "add_sub_type_prefs_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Update PhD scholarship types from hierarchical to multiple selection mode
    op.execute(
        sa.text(
            "UPDATE scholarship_types "
            "SET sub_type_selection_mode = 'multiple' "
            "WHERE code = 'phd' AND sub_type_selection_mode = 'hierarchical'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE scholarship_types "
            "SET sub_type_selection_mode = 'hierarchical' "
            "WHERE code = 'phd' AND sub_type_selection_mode = 'multiple'"
        )
    )

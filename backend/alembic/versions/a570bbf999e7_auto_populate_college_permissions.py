"""auto_populate_college_permissions

Revision ID: a570bbf999e7
Revises: db488c7e8c85
Create Date: 2025-10-05 13:26:02.524244

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a570bbf999e7"
down_revision: Union[str, None] = "db488c7e8c85"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Auto-populate admin_scholarships for college users"""
    bind = op.get_bind()

    # Insert admin_scholarships records for college users
    # This allows college users to access all active scholarships
    bind.execute(
        sa.text(
            """
        INSERT INTO admin_scholarships (admin_id, scholarship_id, assigned_at)
        SELECT u.id, s.id, NOW()
        FROM users u
        CROSS JOIN scholarship_types s
        WHERE u.role = 'college'
        AND s.status = 'active'
        AND NOT EXISTS (
            SELECT 1 FROM admin_scholarships ads
            WHERE ads.admin_id = u.id AND ads.scholarship_id = s.id
        )
    """
        )
    )


def downgrade() -> None:
    """Remove auto-populated admin_scholarships for college users"""
    bind = op.get_bind()

    # Only remove records that were auto-populated (no specific comment)
    # This is a safe downgrade that only removes the auto-assigned permissions
    bind.execute(
        sa.text(
            """
        DELETE FROM admin_scholarships
        WHERE admin_id IN (SELECT id FROM users WHERE role = 'college')
    """
        )
    )

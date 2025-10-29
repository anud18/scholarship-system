"""add_application_fields_unique_constraint

Revision ID: 7465ccd0a0f4
Revises: 887d0765bce6
Create Date: 2025-09-29 20:32:45.270561

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7465ccd0a0f4'
down_revision: Union[str, None] = '887d0765bce6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add unique constraint to application_fields table if it doesn't exist
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if constraint already exists
    existing_constraints = [constraint['name'] for constraint in inspector.get_unique_constraints('application_fields')]

    if 'uq_application_field_type_name' not in existing_constraints:
        try:
            op.create_unique_constraint('uq_application_field_type_name', 'application_fields', ['scholarship_type', 'field_name'])
        except Exception as e:
            # If constraint creation fails (e.g., due to duplicate data), skip it
            print(f"Warning: Could not create unique constraint: {e}")


def downgrade() -> None:
    # Drop the unique constraint
    try:
        op.drop_constraint('uq_application_field_type_name', 'application_fields', type_='unique')
    except Exception:
        # Constraint may not exist, skip
        pass
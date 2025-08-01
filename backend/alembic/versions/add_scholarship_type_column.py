"""Add scholarship_type column for backward compatibility

Revision ID: add_scholarship_type_column
Revises: 002_enhance_applications
Create Date: 2025-08-01 03:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'add_scholarship_type_column'
down_revision = '002_enhance_applications'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add scholarship_type column for backward compatibility
    op.add_column('applications', sa.Column('scholarship_type', sa.String(length=50), nullable=True))
    
    # Update existing records with a default value based on scholarship_type_id
    # This query will set scholarship_type to the code of the corresponding scholarship
    op.execute("""
        UPDATE applications 
        SET scholarship_type = COALESCE(st.code, 'unknown')
        FROM scholarship_types st 
        WHERE applications.scholarship_type_id = st.id
    """)
    
    # For records without a matching scholarship_type_id, set a default
    op.execute("UPDATE applications SET scholarship_type = 'unknown' WHERE scholarship_type IS NULL")


def downgrade() -> None:
    # Remove the scholarship_type column
    op.drop_column('applications', 'scholarship_type')
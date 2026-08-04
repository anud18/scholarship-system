"""update master_school_info field labels, placeholder, and help_text

Revision ID: update_master_school_info_001
Revises: add_college_rejected_001, b7c3a1f8d290
Create Date: 2026-04-28 02:30:00.000000

Updates the phd master_school_info application field:
- field_label: 碩士畢業學校學院系所 -> 碩士畢業學校/學院/系所
- placeholder: shorter, more direct example
- help_text: clarifies which department to fill for 碩逕博 vs 學逕博

Also serves as a merge revision for the two divergent heads:
add_college_rejected_001 and b7c3a1f8d290.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "update_master_school_info_001"
down_revision: Union[str, Sequence[str], None] = (
    "add_college_rejected_001",
    "b7c3a1f8d290",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE application_fields
        SET
            field_label = '碩士畢業學校/學院/系所',
            placeholder = '陽明交通大學工學院土木工程學系',
            placeholder_en = 'e.g., NYCU College of Engineering, Department of Civil Engineering',
            help_text = E'1.碩逕博請填原就讀碩士班、學逕博請填學士班畢業學系\n2.請填完整名稱',
            help_text_en = E'1. PhD via Master''s: provide the original Master''s program; PhD via Bachelor''s: provide the Bachelor''s department.\n2. Please provide the complete name.'
        WHERE scholarship_type = 'phd' AND field_name = 'master_school_info'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE application_fields
        SET
            field_label = '碩士畢業學校學院系所',
            placeholder = '例如：國立陽明交通大學 資訊學院 資訊工程學系',
            placeholder_en = 'e.g., NYCU College of Computer Science, Department of Computer Science',
            help_text = '請填寫完整的畢業學校、學院、系所名稱',
            help_text_en = 'Please provide complete school, college, and department names'
        WHERE scholarship_type = 'phd' AND field_name = 'master_school_info'
        """
    )

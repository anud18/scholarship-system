"""Seed PhD application fields for college Excel export

Flag the existing PhD dynamic fields (master_school_info, contact_phone)
for college export, and insert two missing fields the sample 學生資料彙整表
expects (student_address, bank_account).

Idempotent — safe to re-run.

Revision ID: seed_phd_college_export_001
Revises: add_college_export_flag_001
Create Date: 2026-05-09
"""

import sqlalchemy as sa
from alembic import op

revision = "seed_phd_college_export_001"
down_revision = "add_college_export_flag_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Enable export flag on existing PhD fields.
    bind.execute(
        sa.text(
            """
            UPDATE application_fields
               SET include_in_college_export = true
             WHERE scholarship_type = 'phd'
               AND field_name = 'master_school_info'
               AND include_in_college_export IS DISTINCT FROM true
            """
        )
    )

    # contact_phone shows up in the export with the 學生手機 column header.
    bind.execute(
        sa.text(
            """
            UPDATE application_fields
               SET include_in_college_export = true,
                   export_column_label = '學生手機'
             WHERE scholarship_type = 'phd'
               AND field_name = 'contact_phone'
               AND (
                    include_in_college_export IS DISTINCT FROM true
                 OR export_column_label IS DISTINCT FROM '學生手機'
               )
            """
        )
    )

    # NOTE: 學生匯款帳號 and 學生通訊地址 are NOT seeded as dynamic fields —
    # the bank account lives on user_profiles.account_number (collected by
    # the application wizard's bank-account step), and the address comes
    # from the SIS API field student_data.com_commadd. Both are rendered as
    # STATIC columns by CollegeRankingExportService.
    # Only flag flips (above) are needed.


def downgrade() -> None:
    bind = op.get_bind()

    bind.execute(
        sa.text(
            """
            UPDATE application_fields
               SET include_in_college_export = false,
                   export_column_label = NULL
             WHERE scholarship_type = 'phd'
               AND field_name IN ('master_school_info', 'contact_phone')
            """
        )
    )

    # No dynamic field rows to remove — only flag flips were applied in upgrade().

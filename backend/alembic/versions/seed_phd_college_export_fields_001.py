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

    # 2. Insert missing dynamic fields (idempotent via ON CONFLICT).
    new_fields = [
        {
            "scholarship_type": "phd",
            "field_name": "student_address",
            "field_label": "學生通訊地址",
            "field_label_en": "Student Mailing Address",
            "field_type": "text",
            "is_required": True,
            "placeholder": "例:台北市北投區義理街3段5巷1號",
            "placeholder_en": "e.g., No. 1, Lane 5, Sec. 3, Yili St., Beitou, Taipei",
            "max_length": 200,
            "display_order": 3,
            "is_active": True,
            "include_in_college_export": True,
            "export_column_label": "學生通訊地址",
        },
        {
            "scholarship_type": "phd",
            "field_name": "bank_account",
            "field_label": "學生匯款帳號",
            "field_label_en": "Student Bank Account",
            "field_type": "text",
            "is_required": True,
            "placeholder": "EX:277506027171 請提供郵局帳戶",
            "placeholder_en": "e.g., 277506027171 (please provide a Chunghwa Post account)",
            "max_length": 50,
            "display_order": 4,
            "is_active": True,
            "include_in_college_export": True,
            "export_column_label": "學生匯款帳號",
        },
    ]

    for field in new_fields:
        bind.execute(
            sa.text(
                """
                INSERT INTO application_fields
                    (scholarship_type, field_name, field_label, field_label_en,
                     field_type, is_required, placeholder, placeholder_en,
                     max_length, display_order, is_active,
                     include_in_college_export, export_column_label)
                VALUES
                    (:scholarship_type, :field_name, :field_label, :field_label_en,
                     :field_type, :is_required, :placeholder, :placeholder_en,
                     :max_length, :display_order, :is_active,
                     :include_in_college_export, :export_column_label)
                ON CONFLICT (scholarship_type, field_name) DO UPDATE SET
                    include_in_college_export = EXCLUDED.include_in_college_export,
                    export_column_label = EXCLUDED.export_column_label,
                    is_active = EXCLUDED.is_active
                """
            ),
            field,
        )


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

    bind.execute(
        sa.text(
            """
            DELETE FROM application_fields
             WHERE scholarship_type = 'phd'
               AND field_name IN ('student_address', 'bank_account')
            """
        )
    )

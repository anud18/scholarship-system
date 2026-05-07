"""Add required contact_phone field to all scholarship application forms (#60)

Revision ID: add_contact_phone_field_001
Revises: enable_automation_rules_001
Create Date: 2026-05-07 06:00:00.000000

Per the 0421/0428 meeting notes (#60), the student application form needs
a required "聯絡電話" (contact_phone) input that stores into
submitted_form_data.fields.contact_phone. The field is added to every
scholarship_type currently in the application_fields table.

Validation pattern accepts:
  - Taiwan mobile:  09XXXXXXXX (10 digits starting with 09)
  - Taiwan landline: 0X-XXXXXXXX or 0XXXXXXXXX (8-9 digits with optional area code)
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "add_contact_phone_field_001"
down_revision: Union[str, None] = "enable_automation_rules_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CONTACT_PHONE_VALIDATION = {
    "pattern": r"^09\d{8}$|^0\d{1,2}-?\d{6,8}$",
    "patternMessage": "請輸入有效的台灣手機 (09xxxxxxxx) 或市話 (含區碼)",
}


def upgrade() -> None:
    bind = op.get_bind()

    # Discover all scholarship_types that currently have at least one
    # application_field row OR are defined in scholarship_types table.
    types_result = bind.execute(
        sa.text(
            """
            SELECT DISTINCT t FROM (
                SELECT scholarship_type AS t FROM application_fields
                UNION
                SELECT code AS t FROM scholarship_types
            ) s
            WHERE t IS NOT NULL
            """
        )
    )
    scholarship_types = [row[0] for row in types_result]

    if not scholarship_types:
        return

    # Compute a sensible display_order: just past the current max for each type.
    for stype in scholarship_types:
        max_order = bind.execute(
            sa.text(
                "SELECT COALESCE(MAX(display_order), 0) FROM application_fields "
                "WHERE scholarship_type = :stype"
            ),
            {"stype": stype},
        ).scalar() or 0

        # Idempotent: skip if contact_phone already exists for this type.
        existing = bind.execute(
            sa.text(
                "SELECT 1 FROM application_fields "
                "WHERE scholarship_type = :stype AND field_name = 'contact_phone'"
            ),
            {"stype": stype},
        ).first()
        if existing:
            continue

        bind.execute(
            sa.text(
                """
                INSERT INTO application_fields (
                    scholarship_type, field_name, field_label, field_label_en,
                    field_type, is_required, placeholder, placeholder_en,
                    max_length, display_order, is_active, validation_rules,
                    help_text, help_text_en
                ) VALUES (
                    :stype, 'contact_phone', '聯絡電話', 'Contact Phone',
                    'text', TRUE, '0912345678', '0912345678',
                    20, :order, TRUE, CAST(:validation AS JSON),
                    '若有審核問題，將以此電話聯絡您。',
                    'Used by the review team to reach you about your application.'
                )
                """
            ),
            {
                "stype": stype,
                "order": max_order + 1,
                "validation": json.dumps(CONTACT_PHONE_VALIDATION),
            },
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM application_fields WHERE field_name = 'contact_phone'"
    )

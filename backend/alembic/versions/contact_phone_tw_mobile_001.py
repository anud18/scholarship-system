"""Tighten contact_phone validation to Taiwan mobile only (09 + 8 digits)

Revision ID: contact_phone_tw_mobile_001
Revises: add_roster_student_number_001
Create Date: 2026-06-09 00:00:00.000000

Per request, the student application 聯絡電話 (contact_phone) field must:
  - show the help text "請輸入本人有效的台灣手機 (09xxxxxx)"
  - only accept a pure-digit Taiwan mobile number: starts with 09, 10 digits.

This supersedes ``add_contact_phone_field_001`` (which also accepted landline
numbers). It updates the validation_rules JSON on every existing contact_phone
row across all scholarship types.
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "contact_phone_tw_mobile_001"
down_revision: Union[str, None] = "add_roster_student_number_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Taiwan mobile only: 09 followed by exactly 8 digits (10 digits total, pure numbers).
NEW_VALIDATION = {
    "pattern": r"^09\d{8}$",
    "patternMessage": "請輸入本人有效的台灣手機 (09xxxxxx)",
}

# Previous rule (mobile OR landline) restored on downgrade.
OLD_VALIDATION = {
    "pattern": r"^09\d{8}$|^0\d{1,2}-?\d{6,8}$",
    "patternMessage": "請輸入有效的台灣手機 (09xxxxxxxx) 或市話 (含區碼)",
}


def _set_validation(rules: dict) -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE application_fields "
            "SET validation_rules = CAST(:rules AS JSON) "
            "WHERE field_name = 'contact_phone'"
        ),
        {"rules": json.dumps(rules)},
    )


def upgrade() -> None:
    _set_validation(NEW_VALIDATION)


def downgrade() -> None:
    _set_validation(OLD_VALIDATION)

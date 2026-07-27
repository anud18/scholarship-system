"""zh-TW labels for the dynamic form fields stored in an application.

`Application.submitted_form_data["fields"]` entries carry only the English
`field_id` (see `app.schemas.application.DynamicFormField` — there is no
`label` key), so every surface that renders submitted form data has to
resolve the Chinese label itself.

Two sources feed the map:
- `application_fields.field_label` — the admin-configured fields, keyed by
  `ScholarshipType.code`.
- `FIXED_FIELD_LABELS` — built-in ids that are NOT rows in `application_fields`
  and so have no admin-configured label, making this module their only source.
"""

from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_field import ApplicationField

# field_id -> zh-TW label for the built-in ids, none of which is an
# application_fields row:
#   postal_account / advisor_* — injected into the form config at runtime by
#     ApplicationFieldService._create_fixed_bank_account_field and
#     _create_fixed_advisor_fields.
#   account_number / bank_account — account ids minted client-side or carried
#     by older submissions; both are probed as stored field keys by
#     bank_verification_service, roster_service and payment_rosters.
FIXED_FIELD_LABELS: Dict[str, str] = {
    "postal_account": "郵局帳號",
    "account_number": "郵局帳號",
    "bank_account": "銀行帳戶",
    "advisor_name": "指導教授姓名",
    "advisor_email": "指導教授Email",
    "advisor_nycu_id": "指導教授本校人事編號",
}

# The ids that carry the one account number a student typed. They resolve to
# the same label, so the summary PDF prints only the first of an identical
# (label, value) pair — see _generate_summary_pdf.
ACCOUNT_FIELD_SYNONYMS = frozenset({"postal_account", "account_number"})


async def load_form_field_labels(db: AsyncSession, scholarship_code: Optional[str]) -> Dict[str, str]:
    """Build the field_id -> zh-TW label map for one scholarship type.

    Uses `field_label`, not `export_column_label`: the latter renames a column
    of the 學生資料彙整表 workbook (phd/contact_phone exports as 學生手機), which
    is not what the form field is called on a form-data page.

    Admin-configured rows win over the fixed defaults: `bulk_update_fields`
    re-inserts whatever the admin UI posts, so a fixed field can also exist as
    a real row, and then the admin owns its label.

    Deliberately NOT filtered by `is_active`, so a field deactivated after a
    student submitted still renders. Note this cannot rescue a field the admin
    *removed*: `bulk_update_fields` hard-deletes rows, and `resolve_field_label`
    then falls back to the raw id for those historical submissions.
    """
    labels = dict(FIXED_FIELD_LABELS)
    if not scholarship_code:
        return labels

    stmt = select(ApplicationField.field_name, ApplicationField.field_label).where(
        ApplicationField.scholarship_type == scholarship_code
    )
    for field_name, field_label in (await db.execute(stmt)).all():
        if field_name and field_label:
            labels[field_name] = field_label
    return labels


def resolve_field_label(field_id: str, labels: Dict[str, str]) -> str:
    """zh-TW label for one field id, falling back to the raw id.

    Admin-created ids and batch-import `custom_<x>` columns can have no
    definition at all — showing the raw id beats showing nothing.
    """
    return labels.get(field_id) or field_id

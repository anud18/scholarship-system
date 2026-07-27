"""zh-TW labels for the dynamic form fields stored in an application.

`Application.submitted_form_data["fields"]` entries carry only the English
`field_id` (see `app.schemas.application.DynamicFormField` — there is no
`label` key), so every surface that renders submitted form data has to
resolve the Chinese label itself.

Two sources feed the map:
- `application_fields.field_label` — the admin-configured fields, keyed by
  `ScholarshipType.code`.
- `FIXED_FIELD_LABELS` — the "fixed" fields `ApplicationFieldService` injects
  into the form config at runtime. They are NOT rows in `application_fields`,
  so this module is their single source of truth.
"""

from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_field import ApplicationField

# field_id -> zh-TW label for the fields injected by
# ApplicationFieldService._create_fixed_bank_account_field /
# _create_fixed_advisor_fields, which have no application_fields row.
FIXED_FIELD_LABELS: Dict[str, str] = {
    "postal_account": "郵局帳號",
    # Minted by the student wizard next to postal_account (see
    # buildApplicationFormFields) and carries the same 郵局帳號 value.
    "account_number": "郵局帳號",
    "advisor_name": "指導教授姓名",
    "advisor_email": "指導教授Email",
    "advisor_nycu_id": "指導教授本校人事編號",
}


async def load_form_field_labels(db: AsyncSession, scholarship_code: Optional[str]) -> Dict[str, str]:
    """Build the field_id -> zh-TW label map for one scholarship type.

    Admin-configured rows win over the fixed defaults: `bulk_update_fields`
    re-inserts whatever the admin UI posts, so a fixed field can also exist as
    a real row, and then the admin owns its label.

    Deliberately NOT filtered by `is_active` — a field deactivated after a
    student submitted still needs its label to render that submission.
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

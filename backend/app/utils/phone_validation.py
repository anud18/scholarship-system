"""Taiwan mobile phone validation for student application contact_phone."""

import re
from typing import Any, Mapping, Optional

# A valid Taiwan mobile number is pure digits, starts with 09 and is 10 digits long.
TAIWAN_MOBILE_PATTERN = re.compile(r"^09\d{8}$")

# Shown to the student and returned on rejection. Kept identical to the
# contact_phone field's patternMessage so the client and server agree.
TAIWAN_MOBILE_MESSAGE = "請輸入本人有效的台灣手機 (09xxxxxx)"


def is_valid_taiwan_mobile(value: Any) -> bool:
    """Return True if value is a valid Taiwan mobile number (09 + 8 digits)."""
    if value is None:
        return False
    return bool(TAIWAN_MOBILE_PATTERN.match(str(value)))


def extract_contact_phone(form_fields: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Pull the contact_phone value out of a submitted_form_data ``fields`` map.

    Each field is stored as ``{field_id, field_type, value, required, ...}``.
    Returns the raw value (may be ``None``/empty); returns ``None`` when the
    field is absent so callers can skip format checks for forms without it.
    """
    if not form_fields:
        return None
    field = form_fields.get("contact_phone")
    if field is None:
        return None
    if isinstance(field, Mapping):
        return field.get("value")
    # Pydantic model / object with a ``value`` attribute.
    return getattr(field, "value", None)

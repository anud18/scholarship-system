"""Read the `mail` claim of a NYCU Portal payload."""

import logging
from typing import Any, Optional

from pydantic import EmailStr, TypeAdapter, ValidationError

logger = logging.getLogger(__name__)

_EMAIL = TypeAdapter(EmailStr)


def normalize_portal_email(raw: Any) -> Optional[str]:
    """Return the Portal mail to store, or None when there is nothing usable.

    Portal sends `""` for accounts without a registered address, and the payload is
    external, so the value may also be malformed or not a string. None (stored as
    NULL) is the only representation of "no email": an empty string fails EmailStr
    when the user is serialized, which blocked both login and the admin role form.
    """
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    try:
        _EMAIL.validate_python(value)
    except ValidationError:
        # Log no value: it is personal data.
        logger.warning("Ignoring Portal mail that is not a valid email address")
        return None
    return value

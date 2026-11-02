"""Which `submitted_form_data.fields` entry holds an application's 郵局帳號.

Readers (roster generation, bank verification) and the account-correction
writer must agree on one priority, otherwise a correction lands in a field the
readers never look at.

`account_number` comes first: the application wizard writes the student's own
typed account there. `postal_account` in a wizard application may hold another
student's account leaked through the shared form-config prefill (#1443).
Batch/renewal-imported applications carry only `postal_account`, so they fall
through to it.
"""

import re
from typing import Any, Mapping, Optional

BANK_ACCOUNT_FIELD_KEYS = ("account_number", "postal_account", "bank_account")

# Plus the free-text labels older forms used as field ids.
BANK_ACCOUNT_FIELD_LOOKUP = (*BANK_ACCOUNT_FIELD_KEYS, "帳戶號碼", "帳號", "郵局帳號")

POSTAL_ACCOUNT_DIGITS = 14


def submitted_bank_account(form_data: Optional[Mapping[str, Any]]) -> str:
    """The 郵局帳號 a roster item snapshots from `submitted_form_data`, "" when there is none.

    Older applications stored fields flat instead of under `fields`; a key's
    nested entry wins over its flat copy, and an empty key falls through to the
    next one.
    """
    form_data = form_data or {}
    fields = form_data.get("fields") or {}
    for key in BANK_ACCOUNT_FIELD_LOOKUP:
        entry = fields.get(key)
        nested = entry.get("value") if isinstance(entry, Mapping) else None
        value = nested or form_data.get(key)
        if value:
            return str(value)
    return ""


def normalize_account_number(account: str) -> str:
    """Keep only the digits, so spaces and dashes typed between groups don't matter."""
    if not account:
        return ""
    return re.sub(r"[^0-9]", "", account)


def validate_postal_account_format(account_number: str) -> tuple[bool, Optional[str]]:
    """A Taiwanese postal account is 14 digits (局號 7 + 帳號 7); returns (is_valid, error_message)."""
    if not account_number:
        return False, "帳號不可為空"

    cleaned = normalize_account_number(account_number)
    if len(cleaned) != POSTAL_ACCOUNT_DIGITS:
        return False, f"郵局帳號必須為 {POSTAL_ACCOUNT_DIGITS} 位數字，目前為 {len(cleaned)} 位"

    return True, None

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

BANK_ACCOUNT_FIELD_KEYS = ("account_number", "postal_account", "bank_account")

# Plus the free-text labels older forms used as field ids.
BANK_ACCOUNT_FIELD_LOOKUP = (*BANK_ACCOUNT_FIELD_KEYS, "帳戶號碼", "帳號", "郵局帳號")

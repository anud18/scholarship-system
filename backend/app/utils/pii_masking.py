"""Masking helpers for personally identifiable information (PII).

These mirror the frontend ``maskIdNumber`` helper
(``frontend/lib/utils/mask.ts``) so a national ID rendered after the backend
has masked it looks identical whether or not the frontend masks it again.

Masking happens at the API response boundary (the data the backend *sends*),
so the full plaintext national ID never leaves the server for display-only
endpoints. Exports that legitimately need the full ID (e.g. the payment
roster Excel) read the raw value directly and must not call these helpers.
"""

from __future__ import annotations

from typing import Optional

# Keep this many trailing characters visible (e.g. "...789").
_VISIBLE_TAIL = 3
# Below this length, keeping the tail would expose almost the whole value,
# so only the first character is kept.
_MIN_LEN_FOR_TAIL = 4


def mask_id_number(id_number: Optional[str]) -> str:
    """Mask a national ID number (身分證字號) for display.

    Keeps the first character and the last three characters, replacing
    everything in between with asterisks. Values of four characters or fewer
    keep only the first character (the rest masked).

    The transform is idempotent: masking an already-masked value returns the
    same string, so it is safe even if the frontend masks again.

    Mirrors ``maskIdNumber`` in ``frontend/lib/utils/mask.ts`` exactly.

    Examples::

        mask_id_number("A123456789")  # -> "A******789"
        mask_id_number("ABCD")        # -> "A***"
        mask_id_number("")            # -> ""
        mask_id_number(None)          # -> ""
    """
    if not id_number:
        return ""
    value = id_number.strip()
    if len(value) <= _MIN_LEN_FOR_TAIL:
        return value[:1] + "*" * max(len(value) - 1, 0)
    return value[:1] + "*" * (len(value) - _VISIBLE_TAIL - 1) + value[-_VISIBLE_TAIL:]

"""
SQLAlchemy TypeDecorator for JSON columns that transparently encrypt/decrypt
the Taiwan national ID (``std_pid``) field at the storage boundary.

This is the single integration point for issue #73: applying
``StudentDataJSON`` to ``Application.student_data`` ensures every persist
encrypts ``std_pid`` and every load decrypts it, so the 30+ call sites that
read or write that column need no individual changes.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator

from app.core.pii_crypto import decrypt_pii, encrypt_pii_idempotent, is_encrypted


class StudentDataJSON(TypeDecorator):
    """JSON column that encrypts the ``std_pid`` key at rest.

    Only the ``std_pid`` value is transformed; every other key passes through
    untouched, so existing queries / dict access patterns keep working.

    The decorator is **idempotent**: re-encrypting an already-enveloped value
    is a no-op (see ``encrypt_pii_idempotent``), so the data migration can run
    safely before this column type is in effect and again afterwards.
    """

    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: Optional[dict], dialect: Any) -> Optional[dict]:
        if not isinstance(value, dict):
            return value
        pid = value.get("std_pid")
        if pid is None or pid == "" or is_encrypted(pid):
            return value
        # Shallow-copy so we don't mutate the caller's dict in place.
        out = dict(value)
        out["std_pid"] = encrypt_pii_idempotent(pid)
        return out

    def process_result_value(self, value: Optional[dict], dialect: Any) -> Optional[dict]:
        if not isinstance(value, dict):
            return value
        pid = value.get("std_pid")
        if not is_encrypted(pid):
            return value
        out = dict(value)
        out["std_pid"] = decrypt_pii(pid)
        return out

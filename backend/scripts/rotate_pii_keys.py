"""
Rotate the PII encryption key version for every encrypted row.

Re-encrypts ``applications.student_data.std_pid`` from the *old* key version
embedded in each envelope to the version specified by
``PII_ENCRYPTION_ACTIVE_VERSION``. Idempotent and safe to re-run.

Prerequisites (env vars):
- ``PII_ENCRYPTION_KEYS``: JSON with BOTH the old version (still readable)
  AND the new active version, e.g. ``{"v1": "<old>", "v2": "<new>"}``.
- ``PII_ENCRYPTION_ACTIVE_VERSION``: ``v2`` (the version to encrypt with).

Usage (from the backend container):

    docker compose -f docker-compose.dev.yml exec backend \
        python scripts/rotate_pii_keys.py

Process:
1. Stream the ``applications`` table in batches of 500.
2. For each row whose ``std_pid`` was encrypted with a version != active,
   decrypt with the embedded version and re-encrypt with the active version.
3. Persist via raw SQL ``UPDATE``.

Rollback: re-run with the previous version set as active.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

# Make app/ importable when running via `python scripts/rotate_pii_keys.py`.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.abspath(os.path.join(_THIS_DIR, os.pardir))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.pii_crypto import (  # noqa: E402
    PIICryptoError,
    decrypt_pii,
    encrypt_pii,
    is_encrypted,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("rotate_pii_keys")

_BATCH_SIZE = 500


def _envelope_version(envelope: str) -> str:
    return envelope.split(":", 2)[1]


def rotate(dry_run: bool = False) -> int:
    active = os.getenv("PII_ENCRYPTION_ACTIVE_VERSION", "v1")
    logger.info("Active PII key version: %s", active)

    engine = create_engine(settings.database_url_sync)
    rotated = 0
    last_id = 0
    with engine.begin() as conn:
        while True:
            rows = conn.execute(
                text(
                    "SELECT id, student_data FROM applications "
                    "WHERE id > :last_id AND student_data IS NOT NULL "
                    "ORDER BY id ASC LIMIT :limit"
                ),
                {"last_id": last_id, "limit": _BATCH_SIZE},
            ).fetchall()
            if not rows:
                break

            for app_id, sd in rows:
                last_id = app_id
                if not isinstance(sd, dict):
                    continue
                pid = sd.get("std_pid")
                if not is_encrypted(pid):
                    continue
                if _envelope_version(pid) == active:
                    continue
                try:
                    plaintext = decrypt_pii(pid)
                    new_envelope = encrypt_pii(plaintext)
                except PIICryptoError as exc:
                    logger.error("application id=%s: rotation failed: %s", app_id, exc)
                    raise

                new_sd = dict(sd)
                new_sd["std_pid"] = new_envelope
                rotated += 1
                if dry_run:
                    logger.info("[DRY] would rotate application id=%s", app_id)
                    continue
                conn.execute(
                    text("UPDATE applications SET student_data = CAST(:sd AS JSON) " "WHERE id = :id"),
                    {"sd": json.dumps(new_sd, ensure_ascii=False), "id": app_id},
                )

    logger.info("Rotation %s. Rows touched: %d", "DRY-RUN" if dry_run else "complete", rotated)
    return rotated


def main() -> int:
    parser = argparse.ArgumentParser(description="Rotate PII keys.")
    parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = parser.parse_args()
    try:
        rotate(dry_run=args.dry_run)
    except PIICryptoError as exc:
        logger.error("Rotation aborted: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

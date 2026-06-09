"""
Backfill legacy "Placeholder content" bank-account-proof documents.

Background
----------
Applications created BEFORE PR #887 may have a ``bank_account_proof``
``ApplicationFile`` whose MinIO object is the literal 19-byte string
``b"Placeholder content"``. This happened because the OLD
``MinIOService.clone_file_to_application`` silently wrote a placeholder when
its ``copy_object`` call failed (violating CLAUDE.md error-handling principle
#1). PR #887 fixed the clone for NEW applications (it now uses ``CopySource``
and re-raises on failure), but it did NOT backfill the broken rows already in
the database. For those applications the reviewer's 存摺封面 (bank passbook
cover) preview shows 19 bytes of garbage instead of the real document.

What this script does
---------------------
For every ``ApplicationFile`` of ``file_type == "bank_account_proof"``:

  1. ``stat`` + ``read`` its MinIO object. Treat it as a placeholder ONLY when
     the object is exactly 19 bytes AND its content equals
     ``b"Placeholder content"``. (The DB cannot be used to discriminate good
     from bad rows: the fixed clone also stores ``file_size=0`` /
     ``content_type="application/octet-stream"`` in the DB, so both good and
     bad rows look identical in Postgres — detection must read the object.)

  2. Look up the owning application's user → their ``UserProfile`` →
     ``bank_document_object_name`` (the REAL uploaded bank doc). If the user
     has no profile bank doc, or the source object is missing, or the source
     is ITSELF a 19-byte placeholder, the row is SKIPPED (logged) — we never
     propagate garbage.

  3. Re-copy the real source object into the application path using the FIXED
     ``minio_service.clone_file_to_application`` primitive (an S3 server-side
     ``copy_object`` within the default bucket — the same primitive the live
     code path uses), then ``stat`` the NEW object to obtain its real size /
     content-type and update the ``ApplicationFile`` row's ``object_name``,
     ``file_size``, ``content_type`` and ``mime_type`` to point at the real
     copy.

Safety properties
-----------------
* **Idempotent.** Detection is content-based: after a successful fix the
  object is no longer a 19-byte placeholder, so a second run skips it.
* **Dry-run-able.** ``--dry-run`` performs ZERO writes (no MinIO copy, no DB
  mutation, no commit) — it only reports what WOULD be done. The ``--dry-run``
  pass doubles as the census (the DB alone cannot count these rows).
* **Never deletes data.** The old placeholder object is left orphaned in
  MinIO, not removed.

Usage
-----
    # from the backend/ directory (or inside the backend container)
    python -m app.scripts.backfill_placeholder_bank_docs --dry-run
    python -m app.scripts.backfill_placeholder_bank_docs        # apply
"""

import argparse
import asyncio
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from minio.error import S3Error
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.application import Application, ApplicationFile
from app.models.user_profile import UserProfile
from app.services.minio_service import get_minio_service

logger = logging.getLogger("backfill_placeholder_bank_docs")

PLACEHOLDER_BYTES = b"Placeholder content"
PLACEHOLDER_SIZE = len(PLACEHOLDER_BYTES)  # 19
BANK_FILE_TYPE = "bank_account_proof"


@dataclass
class Stats:
    scanned: int = 0
    placeholders_found: int = 0
    fixed: int = 0
    skipped_no_profile_doc: int = 0
    skipped_source_missing: int = 0
    skipped_source_placeholder: int = 0
    errors: int = 0
    fixed_file_ids: List[int] = field(default_factory=list)


def _read_object_bytes(minio_service, object_name: str) -> Optional[bytes]:
    """Read the full bytes of an object from the default bucket.

    Returns None if the object does not exist (NoSuchKey). Re-raises any other
    S3 / connection error so genuine infrastructure problems are not masked.
    """
    response = None
    try:
        response = minio_service.client.get_object(minio_service.default_bucket, object_name)
        return response.read()
    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchBucket"):
            return None
        raise
    finally:
        if response is not None:
            try:
                response.close()
                response.release_conn()
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass


def _is_placeholder(minio_service, object_name: Optional[str]) -> Optional[bool]:
    """Decide whether an object is the 19-byte placeholder.

    Returns:
        True  -> object exists and is exactly b"Placeholder content"
        False -> object exists and is a real document
        None  -> object name is empty OR the object is missing in MinIO
    """
    if not object_name:
        return None

    # Fast pre-filter on size, then confirm content (cheap + exact).
    try:
        stat = minio_service.client.stat_object(minio_service.default_bucket, object_name)
    except S3Error as e:
        if e.code in ("NoSuchKey", "NoSuchBucket"):
            return None
        raise

    if stat.size != PLACEHOLDER_SIZE:
        return False

    content = _read_object_bytes(minio_service, object_name)
    if content is None:
        return None
    return content == PLACEHOLDER_BYTES


async def _resolve_profile_source(db, user_id: int) -> Optional[str]:
    """Return the user's real bank-document object name, or None if absent."""
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        return None
    return profile.bank_document_object_name or None


async def backfill(dry_run: bool) -> Stats:
    stats = Stats()
    minio_service = get_minio_service()

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ApplicationFile).where(ApplicationFile.file_type == BANK_FILE_TYPE))
        files = result.scalars().all()
        logger.info("Found %d %s ApplicationFile rows to scan", len(files), BANK_FILE_TYPE)

        for app_file in files:
            stats.scanned += 1
            object_name = app_file.object_name

            try:
                is_ph = _is_placeholder(minio_service, object_name)
            except Exception:  # noqa: BLE001
                logger.exception("file_id=%s: error reading object %r — skipping", app_file.id, object_name)
                stats.errors += 1
                continue

            if is_ph is None:
                logger.warning(
                    "file_id=%s: object %r missing in MinIO — skipping (not a placeholder we can fix)",
                    app_file.id,
                    object_name,
                )
                continue
            if is_ph is False:
                # Real document already — nothing to do (also the idempotency path).
                continue

            stats.placeholders_found += 1

            # Resolve owning application -> user -> profile bank doc.
            app_result = await db.execute(select(Application).where(Application.id == app_file.application_id))
            application = app_result.scalar_one_or_none()
            if application is None:
                logger.warning(
                    "file_id=%s: owning application_id=%s not found — skipping",
                    app_file.id,
                    app_file.application_id,
                )
                stats.skipped_no_profile_doc += 1
                continue

            source_object_name = await _resolve_profile_source(db, application.user_id)
            if not source_object_name:
                logger.info(
                    "file_id=%s app_id=%s user_id=%s: user has no profile bank document — SKIP",
                    app_file.id,
                    application.app_id,
                    application.user_id,
                )
                stats.skipped_no_profile_doc += 1
                continue

            # Validate the SOURCE before we copy it: it must exist and must not
            # itself be a placeholder, otherwise we'd propagate garbage.
            try:
                source_is_ph = _is_placeholder(minio_service, source_object_name)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "file_id=%s: error reading source %r — skipping",
                    app_file.id,
                    source_object_name,
                )
                stats.errors += 1
                continue

            if source_is_ph is None:
                logger.warning(
                    "file_id=%s app_id=%s: profile source %r missing in MinIO — SKIP",
                    app_file.id,
                    application.app_id,
                    source_object_name,
                )
                stats.skipped_source_missing += 1
                continue
            if source_is_ph is True:
                logger.warning(
                    "file_id=%s app_id=%s: profile source %r is itself a placeholder — SKIP",
                    app_file.id,
                    application.app_id,
                    source_object_name,
                )
                stats.skipped_source_placeholder += 1
                continue

            if dry_run:
                logger.info(
                    "[DRY-RUN] WOULD fix file_id=%s app_id=%s: re-copy %r -> applications/%s/documents/...",
                    app_file.id,
                    application.app_id,
                    source_object_name,
                    application.app_id,
                )
                stats.fixed += 1
                stats.fixed_file_ids.append(app_file.id)
                continue

            # --- APPLY: server-side copy real source into the application path ---
            try:
                new_object_name = minio_service.clone_file_to_application(
                    source_object_name=source_object_name,
                    application_id=application.app_id,
                )
                new_stat = minio_service.client.stat_object(minio_service.default_bucket, new_object_name)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "file_id=%s app_id=%s: clone failed — leaving placeholder untouched",
                    app_file.id,
                    application.app_id,
                )
                stats.errors += 1
                continue

            old_object_name = app_file.object_name
            app_file.object_name = new_object_name
            app_file.file_size = new_stat.size
            app_file.content_type = new_stat.content_type
            app_file.mime_type = new_stat.content_type

            await db.commit()

            logger.info(
                "FIXED file_id=%s app_id=%s: %r (placeholder, orphaned) -> %r (%d bytes, %s)",
                app_file.id,
                application.app_id,
                old_object_name,
                new_object_name,
                new_stat.size,
                new_stat.content_type,
            )
            stats.fixed += 1
            stats.fixed_file_ids.append(app_file.id)

    return stats


def _print_summary(stats: Stats, dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "APPLY"
    logger.info("==================== %s SUMMARY ====================", mode)
    logger.info("Scanned bank_account_proof files : %d", stats.scanned)
    logger.info("Placeholder objects found        : %d", stats.placeholders_found)
    logger.info("%s                          : %d", "Would fix" if dry_run else "Fixed    ", stats.fixed)
    logger.info("Skipped (no profile bank doc)    : %d", stats.skipped_no_profile_doc)
    logger.info("Skipped (source missing)         : %d", stats.skipped_source_missing)
    logger.info("Skipped (source is placeholder)  : %d", stats.skipped_source_placeholder)
    logger.info("Errors                           : %d", stats.errors)
    if stats.fixed_file_ids:
        logger.info("Affected file_ids                : %s", stats.fixed_file_ids)
    logger.info("===================================================")


def main() -> None:
    parser = argparse.ArgumentParser(description='Backfill legacy "Placeholder content" bank_account_proof documents.')
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing to MinIO or the database.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    stats = asyncio.run(backfill(dry_run=args.dry_run))
    _print_summary(stats, dry_run=args.dry_run)


if __name__ == "__main__":
    main()

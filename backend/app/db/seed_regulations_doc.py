"""
Seed the 獎學金要點 (scholarship regulations) system document.

Uploads the bundled PhD scholarship regulations PDF to MinIO and registers it
under the ``regulations_url`` system setting so the student-facing application
wizard can render it inline via react-pdf.

The canonical asset lives inside the backend package (``seed_assets/``) because
the Docker build context is ``./backend`` and the repo-level ``docs/`` directory
is neither copied into the image nor mounted into the container at seed time.
A human-readable copy is kept under ``docs/samples/`` for reference only.

Idempotent: if an admin has already configured ``regulations_url`` we leave it
untouched so a real upload is never clobbered by the seed.
"""

import io
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import ConfigCategory, ConfigDataType, SystemSetting
from app.services.minio_service import minio_service

_ASSET_PATH = Path(__file__).resolve().parent / "seed_assets" / "phd_regulations_114.pdf"
_DOC_KEY = "regulations_url"
_FILENAME_KEY = "regulations_url_filename"
_ORIGINAL_FILENAME = "114年國立陽明交通大學博士生獎學金申請注意事項.pdf"
# Fixed object name (no timestamp) keeps the seed deterministic and avoids
# orphaning MinIO objects across repeated seeds.
_OBJECT_NAME = "system-docs/regulations_url_seed.pdf"


def _make_setting(key: str, value: str, description: str, system_user_id: int) -> SystemSetting:
    return SystemSetting(
        key=key,
        value=value,
        category=ConfigCategory.file_storage,
        data_type=ConfigDataType.string,
        description=description,
        is_sensitive=False,
        is_readonly=False,
        allow_empty=True,
        last_modified_by=system_user_id,
    )


async def seed_regulations_doc(db: AsyncSession, system_user_id: int = 1) -> None:
    """Upload the bundled 獎學金要點 PDF and register it in ``system_settings``.

    Args:
        db: Database session
        system_user_id: User ID for audit trail. Defaults to 1; the seed
            entrypoints invoke this after ``seed_test_users`` /
            ``seed_admin_user``, so user 1 is guaranteed to exist.
    """
    # Load any existing rows for both keys up front so we can upsert (rather
    # than blindly insert) and never hit a unique-key violation on a partially
    # committed prior seed.
    result = await db.execute(select(SystemSetting).where(SystemSetting.key.in_([_DOC_KEY, _FILENAME_KEY])))
    existing = {row.key: row for row in result.scalars().all()}

    # Skip if an admin already configured this doc — never clobber a real upload.
    if _DOC_KEY in existing:
        print("  - 獎學金要點 already configured, skipping seed upload")
        return

    # A committed, bundled asset that is missing or not a PDF is a packaging
    # defect, not an expected runtime state — fail loudly rather than ship a
    # wizard with no regulations document (CLAUDE.md §1: never swallow errors).
    if not _ASSET_PATH.exists():
        raise FileNotFoundError(f"Regulations seed asset not found: {_ASSET_PATH}")

    file_content = _ASSET_PATH.read_bytes()

    # The wizard renders this inline via react-pdf, which only supports PDF.
    if not file_content.startswith(b"%PDF-"):
        raise ValueError(f"Regulations seed asset is not a valid PDF: {_ASSET_PATH}")

    minio_service.client.put_object(
        bucket_name=minio_service.default_bucket,
        object_name=_OBJECT_NAME,
        data=io.BytesIO(file_content),
        length=len(file_content),
        content_type="application/pdf",
    )

    def _upsert(key: str, value: str, description: str) -> None:
        row = existing.get(key)
        if row is not None:
            # Reuse a dangling row (e.g. a filename row left by a partial seed).
            row.value = value
            row.last_modified_by = system_user_id
        else:
            db.add(_make_setting(key, value, description, system_user_id))

    _upsert(_DOC_KEY, _OBJECT_NAME, "獎學金要點")
    _upsert(_FILENAME_KEY, _ORIGINAL_FILENAME, "獎學金要點 原始檔名")
    await db.commit()

    print(f"  ✓ Seeded 獎學金要點 system document ({len(file_content)} bytes)")

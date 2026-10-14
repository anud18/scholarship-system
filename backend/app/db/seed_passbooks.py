"""
Dev-only: give the seeded student accounts a 存摺封面 on their profile.

提交申請 and the direct (non-draft) create path refuse a profile without
``bank_document_photo_url``, and the wizard's 個人資料 section cannot be saved
without one. Returning students would have uploaded theirs in an earlier
year, so the base test accounts and the 續領 / 114 新申請 / 批次匯入 cohorts get
a placeholder passbook uploaded to MinIO exactly as the wizard would. The
115 新申請 accounts are left without one on purpose: they walk the full
wizard, upload included.

Idempotent: a profile that already carries a passbook is skipped. Run it
standalone to backfill an already-seeded dev database:

    python -m app.db.seed_passbooks
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_ay115_demo import BATCH_IMPORT_STUDENTS_115, NEW_RECIPIENTS_114, RENEWAL_COHORT
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.user_profile import BankDocumentPhotoUpload
from app.services.user_profile_service import UserProfileService

BASE_STUDENT_IDS = (
    "stuunder1",
    "stuphd001",
    "studirect",
    "stumaster",
    "phdchina1",
    "stuchina1",
    "stuleave1",
    "csphd0001",
    "csphd0002",
    "csphd0003",
)
PASSBOOK_STUDENT_IDS = BASE_STUDENT_IDS + tuple(
    entry[0] for entry in RENEWAL_COHORT + NEW_RECIPIENTS_114 + BATCH_IMPORT_STUDENTS_115
)

# 1x1 transparent PNG — a real image, so the upload's PIL/MIME validation
# accepts it the same way it accepts a student's photo.
_PASSBOOK_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
_PASSBOOK_UPLOAD = BankDocumentPhotoUpload(
    photo_data=_PASSBOOK_PNG_BASE64,
    filename="seed-passbook.png",
    content_type="image/png",
)


async def seed_passbooks(session: AsyncSession) -> int:
    """Upload the placeholder 存摺封面 for every listed student that has none; returns the count."""
    users = (await session.execute(select(User).where(User.nycu_id.in_(PASSBOOK_STUDENT_IDS)))).scalars().all()
    profile_rows = (
        await session.execute(select(UserProfile).where(UserProfile.user_id.in_([user.id for user in users])))
    ).scalars()
    profiles = {profile.user_id: profile for profile in profile_rows}

    service = UserProfileService(session)
    uploaded = 0
    for user in users:
        profile = profiles.get(user.id)
        if profile is not None and profile.bank_document_photo_url:
            continue
        await service.upload_bank_document_to_minio(user_id=user.id, document_upload=_PASSBOOK_UPLOAD)
        uploaded += 1
    return uploaded


async def _main() -> None:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        uploaded = await seed_passbooks(session)
    print(f"  ✓ 存摺封面 uploaded for seeded students: +{uploaded}")


if __name__ == "__main__":
    asyncio.run(_main())

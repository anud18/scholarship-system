"""
Seed a ready-to-submit DRAFT PhD scholarship application using the exact form
values from the UI test scenario:

  指導教授資訊
    教授姓名:               p
    教授 Email:             professor@nycu.edu.tw
    指導教授本校人事編號:    professor

  郵局帳號資訊
    郵局局號加帳號 (14 碼):  12341234123400
    存摺封面照片:           placeholder upload

  申請獎學金 — 博士生獎學金 114 學年
    申請項目:               nstc + moe_1w (multiple)
    碩士畢業學校/學院/系所:   0989890890
    聯絡電話:               0987789789
    申請文件:               placeholder upload

Outputs an application in status=draft / review_stage=student_draft so the
student can review then click "提交申請" in the UI to actually send it.

Usage:
  python seed_phd_test_draft.py <nycu_id>
  python seed_phd_test_draft.py stuphd001
  python seed_phd_test_draft.py csphd0001
"""
import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, text

from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
from app.models.user_profile import UserProfile
from app.services.student_service import StudentService


ADVISOR_NAME = "p"
ADVISOR_EMAIL = "professor@nycu.edu.tw"
ADVISOR_NYCU_ID = "professor"
POSTAL_ACCOUNT = "12341234123400"
BANK_DOC_OBJECT = "bank_docs/test/seed_bank_cover.jpeg"
BANK_DOC_FILENAME = "郵局.jpeg"

MASTER_SCHOOL_INFO = "0989890890"
CONTACT_PHONE = "0987789789"
APPLICATION_DOC_OBJECT = "applications/test/seed_application_doc.jpeg"
APPLICATION_DOC_FILENAME = "郵局.jpeg"
APPLICATION_DOC_SIZE = 25356  # 24.76 KB shown in UI
APPLICATION_DOC_MIME = "image/jpeg"

SUBTYPES = ["nstc", "moe_1w"]


async def seed(nycu_id: str):
    async with AsyncSessionLocal() as session:
        user_row = await session.execute(
            text("SELECT id, nycu_id, name FROM users WHERE nycu_id = :nid"),
            {"nid": nycu_id},
        )
        user = user_row.fetchone()
        if not user:
            print(f"❌ User {nycu_id} not found in database")
            return

        config_row = await session.execute(
            text("""
                SELECT sc.id, sc.scholarship_type_id, sc.academic_year, sc.semester,
                       st.code, st.name
                FROM scholarship_configurations sc
                JOIN scholarship_types st ON st.id = sc.scholarship_type_id
                WHERE st.code = 'phd' AND sc.academic_year = 114
            """)
        )
        config = config_row.fetchone()
        if not config:
            print("❌ PhD scholarship configuration for year 114 not found")
            return

        print(f"👤 User: {user.name} ({user.nycu_id}), id={user.id}")
        print(f"🎓 Scholarship: {config.name}, config_id={config.id}")

        profile_row = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        profile = profile_row.scalar_one_or_none()
        if not profile:
            profile = UserProfile(
                user_id=user.id,
                account_number=POSTAL_ACCOUNT,
                bank_document_object_name=BANK_DOC_OBJECT,
                bank_document_photo_url=BANK_DOC_OBJECT,
                advisor_name=ADVISOR_NAME,
                advisor_email=ADVISOR_EMAIL,
                advisor_nycu_id=ADVISOR_NYCU_ID,
            )
            session.add(profile)
            print("  ✓ User profile created with screenshot values")
        else:
            profile.account_number = POSTAL_ACCOUNT
            profile.bank_document_object_name = BANK_DOC_OBJECT
            profile.bank_document_photo_url = BANK_DOC_OBJECT
            profile.advisor_name = ADVISOR_NAME
            profile.advisor_email = ADVISOR_EMAIL
            profile.advisor_nycu_id = ADVISOR_NYCU_ID
            print("  ✓ User profile overwritten with screenshot values")

        existing = await session.execute(
            select(Application).where(
                Application.user_id == user.id,
                Application.scholarship_type_id == config.scholarship_type_id,
                Application.academic_year == config.academic_year,
            )
        )
        if existing.scalar_one_or_none():
            print("⚠️  Application already exists for this user / year, skipping create")
            await session.commit()
            return

        print("  📡 Fetching student data from SIS API...")
        student_service = StudentService()
        try:
            student_data = await student_service.get_student_snapshot(
                nycu_id, academic_year=str(config.academic_year), semester=config.semester
            )
            print(f"  ✓ Student data: {student_data.get('std_cname', nycu_id)}")
        except Exception as e:
            print(f"  ⚠️  API fetch failed ({e}), using minimal snapshot")
            student_data = {
                "std_stdcode": nycu_id,
                "std_cname": user.name,
                "com_email": f"{nycu_id}@nycu.edu.tw",
                "_api_fetched_at": datetime.now(timezone.utc).isoformat(),
                "_term_data_status": "fallback",
            }

        now_iso = datetime.now(timezone.utc).isoformat()
        submitted_form_data = {
            "fields": {
                "master_school_info": {
                    "field_id": "master_school_info",
                    "field_type": "text",
                    "value": MASTER_SCHOOL_INFO,
                    "required": True,
                },
                "contact_phone": {
                    "field_id": "contact_phone",
                    "field_type": "text",
                    "value": CONTACT_PHONE,
                    "required": True,
                },
            },
            "documents": [
                {
                    "document_id": "application_document",
                    "document_type": "申請文件",
                    "file_path": APPLICATION_DOC_OBJECT,
                    "original_filename": APPLICATION_DOC_FILENAME,
                    "upload_time": now_iso,
                    "file_size": APPLICATION_DOC_SIZE,
                    "mime_type": APPLICATION_DOC_MIME,
                },
            ],
        }

        seq_row = await session.execute(
            text("""
                INSERT INTO application_sequences (academic_year, semester, last_sequence)
                VALUES (:year, :semester, 1)
                ON CONFLICT (academic_year, semester)
                DO UPDATE SET last_sequence = application_sequences.last_sequence + 1
                RETURNING last_sequence
            """),
            {"year": config.academic_year, "semester": config.semester or "yearly"},
        )
        seq = seq_row.scalar()
        semester_code = {"first": "1", "second": "2"}.get(str(config.semester or ""), "0")
        app_id = f"APP-{config.academic_year}-{semester_code}-{seq:05d}"

        application = Application(
            app_id=app_id,
            user_id=user.id,
            scholarship_type_id=config.scholarship_type_id,
            scholarship_configuration_id=config.id,
            scholarship_name=config.name,
            scholarship_subtype_list=SUBTYPES,
            sub_type_selection_mode=SubTypeSelectionMode.multiple,
            sub_scholarship_type=SUBTYPES[0],
            status=ApplicationStatus.draft,
            status_name="草稿",
            review_stage=ReviewStage.student_draft,
            academic_year=config.academic_year,
            semester=config.semester,
            is_renewal=False,
            agree_terms=True,
            student_data=student_data,
            submitted_form_data=submitted_form_data,
        )
        session.add(application)
        await session.commit()

        print(f"\n✅ Draft application created: {app_id}")
        print(f"   Student:     {user.name} ({nycu_id})")
        print(f"   Scholarship: {config.name}")
        print(f"   Sub-types:   {', '.join(SUBTYPES)}")
        print(f"   Advisor:     {ADVISOR_NAME} <{ADVISOR_EMAIL}> ({ADVISOR_NYCU_ID})")
        print(f"   Postal acct: {POSTAL_ACCOUNT}")
        print(f"   Master info: {MASTER_SCHOOL_INFO}")
        print(f"   Contact:     {CONTACT_PHONE}")
        print("   Ready to submit via UI (提交申請)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed a PhD application draft using UI screenshot values")
    parser.add_argument("nycu_id", help="Student NYCU ID (e.g. stuphd001, csphd0001)")
    args = parser.parse_args()
    asyncio.run(seed(args.nycu_id))

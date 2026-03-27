"""
Seed a ready-to-submit draft PhD scholarship application for a given student.
Fetches student data from mock SIS API via the existing StudentService.

Usage:
  python seed_csphd001_draft.py <nycu_id>
  python seed_csphd001_draft.py csphd0001
  python seed_csphd001_draft.py csphd0002
"""
import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select, text
from app.db.session import AsyncSessionLocal
from app.models.application import Application
from app.models.user_profile import UserProfile
from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
from app.services.student_service import StudentService


async def seed(nycu_id: str):
    async with AsyncSessionLocal() as session:
        # 1. Get user
        user_result = await session.execute(
            text("SELECT id, nycu_id, name FROM users WHERE nycu_id = :nid"),
            {"nid": nycu_id},
        )
        user = user_result.fetchone()
        if not user:
            print(f"❌ User {nycu_id} not found in database")
            return

        # 2. Get PhD scholarship config for year 114
        config_result = await session.execute(
            text("""
                SELECT sc.id, sc.scholarship_type_id, sc.academic_year, sc.semester,
                       st.code, st.name
                FROM scholarship_configurations sc
                JOIN scholarship_types st ON st.id = sc.scholarship_type_id
                WHERE st.code = 'phd' AND sc.academic_year = 114
            """)
        )
        config = config_result.fetchone()
        if not config:
            print("❌ PhD scholarship configuration for year 114 not found")
            return

        print(f"👤 User: {user.name} ({user.nycu_id}), id={user.id}")
        print(f"🎓 Scholarship: {config.name}, config_id={config.id}")

        # 3. Create or update user_profile (fixed fields)
        profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        profile = profile_result.scalar_one_or_none()
        if not profile:
            profile = UserProfile(
                user_id=user.id,
                account_number="0011234-5678901",
                advisor_name="張教授",
                advisor_email="professor@nycu.edu.tw",
                advisor_nycu_id="T001",
            )
            session.add(profile)
            print("  ✓ User profile created")
        else:
            profile.account_number = profile.account_number or "0011234-5678901"
            profile.advisor_name = profile.advisor_name or "張教授"
            profile.advisor_email = profile.advisor_email or "professor@nycu.edu.tw"
            profile.advisor_nycu_id = profile.advisor_nycu_id or "T001"
            print("  ✓ User profile updated")

        # 4. Check existing application
        existing = await session.execute(
            select(Application).where(
                Application.user_id == user.id,
                Application.scholarship_type_id == config.scholarship_type_id,
                Application.academic_year == config.academic_year,
            )
        )
        if existing.scalar_one_or_none():
            print("⚠️  Application already exists, skipping")
            await session.commit()
            return

        # 5. Fetch student data via StudentService (uses mock API with auth)
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

        # 6. Build submitted_form_data
        submitted_form_data = {
            "fields": {
                "master_school_info": {
                    "field_id": "master_school_info",
                    "field_type": "text",
                    "value": f"{student_data.get('std_highestschname', '國立陽明交通大學')} 資訊工程研究所",
                    "required": True,
                },
            },
            "documents": [],
        }

        # 7. Generate app_id
        seq_result = await session.execute(
            text("""
                INSERT INTO application_sequences (academic_year, semester, last_sequence)
                VALUES (:year, :semester, 1)
                ON CONFLICT (academic_year, semester)
                DO UPDATE SET last_sequence = application_sequences.last_sequence + 1
                RETURNING last_sequence
            """),
            {"year": config.academic_year, "semester": config.semester or "yearly"},
        )
        seq = seq_result.scalar()
        app_id = f"APP-{config.academic_year}-0-{seq:05d}"

        # 8. Create draft application
        application = Application(
            app_id=app_id,
            user_id=user.id,
            scholarship_type_id=config.scholarship_type_id,
            scholarship_configuration_id=config.id,
            scholarship_name=config.name,
            scholarship_subtype_list=["nstc"],
            sub_type_selection_mode=SubTypeSelectionMode.multiple,
            sub_scholarship_type="nstc",
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
        print(f"   Student: {user.name} ({nycu_id})")
        print(f"   Scholarship: {config.name} (nstc)")
        print(f"   Ready to submit via UI")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed a draft PhD application")
    parser.add_argument("nycu_id", help="Student NYCU ID (e.g. csphd0001)")
    args = parser.parse_args()
    asyncio.run(seed(args.nycu_id))

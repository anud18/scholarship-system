"""
Seed test data for manual distribution end-to-end verification.

Creates:
- 1 scholarship configuration for 114 first semester PhD
- 3 applications (1 renewal nstc, 1 renewal moe_1w, 1 new)
- 1 college ranking with 3 items

Usage:
    docker compose -f docker-compose.dev.yml exec backend python scripts/seed_distribution_test_data.py
"""

import asyncio
import sys

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ReviewStage, Semester
from app.models.scholarship import ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType


async def main():
    async with AsyncSessionLocal() as db:
        # Get PhD scholarship type
        st_result = await db.execute(select(ScholarshipType).where(ScholarshipType.code == "phd"))
        phd = st_result.scalar_one_or_none()
        if not phd:
            print("ERROR: PhD scholarship type not found. Run seed first.")
            sys.exit(1)

        # Find or create test students
        students_info = [
            ("310460001", "測試學生甲", "test1@g2.nctu.edu.tw", "nstc", True, 113),
            ("310460002", "測試學生乙", "test2@g2.nctu.edu.tw", "moe_1w", True, 113),
            ("310460003", "測試學生丙", "test3@g2.nctu.edu.tw", "nstc", False, None),
        ]

        apps = []
        for idx, (stdcode, name, email, sub_type, is_renewal, renewal_year) in enumerate(students_info, 1):
            # User
            u_result = await db.execute(select(User).where(User.nycu_id == stdcode))
            user = u_result.scalar_one_or_none()
            if not user:
                user = User(
                    nycu_id=stdcode,
                    name=name,
                    email=email,
                    user_type=UserType.student,
                    role=UserRole.student,
                )
                db.add(user)
                await db.flush()

            # Application
            app_id = f"APP-114-1-{idx:05d}"
            app_result = await db.execute(select(Application).where(Application.app_id == app_id))
            app = app_result.scalar_one_or_none()
            if not app:
                app = Application(
                    app_id=app_id,
                    user_id=user.id,
                    scholarship_type_id=phd.id,
                    scholarship_subtype_list=[sub_type],
                    sub_type_selection_mode=SubTypeSelectionMode.multiple,
                    sub_scholarship_type=sub_type,
                    is_renewal=is_renewal,
                    renewal_year=renewal_year,
                    status=ApplicationStatus.approved.value,
                    review_stage=ReviewStage.completed.value,
                    academic_year=114,
                    semester=Semester.first,
                    student_data={
                        "std_stdcode": stdcode,
                        "std_cname": name,
                        "trm_termcount": 3 + idx,
                        "trm_academyname": "電機學院",
                        "trm_depname": "電機工程學系",
                        "std_academyno": "B",
                        "std_nation": "中華民國",
                        "std_enrollyear": 113,
                        "std_enrollterm": 1,
                    },
                    agree_terms=True,
                )
                db.add(app)
                await db.flush()
            apps.append(app)

        # College ranking
        cr_result = await db.execute(
            select(CollegeRanking).where(
                CollegeRanking.scholarship_type_id == phd.id,
                CollegeRanking.academic_year == 114,
                CollegeRanking.semester == "first",
                CollegeRanking.sub_type_code == "nstc",
            )
        )
        ranking = cr_result.scalar_one_or_none()
        if not ranking:
            ranking = CollegeRanking(
                scholarship_type_id=phd.id,
                sub_type_code="nstc",
                academic_year=114,
                semester="first",
                ranking_name="Test Ranking 114-1 NSTC",
                total_applications=len(apps),
                total_quota=10,
                ranking_status="finalized",
                is_finalized=True,
            )
            db.add(ranking)
            await db.flush()

        # Ranking items
        for idx, app in enumerate(apps, 1):
            ri_result = await db.execute(
                select(CollegeRankingItem).where(
                    CollegeRankingItem.ranking_id == ranking.id,
                    CollegeRankingItem.application_id == app.id,
                )
            )
            item = ri_result.scalar_one_or_none()
            if not item:
                item = CollegeRankingItem(
                    ranking_id=ranking.id,
                    application_id=app.id,
                    rank_position=idx,
                    status="ranked",
                    allocated_sub_type=None,
                    allocation_year=None,
                )
                db.add(item)

        await db.commit()
        print(f"Seeded: {len(apps)} applications, 1 ranking with {len(apps)} items")
        print(f"  Scholarship type ID: {phd.id} (for API calls)")
        print(f"  Academic year: 114, semester: first")


if __name__ == "__main__":
    asyncio.run(main())

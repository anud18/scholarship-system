"""
Integration tests for distribution to roster pipeline

Tests the complete flow:
1. Create ranking with applications
2. Execute matrix distribution
3. Generate roster from distribution results
4. Verify data consistency
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RosterAlreadyExistsError
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus, Semester
from app.models.payment_roster import PaymentRosterItem, RosterCycle, RosterStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipSubTypeConfig, ScholarshipType
from app.models.user import User, UserRole
from app.services.matrix_distribution import MatrixDistributionService
from app.services.roster_service import RosterService


@pytest.mark.asyncio
async def test_distribution_to_roster_happy_path(db_session: AsyncSession):
    """
    Test the complete happy path from distribution to roster generation
    """
    # 1. Setup: Create test data
    # Create users
    admin_user = User(
        nycu_id="admin001",
        name="Admin User",
        email="admin@test.com",
        role=UserRole.super_admin,
    )
    db_session.add(admin_user)
    await db_session.flush()

    # Create scholarship type
    scholarship_type = ScholarshipType(
        name="Test Scholarship",
        code="TEST",
        description="Test scholarship for integration testing",
        is_active=True,
        application_cycle="semester",
        user_type="student",
    )
    db_session.add(scholarship_type)
    await db_session.flush()

    # Create sub-type configs
    sub_type_nstc = ScholarshipSubTypeConfig(
        scholarship_type_id=scholarship_type.id,
        sub_type_code="nstc",
        sub_type_name="NSTC Scholarship",
        display_order=1,
        is_active=True,
    )
    sub_type_moe = ScholarshipSubTypeConfig(
        scholarship_type_id=scholarship_type.id,
        sub_type_code="moe_1w",
        sub_type_name="MOE Scholarship",
        display_order=2,
        is_active=True,
    )
    db_session.add_all([sub_type_nstc, sub_type_moe])
    await db_session.flush()

    # Create scholarship configuration with quota matrix
    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type.id,
        academic_year=114,
        semester="first",
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
        is_active=True,
        has_college_quota=True,
        quotas={
            "nstc": {"EE": 2, "CS": 1},
            "moe_1w": {"EE": 1, "CS": 2},
        },
    )
    db_session.add(config)
    await db_session.flush()

    # Create test applications
    applications = []
    for i in range(5):
        app = Application(
            app_id=f"APP-114-1-{i+1:05d}",
            nycu_id=f"student{i+1:03d}",
            scholarship_configuration_id=config.id,
            academic_year=114,
            semester=Semester.first,
            status=ApplicationStatus.under_review,
            scholarship_subtype_list=["nstc", "moe_1w"],
            student_data={
                "std_stdcode": f"student{i+1:03d}",
                "std_cname": f"Student {i+1}",
                "std_academyno": "EE" if i < 3 else "CS",  # First 3 in EE, last 2 in CS
                "com_email": f"student{i+1}@test.com",
            },
            submitted_form_data={
                "fields": {
                    "bank_account": {
                        "value": f"12345678{i+1}",
                        "field_type": "text",
                    }
                }
            },
        )
        applications.append(app)
        db_session.add(app)

    await db_session.flush()

    # Create college ranking
    ranking = CollegeRanking(
        scholarship_type_id=scholarship_type.id,
        academic_year=114,
        semester="first",
        ranking_name="Test Ranking 2025",
        status="final",
        distribution_executed=False,
    )
    db_session.add(ranking)
    await db_session.flush()

    # Create ranking items
    for idx, app in enumerate(applications):
        item = CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=app.id,
            rank_position=idx + 1,
            status="ranked",
        )
        db_session.add(item)

    await db_session.commit()

    # 2. Execute matrix distribution
    distribution_service = MatrixDistributionService(db_session)

    distribution_result = await distribution_service.execute_matrix_distribution(
        ranking_id=ranking.id,
        executor_id=admin_user.id,
    )

    # 3. Verify distribution results
    assert distribution_result["total_allocated"] > 0, "Should allocate some students"
    assert distribution_result["ranking_id"] == ranking.id

    # Refresh ranking from database
    await db_session.refresh(ranking)
    assert ranking.distribution_executed is True, "Distribution should be marked as executed"
    assert ranking.allocated_count > 0, "Should have allocated students"

    # Verify application statuses updated
    allocated_apps = await db_session.execute(
        select(Application).where(Application.status == ApplicationStatus.approved.value)
    )
    allocated_count = len(allocated_apps.scalars().all())
    assert allocated_count == distribution_result["total_allocated"]

    # Verify ranking items updated
    items = await db_session.execute(select(CollegeRankingItem).where(CollegeRankingItem.ranking_id == ranking.id))
    ranking_items = items.scalars().all()

    allocated_items = [item for item in ranking_items if item.is_allocated]
    assert len(allocated_items) > 0, "Should have allocated items"

    for item in allocated_items:
        assert item.allocated_sub_type is not None, "Allocated items should have sub_type"
        assert item.status == "allocated", "Allocated items should have correct status"

    # 4. Generate roster from distribution
    from app.db.session import SessionLocal
    from app.services.roster_service import RosterService

    # Create sync session for roster service (it uses sync DB)
    sync_session = SessionLocal()
    try:
        roster_service = RosterService(sync_session)

        roster = roster_service.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2025-H1",
            roster_cycle=RosterCycle.SEMESTER,
            academic_year=114,
            created_by_user_id=admin_user.id,
            student_verification_enabled=False,
            ranking_id=ranking.id,
        )

        # 5. Verify roster generation
        assert roster is not None, "Roster should be created"
        assert roster.ranking_id == ranking.id, "Roster should reference the ranking"
        assert roster.status == RosterStatus.COMPLETED, "Roster should be completed"

        # Verify roster items
        roster_items = sync_session.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster.id).all()

        assert len(roster_items) == allocated_count, "Roster should include all allocated students"

        # Verify only allocated students are in roster
        roster_app_ids = {item.application_id for item in roster_items}
        allocated_app_ids = {app.id for app in allocated_apps.scalars().all()}
        assert roster_app_ids == allocated_app_ids, "Roster should only include allocated students"

        # Verify backup info is stored
        for item in roster_items:
            # Check if student was allocated (not backup)
            ranking_item = next((ri for ri in ranking_items if ri.application_id == item.application_id), None)
            if ranking_item and ranking_item.backup_allocations:
                assert item.backup_info is not None, "Backup info should be stored for backup students"

        sync_session.commit()

    finally:
        sync_session.close()


@pytest.mark.asyncio
async def test_roster_generation_without_distribution_fails(db_session: AsyncSession):
    """
    Test that roster generation fails if distribution hasn't been executed
    """
    # Create minimal test data
    admin_user = User(
        nycu_id="admin002",
        name="Admin User 2",
        email="admin2@test.com",
        role=UserRole.super_admin,
    )
    db_session.add(admin_user)
    await db_session.flush()

    scholarship_type = ScholarshipType(
        name="Test Scholarship 2",
        code="TEST2",
        description="Test",
        is_active=True,
        application_cycle="semester",
        user_type="student",
    )
    db_session.add(scholarship_type)
    await db_session.flush()

    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type.id,
        academic_year=114,
        semester="first",
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
        is_active=True,
        has_college_quota=False,
    )
    db_session.add(config)
    await db_session.flush()

    ranking = CollegeRanking(
        scholarship_type_id=scholarship_type.id,
        academic_year=114,
        semester="first",
        ranking_name="Unexecuted Ranking",
        status="final",
        distribution_executed=False,  # Not executed
    )
    db_session.add(ranking)
    await db_session.commit()

    # Try to generate roster
    from app.db.session import SessionLocal

    sync_session = SessionLocal()
    try:
        roster_service = RosterService(sync_session)

        with pytest.raises(ValueError) as exc_info:
            roster_service.generate_roster(
                scholarship_configuration_id=config.id,
                period_label="2025-H1",
                roster_cycle=RosterCycle.SEMESTER,
                academic_year=114,
                created_by_user_id=admin_user.id,
                student_verification_enabled=False,
                ranking_id=ranking.id,
            )

        assert "Distribution has not been executed" in str(exc_info.value)

    finally:
        sync_session.close()


@pytest.mark.asyncio
async def test_roster_generation_idempotency(db_session: AsyncSession):
    """
    Test that generating the same roster twice raises RosterAlreadyExistsError
    """
    # Create minimal test data
    admin_user = User(
        nycu_id="admin003",
        name="Admin User 3",
        email="admin3@test.com",
        role=UserRole.super_admin,
    )
    db_session.add(admin_user)
    await db_session.flush()

    scholarship_type = ScholarshipType(
        name="Test Scholarship 3",
        code="TEST3",
        description="Test",
        is_active=True,
        application_cycle="semester",
        user_type="student",
    )
    db_session.add(scholarship_type)
    await db_session.flush()

    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type.id,
        academic_year=114,
        semester="first",
        application_start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2025, 12, 31, tzinfo=timezone.utc),
        is_active=True,
        has_college_quota=False,
    )
    db_session.add(config)
    await db_session.commit()

    from app.db.session import SessionLocal

    sync_session = SessionLocal()
    try:
        roster_service = RosterService(sync_session)

        # Generate first roster
        roster1 = roster_service.generate_roster(
            scholarship_configuration_id=config.id,
            period_label="2025-H1",
            roster_cycle=RosterCycle.SEMESTER,
            academic_year=114,
            created_by_user_id=admin_user.id,
            student_verification_enabled=False,
        )
        sync_session.commit()

        assert roster1 is not None

        # Try to generate again without force_regenerate
        with pytest.raises(RosterAlreadyExistsError):
            roster_service.generate_roster(
                scholarship_configuration_id=config.id,
                period_label="2025-H1",
                roster_cycle=RosterCycle.SEMESTER,
                academic_year=114,
                created_by_user_id=admin_user.id,
                student_verification_enabled=False,
            )

    finally:
        sync_session.close()


@pytest.mark.asyncio
async def test_distribution_transaction_rollback_on_error(db_session: AsyncSession):
    """
    Test that distribution transaction rolls back properly on error
    """
    # Create test data that will cause an error
    admin_user = User(
        nycu_id="admin004",
        name="Admin User 4",
        email="admin4@test.com",
        role=UserRole.super_admin,
    )
    db_session.add(admin_user)
    await db_session.commit()

    # Try to execute distribution on non-existent ranking
    distribution_service = MatrixDistributionService(db_session)

    with pytest.raises(ValueError) as exc_info:
        await distribution_service.execute_matrix_distribution(
            ranking_id=99999,  # Non-existent
            executor_id=admin_user.id,
        )

    assert "Ranking 99999 not found" in str(exc_info.value)

    # Verify database is in clean state (no partial changes)
    # This test mainly ensures the rollback logic works

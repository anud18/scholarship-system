"""DB- and SIS-API-aware tests for SupplementaryImportService."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.supplementary_import_service import (
    SupplementaryImportService,
    SupplementaryRow,
)


@pytest.mark.asyncio
class TestValidateNoDuplicateApplications:
    async def test_returns_empty_when_no_duplicates(self, db: AsyncSession):
        service = SupplementaryImportService(db, student_service=AsyncMock())
        rows = [SupplementaryRow("310460001", 1, ["nstc"], None, None, {})]
        conflicts = await service.validate_no_duplicate_applications(
            rows, scholarship_type_id=1, academic_year=114, semester="yearly"
        )
        assert conflicts == []

    async def test_returns_conflict_ids_when_duplicate_exists(self, db: AsyncSession):
        user = User(
            nycu_id="310460001",
            name="王小明",
            email="test@nycu.edu.tw",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(user)
        await db.flush()

        app = Application(
            app_id="APP-114-0-00001",
            user_id=user.id,
            scholarship_type_id=1,
            academic_year=114,
            semester=None,  # yearly is stored as NULL
            status=ApplicationStatus.submitted,
            sub_type_selection_mode=SubTypeSelectionMode.single,
        )
        db.add(app)
        await db.flush()

        service = SupplementaryImportService(db, student_service=AsyncMock())
        rows = [SupplementaryRow("310460001", 1, ["nstc"], None, None, {})]
        conflicts = await service.validate_no_duplicate_applications(
            rows, scholarship_type_id=1, academic_year=114, semester="yearly"
        )
        assert "310460001" in conflicts


@pytest.mark.asyncio
class TestFetchStudentDataBulk:
    async def test_returns_data_for_known_ids(self, db: AsyncSession):
        mock_student_service = AsyncMock()
        mock_student_service.api_enabled = True
        mock_student_service.get_student_snapshot = AsyncMock(
            return_value={
                "std_stdcode": "310460001",
                "std_cname": "王小明",
                "com_email": "test@nycu.edu.tw",
                "_api_fetched_at": "2025-10-22T17:27:08Z",
                "_term_data_status": "success",
            }
        )
        service = SupplementaryImportService(db, student_service=mock_student_service)
        data_map, missing = await service.fetch_student_data_bulk(["310460001"], academic_year=114, semester="yearly")
        assert "310460001" in data_map
        assert missing == []

    async def test_returns_missing_for_unknown_ids(self, db: AsyncSession):
        mock_student_service = AsyncMock()
        mock_student_service.api_enabled = True
        mock_student_service.get_student_snapshot = AsyncMock(side_effect=NotFoundError("student not found"))
        service = SupplementaryImportService(db, student_service=mock_student_service)
        data_map, missing = await service.fetch_student_data_bulk(["999999"], academic_year=114, semester="yearly")
        assert missing == ["999999"]
        assert data_map == {}

    async def test_raises_when_api_disabled(self, db: AsyncSession):
        mock_student_service = AsyncMock()
        mock_student_service.api_enabled = False
        service = SupplementaryImportService(db, student_service=mock_student_service)
        with pytest.raises(ValueError, match="學生 API 未啟用"):
            await service.fetch_student_data_bulk(["310460001"], academic_year=114, semester="yearly")


@pytest.mark.asyncio
class TestFindOrCreateUsers:
    async def test_creates_new_user_when_not_found(self, db: AsyncSession):
        service = SupplementaryImportService(db, student_service=AsyncMock())
        student_data_map = {
            "310460002": {
                "std_stdcode": "310460002",
                "std_cname": "新學生",
                "com_email": "new@nycu.edu.tw",
                "std_depno": "4460",
            }
        }
        user_map = await service.find_or_create_users(student_data_map)
        assert "310460002" in user_map
        assert user_map["310460002"].nycu_id == "310460002"
        assert user_map["310460002"].name == "新學生"
        assert user_map["310460002"].email == "new@nycu.edu.tw"

    async def test_reuses_existing_user(self, db: AsyncSession):
        existing = User(
            nycu_id="310460003",
            name="既有",
            email="existing@nycu.edu.tw",
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(existing)
        await db.flush()
        existing_id = existing.id

        service = SupplementaryImportService(db, student_service=AsyncMock())
        user_map = await service.find_or_create_users({"310460003": {"std_cname": "x"}})
        assert user_map["310460003"].id == existing_id


@pytest.mark.asyncio
class TestCreateApplicationsAndItems:
    async def test_populates_scholarship_subtype_list_for_distribution_panel(self, db: AsyncSession):
        """Distribution panel reads applied_sub_types from
        scholarship_subtype_list — supplementary import must populate it
        (not just sub_type_preferences) or imported students go invisible there.
        """
        from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
        from app.models.college_review import CollegeRanking
        from app.models.user import User as UserModel

        # Minimal scholarship + config + ranking + creator
        scholarship = ScholarshipType(
            code="phd_subtype_test",
            name="Test",
            sub_type_selection_mode=SubTypeSelectionMode.single,
            status="active",
        )
        db.add(scholarship)
        await db.flush()

        config = ScholarshipConfiguration(
            scholarship_type_id=scholarship.id,
            academic_year=114,
            config_name="Test 114學年",
            config_code="phd_subtype_test_114",
            amount=30000,
        )
        db.add(config)
        await db.flush()

        creator = UserModel(
            nycu_id="col_subtype",
            name="College",
            email="cs@nycu.edu.tw",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code="A",
        )
        db.add(creator)
        await db.flush()

        ranking = CollegeRanking(
            scholarship_type_id=scholarship.id,
            sub_type_code="nstc",
            academic_year=114,
            ranking_name="r",
            created_by=creator.id,
        )
        db.add(ranking)
        await db.flush()
        # Refresh so ranking.scholarship_type relationship is populated
        await db.refresh(ranking, attribute_names=["scholarship_type"])

        service = SupplementaryImportService(db, student_service=AsyncMock())

        # One imported row preferring nstc then moe_1w
        rows = [
            SupplementaryRow(
                student_id="310460050",
                excel_rank=1,
                sub_type_preferences=["nstc", "moe_1w"],
                bank_account=None,
                advisor_name=None,
                submitted_form_fields={},
            )
        ]
        student_data_map = {"310460050": {"std_stdcode": "310460050", "std_cname": "新生"}}
        user_map = await service.find_or_create_users(student_data_map)

        created = await service.create_applications_and_items(
            rows, user_map, student_data_map, ranking, max_existing_rank=0, scholarship_configuration=config
        )
        await db.flush()
        assert created == 1

        # Inspect the resulting Application
        from sqlalchemy import select

        result = await db.execute(select(Application).where(Application.user_id == user_map["310460050"].id))
        app_row = result.scalar_one()
        assert app_row.scholarship_subtype_list == ["nstc", "moe_1w"], (
            "scholarship_subtype_list must be populated so manual distribution panel " "renders the applied sub-types"
        )
        assert app_row.sub_type_preferences == ["nstc", "moe_1w"]
        assert app_row.scholarship_configuration_id == config.id, (
            "scholarship_configuration_id must be set or roster rule validation "
            "excludes the student with 未關聯獎學金配置 (issue #1213)"
        )
        # Shared submitted-application invariants (application_builder parity):
        # roster rule validation selects rule sets by sub_scholarship_type, so
        # the "general" default would pick the wrong rules.
        assert app_row.sub_scholarship_type == "nstc"
        assert app_row.status == ApplicationStatus.submitted
        assert app_row.submitted_at is not None
        assert app_row.amount == 30000
        assert app_row.scholarship_name == "Test 114學年"

    async def test_rejects_missing_scholarship_configuration(self, db: AsyncSession):
        """Creating supplementary applications without a resolved configuration
        must fail up front — a NULL scholarship_configuration_id application
        gets excluded from 造冊 later (issue #1213).
        """
        service = SupplementaryImportService(db, student_service=AsyncMock())
        rows = [SupplementaryRow("310460051", 1, ["nstc"], None, None, {})]

        with pytest.raises(ValueError, match="找不到對應的獎學金配置"):
            await service.create_applications_and_items(
                rows,
                user_map={},
                student_data_map={},
                ranking=None,
                max_existing_rank=0,
                scholarship_configuration=None,
            )

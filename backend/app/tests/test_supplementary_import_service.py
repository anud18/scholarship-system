"""DB- and SIS-API-aware tests for SupplementaryImportService."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.supplementary_import_service import SupplementaryImportService


def _row(student_id: str, sub_types=("nstc",), *, advisor_nycu_id=None, custom_fields=None):
    """One parsed row in the batch-import shape 補充匯入 now consumes."""
    return {
        "student_id": student_id,
        "student_name": "測試生",
        "postal_account": None,
        "advisor_name": None,
        "advisor_email": None,
        "advisor_nycu_id": advisor_nycu_id,
        "is_renewal": False,
        "renewal_year": None,
        "sub_types": list(sub_types),
        "custom_fields": custom_fields or {},
    }


@pytest.mark.asyncio
class TestValidateNoDuplicateApplications:
    async def test_returns_empty_when_no_duplicates(self, db: AsyncSession):
        service = SupplementaryImportService(db, student_service=AsyncMock())
        rows = [_row("310460001")]
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
        rows = [_row("310460001")]
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
        data_map, missing, errored = await service.fetch_student_data_bulk(
            ["310460001"], academic_year=114, semester="yearly"
        )
        assert "310460001" in data_map
        assert missing == []
        assert errored == []

    async def test_returns_missing_for_unknown_ids(self, db: AsyncSession):
        mock_student_service = AsyncMock()
        mock_student_service.api_enabled = True
        mock_student_service.get_student_snapshot = AsyncMock(side_effect=NotFoundError("student not found"))
        service = SupplementaryImportService(db, student_service=mock_student_service)
        data_map, missing, errored = await service.fetch_student_data_bulk(
            ["999999"], academic_year=114, semester="yearly"
        )
        assert missing == ["999999"]
        assert data_map == {}
        assert errored == []

    async def test_separates_sis_errors_from_unknown_ids(self, db: AsyncSession):
        """A timeout/5xx is NOT a wrong 學號 — reporting it as 查無學號 sends the
        college hunting for a typo in a perfectly correct number."""
        from app.core.exceptions import ServiceUnavailableError

        mock_student_service = AsyncMock()
        mock_student_service.api_enabled = True
        mock_student_service.get_student_snapshot = AsyncMock(
            side_effect=ServiceUnavailableError("Student API is unavailable")
        )
        service = SupplementaryImportService(db, student_service=mock_student_service)
        data_map, missing, errored = await service.fetch_student_data_bulk(
            ["310460001"], academic_year=114, semester="yearly"
        )
        assert data_map == {}
        assert missing == []
        assert errored == ["310460001"]

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


async def _make_scholarship_and_config(db: AsyncSession, *, code: str, semester=None):
    """Minimal ScholarshipType + ScholarshipConfiguration for import tests."""
    from app.models.scholarship import ScholarshipConfiguration, ScholarshipType

    scholarship = ScholarshipType(
        code=code,
        name="Test",
        sub_type_list=["nstc", "moe_1w"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status="active",
    )
    db.add(scholarship)
    await db.flush()

    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=114,
        semester=semester,
        config_name="Test 114學年",
        config_code=f"{code}_114",
        amount=30000,
    )
    db.add(config)
    await db.flush()
    await db.refresh(config, attribute_names=["scholarship_type"])
    return scholarship, config


async def _make_importer(db: AsyncSession, nycu_id: str):
    from app.models.user import User as UserModel

    importer = UserModel(
        nycu_id=nycu_id,
        name="College",
        email=f"{nycu_id}@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.college,
        college_code="A",
    )
    db.add(importer)
    await db.flush()
    return importer


@pytest.mark.asyncio
class TestCreateApplications:
    async def test_populates_scholarship_subtype_list_for_distribution_panel(self, db: AsyncSession):
        """Distribution panel reads applied_sub_types from
        scholarship_subtype_list — supplementary import must populate it
        (not just sub_type_preferences) or imported students go invisible there.
        """
        _, config = await _make_scholarship_and_config(db, code="phd_subtype_test")
        importer = await _make_importer(db, "col_subtype")

        service = SupplementaryImportService(db, student_service=AsyncMock())

        # One imported row preferring nstc then moe_1w
        rows = [_row("310460050", sub_types=["nstc", "moe_1w"])]
        student_data_map = {"310460050": {"std_stdcode": "310460050", "std_cname": "新生"}}
        user_map = await service.find_or_create_users(student_data_map)

        created, unresolved = await service.create_applications(
            rows, user_map, student_data_map, config, importer_id=importer.id
        )
        await db.flush()
        assert created == 1
        # No advisor on file → the student cannot be routed to a professor yet.
        assert unresolved == ["310460050"]

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
        # Provenance: the row is a college-submitted application, not an online one
        assert app_row.import_source == "supplementary_import"
        assert app_row.imported_by_id == importer.id

    async def test_creates_no_ranking_item(self, db: AsyncSession):
        """補充匯入 students carry no rank — they are ranked later by the ordinary
        college ranking flow, so no CollegeRankingItem may be written here."""
        from sqlalchemy import select

        from app.models.college_review import CollegeRankingItem

        _, config = await _make_scholarship_and_config(db, code="phd_no_rank_item")
        importer = await _make_importer(db, "col_no_rank")

        service = SupplementaryImportService(db, student_service=AsyncMock())
        rows = [_row("310460060")]
        student_data_map = {"310460060": {"std_stdcode": "310460060", "std_cname": "新生"}}
        user_map = await service.find_or_create_users(student_data_map)

        created, _unresolved = await service.create_applications(
            rows, user_map, student_data_map, config, importer_id=importer.id
        )
        await db.flush()
        assert created == 1

        app_row = (
            await db.execute(select(Application).where(Application.user_id == user_map["310460060"].id))
        ).scalar_one()
        items = (
            (await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.application_id == app_row.id)))
            .scalars()
            .all()
        )
        assert items == []

    async def test_assigns_professor_from_advisor_nycu_id_in_the_sheet(self, db: AsyncSession):
        """Professor review lists filter on Application.professor_id, so the import
        must link the advisor the same way the student and batch paths do.

        The 批次匯入 workbook carries 指導教授本校人事編號, so this must resolve for a
        brand-new student with no prior profile — that is the whole reason 補充匯入
        moved onto this format.
        """
        from app.models.user import User as UserModel

        _, config = await _make_scholarship_and_config(db, code="phd_prof_link")
        importer = await _make_importer(db, "col_prof_link")

        professor = UserModel(
            nycu_id="P0001",
            name="指導教授A",
            email="prof@nycu.edu.tw",
            user_type=UserType.employee,
            role=UserRole.professor,
        )
        db.add(professor)
        await db.flush()

        service = SupplementaryImportService(db, student_service=AsyncMock())
        rows = [_row("310460070", advisor_nycu_id="P0001")]
        student_data_map = {"310460070": {"std_stdcode": "310460070", "std_cname": "新生"}}
        user_map = await service.find_or_create_users(student_data_map)

        # No pre-existing UserProfile — the 人事編號 comes from the uploaded sheet.
        profile_map = await service.upsert_user_profiles(user_map, rows)

        created, unresolved = await service.create_applications(
            rows, user_map, student_data_map, config, importer_id=importer.id, profile_map=profile_map
        )
        await db.flush()
        assert created == 1
        assert unresolved == []

        from sqlalchemy import select

        app_row = (
            await db.execute(select(Application).where(Application.user_id == user_map["310460070"].id))
        ).scalar_one()
        assert app_row.professor_id == professor.id

    async def test_yearly_config_stores_null_semester(self, db: AsyncSession):
        """A yearly cycle stores NULL in Application.semester while the app-id
        sequence keys on the "yearly" string (semester code 0)."""
        from app.models.enums import Semester

        _, config = await _make_scholarship_and_config(db, code="phd_yearly", semester=Semester.yearly)
        importer = await _make_importer(db, "col_yearly")

        service = SupplementaryImportService(db, student_service=AsyncMock())
        rows = [_row("310460080")]
        student_data_map = {"310460080": {"std_stdcode": "310460080", "std_cname": "新生"}}
        user_map = await service.find_or_create_users(student_data_map)

        await service.create_applications(rows, user_map, student_data_map, config, importer_id=importer.id)
        await db.flush()

        from sqlalchemy import select

        app_row = (
            await db.execute(select(Application).where(Application.user_id == user_map["310460080"].id))
        ).scalar_one()
        assert app_row.semester is None
        assert app_row.app_id.startswith("APP-114-0-")

    async def test_rejects_general_sub_type_when_scholarship_defines_sub_types(self, db: AsyncSession):
        """A blank 申請獎學金類別 cell would mint a "general" application that maps to
        no quota slot — reject it the way the student submit path does."""
        from app.core.exceptions import ValidationError

        _, config = await _make_scholarship_and_config(db, code="phd_general_reject")
        importer = await _make_importer(db, "col_general")

        service = SupplementaryImportService(db, student_service=AsyncMock())
        rows = [_row("310460090", sub_types=[])]
        student_data_map = {"310460090": {"std_stdcode": "310460090", "std_cname": "新生"}}
        user_map = await service.find_or_create_users(student_data_map)

        with pytest.raises(ValidationError, match="310460090"):
            await service.create_applications(rows, user_map, student_data_map, config, importer_id=importer.id)

    async def test_rejects_missing_scholarship_configuration(self, db: AsyncSession):
        """Creating supplementary applications without a resolved configuration
        must fail up front — a NULL scholarship_configuration_id application
        gets excluded from 造冊 later (issue #1213).
        """
        service = SupplementaryImportService(db, student_service=AsyncMock())
        rows = [_row("310460051")]

        with pytest.raises(ValueError, match="找不到對應的獎學金配置"):
            await service.create_applications(
                rows,
                user_map={},
                student_data_map={},
                scholarship_configuration=None,
                importer_id=1,
            )

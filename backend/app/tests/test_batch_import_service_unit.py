"""
Unit tests for BatchImportService

Tests file parsing, validation, bulk operations, and transaction rollback.
"""

import io
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pandas as pd
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BatchImportError
from app.models.application import Application, ApplicationStatus
from app.models.batch_import import BatchImport
from app.models.enums import BatchImportStatus, ReviewStage, Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.batch_import import BatchImportValidationError
from app.services.batch_import_service import BatchImportService


class TestBatchImportService:
    """Test cases for BatchImportService"""

    @pytest.fixture
    def service(self, db: AsyncSession):
        """Create BatchImportService instance for testing"""
        return BatchImportService(db)

    @pytest.fixture
    def mock_scholarship(self):
        """Mock scholarship type"""
        scholarship = Mock(spec=ScholarshipType)
        scholarship.id = 1
        scholarship.name = "Test Scholarship"
        scholarship.code = "test_scholarship"
        scholarship.amount = 10000
        scholarship.main_type = "general"
        scholarship.sub_type_selection_mode = "single"
        # No real sub-types → parse_excel_file must not require sub-type marks.
        scholarship.sub_type_list = []
        return scholarship

    @pytest.fixture
    def mock_scholarship_config(self):
        """Mock scholarship configuration"""
        config = Mock(spec=ScholarshipConfiguration)
        config.id = 1
        config.scholarship_type_id = 1
        config.academic_year = 113
        config.semester = Semester.first
        config.config_name = "Test Scholarship 113-1"
        config.config_code = "test_113_1"
        config.amount = 10000
        return config

    @pytest.fixture
    def sample_excel_data(self):
        """Sample parsed Excel data"""
        return [
            {
                "student_id": "111111111",
                "student_name": "王小明",
                "dept_code": "5201",
                "bank_account": "1234567890",
                "account_holder": "王小明",
                "bank_name": "台灣銀行",
                "gpa": 3.8,
                "sub_types": ["type_a"],
            },
            {
                "student_id": "222222222",
                "student_name": "陳小華",
                "dept_code": "5202",
                "bank_account": "9876543210",
                "account_holder": "陳小華",
                "bank_name": "第一銀行",
                "gpa": 3.9,
                "sub_types": [],
            },
        ]

    @pytest.mark.asyncio
    async def test_parse_excel_file_success(self, service, mock_scholarship):
        """Test successful Excel file parsing"""
        # Create valid Excel content (minimal valid XLSX)
        import io

        import pandas as pd

        df = pd.DataFrame(
            {
                "student_id": ["111111111", "222222222"],
                "student_name": ["王小明", "陳小華"],
                "dept_code": ["5201", "5202"],
            }
        )

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        file_content = buffer.getvalue()

        # Mock scholarship lookup; custom_fields query hits real empty test DB (returns [])
        with patch.object(service.db, "get", return_value=mock_scholarship):
            parsed_data, errors = await service.parse_excel_file(
                file_content=file_content, scholarship_type_id=1, academic_year=113, semester="first"
            )

        # Assertions
        assert len(parsed_data) == 2
        assert len(errors) == 0
        assert parsed_data[0]["student_id"] == "111111111"
        assert parsed_data[0]["student_name"] == "王小明"

    @pytest.mark.asyncio
    async def test_parse_excel_file_missing_columns(self, service, mock_scholarship):
        """Test Excel parsing with missing required columns"""
        import io

        import pandas as pd

        # Missing student_name column
        df = pd.DataFrame({"student_id": ["111111111"]})

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False)
        file_content = buffer.getvalue()

        # Mock scholarship lookup; custom_fields query hits real empty test DB (returns [])
        with patch.object(service.db, "get", return_value=mock_scholarship):
            parsed_data, errors = await service.parse_excel_file(
                file_content=file_content, scholarship_type_id=1, academic_year=113, semester="first"
            )

        # Assertions
        assert len(parsed_data) == 0
        assert len(errors) == 1
        assert errors[0].error_type == "missing_columns"
        assert "student_name" in errors[0].message

    @pytest.mark.asyncio
    async def test_get_or_create_users_bulk_existing(self, service, sample_excel_data):
        """Test bulk user fetching when users already exist"""
        # Mock existing users
        existing_user_1 = Mock(spec=User)
        existing_user_1.nycu_id = "111111111"
        existing_user_1.id = 1

        existing_user_2 = Mock(spec=User)
        existing_user_2.nycu_id = "222222222"
        existing_user_2.id = 2

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [existing_user_1, existing_user_2]

        with patch.object(service.db, "execute", return_value=mock_result):
            user_map = await service._get_or_create_users_bulk(sample_excel_data)

            assert len(user_map) == 2
            assert user_map["111111111"].id == 1
            assert user_map["222222222"].id == 2

    @pytest.mark.asyncio
    async def test_get_or_create_users_bulk_create_new(self, service, sample_excel_data):
        """Test bulk user creation when users don't exist"""
        # Mock no existing users
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []

        with (
            patch.object(service.db, "execute", return_value=mock_result),
            patch.object(service.db, "add") as mock_add,
            patch.object(service.db, "flush", new_callable=AsyncMock) as mock_flush,
        ):
            user_map = await service._get_or_create_users_bulk(sample_excel_data)

            # Should create 2 new users
            assert mock_add.call_count == 2
            assert mock_flush.call_count == 1
            assert len(user_map) == 2

    @pytest.mark.asyncio
    async def test_create_applications_from_batch_success(
        self, service, mock_scholarship, mock_scholarship_config, sample_excel_data
    ):
        """Test successful application creation from batch"""
        batch_import = Mock(spec=BatchImport)
        batch_import.id = 1
        batch_import.importer_id = 10

        # Mock user map
        user_1 = Mock(spec=User)
        user_1.id = 1
        user_1.nycu_id = "111111111"

        user_2 = Mock(spec=User)
        user_2.id = 2
        user_2.nycu_id = "222222222"

        user_map = {"111111111": user_1, "222222222": user_2}

        # Mock student snapshot data
        mock_student_snapshot = {
            "std_stdcode": "111111111",
            "std_cname": "王小明",
            "std_depno": "5201",
            "std_academyno": "A",
            "trm_year": 113,
            "trm_term": 1,
            "com_email": "test@nctu.edu.tw",
            "_api_fetched_at": "2025-10-24T00:00:00Z",
            "_term_data_status": "success",
        }

        with (
            patch.object(service.db, "get", return_value=mock_scholarship),
            patch.object(service, "_get_or_create_users_bulk", return_value=user_map),
            patch.object(service.db, "add") as mock_add,
            patch.object(service.db, "flush", new_callable=AsyncMock),
            patch.object(
                service.student_service,
                "get_student_snapshot",
                new_callable=AsyncMock,
                return_value=mock_student_snapshot,
            ),
            # The profile upsert, form-data shaping and professor assignment each
            # run their own DB queries; patch them here so this stays a focused
            # unit test of the orchestration (the DB-backed tests below exercise
            # the real helpers). Their absence keeps db.execute to config + one
            # sequence lookup per row.
            patch.object(
                service,
                "_build_submitted_form_data",
                new_callable=AsyncMock,
                return_value={"fields": {}, "documents": []},
            ),
            patch.object(service, "_upsert_user_profile", new_callable=AsyncMock),
            patch(
                "app.services.batch_import_service.assign_professor_from_profile",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch.object(service.db, "execute") as mock_execute,
        ):
            # Mock scholarship configuration lookup and ApplicationSequence lookup
            mock_config_result = Mock()
            mock_config_result.scalar_one_or_none.return_value = mock_scholarship_config

            mock_seq_result = Mock()
            mock_seq_result.scalar_one_or_none.return_value = None

            # Set up execute to return config first, then sequence on subsequent calls
            mock_execute.side_effect = [mock_config_result] + [mock_seq_result] * 2

            created_ids, errors = await service.create_applications_from_batch(
                batch_import=batch_import,
                parsed_data=sample_excel_data,
                scholarship_type_id=1,
                academic_year=113,
                semester="first",
            )

            # Should create 2 applications + 2 ApplicationSequence records (one per student)
            assert mock_add.call_count == 4
            assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_create_applications_from_batch_rollback_on_error(
        self, service, mock_scholarship, mock_scholarship_config, sample_excel_data
    ):
        """Test transaction rollback on error"""
        batch_import = Mock(spec=BatchImport)
        batch_import.id = 1
        batch_import.importer_id = 10

        with (
            patch.object(service.db, "get", return_value=mock_scholarship),
            patch.object(service, "_get_or_create_users_bulk", side_effect=Exception("Database error")),
            patch.object(service.db, "rollback", new_callable=AsyncMock) as mock_rollback,
            patch.object(service.db, "commit", new_callable=AsyncMock),
            patch.object(service.db, "execute") as mock_execute,
        ):
            # Mock configuration lookup
            mock_config_result = Mock()
            mock_config_result.scalar_one_or_none.return_value = mock_scholarship_config
            mock_execute.return_value = mock_config_result

            with pytest.raises(BatchImportError) as exc_info:
                await service.create_applications_from_batch(
                    batch_import=batch_import,
                    parsed_data=sample_excel_data,
                    scholarship_type_id=1,
                    academic_year=113,
                    semester="first",
                )

            # Should rollback transaction
            assert mock_rollback.call_count == 1
            assert "Database error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_applications_from_batch_no_scholarship(self, service, sample_excel_data):
        """Test error when scholarship type doesn't exist"""
        batch_import = Mock(spec=BatchImport)
        batch_import.id = 1

        with patch.object(service.db, "get", return_value=None):
            with pytest.raises(BatchImportError) as exc_info:
                await service.create_applications_from_batch(
                    batch_import=batch_import,
                    parsed_data=sample_excel_data,
                    scholarship_type_id=999,
                    academic_year=113,
                    semester="first",
                )

            assert "不存在" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_applications_from_batch_no_configuration(self, service, mock_scholarship, sample_excel_data):
        """Test error when scholarship configuration doesn't exist for the academic period"""
        batch_import = Mock(spec=BatchImport)
        batch_import.id = 1

        with (
            patch.object(service.db, "get", return_value=mock_scholarship),
            patch.object(service.db, "execute") as mock_execute,
        ):
            # Mock configuration lookup returning None (no config found)
            mock_config_result = Mock()
            mock_config_result.scalar_one_or_none.return_value = None
            mock_execute.return_value = mock_config_result

            with pytest.raises(BatchImportError) as exc_info:
                await service.create_applications_from_batch(
                    batch_import=batch_import,
                    parsed_data=sample_excel_data,
                    scholarship_type_id=1,
                    academic_year=113,
                    semester="first",
                )

            # Should mention configuration not found
            assert "找不到獎學金配置" in str(exc_info.value)
            assert "113學年度" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_bulk_validate_missing_student_with_dept(self):
        """Missing students should be marked as valid and will be created later with SIS data."""
        db_mock = AsyncMock()
        service = BatchImportService(db_mock)

        # Mock: no existing users in database
        user_result = Mock()
        user_scalars = Mock()
        user_scalars.all.return_value = []
        user_result.scalars.return_value = user_scalars

        db_mock.execute.side_effect = [user_result]

        permission_results, duplicate_results, warnings = await service.bulk_validate_permissions_and_duplicates(
            student_ids=["111111111"],
            college_code="C",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            student_dept_map={"111111111": "5201"},
        )

        assert permission_results["111111111"] == (True, None)
        assert duplicate_results["111111111"] == (False, None)
        # New students should not generate "student_not_in_system" warning
        # They will be created later by _get_or_create_users_bulk with SIS data
        assert not any(w.get("warning_type") == "student_not_in_system" for w in warnings)

    @pytest.mark.asyncio
    async def test_bulk_validate_existing_student_uses_file_dept(self):
        """Existing student without dept should use batch dept_code for validation."""
        from app.models.student import Department

        db_mock = AsyncMock()
        mock_student_service = MagicMock()
        mock_student_service.api_enabled = False
        service = BatchImportService(db_mock, student_service=mock_student_service)

        student = Mock(spec=User)
        student.nycu_id = "111111111"
        student.dept_code = None
        student.raw_data = None
        student.id = 10

        user_result = Mock()
        user_scalars = Mock()
        user_scalars.all.return_value = [student]
        user_result.scalars.return_value = user_scalars

        duplicates_result = Mock()
        duplicates_scalars = Mock()
        duplicates_scalars.all.return_value = []
        duplicates_result.scalars.return_value = duplicates_scalars

        db_mock.execute.side_effect = [user_result, duplicates_result]

        permission_results, duplicate_results, warnings = await service.bulk_validate_permissions_and_duplicates(
            student_ids=["111111111"],
            college_code="C",
            scholarship_type_id=1,
            academic_year=113,
            semester="first",
            student_dept_map={"111111111": "5201"},
        )

        assert permission_results["111111111"] == (True, None)
        assert duplicate_results["111111111"] == (False, None)
        assert warnings == []

    @pytest.mark.asyncio
    async def test_check_duplicate_application_exists(self, service):
        """Test duplicate application detection"""
        from app.models.application import Application

        # Mock existing application
        existing_app = Mock(spec=Application)
        existing_app.id = 100

        with patch.object(service.db, "execute") as mock_execute:
            # Mock user exists
            user_result = Mock()
            user_result.scalar_one_or_none.return_value = Mock(id=1)

            # Mock application exists
            app_result = Mock()
            app_result.scalar_one_or_none.return_value = existing_app

            mock_execute.side_effect = [user_result, app_result]

            is_duplicate, error_msg = await service.check_duplicate_application(
                student_id="111111111", scholarship_type_id=1, academic_year=113, semester="first"
            )

            assert is_duplicate is True
            assert "APP-100" in error_msg

    @pytest.mark.asyncio
    async def test_check_duplicate_application_not_exists(self, service):
        """Test no duplicate when application doesn't exist"""
        with patch.object(service.db, "execute") as mock_execute:
            # Mock user exists
            user_result = Mock()
            user_result.scalar_one_or_none.return_value = Mock(id=1)

            # Mock no application
            app_result = Mock()
            app_result.scalar_one_or_none.return_value = None

            mock_execute.side_effect = [user_result, app_result]

            is_duplicate, error_msg = await service.check_duplicate_application(
                student_id="111111111", scholarship_type_id=1, academic_year=113, semester="first"
            )

            assert is_duplicate is False
            assert error_msg is None

    @pytest.mark.asyncio
    async def test_create_batch_import_record(self, service):
        """Test batch import record creation"""
        with (
            patch.object(service.db, "add") as mock_add,
            patch.object(service.db, "flush", new_callable=AsyncMock) as mock_flush,
        ):
            batch_import = await service.create_batch_import_record(
                importer_id=10,
                college_code="E",
                scholarship_type_id=1,
                academic_year=113,
                semester="first",
                file_name="test.xlsx",
                total_records=50,
            )

            assert batch_import.importer_id == 10
            assert batch_import.college_code == "E"
            assert batch_import.total_records == 50
            assert batch_import.import_status == BatchImportStatus.pending.value
            assert mock_add.call_count == 1
            assert mock_flush.call_count == 1

    @pytest.mark.asyncio
    async def test_update_batch_import_status(self, service):
        """Test batch import status update"""
        batch_import = Mock(spec=BatchImport)
        errors = [
            BatchImportValidationError(
                row_number=2,
                student_id="111111111",
                field="bank_account",
                error_type="validation_error",
                message="Invalid format",
            )
        ]

        with patch.object(service.db, "commit", new_callable=AsyncMock):
            await service.update_batch_import_status(
                batch_import=batch_import,
                success_count=45,
                failed_count=5,
                errors=errors,
                status="partial",
            )

            assert batch_import.success_count == 45
            assert batch_import.failed_count == 5
            assert batch_import.import_status == "partial"
            assert batch_import.error_summary["total_errors"] == 1


# ─── parse_excel_file sub-type parsing (checkmark semantics) ─────────


@pytest_asyncio.fixture
async def scholarship_with_sub_types(db: AsyncSession):
    """A ScholarshipType that defines real sub-types (nstc, moe_1w).

    Mirrors the ScholarshipType construction style in
    test_batch_import_endpoints.py: only columns that exist on
    ScholarshipType are set (period/amount live on ScholarshipConfiguration).
    """
    scholarship = ScholarshipType(
        code="phd_sub_types",
        name="PhD Scholarship With Sub Types",
        sub_type_list=["nstc", "moe_1w"],
        sub_type_selection_mode="multiple",
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


@pytest.mark.asyncio
async def test_parse_orders_preferences_moe_first_regardless_of_numbers(db, scholarship_with_sub_types):
    # 國科會=1, 教育部=2 in the Excel — moe_1w must STILL come first
    df = pd.DataFrame([{"學號": "313554001", "學生姓名": "王小明", "國科會": 1, "教育部": 2}])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)

    service = BatchImportService(db)
    parsed, errors = await service.parse_excel_file(buf.getvalue(), scholarship_with_sub_types.id, 114, None)

    assert errors == []
    assert parsed[0]["sub_types"] == ["moe_1w", "nstc"]


@pytest.mark.asyncio
async def test_parse_accepts_checkmark_v(db, scholarship_with_sub_types):
    df = pd.DataFrame([{"學號": "313554001", "學生姓名": "王小明", "國科會": "V", "教育部": ""}])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)

    service = BatchImportService(db)
    parsed, errors = await service.parse_excel_file(buf.getvalue(), scholarship_with_sub_types.id, 114, None)

    assert errors == []
    assert parsed[0]["sub_types"] == ["nstc"]


@pytest.mark.asyncio
async def test_parse_missing_sub_type_is_hard_error(db, scholarship_with_sub_types):
    df = pd.DataFrame([{"學號": "313554001", "學生姓名": "王小明", "國科會": "", "教育部": ""}])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)

    service = BatchImportService(db)
    parsed, errors = await service.parse_excel_file(buf.getvalue(), scholarship_with_sub_types.id, 114, None)

    assert parsed == []
    assert len(errors) == 1
    assert errors[0].error_type == "missing_sub_type"
    assert errors[0].student_id == "313554001"


@pytest_asyncio.fixture
async def scholarship_general_only(db: AsyncSession):
    """A ScholarshipType carrying only the synthetic "general" placeholder
    (the model default). It defines NO real sub-types, so rows must NOT be
    required to mark one."""
    scholarship = ScholarshipType(
        code="general_only",
        name="General Scholarship",
        sub_type_list=["general"],
        sub_type_selection_mode="single",
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


@pytest.mark.asyncio
async def test_parse_general_only_scholarship_needs_no_sub_type_mark(db, scholarship_general_only):
    # No sub-type columns at all; a "general"-only scholarship must parse cleanly.
    df = pd.DataFrame([{"學號": "313554001", "學生姓名": "王小明"}])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)

    service = BatchImportService(db)
    parsed, errors = await service.parse_excel_file(buf.getvalue(), scholarship_general_only.id, 114, None)

    assert errors == []
    assert len(parsed) == 1
    assert parsed[0]["sub_types"] == []


# ─── create_applications_from_batch: student-submission parity ───────
#
# These are DB-backed (unlike the mocked TestBatchImportService cases
# above): they persist real rows and read them back so the spec
# behaviour — batch-created applications entering the standard review
# flow — is verified against real DB state, not mocks.


def _no_sis_student_service():
    """A StudentService stub that reports no SIS data, so the batch
    path falls back to Excel values without any network call (the test
    env's default settings have the SIS API 'enabled')."""
    stub = MagicMock()
    stub.get_student_basic_info = AsyncMock(return_value=None)
    stub.get_student_snapshot = AsyncMock(return_value=None)
    return stub


@pytest_asyncio.fixture
async def scholarship_with_config(db: AsyncSession):
    """A ScholarshipType plus a matching 114-year ScholarshipConfiguration
    (period/amount/config_name live on the configuration)."""
    scholarship = ScholarshipType(
        code="phd_batch",
        name="PhD Batch Scholarship",
        sub_type_list=["nstc", "moe_1w"],
        sub_type_selection_mode="multiple",
    )
    db.add(scholarship)
    await db.flush()

    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=114,
        semester=None,
        config_name="PhD Batch Scholarship 114",
        config_code="phd_batch_114",
        amount=10000,
    )
    db.add(config)
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


@pytest_asyncio.fixture
async def batch_import_fixture(db: AsyncSession):
    """A persisted BatchImport record and its importer user."""
    importer = User(nycu_id="importer_admin", name="Importer", role="admin", user_type="employee")
    db.add(importer)
    await db.flush()

    batch = BatchImport(
        importer_id=importer.id,
        college_code="E",
        academic_year=114,
        file_name="test.xlsx",
        total_records=1,
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return batch


@pytest.mark.asyncio
async def test_batch_created_application_matches_student_submission_shape(
    db, batch_import_fixture, scholarship_with_config
):
    """Core spec assertion: a batch-created application looks like a
    student-submitted one (status/review_stage/amount/name/form_data)."""
    parsed_data = [
        {
            "student_id": "313554001",
            "student_name": "王小明",
            "postal_account": "1234567890123",
            "advisor_name": "張教授",
            "advisor_email": "chang@nycu.edu.tw",
            "advisor_nycu_id": "P001234",
            "is_renewal": False,
            "renewal_year": None,
            "sub_types": ["moe_1w", "nstc"],
            "custom_fields": {"contact_phone": "0912345678"},
            "row_number": 2,
        }
    ]

    service = BatchImportService(db, student_service=_no_sis_student_service())
    created_ids, errors = await service.create_applications_from_batch(
        batch_import=batch_import_fixture,
        parsed_data=parsed_data,
        scholarship_type_id=scholarship_with_config.id,
        academic_year=114,
        semester=None,
    )

    assert errors == []
    # Commit + expunge so the re-read is a fresh DB load (enum columns come
    # back as enum members, not the strings set in-session).
    await db.commit()
    db.expunge_all()
    app = await db.get(Application, created_ids[0])

    # Review flow parity
    assert app.status == ApplicationStatus.submitted
    assert app.review_stage == ReviewStage.student_submitted
    assert app.submitted_at is not None
    # Value parity (config-sourced)
    assert app.amount is not None
    assert "114" in app.scholarship_name  # config_name carries the year
    # app_id keeps the batch marker
    assert app.app_id.endswith("U")
    # Standard form-data structure; postal/advisor NOT inside
    assert set(app.submitted_form_data.keys()) == {"fields", "documents"}
    assert app.submitted_form_data["documents"] == []
    assert app.submitted_form_data["fields"]["contact_phone"]["value"] == "0912345678"
    assert "postal_account" not in app.submitted_form_data["fields"]
    # Sub-type scalar via shared derivation
    assert app.sub_scholarship_type == "moe_1w"
    assert app.sub_type_preferences == ["moe_1w", "nstc"]
    # Unchanged batch markers
    assert app.import_source == "batch_import"
    assert app.batch_import_id == batch_import_fixture.id
    assert app.document_status == "pending_documents"


@pytest.mark.asyncio
async def test_batch_upserts_user_profile_with_overwrite(db, batch_import_fixture, scholarship_with_config):
    # Pre-existing profile: advisor set by the student, postal blank
    user = User(nycu_id="313554002", name="陳小華", role="student", user_type="student")
    db.add(user)
    await db.flush()
    db.add(UserProfile(user_id=user.id, account_number=None, advisor_name="舊教授", advisor_nycu_id="P000001"))
    await db.flush()

    parsed_data = [
        {
            "student_id": "313554002",
            "student_name": "陳小華",
            "postal_account": "9876543210987",
            "advisor_name": "李教授",
            "advisor_email": None,  # blank in Excel — must preserve existing (None here)
            "advisor_nycu_id": "P005678",
            "is_renewal": False,
            "renewal_year": None,
            "sub_types": ["nstc"],
            "custom_fields": {},
            "row_number": 2,
        }
    ]

    service = BatchImportService(db, student_service=_no_sis_student_service())
    await service.create_applications_from_batch(
        batch_import=batch_import_fixture,
        parsed_data=parsed_data,
        scholarship_type_id=scholarship_with_config.id,
        academic_year=114,
        semester=None,
    )
    await db.commit()

    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    profile = profile_result.scalar_one()
    assert profile.account_number == "9876543210987"  # filled from Excel
    assert profile.advisor_name == "李教授"  # Excel value overwrites
    assert profile.advisor_email is None  # blank Excel cell preserves existing
    assert profile.advisor_nycu_id == "P005678"  # Excel value overwrites


@pytest.mark.asyncio
async def test_batch_assigns_professor_when_account_exists(db, batch_import_fixture, scholarship_with_config):
    professor = User(nycu_id="P001234", name="張教授", role="professor", user_type="employee")
    db.add(professor)
    await db.flush()

    parsed_data = [
        {
            "student_id": "313554003",
            "student_name": "林小強",
            "postal_account": None,
            "advisor_name": "張教授",
            "advisor_email": "chang@nycu.edu.tw",
            "advisor_nycu_id": "P001234",
            "is_renewal": False,
            "renewal_year": None,
            "sub_types": ["nstc"],
            "custom_fields": {},
            "row_number": 2,
        }
    ]

    service = BatchImportService(db, student_service=_no_sis_student_service())
    created_ids, _ = await service.create_applications_from_batch(
        batch_import=batch_import_fixture,
        parsed_data=parsed_data,
        scholarship_type_id=scholarship_with_config.id,
        academic_year=114,
        semester=None,
    )
    await db.commit()

    app = await db.get(Application, created_ids[0])
    assert app.professor_id == professor.id


# ─── bulk_check_eligibility: preview-stage warnings ──────────────────


@pytest.mark.asyncio
async def test_bulk_check_eligibility_flags_failures_but_filters_period(db, scholarship_with_config, monkeypatch):
    service = BatchImportService(db)

    async def fake_snapshot(student_id, academic_year=None, semester=None):
        return {"std_stdcode": student_id, "trm_ascore_gpa": 2.0}

    monkeypatch.setattr(service.student_service, "get_student_snapshot", fake_snapshot)

    async def fake_check(student_data, config, user_id=None):
        # Simulates: outside application period AND a real rule failure
        return False, ["不在申請期間內", "GPA 未達標準"]

    from app.services import batch_import_service as bis_module

    monkeypatch.setattr(
        bis_module.EligibilityService, "check_student_eligibility", staticmethod(fake_check), raising=False
    )

    parsed_data = [{"student_id": "313554001", "sub_types": ["nstc"], "advisor_nycu_id": None, "row_number": 2}]
    warnings = await service.bulk_check_eligibility(parsed_data, scholarship_with_config.id, 114, None)

    eligibility_warnings = [w for w in warnings if w["warning_type"] == "eligibility_failed"]
    assert len(eligibility_warnings) == 1
    assert "GPA 未達標準" in eligibility_warnings[0]["message"]
    # Application-period reason is exempted for batch import (late entry)
    assert "不在申請期間內" not in eligibility_warnings[0]["message"]


@pytest.mark.asyncio
async def test_bulk_check_eligibility_warns_missing_professor_account(db, scholarship_with_config, monkeypatch):
    service = BatchImportService(db)

    async def fake_snapshot(student_id, academic_year=None, semester=None):
        return {"std_stdcode": student_id}

    monkeypatch.setattr(service.student_service, "get_student_snapshot", fake_snapshot)

    parsed_data = [{"student_id": "313554001", "sub_types": ["nstc"], "advisor_nycu_id": "NOSUCH", "row_number": 2}]
    warnings = await service.bulk_check_eligibility(parsed_data, scholarship_with_config.id, 114, None)

    professor_warnings = [w for w in warnings if w["warning_type"] == "professor_not_found"]
    assert len(professor_warnings) == 1
    assert "NOSUCH" in professor_warnings[0]["message"]


@pytest.mark.asyncio
async def test_bulk_check_eligibility_real_check_no_missing_greenlet(db, scholarship_with_config, monkeypatch):
    """Runs the REAL check_student_eligibility with the ScholarshipType NOT in
    the session identity map (revalidate path). check_student_eligibility reads
    config.scholarship_type.whitelist_enabled, so without eager-loading this
    would raise MissingGreenlet on an async lazy-load."""
    config_id = scholarship_with_config.id
    # Drop everything from the identity map so config.scholarship_type must be
    # resolved from the query, not the identity map.
    db.expunge_all()

    service = BatchImportService(db)

    async def fake_snapshot(student_id, academic_year=None, semester=None):
        return {"std_stdcode": student_id}

    monkeypatch.setattr(service.student_service, "get_student_snapshot", fake_snapshot)

    parsed_data = [{"student_id": "313554001", "sub_types": ["nstc"], "advisor_nycu_id": None, "row_number": 2}]
    # Must not raise (regression guard for MissingGreenlet).
    warnings = await service.bulk_check_eligibility(parsed_data, config_id, 114, None)

    # No skip warning about missing config (the config was found).
    assert not any(w["warning_type"] == "eligibility_check_skipped" and w["field"] == "configuration" for w in warnings)

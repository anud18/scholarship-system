"""
Integration tests for ApplicationService
Target: Increase coverage from 12% to 70%
Focus: Real execution, test actual methods
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.enums import Semester
from app.models.user import User, UserRole
from app.services.application_service import ApplicationService, get_student_data_from_user


class TestApplicationServiceHelpers:
    """Test helper methods"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ApplicationService(db)

    def test_serialize_for_json_decimal(self, service):
        """Test Decimal serialization"""
        result = service._serialize_for_json(Decimal("3.14"))
        assert result == 3.14
        assert isinstance(result, float)

    def test_serialize_for_json_datetime(self, service):
        """Test datetime serialization"""
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = service._serialize_for_json(dt)
        assert "2024-01-01" in result
        assert isinstance(result, str)

    def test_serialize_for_json_list(self, service):
        """Test list serialization"""
        data = [Decimal("3.14"), Decimal("2.71")]
        result = service._serialize_for_json(data)
        assert result == [3.14, 2.71]

    def test_serialize_for_json_dict(self, service):
        """Test dict serialization"""
        data = {
            "gpa": Decimal("3.5"),
            "timestamp": datetime(2024, 1, 1, tzinfo=timezone.utc),
        }
        result = service._serialize_for_json(data)
        assert result["gpa"] == 3.5
        assert isinstance(result["timestamp"], str)

    def test_serialize_for_json_primitive(self, service):
        """Test primitive value passthrough"""
        assert service._serialize_for_json("test") == "test"
        assert service._serialize_for_json(123) == 123
        assert service._serialize_for_json(None) is None

    def test_get_student_id_from_user(self, service):
        """Test getting student ID from user"""
        user = Mock(spec=User)
        user.nycu_id = "112550001"

        result = service._get_student_id_from_user(user)
        assert result == "112550001"

    def test_get_student_id_from_user_none(self, service):
        """Test getting student ID with None user"""
        result = service._get_student_id_from_user(None)
        assert result is None

    def test_get_student_id_from_user_no_nycu_id(self, service):
        """Test getting student ID with no nycu_id"""
        user = Mock(spec=User)
        user.nycu_id = None

        result = service._get_student_id_from_user(user)
        assert result is None

    def test_convert_semester_to_string_first(self, service):
        """Test semester conversion for first semester"""
        result = service._convert_semester_to_string(Semester.first)
        assert result == "first"

    def test_convert_semester_to_string_second(self, service):
        """Test semester conversion for second semester"""
        result = service._convert_semester_to_string(Semester.second)
        assert result == "second"

    def test_convert_semester_to_string_none(self, service):
        """Test semester conversion for None"""
        result = service._convert_semester_to_string(None)
        assert result is None


@pytest.mark.asyncio
class TestGetStudentDataFromUser:
    """Test standalone get_student_data_from_user function"""

    async def test_get_student_data_student_role(self):
        """Test getting student data for student role"""
        user = Mock(spec=User)
        user.role = UserRole.student
        user.nycu_id = "112550001"

        with patch("app.services.application_service.StudentService") as mock_service:
            mock_instance = AsyncMock()
            mock_service.return_value = mock_instance
            mock_instance.get_student_basic_info.return_value = {"student_id": "112550001"}

            result = await get_student_data_from_user(user)
            assert result == {"student_id": "112550001"}

    async def test_get_student_data_non_student(self):
        """Test getting student data for non-student role"""
        user = Mock(spec=User)
        user.role = UserRole.admin
        user.nycu_id = "admin001"

        result = await get_student_data_from_user(user)
        assert result is None

    async def test_get_student_data_no_nycu_id(self):
        """Test getting student data with no nycu_id"""
        user = Mock(spec=User)
        user.role = UserRole.student
        user.nycu_id = None

        result = await get_student_data_from_user(user)
        assert result is None


@pytest.mark.asyncio
class TestApplicationServiceIntegration:
    """Test application integration methods"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ApplicationService(db)

    def test_integrate_application_file_data_basic(self, service):
        """Test file data integration"""
        application = Mock(spec=Application)
        application.submitted_form_data = {"name": "Test"}
        application.documents = {}
        application.app_id = "APP001"
        application.files = []

        user = Mock(spec=User)

        result = service._integrate_application_file_data(application, user)
        # _normalize_submitted_form_data converts flat dict → {fields: {…}, documents: […]}
        assert "fields" in result
        assert result["fields"]["name"]["value"] == "Test"

    def test_integrate_application_file_data_with_documents(self, service):
        """Test file data integration with documents"""
        application = Mock(spec=Application)
        application.submitted_form_data = {"name": "Test"}
        application.documents = {"transcript": "path/to/file.pdf"}
        application.app_id = "APP001"
        application.files = []

        user = Mock(spec=User)

        result = service._integrate_application_file_data(application, user)
        assert "documents" in result

    @staticmethod
    def _fake_file(**over):
        """Build a duck-typed ApplicationFile with all attrs the helper reads."""
        from types import SimpleNamespace

        defaults = dict(
            id=42,
            file_type="transcript",
            filename="t.pdf",
            original_filename="transcript.pdf",
            file_size=1234,
            mime_type="application/pdf",
            content_type="application/pdf",
            is_verified=True,
            object_name="applications/1/documents/abc.pdf",
            uploaded_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        defaults.update(over)
        return SimpleNamespace(**defaults)

    def test_integrate_adds_file_missing_from_documents(self, service):
        """#885 regression guard: a file present in application.files but ABSENT
        from documents[] (e.g. a draft saved with documents:[]) MUST be added on
        read. This is the create branch shared by get_application_by_id,
        get_user_applications, get_applications, get_applications_for_review,
        submit_application, and get_student_dashboard_stats."""
        application = Mock(spec=Application)
        application.submitted_form_data = {"fields": {}, "documents": []}
        application.app_id = "APP001"
        application.id = 1
        application.files = [self._fake_file(file_type="transcript", id=42)]
        user = Mock(spec=User)
        user.id = 7

        result = service._integrate_application_file_data(application, user)

        docs = result["documents"]
        assert len(docs) == 1, "uploaded file must be added, not dropped"
        d = docs[0]
        assert d["file_id"] == 42
        assert d["document_type"] == "transcript"
        assert d["object_name"] == "applications/1/documents/abc.pdf"
        assert d["mime_type"] == "application/pdf"
        # same-origin proxy path that files.py serves inline
        assert "/files/applications/1/files/42" in d["file_path"]

    def test_integrate_updates_existing_doc_without_duplicating(self, service):
        """A partial doc already in documents[] (matching file_type) must be
        enriched in place — not duplicated — when its ApplicationFile exists."""
        application = Mock(spec=Application)
        application.submitted_form_data = {
            "fields": {},
            "documents": [{"document_type": "transcript", "document_id": "transcript"}],
        }
        application.app_id = "APP001"
        application.id = 1
        application.files = [self._fake_file(file_type="transcript", id=99)]
        user = Mock(spec=User)
        user.id = 7

        result = service._integrate_application_file_data(application, user)

        docs = result["documents"]
        assert len(docs) == 1, "matching doc must be updated in place, not duplicated"
        assert docs[0]["file_id"] == 99


@pytest.mark.asyncio
class TestUploadReplacesStaleDuplicates:
    """Re-uploading the same document (same file_type + original filename)
    must REPLACE the previous ApplicationFile rows, not append — repeated
    draft saves used to duplicate every document, and the college export
    then listed 成績 1..N copies of one file."""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ApplicationService(db)

    @staticmethod
    def _upload_mocks(service, stale_files, max_file_count=None):
        """Wire db.execute for the three selects the upload path runs:
        application lookup, document max_file_count lookup, then the
        stale-duplicate lookup."""
        application = Mock(spec=Application)
        application.id = 1
        application.user_id = 7
        application.scholarship_type_id = 3

        app_result = Mock()
        app_result.scalar_one_or_none.return_value = application
        max_count_result = Mock()
        max_count_result.scalars.return_value.first.return_value = max_file_count
        stale_result = Mock()
        stale_result.scalars.return_value.all.return_value = stale_files
        service.db.execute = AsyncMock(side_effect=[app_result, max_count_result, stale_result])
        service.db.add = Mock()
        service.db.delete = AsyncMock()
        service.db.commit = AsyncMock()
        service.db.refresh = AsyncMock()

        user = Mock(spec=User)
        user.id = 7
        user.role = UserRole.student
        return user

    @staticmethod
    def _stale(object_name):
        from types import SimpleNamespace

        return SimpleNamespace(object_name=object_name)

    async def test_reupload_deletes_stale_rows_and_objects(self, service):
        stale_files = [
            self._stale("applications/1/documents/old-1.pdf"),
            self._stale("applications/1/documents/old-2.pdf"),
        ]
        user = self._upload_mocks(service, stale_files)
        upload_file = Mock(filename="成績單.pdf", content_type="application/pdf")

        with patch("app.services.application_service.minio_service") as mock_minio:
            mock_minio.upload_file = AsyncMock(return_value=("applications/1/documents/new.pdf", 111))
            mock_minio.delete_file = Mock(return_value=True)

            result = await service.upload_application_file_minio(1, user, upload_file, "transcript")

        assert result["success"] is True
        # Both stale rows removed from the DB and their objects from MinIO.
        assert service.db.delete.await_count == 2
        deleted_objects = [call.args[0] for call in mock_minio.delete_file.call_args_list]
        assert deleted_objects == [
            "applications/1/documents/old-1.pdf",
            "applications/1/documents/old-2.pdf",
        ]
        # Exactly one replacement record inserted.
        assert service.db.add.call_count == 1
        new_record = service.db.add.call_args.args[0]
        assert new_record.object_name == "applications/1/documents/new.pdf"
        assert new_record.file_type == "transcript"

    async def test_first_upload_deletes_nothing(self, service):
        user = self._upload_mocks(service, stale_files=[])
        upload_file = Mock(filename="成績單.pdf", content_type="application/pdf")

        with patch("app.services.application_service.minio_service") as mock_minio:
            mock_minio.upload_file = AsyncMock(return_value=("applications/1/documents/new.pdf", 111))
            mock_minio.delete_file = Mock(return_value=True)

            result = await service.upload_application_file_minio(1, user, upload_file, "transcript")

        assert result["success"] is True
        service.db.delete.assert_not_awaited()
        mock_minio.delete_file.assert_not_called()
        assert service.db.add.call_count == 1

    async def test_single_file_slot_replaces_whole_type(self, service):
        """max_file_count == 1: swapping to a DIFFERENTLY-named file must
        still evict the old row — the stale query drops the filename filter."""
        stale = self._stale("applications/1/documents/old-name.pdf")
        user = self._upload_mocks(service, stale_files=[stale], max_file_count=1)
        upload_file = Mock(filename="全新檔名.pdf", content_type="application/pdf")

        with patch("app.services.application_service.minio_service") as mock_minio:
            mock_minio.upload_file = AsyncMock(return_value=("applications/1/documents/new.pdf", 111))
            mock_minio.delete_file = Mock(return_value=True)

            result = await service.upload_application_file_minio(1, user, upload_file, "成績")

        assert result["success"] is True
        assert service.db.delete.await_count == 1
        # The stale SELECT must NOT be narrowed to the (new) original filename
        # (the column always appears in the SELECT list; check the predicate).
        stale_query = str(service.db.execute.await_args_list[2].args[0])
        assert "original_filename =" not in stale_query

    async def test_multi_file_slot_keeps_filename_filter(self, service):
        """max_file_count > 1: other files of the slot must survive, so the
        stale query stays keyed on the original filename."""
        user = self._upload_mocks(service, stale_files=[], max_file_count=3)
        upload_file = Mock(filename="第二份.pdf", content_type="application/pdf")

        with patch("app.services.application_service.minio_service") as mock_minio:
            mock_minio.upload_file = AsyncMock(return_value=("applications/1/documents/new.pdf", 111))
            mock_minio.delete_file = Mock(return_value=True)

            result = await service.upload_application_file_minio(1, user, upload_file, "多檔文件")

        assert result["success"] is True
        service.db.delete.assert_not_awaited()
        stale_query = str(service.db.execute.await_args_list[2].args[0])
        assert "original_filename =" in stale_query


@pytest.mark.asyncio
class TestApplicationServiceDashboard:
    """Test dashboard methods"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ApplicationService(db)

    async def test_get_student_dashboard_stats(self, service):
        """Test getting student dashboard stats"""
        user = Mock(spec=User)
        user.id = 1
        user.nycu_id = "112550001"

        # First execute: status counts (iterable rows); second: recent applications list
        mock_result_1 = Mock()
        mock_result_1.__iter__ = Mock(return_value=iter([]))
        mock_result_2 = Mock()
        mock_result_2.scalars.return_value.all.return_value = []
        service.db.execute = AsyncMock(side_effect=[mock_result_1, mock_result_2])

        stats = await service.get_student_dashboard_stats(user)

        # Service returns {total_applications, status_counts, recent_applications}
        assert "total_applications" in stats
        assert "status_counts" in stats
        assert "recent_applications" in stats


@pytest.mark.asyncio
class TestApplicationServiceListResponse:
    """Test list response creation"""

    @pytest.fixture
    def service(self):
        db = Mock(spec=AsyncSession)
        return ApplicationService(db)

    def test_create_application_list_response(self, service):
        """Test creating application list response"""
        now = datetime.now(timezone.utc)
        application = Mock(spec=Application)
        application.id = 1
        application.app_id = "APP001"
        application.user_id = 1
        application.scholarship_type_id = 1
        application.scholarship_subtype_list = ["type_a"]
        application.scholarship = None
        application.scholarship_configuration = None
        application.status = ApplicationStatus.draft.value
        application.status_name = "草稿"
        application.review_stage = None
        application.is_renewal = False
        application.renewal_year = None
        application.previous_application_id = None
        application.challenges_application_id = None
        application.cancelled_due_to_application_id = None
        application.academic_year = 113
        application.semester = Semester.first
        application.student_data = {}
        application.agree_terms = True
        application.sub_scholarship_type = None
        application.professor_id = None
        application.reviewer_id = None
        application.final_approver_id = None
        application.submitted_at = None
        application.reviewed_at = None
        application.approved_at = None
        application.created_at = now
        application.updated_at = now
        application.meta_data = None

        user = Mock(spec=User)
        user.nycu_id = "112550001"

        integrated_data = {"name": "Test"}

        response = service._create_application_list_response(application, user, integrated_data)

        assert response.app_id == "APP001"
        assert response.status == ApplicationStatus.draft.value

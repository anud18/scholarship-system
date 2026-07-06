"""
HTTP-layer authorization-scoping tests for issue #1081 findings E and F.

E — GET /college-review/students/{student_id}/preview must be college-scoped:
    a college reviewer may only preview students with at least one application
    managed by their college. Unrelated/nonexistent students both return 404 so
    the endpoint is not a student-existence oracle. Admins bypass.

F — GET /applications/{id}/application-document must not grant any professor
    blanket access: professors need an active view_applications relationship
    with the applicant (mirrors the files.py proxy gate). Owner, college and
    admin access is unchanged.

Authentication is simulated by overriding `get_current_user` with real
DB-backed User rows so the actual role gates and scoping logic run unmodified.
(Findings C/D are covered in test_ranking_management_endpoints.py.)
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.models.application import Application, ApplicationStatus
from app.models.professor_student import ProfessorStudentRelationship
from app.models.scholarship import ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType

PREVIEW_URL = "/api/v1/college-review/students/{student_id}/preview"
DOCUMENT_URL = "/api/v1/applications/{application_id}/application-document"


@pytest_asyncio.fixture
async def login():
    """Authenticate the test client as a given User via dependency override."""
    from app.core.security import get_current_user
    from app.main import app

    def _login(user: User) -> None:
        async def _override():
            return user

        app.dependency_overrides[get_current_user] = _override

    yield _login
    from app.core.security import get_current_user as _gcu
    from app.main import app as _app

    _app.dependency_overrides.pop(_gcu, None)


@pytest_asyncio.fixture
async def scope_users(db):
    users = {
        "college_eng": User(
            nycu_id="scope_eng1",
            name="ENG Reviewer",
            email="scope_eng1@test.edu",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code="ENG",
        ),
        "college_sci": User(
            nycu_id="scope_sci1",
            name="SCI Reviewer",
            email="scope_sci1@test.edu",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code="SCI",
        ),
        "college_unbound": User(
            nycu_id="scope_unbound",
            name="Unbound Reviewer",
            email="scope_unbound@test.edu",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code=None,
        ),
        "admin": User(
            nycu_id="scope_admin",
            name="Scope Admin",
            email="scope_admin@test.edu",
            user_type=UserType.employee,
            role=UserRole.admin,
        ),
        "professor_related": User(
            nycu_id="scope_prof_rel",
            name="Related Professor",
            email="scope_prof_rel@test.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        ),
        "professor_unrelated": User(
            nycu_id="scope_prof_unrel",
            name="Unrelated Professor",
            email="scope_prof_unrel@test.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        ),
        "student_eng": User(
            nycu_id="S881001",
            name="ENG Student",
            email="scope_stu_eng@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        ),
        "student_other": User(
            nycu_id="S881002",
            name="Other Student",
            email="scope_stu_other@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        ),
    }
    for user in users.values():
        db.add(user)
    await db.commit()
    for user in users.values():
        await db.refresh(user)
    return users


@pytest_asyncio.fixture
async def scope_scholarship(db) -> ScholarshipType:
    scholarship = ScholarshipType(
        code="authz_scope_scholarship",
        name="Authz Scoping Test Scholarship",
        description="Scholarship used by issue #1081 authz scoping tests",
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


@pytest_asyncio.fixture
async def eng_application(db, scope_users, scope_scholarship) -> Application:
    """Application of student_eng, managed by ENG college, with a document."""
    application = Application(
        app_id="APP-114-1-08001",
        user_id=scope_users["student_eng"].id,
        scholarship_type_id=scope_scholarship.id,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status=ApplicationStatus.submitted.value,
        academic_year=114,
        semester="first",
        scholarship_subtype_list=["nstc"],
        student_data={"std_stdcode": "S881001", "std_cname": "ENG Student", "std_academyno": "ENG"},
        submitted_form_data={},
        agree_terms=True,
        application_document_url="application-documents/8001_test.pdf",
        application_document_original_filename="申請文件.pdf",
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


@pytest_asyncio.fixture
async def related_professor_relationship(db, scope_users) -> ProfessorStudentRelationship:
    rel = ProfessorStudentRelationship(
        professor_id=scope_users["professor_related"].id,
        student_id=scope_users["student_eng"].id,
        relationship_type="advisor",
        is_active=True,
        can_view_applications=True,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)
    return rel


_STUDENT_BASIC = {
    "std_stdcode": "S881001",
    "std_cname": "ENG Student",
    "std_academyno": "ENG",
    "std_enrollyear": "113",
}

STUDENT_SERVICE_PATH = "app.api.v1.endpoints.college_review.application_review.StudentService"


def _mock_student_service():
    """Patch the StudentService used by the preview endpoint."""
    patcher = patch(STUDENT_SERVICE_PATH)
    mock_cls = patcher.start()
    mock_cls.return_value.get_student_basic_info = AsyncMock(return_value=dict(_STUDENT_BASIC))
    mock_cls.return_value.get_student_term_info = AsyncMock(return_value=None)
    return patcher, mock_cls


@pytest.mark.api
class TestStudentPreviewScoping:
    """Issue #1081 finding E: college-scoped student preview."""

    async def test_unauthenticated_401(self, client):
        response = await client.get(PREVIEW_URL.format(student_id="S881001"))
        assert response.status_code == 401

    async def test_student_role_403(self, client, login, scope_users):
        login(scope_users["student_eng"])
        response = await client.get(PREVIEW_URL.format(student_id="S881001"))
        assert response.status_code == 403

    async def test_cross_college_preview_404_and_no_sis_call(self, client, login, scope_users, eng_application):
        """SCI reviewer must not read an ENG-managed student — and must get 404
        (not 403) so out-of-scope IDs look exactly like nonexistent ones."""
        patcher, mock_cls = _mock_student_service()
        try:
            login(scope_users["college_sci"])
            response = await client.get(PREVIEW_URL.format(student_id="S881001"))
            assert response.status_code == 404
            # The SIS lookup must not run for an out-of-scope student.
            mock_cls.return_value.get_student_basic_info.assert_not_awaited()
        finally:
            patcher.stop()

    async def test_nonexistent_student_404_indistinguishable(self, client, login, scope_users, eng_application):
        """Nonexistent student returns the same 404 shape as an out-of-scope one."""
        login(scope_users["college_sci"])
        nonexistent = await client.get(PREVIEW_URL.format(student_id="NO_SUCH_STUDENT"))
        out_of_scope = await client.get(PREVIEW_URL.format(student_id="S881001"))
        assert nonexistent.status_code == 404
        assert out_of_scope.status_code == 404

    async def test_student_without_any_application_404_for_college(self, client, login, scope_users):
        """A real student with no applications is out of every college's scope."""
        login(scope_users["college_eng"])
        response = await client.get(PREVIEW_URL.format(student_id="S881002"))
        assert response.status_code == 404

    async def test_college_without_college_code_403(self, client, login, scope_users, eng_application):
        login(scope_users["college_unbound"])
        response = await client.get(PREVIEW_URL.format(student_id="S881001"))
        assert response.status_code == 403

    async def test_owning_college_preview_200(self, client, login, scope_users, eng_application):
        patcher, _ = _mock_student_service()
        try:
            login(scope_users["college_eng"])
            response = await client.get(PREVIEW_URL.format(student_id="S881001"))
            assert response.status_code == 200
            body = response.json()
            assert body["success"] is True
            assert body["data"]["basic"]["std_cname"] == "ENG Student"
        finally:
            patcher.stop()

    async def test_admin_bypasses_college_scope_200(self, client, login, scope_users, eng_application):
        patcher, _ = _mock_student_service()
        try:
            login(scope_users["admin"])
            response = await client.get(PREVIEW_URL.format(student_id="S881001"))
            assert response.status_code == 200
            assert response.json()["success"] is True
        finally:
            patcher.stop()


def _mock_minio():
    """Patch the minio_service singleton used by the document endpoint."""
    patcher = patch("app.services.minio_service.minio_service")
    fake = patcher.start()
    fake.default_bucket = "test-bucket"
    fake.client.get_object.return_value.read.return_value = b"%PDF-1.4 test-bytes"
    return patcher, fake


@pytest.mark.api
class TestApplicationDocumentAccess:
    """Issue #1081 finding F: per-student relationship check for professors."""

    async def test_unauthenticated_401(self, client, eng_application):
        response = await client.get(DOCUMENT_URL.format(application_id=eng_application.id))
        assert response.status_code == 401

    async def test_unrelated_professor_403(self, client, login, scope_users, eng_application):
        patcher, fake = _mock_minio()
        try:
            login(scope_users["professor_unrelated"])
            response = await client.get(DOCUMENT_URL.format(application_id=eng_application.id))
            assert response.status_code == 403
            fake.client.get_object.assert_not_called()
        finally:
            patcher.stop()

    async def test_inactive_relationship_professor_403(self, client, login, db, scope_users, eng_application):
        rel = ProfessorStudentRelationship(
            professor_id=scope_users["professor_unrelated"].id,
            student_id=scope_users["student_eng"].id,
            relationship_type="advisor",
            is_active=False,
            can_view_applications=True,
        )
        db.add(rel)
        await db.commit()

        login(scope_users["professor_unrelated"])
        response = await client.get(DOCUMENT_URL.format(application_id=eng_application.id))
        assert response.status_code == 403

    async def test_relationship_without_view_permission_403(self, client, login, db, scope_users, eng_application):
        rel = ProfessorStudentRelationship(
            professor_id=scope_users["professor_unrelated"].id,
            student_id=scope_users["student_eng"].id,
            relationship_type="committee_member",
            is_active=True,
            can_view_applications=False,
        )
        db.add(rel)
        await db.commit()

        login(scope_users["professor_unrelated"])
        response = await client.get(DOCUMENT_URL.format(application_id=eng_application.id))
        assert response.status_code == 403

    async def test_other_student_403(self, client, login, scope_users, eng_application):
        login(scope_users["student_other"])
        response = await client.get(DOCUMENT_URL.format(application_id=eng_application.id))
        assert response.status_code == 403

    async def test_related_professor_200(
        self, client, login, scope_users, eng_application, related_professor_relationship
    ):
        patcher, _ = _mock_minio()
        try:
            login(scope_users["professor_related"])
            response = await client.get(DOCUMENT_URL.format(application_id=eng_application.id))
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/pdf"
            assert response.content == b"%PDF-1.4 test-bytes"
        finally:
            patcher.stop()

    async def test_assigned_reviewer_professor_200(self, client, login, db, scope_users, eng_application):
        """The professor an application is routed to (Application.professor_id)
        keeps document access even without a relationship-table row."""
        eng_application.professor_id = scope_users["professor_unrelated"].id
        await db.commit()

        patcher, _ = _mock_minio()
        try:
            login(scope_users["professor_unrelated"])
            response = await client.get(DOCUMENT_URL.format(application_id=eng_application.id))
            assert response.status_code == 200
        finally:
            patcher.stop()

    async def test_owner_student_200(self, client, login, scope_users, eng_application):
        patcher, _ = _mock_minio()
        try:
            login(scope_users["student_eng"])
            response = await client.get(DOCUMENT_URL.format(application_id=eng_application.id))
            assert response.status_code == 200
        finally:
            patcher.stop()

    async def test_college_user_200(self, client, login, scope_users, eng_application):
        patcher, _ = _mock_minio()
        try:
            login(scope_users["college_eng"])
            response = await client.get(DOCUMENT_URL.format(application_id=eng_application.id))
            assert response.status_code == 200
        finally:
            patcher.stop()

    async def test_admin_200(self, client, login, scope_users, eng_application):
        patcher, _ = _mock_minio()
        try:
            login(scope_users["admin"])
            response = await client.get(DOCUMENT_URL.format(application_id=eng_application.id))
            assert response.status_code == 200
        finally:
            patcher.stop()

    async def test_missing_application_404(self, client, login, scope_users):
        login(scope_users["admin"])
        response = await client.get(DOCUMENT_URL.format(application_id=999999))
        assert response.status_code == 404

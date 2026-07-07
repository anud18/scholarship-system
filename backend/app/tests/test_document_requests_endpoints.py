"""
HTTP-layer tests for the document-request endpoints
(app/api/v1/endpoints/document_requests.py).

Focus: authorization boundaries (staff-only create/list/cancel vs student-only
my-requests/fulfill), ownership scoping (a student may only fulfill requests on
their own applications), input validation, not-found handling, and the
{success, message, data} response envelope.

The document-request router resolves auth via `app.core.security` role
dependencies (require_staff / require_student), all of which depend on
`app.core.security.get_current_user`; the login fixture overrides that.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio

from app.models.application import Application, ApplicationStatus
from app.models.document_request import DocumentRequest, DocumentRequestStatus
from app.models.scholarship import ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType

PREFIX = "/api/v1"


@pytest_asyncio.fixture
async def login():
    """Authenticate the test client as a given User by overriding get_current_user."""
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
async def doc_users(db):
    users = {
        "student": User(
            nycu_id="dr_student",
            name="Doc Student",
            email="dr_student@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        ),
        "other_student": User(
            nycu_id="dr_student2",
            name="Other Doc Student",
            email="dr_student2@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        ),
        "professor": User(
            nycu_id="dr_prof",
            name="Doc Professor",
            email="dr_prof@test.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        ),
        "college": User(
            nycu_id="dr_college",
            name="Doc College",
            email="dr_college@test.edu",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code="ENG",
        ),
        "admin": User(
            nycu_id="dr_admin",
            name="Doc Admin",
            email="dr_admin@test.edu",
            user_type=UserType.employee,
            role=UserRole.admin,
        ),
    }
    for user in users.values():
        db.add(user)
    await db.commit()
    for user in users.values():
        await db.refresh(user)
    return users


@pytest_asyncio.fixture
async def doc_scholarship(db) -> ScholarshipType:
    scholarship = ScholarshipType(
        code="dr_scholarship",
        name="Doc Request Scholarship",
        description="For document request endpoint tests",
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


@pytest_asyncio.fixture
async def student_application(db, doc_users, doc_scholarship) -> Application:
    """Application owned by `student`."""
    application = Application(
        app_id="APP-114-1-00010",
        user_id=doc_users["student"].id,
        scholarship_type_id=doc_scholarship.id,
        scholarship_name="Doc Request Scholarship",
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status=ApplicationStatus.under_review.value,
        academic_year=114,
        semester="first",
        student_data={"std_cname": "Doc Student", "email": "dr_student@test.edu"},
        submitted_form_data={},
        agree_terms=True,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


async def _make_request(db, application, requester, status=DocumentRequestStatus.pending.value) -> DocumentRequest:
    doc_req = DocumentRequest(
        application_id=application.id,
        requested_by_id=requester.id,
        requested_at=datetime.now(timezone.utc),
        requested_documents=["transcript"],
        reason="Need the transcript to verify GPA",
        status=status,
    )
    db.add(doc_req)
    await db.commit()
    await db.refresh(doc_req)
    return doc_req


def _create_body(**overrides) -> dict:
    body = {
        "requested_documents": ["transcript", "recommendation_letter"],
        "reason": "Need supplementary documents to verify eligibility",
    }
    body.update(overrides)
    return body


def _app_dr_url(application_id: int) -> str:
    return f"{PREFIX}/applications/{application_id}/document-requests"


@pytest.mark.api
class TestDocumentRequestsAuthorization:
    """Staff-only vs student-only route gating."""

    async def test_create_unauthenticated_401(self, client, student_application):
        response = await client.post(_app_dr_url(student_application.id), json=_create_body())
        assert response.status_code == 401

    async def test_create_student_forbidden(self, client, login, doc_users, student_application):
        # create is require_staff; a student may not request documents.
        login(doc_users["student"])
        response = await client.post(_app_dr_url(student_application.id), json=_create_body())
        assert response.status_code == 403

    async def test_list_unauthenticated_401(self, client, student_application):
        response = await client.get(_app_dr_url(student_application.id))
        assert response.status_code == 401

    async def test_list_student_forbidden(self, client, login, doc_users, student_application):
        login(doc_users["student"])
        response = await client.get(_app_dr_url(student_application.id))
        assert response.status_code == 403

    async def test_my_requests_unauthenticated_401(self, client):
        response = await client.get(f"{PREFIX}/document-requests/my-requests")
        assert response.status_code == 401

    async def test_my_requests_staff_forbidden(self, client, login, doc_users):
        # my-requests is require_student; staff may not use it.
        login(doc_users["professor"])
        response = await client.get(f"{PREFIX}/document-requests/my-requests")
        assert response.status_code == 403

    async def test_fulfill_staff_forbidden(self, client, login, db, doc_users, student_application):
        doc_req = await _make_request(db, student_application, doc_users["professor"])
        # fulfill is require_student; a staff member may not fulfill.
        login(doc_users["admin"])
        response = await client.patch(f"{PREFIX}/document-requests/{doc_req.id}/fulfill", json={})
        assert response.status_code == 403

    async def test_cancel_student_forbidden(self, client, login, db, doc_users, student_application):
        doc_req = await _make_request(db, student_application, doc_users["professor"])
        # cancel is require_staff; a student may not cancel.
        login(doc_users["student"])
        response = await client.patch(
            f"{PREFIX}/document-requests/{doc_req.id}/cancel",
            json={"cancellation_reason": "no longer needed"},
        )
        assert response.status_code == 403


@pytest.mark.api
class TestDocumentRequestsOwnershipAndNotFound:
    """Ownership scoping and not-found handling."""

    async def test_fulfill_other_students_request_forbidden(self, client, login, db, doc_users, student_application):
        # SECURITY: a student may only fulfill requests on their OWN application.
        doc_req = await _make_request(db, student_application, doc_users["professor"])
        login(doc_users["other_student"])
        response = await client.patch(f"{PREFIX}/document-requests/{doc_req.id}/fulfill", json={})
        assert response.status_code == 403

    async def test_create_nonexistent_application_404(self, client, login, doc_users):
        login(doc_users["admin"])
        response = await client.post(_app_dr_url(999999), json=_create_body())
        assert response.status_code == 404

    async def test_list_nonexistent_application_404(self, client, login, doc_users):
        login(doc_users["admin"])
        response = await client.get(_app_dr_url(999999))
        assert response.status_code == 404

    async def test_fulfill_nonexistent_request_404(self, client, login, doc_users):
        login(doc_users["student"])
        response = await client.patch(f"{PREFIX}/document-requests/999999/fulfill", json={})
        assert response.status_code == 404

    async def test_cancel_nonexistent_request_404(self, client, login, doc_users):
        login(doc_users["admin"])
        response = await client.patch(
            f"{PREFIX}/document-requests/999999/cancel",
            json={"cancellation_reason": "not needed"},
        )
        assert response.status_code == 404


@pytest.mark.api
class TestDocumentRequestsValidation:
    """Input validation and status-guard 400s."""

    async def test_create_reason_too_short_422(self, client, login, doc_users, student_application):
        login(doc_users["admin"])
        response = await client.post(_app_dr_url(student_application.id), json=_create_body(reason="short"))
        assert response.status_code == 422

    async def test_create_missing_documents_422(self, client, login, doc_users, student_application):
        login(doc_users["admin"])
        response = await client.post(
            _app_dr_url(student_application.id),
            json={"reason": "Need supplementary documents to verify eligibility"},
        )
        assert response.status_code == 422

    async def test_cancel_reason_too_short_422(self, client, login, db, doc_users, student_application):
        doc_req = await _make_request(db, student_application, doc_users["professor"])
        login(doc_users["admin"])
        response = await client.patch(
            f"{PREFIX}/document-requests/{doc_req.id}/cancel",
            json={"cancellation_reason": "no"},
        )
        assert response.status_code == 422

    async def test_fulfill_already_fulfilled_400(self, client, login, db, doc_users, student_application):
        doc_req = await _make_request(
            db, student_application, doc_users["professor"], status=DocumentRequestStatus.fulfilled.value
        )
        login(doc_users["student"])
        response = await client.patch(f"{PREFIX}/document-requests/{doc_req.id}/fulfill", json={})
        assert response.status_code == 400

    async def test_cancel_non_pending_400(self, client, login, db, doc_users, student_application):
        doc_req = await _make_request(
            db, student_application, doc_users["professor"], status=DocumentRequestStatus.cancelled.value
        )
        login(doc_users["admin"])
        response = await client.patch(
            f"{PREFIX}/document-requests/{doc_req.id}/cancel",
            json={"cancellation_reason": "already cancelled"},
        )
        assert response.status_code == 400


@pytest.mark.api
class TestDocumentRequestsEnvelopeAndFlow:
    """Happy-path behavior and the {success, message, data} envelope."""

    async def test_staff_create_201_envelope(self, client, login, doc_users, student_application):
        login(doc_users["professor"])
        response = await client.post(_app_dr_url(student_application.id), json=_create_body())
        assert response.status_code == 201
        body = response.json()
        assert set(body.keys()) >= {"success", "message", "data"}
        assert body["success"] is True
        data = body["data"]
        assert data["application_id"] == student_application.id
        assert data["status"] == "pending"
        assert data["requested_by_name"] == "Doc Professor"
        assert data["application_app_id"] == "APP-114-1-00010"

    async def test_staff_list_envelope(self, client, login, db, doc_users, student_application):
        await _make_request(db, student_application, doc_users["professor"])
        login(doc_users["admin"])
        response = await client.get(_app_dr_url(student_application.id))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 1
        assert body["data"][0]["requested_by_name"] == "Doc Professor"

    async def test_student_my_requests_envelope(self, client, login, db, doc_users, student_application):
        await _make_request(db, student_application, doc_users["professor"])
        login(doc_users["student"])
        response = await client.get(f"{PREFIX}/document-requests/my-requests")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 1
        assert body["data"][0]["application_app_id"] == "APP-114-1-00010"

    async def test_owning_student_fulfill_200(self, client, login, db, doc_users, student_application):
        doc_req = await _make_request(db, student_application, doc_users["professor"])
        login(doc_users["student"])
        response = await client.patch(
            f"{PREFIX}/document-requests/{doc_req.id}/fulfill",
            json={"notes": "uploaded"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "fulfilled"

    async def test_staff_cancel_200(self, client, login, db, doc_users, student_application):
        doc_req = await _make_request(db, student_application, doc_users["professor"])
        login(doc_users["admin"])
        response = await client.patch(
            f"{PREFIX}/document-requests/{doc_req.id}/cancel",
            json={"cancellation_reason": "documents provided elsewhere"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"]["status"] == "cancelled"
        assert body["data"]["cancelled_by_name"] == "Doc Admin"

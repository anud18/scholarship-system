"""
Regression tests for four missing-authorization-scope bugs found in the same
security audit (issue #1081):

Finding C: GET /college-review/rankings/{id}/distribution-details never scoped
to the caller's college -- any college account could read another college's
applicant PII, ranks, and rejection reasons by ranking-id.

Finding D: GET /college-review/rankings/{id}/roster-status had the same
missing-scope bug (operational metadata only, no PII).

Finding E: GET /college-review/students/{student_id}/preview had no scope
check at all despite its docstring claiming one -- any college account could
read any student's SIS record.

Finding F: GET /applications/{id}/application-document treated every
professor as blanket staff, unlike the sibling files.py proxy which requires
an actual advising relationship.

Fix: C/D now call the same assert_can_manage_ranking helper the properly-
scoped ranking_management.py endpoints already use. E now requires the
target student to have an application in the caller's own college. F now
requires can_access_student_data for professor callers, same as files.py.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.main import app
from app.models.college_review import CollegeRanking
from app.models.user import User, UserRole, UserType


async def _make_college_user(db: AsyncSession, nycu_id: str, college_code: str) -> User:
    user = User(
        nycu_id=nycu_id,
        name=nycu_id,
        email=f"{nycu_id}@university.edu",
        user_type=UserType.employee,
        role=UserRole.college,
        college_code=college_code,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_ranking(db: AsyncSession, college_code: str) -> CollegeRanking:
    ranking = CollegeRanking(
        scholarship_type_id=1,
        sub_type_code="default",
        academic_year=113,
        college_code=college_code,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)
    return ranking


class TestDistributionDetailsScoping:
    @pytest.mark.asyncio
    async def test_cross_college_distribution_details_is_forbidden(self, client: AsyncClient, db: AsyncSession):
        college_a = await _make_college_user(db, "authz_college_a_1", "CS")
        ranking_b = await _make_ranking(db, "EE")

        app.dependency_overrides[get_current_user] = lambda: college_a
        try:
            response = await client.get(f"/api/v1/college-review/rankings/{ranking_b.id}/distribution-details")
        finally:
            del app.dependency_overrides[get_current_user]

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_own_college_distribution_details_is_allowed(self, client: AsyncClient, db: AsyncSession):
        college_a = await _make_college_user(db, "authz_college_a_2", "CS")
        ranking_a = await _make_ranking(db, "CS")

        app.dependency_overrides[get_current_user] = lambda: college_a
        try:
            response = await client.get(f"/api/v1/college-review/rankings/{ranking_a.id}/distribution-details")
        finally:
            del app.dependency_overrides[get_current_user]

        assert response.status_code == 200


class TestRosterStatusScoping:
    @pytest.mark.asyncio
    async def test_cross_college_roster_status_is_forbidden(self, client: AsyncClient, db: AsyncSession):
        college_a = await _make_college_user(db, "authz_college_a_3", "CS")
        ranking_b = await _make_ranking(db, "EE")

        app.dependency_overrides[get_current_user] = lambda: college_a
        try:
            response = await client.get(f"/api/v1/college-review/rankings/{ranking_b.id}/roster-status")
        finally:
            del app.dependency_overrides[get_current_user]

        assert response.status_code == 403


class TestStudentPreviewScoping:
    @pytest.mark.asyncio
    async def test_student_with_no_application_in_college_is_forbidden(self, client: AsyncClient, db: AsyncSession):
        college_a = await _make_college_user(db, "authz_college_a_4", "CS")

        app.dependency_overrides[get_current_user] = lambda: college_a
        try:
            response = await client.get("/api/v1/college-review/students/999999999/preview")
        finally:
            del app.dependency_overrides[get_current_user]

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_student_with_application_in_own_college_passes_scope_check(
        self, client: AsyncClient, db: AsyncSession, test_user: User, test_scholarship
    ):
        from app.models.application import Application
        from app.models.scholarship import SubTypeSelectionMode

        college_a = await _make_college_user(db, "authz_college_a_5", "CS")
        application = Application(
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            status="submitted",
            app_id="TEST-AUTHZ-PREVIEW",
            academic_year=2024,
            semester="first",
            student_data={"std_stdcode": test_user.nycu_id, "std_academyno": "CS"},
            submitted_form_data={},
            agree_terms=True,
        )
        db.add(application)
        await db.commit()

        app.dependency_overrides[get_current_user] = lambda: college_a
        try:
            response = await client.get(f"/api/v1/college-review/students/{test_user.nycu_id}/preview")
        finally:
            del app.dependency_overrides[get_current_user]

        # Scope check passes; downstream SIS lookup then legitimately 404s in this
        # test environment (no external student API) or 500s attempting the call --
        # what matters is it's NOT the 403 the scope gate would raise.
        assert response.status_code != 403


class TestApplicationDocumentProfessorScoping:
    @pytest.mark.asyncio
    async def test_unrelated_professor_cannot_download_document(
        self, client: AsyncClient, db: AsyncSession, test_user: User, test_scholarship
    ):
        from app.models.application import Application
        from app.models.scholarship import SubTypeSelectionMode

        professor = User(
            nycu_id="authz_prof_doc_1",
            name="Prof Doc 1",
            email="authz_prof_doc_1@university.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        )
        db.add(professor)
        await db.commit()
        await db.refresh(professor)
        # can_access_student_data lazily iterates professor_relationships; force it
        # to load now so the dependency-override object doesn't trigger an
        # unawaited lazy-load (MissingGreenlet) inside the request.
        await db.refresh(professor, attribute_names=["professor_relationships"])

        application = Application(
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            sub_type_selection_mode=SubTypeSelectionMode.single,
            status="submitted",
            app_id="TEST-AUTHZ-DOC",
            academic_year=2024,
            semester="first",
            student_data={"name": "Test Student"},
            submitted_form_data={},
            agree_terms=True,
            application_document_url="applications/doc.pdf",
        )
        db.add(application)
        await db.commit()
        await db.refresh(application)

        app.dependency_overrides[get_current_user] = lambda: professor
        try:
            response = await client.get(f"/api/v1/applications/{application.id}/application-document")
        finally:
            del app.dependency_overrides[get_current_user]

        assert response.status_code == 403

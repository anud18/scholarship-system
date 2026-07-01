"""
Regression tests for two authorization-scoping bugs in the multi-role review
endpoints (backend/app/api/v1/endpoints/reviews.py):

Finding A: POST /reviews/applications/{id}/review accepted professor callers
without checking assignment (application.professor_id), the terminal-reject
lock, or the review time window -- unlike the dedicated professor.py path.
An unassigned professor could reject/approve any application; an assigned
professor could reverse their own terminal reject after the fact.

Finding B: GET /reviews/applications/{id}/reviews and /review-status checked
only that the application exists -- any authenticated user, including a
student with no relationship to the application, could read other students'
reviewer identities, recommendations, and rejection comments.

Fix: professor callers to submit_application_review now go through the same
ApplicationService.can_professor_submit_review + assert_professor_review_unlocked
chain professor.py uses; the two read endpoints now scope through the new
ApplicationService.get_viewable_application (student-owns-it /
professor-is-assigned / college-and-admin-pass-through), matching the access
rule used everywhere else an application is read.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.main import app
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService


async def _make_professor(db: AsyncSession, nycu_id: str) -> User:
    professor = User(
        nycu_id=nycu_id,
        name=nycu_id,
        email=f"{nycu_id}@university.edu",
        user_type=UserType.employee,
        role=UserRole.professor,
    )
    db.add(professor)
    await db.commit()
    await db.refresh(professor)
    return professor


async def _make_student(db: AsyncSession, nycu_id: str) -> User:
    student = User(
        nycu_id=nycu_id,
        name=nycu_id,
        email=f"{nycu_id}@university.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    await db.commit()
    await db.refresh(student)
    return student


async def _make_application(
    db: AsyncSession, owner: User, professor: User, status: str = ApplicationStatus.submitted.value
) -> Application:
    scholarship = ScholarshipType(code="test_authz", name="Test Authz Scholarship")
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)

    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=113,
        config_name="Test Authz Config",
        config_code=f"test_authz_config_{owner.id}",
        amount=10000,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    application = Application(
        user_id=owner.id,
        professor_id=professor.id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status=status,
        app_id=f"TEST-AUTHZ-{owner.id}",
        academic_year=2024,
        semester="first",
        student_data={"name": "Test Student"},
        submitted_form_data={"personal_statement": "..."},
        agree_terms=True,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


class TestCanProfessorSubmitReviewScoping:
    """Finding A: assignment + terminal-status scoping."""

    @pytest.mark.asyncio
    async def test_unassigned_professor_cannot_review(self, db: AsyncSession):
        owner = await _make_student(db, "authz_student_1")
        assigned_prof = await _make_professor(db, "authz_prof_assigned_1")
        other_prof = await _make_professor(db, "authz_prof_other_1")
        application = await _make_application(db, owner, assigned_prof)

        service = ApplicationService(db)
        assert await service.can_professor_submit_review(application.id, assigned_prof.id) is True
        assert await service.can_professor_submit_review(application.id, other_prof.id) is False

    @pytest.mark.asyncio
    async def test_terminal_rejected_application_cannot_be_reviewed_again(self, db: AsyncSession):
        owner = await _make_student(db, "authz_student_2")
        assigned_prof = await _make_professor(db, "authz_prof_assigned_2")
        application = await _make_application(db, owner, assigned_prof, status=ApplicationStatus.rejected.value)

        service = ApplicationService(db)
        assert await service.can_professor_submit_review(application.id, assigned_prof.id) is False


class TestGetViewableApplicationScoping:
    """Finding B: same access rule as the rest of the app for reading an application."""

    @pytest.mark.asyncio
    async def test_owner_can_view_own_application(self, db: AsyncSession):
        owner = await _make_student(db, "authz_student_3")
        professor = await _make_professor(db, "authz_prof_3")
        application = await _make_application(db, owner, professor)

        result = await ApplicationService(db).get_viewable_application(application.id, owner)
        assert result is not None
        assert result.id == application.id

    @pytest.mark.asyncio
    async def test_other_student_cannot_view_application(self, db: AsyncSession):
        owner = await _make_student(db, "authz_student_4")
        other_student = await _make_student(db, "authz_student_5")
        professor = await _make_professor(db, "authz_prof_4")
        application = await _make_application(db, owner, professor)

        result = await ApplicationService(db).get_viewable_application(application.id, other_student)
        assert result is None

    @pytest.mark.asyncio
    async def test_assigned_professor_can_view(self, db: AsyncSession):
        owner = await _make_student(db, "authz_student_6")
        professor = await _make_professor(db, "authz_prof_6")
        application = await _make_application(db, owner, professor)

        result = await ApplicationService(db).get_viewable_application(application.id, professor)
        assert result is not None

    @pytest.mark.asyncio
    async def test_unassigned_professor_cannot_view(self, db: AsyncSession):
        owner = await _make_student(db, "authz_student_7")
        assigned_prof = await _make_professor(db, "authz_prof_assigned_7")
        other_prof = await _make_professor(db, "authz_prof_other_7")
        application = await _make_application(db, owner, assigned_prof)

        result = await ApplicationService(db).get_viewable_application(application.id, other_prof)
        assert result is None


class TestReviewEndpointsHttpLevel:
    """End-to-end confirmation through the actual FastAPI routes."""

    @pytest.mark.asyncio
    async def test_unassigned_professor_submit_review_is_403(self, client: AsyncClient, db: AsyncSession):
        owner = await _make_student(db, "authz_student_8")
        assigned_prof = await _make_professor(db, "authz_prof_assigned_8")
        other_prof = await _make_professor(db, "authz_prof_other_8")
        application = await _make_application(db, owner, assigned_prof)

        app.dependency_overrides[get_current_user] = lambda: other_prof
        try:
            response = await client.post(
                f"/api/v1/reviews/applications/{application.id}/review",
                json={"items": [{"sub_type_code": "default", "recommendation": "reject", "comments": "no"}]},
            )
        finally:
            del app.dependency_overrides[get_current_user]

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_non_owner_student_cannot_read_reviews(self, client: AsyncClient, db: AsyncSession):
        owner = await _make_student(db, "authz_student_9")
        other_student = await _make_student(db, "authz_student_10")
        professor = await _make_professor(db, "authz_prof_9")
        application = await _make_application(db, owner, professor)

        app.dependency_overrides[get_current_user] = lambda: other_student
        try:
            response = await client.get(f"/api/v1/reviews/applications/{application.id}/reviews")
        finally:
            del app.dependency_overrides[get_current_user]

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_owner_can_read_own_reviews(self, client: AsyncClient, db: AsyncSession):
        owner = await _make_student(db, "authz_student_11")
        professor = await _make_professor(db, "authz_prof_11")
        application = await _make_application(db, owner, professor)

        app.dependency_overrides[get_current_user] = lambda: owner
        try:
            response = await client.get(f"/api/v1/reviews/applications/{application.id}/reviews")
        finally:
            del app.dependency_overrides[get_current_user]

        assert response.status_code == 200

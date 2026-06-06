"""DB-aware tests for ApplicationService.get_application_available_sub_types.

Guards the fix for "教授看到學生申請的獎學金子類別會看到沒申請的": reviewers
must only see the sub-types the student actually applied for
(``Application.scholarship_subtype_list``), never the full set of active
configs on the scholarship type.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.scholarship import (
    ScholarshipSubTypeConfig,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService


async def _scholarship_with_configs(db: AsyncSession, codes: list[str]) -> ScholarshipType:
    """A ScholarshipType with one active sub-type config per code."""
    scholarship = ScholarshipType(
        code="subtype_visibility_test",
        name="Test",
        sub_type_selection_mode=SubTypeSelectionMode.multiple,
        status="active",
    )
    db.add(scholarship)
    await db.flush()

    for order, code in enumerate(codes):
        db.add(
            ScholarshipSubTypeConfig(
                scholarship_type_id=scholarship.id,
                sub_type_code=code,
                name=f"子類-{code}",
                name_en=code.upper(),
                display_order=order,
                is_active=True,
            )
        )
    await db.flush()
    await db.refresh(scholarship, attribute_names=["sub_type_configs"])
    return scholarship


async def _professor(db: AsyncSession) -> User:
    prof = User(
        nycu_id="prof_subtype",
        name="教授",
        email="prof@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.professor,
    )
    db.add(prof)
    await db.flush()
    return prof


async def _application(
    db: AsyncSession,
    *,
    scholarship: ScholarshipType,
    applied: list[str],
) -> Application:
    student = User(
        nycu_id="310460099",
        name="王小明",
        email="student@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    await db.flush()

    app = Application(
        app_id="APP-114-0-09999",
        user_id=student.id,
        scholarship_type_id=scholarship.id,
        academic_year=114,
        semester=None,
        status=ApplicationStatus.submitted,
        sub_type_selection_mode=SubTypeSelectionMode.multiple,
        scholarship_subtype_list=applied,
    )
    db.add(app)
    await db.flush()
    return app


@pytest.mark.asyncio
class TestGetApplicationAvailableSubTypes:
    async def test_professor_sees_only_applied_subtypes(self, db: AsyncSession):
        """Scholarship has 3 active configs; student applied for 2 → prof sees 2."""
        scholarship = await _scholarship_with_configs(db, ["nstc", "moe_1w", "moe_2w"])
        prof = await _professor(db)
        app = await _application(db, scholarship=scholarship, applied=["nstc", "moe_1w"])

        service = ApplicationService(db)
        result = await service.get_application_available_sub_types(app.id, prof)

        codes = {row["value"] for row in result}
        assert codes == {"nstc", "moe_1w"}
        assert "moe_2w" not in codes  # not applied for — must be hidden

    async def test_applied_codes_normalized_before_matching(self, db: AsyncSession):
        """Mixed-case / whitespace applied codes still match lowercase configs."""
        scholarship = await _scholarship_with_configs(db, ["nstc", "moe_1w"])
        prof = await _professor(db)
        app = await _application(db, scholarship=scholarship, applied=["  NSTC ", "Moe_1w"])

        service = ApplicationService(db)
        result = await service.get_application_available_sub_types(app.id, prof)

        assert {row["value"] for row in result} == {"nstc", "moe_1w"}

    async def test_empty_applied_list_returns_empty(self, db: AsyncSession):
        """No applied sub-types → empty list (frontend falls back to default form)."""
        scholarship = await _scholarship_with_configs(db, ["nstc", "moe_1w"])
        prof = await _professor(db)
        app = await _application(db, scholarship=scholarship, applied=[])

        service = ApplicationService(db)
        result = await service.get_application_available_sub_types(app.id, prof)

        assert result == []

    async def test_college_excludes_professor_rejected_within_applied(self, db: AsyncSession):
        """College sees applied sub-types minus the ones a professor rejected.

        Composition of the two filters: student applied for {nstc, moe_1w}
        (moe_2w configured but not applied), professor rejected nstc → college
        sees only moe_1w. moe_2w stays hidden because it was never applied for.
        """
        from datetime import datetime, timezone

        from app.models.review import ApplicationReview, ApplicationReviewItem

        scholarship = await _scholarship_with_configs(db, ["nstc", "moe_1w", "moe_2w"])
        prof = await _professor(db)
        app = await _application(db, scholarship=scholarship, applied=["nstc", "moe_1w"])

        # Professor rejects the applied sub-type "nstc".
        review = ApplicationReview(
            application_id=app.id,
            reviewer_id=prof.id,
            recommendation="reject",
            reviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        db.add(review)
        await db.flush()
        db.add(
            ApplicationReviewItem(
                review_id=review.id,
                sub_type_code="nstc",
                recommendation="reject",
                comments="不符合",
            )
        )
        await db.flush()

        college = User(
            nycu_id="college_subtype",
            name="學院",
            email="college@nycu.edu.tw",
            user_type=UserType.employee,
            role=UserRole.college,
        )
        db.add(college)
        await db.flush()

        service = ApplicationService(db)
        result = await service.get_application_available_sub_types(app.id, college)

        assert {row["value"] for row in result} == {"moe_1w"}

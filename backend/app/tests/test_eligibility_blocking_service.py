"""Integration tests for EligibilityService.has_blocking_application.

A scholarship is hidden from the apply flow iff the student has a 'blocking'
(submitted-and-beyond) application for the same (type, year, semester).
"""

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import Semester
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.services.eligibility_service import EligibilityService

_SEQ = 0


async def _make_application(db: AsyncSession, user: User, scholarship: ScholarshipType, status: str) -> Application:
    global _SEQ
    _SEQ += 1
    app = Application(
        user_id=user.id,
        scholarship_type_id=scholarship.id,
        sub_type_selection_mode="single",
        status=status,
        app_id=f"TEST-BLOCK-{_SEQ:06d}",
        academic_year=2024,
        semester="first",
        student_data={"name": "Test Student"},
        submitted_form_data={},
        agree_terms=True,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


def _config(scholarship: ScholarshipType) -> SimpleNamespace:
    return SimpleNamespace(
        scholarship_type_id=scholarship.id,
        academic_year=2024,
        semester=Semester.first,
    )


@pytest.mark.parametrize(
    "status,expected",
    [
        ("submitted", True),
        ("under_review", True),
        ("pending_documents", True),
        ("approved", True),
        ("partial_approved", True),
        ("manual_excluded", True),
        ("cancelled_by_challenge", True),
        ("draft", False),
        ("returned", False),
        ("rejected", False),
        ("withdrawn", False),
        ("cancelled", False),
        ("deleted", False),
    ],
)
async def test_has_blocking_application_truth_table(db, test_user, test_scholarship, status, expected):
    await _make_application(db, test_user, test_scholarship, status)
    service = EligibilityService(db)
    result = await service.has_blocking_application(test_user.id, _config(test_scholarship))
    assert result is expected


async def test_no_application_is_not_blocking(db, test_user, test_scholarship):
    service = EligibilityService(db)
    assert await service.has_blocking_application(test_user.id, _config(test_scholarship)) is False


# NOTE: there is intentionally no "rejected + fresh draft" multi-row test.
# Two pure-new applications for the same (user, type, year, semester) can never
# coexist: the `uq_user_pure_new_app` partial unique index in
# Application.__table_args__ forbids it on PostgreSQL, and the SQLite test
# harness ignores the partial `postgresql_where` clause, treating it as a FULL
# unique index — so ANY two same-config rows collide there. The re-applyable
# semantics are already covered by the ("rejected", False) truth-table case
# above. `has_blocking_application` is structurally single-row via `.limit(1)`,
# which still matters: a soft-deleted row CAN coexist with a live one on
# PostgreSQL (excluded from the partial index by `deleted_at IS NULL`).

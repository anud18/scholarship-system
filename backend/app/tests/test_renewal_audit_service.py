"""Unit tests for RenewalAuditService.

Per spec Section 12, every approved challenge application MUST point to a
renewal whose status is ``cancelled_by_challenge``. These tests exercise
the invariant detector for the three relevant cases:

  1. Violation surfaced when the linked renewal is still `approved`.
  2. No violation when the renewal correctly sits in `cancelled_by_challenge`.
  3. No violation when the challenge itself is not yet approved (so the
     invariant doesn't apply).
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import (
    ApplicationStatus,
    ReviewStage,
    SubTypeSelectionMode,
)
from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.renewal_audit_service import RenewalAuditService

CURRENT_YEAR = 114
RENEWAL_YEAR = 113


# --------------------------------------------------------------------------- #
# Fixture helpers (kept local to avoid coupling with other test modules)
# --------------------------------------------------------------------------- #


def _make_user(suffix: str) -> User:
    return User(
        nycu_id=f"audit_{suffix}",
        name=f"Audit Test {suffix}",
        email=f"audit_{suffix}@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )


def _make_application(
    *,
    user_id: int,
    scholarship_type_id: int,
    app_id: str,
    sub_scholarship_type: str,
    status: ApplicationStatus,
    is_renewal: bool = False,
    renewal_year: int | None = None,
    challenges_application_id: int | None = None,
) -> Application:
    return Application(
        app_id=app_id,
        user_id=user_id,
        scholarship_type_id=scholarship_type_id,
        scholarship_subtype_list=[sub_scholarship_type],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type=sub_scholarship_type,
        academic_year=CURRENT_YEAR,
        semester=None,
        status=status,
        review_stage=ReviewStage.quota_distributed,
        is_renewal=is_renewal,
        renewal_year=renewal_year,
        challenges_application_id=challenges_application_id,
        agree_terms=True,
    )


async def _make_scholarship(db: AsyncSession, code: str) -> ScholarshipType:
    sch = ScholarshipType(
        code=code,
        name=f"Audit Test {code}",
        description="Audit fixture",
    )
    db.add(sch)
    await db.commit()
    await db.refresh(sch)
    return sch


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_finds_violation_when_renewal_still_approved(db: AsyncSession):
    """An approved challenge whose renewal is still `approved` is a violation."""
    sch = await _make_scholarship(db, "audit_violation")
    user = _make_user("v")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Renewal: approved (the invariant says it should be cancelled_by_challenge).
    renewal = _make_application(
        user_id=user.id,
        scholarship_type_id=sch.id,
        app_id="AUDIT-V-R",
        sub_scholarship_type="nstc",
        status=ApplicationStatus.approved,
        is_renewal=True,
        renewal_year=RENEWAL_YEAR,
    )
    db.add(renewal)
    await db.commit()
    await db.refresh(renewal)

    # Challenge: approved, linked to the renewal above.
    challenge = _make_application(
        user_id=user.id,
        scholarship_type_id=sch.id,
        app_id="AUDIT-V-C",
        sub_scholarship_type="moe_1w",
        status=ApplicationStatus.approved,
        is_renewal=False,
        challenges_application_id=renewal.id,
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)

    service = RenewalAuditService(db)
    violations = await service.find_invariant_violations()

    assert len(violations) == 1
    violation = violations[0]
    assert violation["challenge_id"] == challenge.id
    assert violation["renewal_id"] == renewal.id
    assert violation["actual_renewal_status"] == ApplicationStatus.approved.value


@pytest.mark.asyncio
async def test_no_violation_when_renewal_correctly_cancelled(db: AsyncSession):
    """When the renewal is cancelled_by_challenge, the invariant holds."""
    sch = await _make_scholarship(db, "audit_ok")
    user = _make_user("ok")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    renewal = _make_application(
        user_id=user.id,
        scholarship_type_id=sch.id,
        app_id="AUDIT-OK-R",
        sub_scholarship_type="nstc",
        status=ApplicationStatus.cancelled_by_challenge,
        is_renewal=True,
        renewal_year=RENEWAL_YEAR,
    )
    db.add(renewal)
    await db.commit()
    await db.refresh(renewal)

    challenge = _make_application(
        user_id=user.id,
        scholarship_type_id=sch.id,
        app_id="AUDIT-OK-C",
        sub_scholarship_type="moe_1w",
        status=ApplicationStatus.approved,
        is_renewal=False,
        challenges_application_id=renewal.id,
    )
    # Reflect the post-release linkage for completeness.
    challenge.app_id = "AUDIT-OK-C"
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)

    # Wire the back-pointer the distribution algorithm would set.
    renewal.cancelled_due_to_application_id = challenge.id
    await db.commit()

    service = RenewalAuditService(db)
    violations = await service.find_invariant_violations()

    assert violations == []


@pytest.mark.asyncio
async def test_no_violation_for_rejected_challenge(db: AsyncSession):
    """A non-approved challenge is outside the invariant scope (not audited)."""
    sch = await _make_scholarship(db, "audit_pending")
    user = _make_user("pend")
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Renewal still approved — but the challenge is rejected, so this is OK.
    renewal = _make_application(
        user_id=user.id,
        scholarship_type_id=sch.id,
        app_id="AUDIT-P-R",
        sub_scholarship_type="nstc",
        status=ApplicationStatus.approved,
        is_renewal=True,
        renewal_year=RENEWAL_YEAR,
    )
    db.add(renewal)
    await db.commit()
    await db.refresh(renewal)

    challenge = _make_application(
        user_id=user.id,
        scholarship_type_id=sch.id,
        app_id="AUDIT-P-C",
        sub_scholarship_type="moe_1w",
        status=ApplicationStatus.rejected,
        is_renewal=False,
        challenges_application_id=renewal.id,
    )
    db.add(challenge)
    await db.commit()
    await db.refresh(challenge)

    service = RenewalAuditService(db)
    violations = await service.find_invariant_violations()

    assert violations == []

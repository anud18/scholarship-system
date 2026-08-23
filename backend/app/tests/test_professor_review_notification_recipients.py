"""Trigger point 1, professor side: 教授審核通知 reaches BOTH advisor addresses.

An advisor is reachable through two independently-populated addresses:

- ``users.email`` of ``applications.professor_id`` — the professor's SSO account,
  assigned at submission only when the professor already has an account.
- ``user_profiles.advisor_email`` — typed by the student (profile form / batch
  import).

They can disagree, and the previous ``COALESCE`` silently dropped whichever
lost. Contract pinned here: the shipped condition_query resolves to the union
of both, folds them when identical, and still works when either side is
missing.
"""

from typing import Optional

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.sql_read_only_guard import assert_read_only_select
from app.db.seed_scholarship_configs import PROFESSOR_REVIEW_NOTIFICATION_CONDITION_QUERY
from app.models.application import Application, ApplicationStatus
from app.models.email_management import EmailAutomationRule, TriggerEvent
from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole, UserType
from app.models.user_profile import UserProfile
from app.services.email_automation_service import email_automation_service

ACCOUNT_EMAIL = "prof.account@nycu.edu.tw"
PROFILE_EMAIL = "prof.typed-by-student@gmail.com"


async def _seed_user(db: AsyncSession, *, nycu_id: str, role: UserRole, email: Optional[str]) -> User:
    user = User(
        nycu_id=nycu_id,
        name=nycu_id,
        email=email,
        user_type=UserType.student if role == UserRole.student else UserType.employee,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seed_application(
    db: AsyncSession,
    *,
    suffix: str,
    advisor_email: Optional[str],
    professor: Optional[User],
    advisor_nycu_id: Optional[str] = None,
) -> Application:
    student = await _seed_user(db, nycu_id=f"stu_{suffix}", role=UserRole.student, email=f"stu_{suffix}@u.edu")
    db.add(UserProfile(user_id=student.id, advisor_email=advisor_email, advisor_nycu_id=advisor_nycu_id))

    scholarship_type = ScholarshipType(code=f"prof_notify_{suffix}", name=f"Prof notify {suffix}", status="active")
    db.add(scholarship_type)
    await db.commit()
    await db.refresh(scholarship_type)

    application = Application(
        app_id=f"APP-PROFNOTIFY-{suffix}",
        user_id=student.id,
        scholarship_type_id=scholarship_type.id,
        academic_year=114,
        sub_type_selection_mode="single",
        status=ApplicationStatus.submitted.value,
        professor_id=professor.id if professor else None,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


def _rule() -> EmailAutomationRule:
    return EmailAutomationRule(
        name="教授審核通知",
        trigger_event=TriggerEvent.application_submitted,
        template_key="professor_review_notification",
        condition_query=PROFESSOR_REVIEW_NOTIFICATION_CONDITION_QUERY,
        delay_hours=0,
        is_active=True,
    )


async def _recipients(db: AsyncSession, application: Application) -> list[str]:
    rows = await email_automation_service._get_recipients(db, _rule(), {"application_id": application.id})
    return sorted(r["email"] for r in rows)


def test_shipped_query_passes_the_read_only_guard():
    assert_read_only_select(PROFESSOR_REVIEW_NOTIFICATION_CONDITION_QUERY)


@pytest.mark.asyncio
async def test_both_addresses_are_notified_when_they_differ(db: AsyncSession):
    professor = await _seed_user(db, nycu_id="prof_both", role=UserRole.professor, email=ACCOUNT_EMAIL)
    application = await _seed_application(db, suffix="both", advisor_email=PROFILE_EMAIL, professor=professor)

    assert await _recipients(db, application) == sorted([ACCOUNT_EMAIL, PROFILE_EMAIL])


@pytest.mark.asyncio
async def test_identical_addresses_are_folded_into_one_send(db: AsyncSession):
    professor = await _seed_user(db, nycu_id="prof_same", role=UserRole.professor, email=ACCOUNT_EMAIL)
    application = await _seed_application(db, suffix="same", advisor_email=ACCOUNT_EMAIL, professor=professor)

    assert await _recipients(db, application) == [ACCOUNT_EMAIL]


@pytest.mark.asyncio
async def test_profile_email_alone_when_professor_has_no_account(db: AsyncSession):
    """The PR #1323 scenario: advisor named before they ever signed in."""
    application = await _seed_application(db, suffix="noacct", advisor_email=PROFILE_EMAIL, professor=None)

    assert await _recipients(db, application) == [PROFILE_EMAIL]


@pytest.mark.asyncio
async def test_account_email_alone_when_profile_has_no_advisor_email(db: AsyncSession):
    professor = await _seed_user(db, nycu_id="prof_only", role=UserRole.professor, email=ACCOUNT_EMAIL)
    application = await _seed_application(db, suffix="acctonly", advisor_email=None, professor=professor)

    assert await _recipients(db, application) == [ACCOUNT_EMAIL]


@pytest.mark.asyncio
async def test_blank_addresses_are_skipped(db: AsyncSession):
    professor = await _seed_user(db, nycu_id="prof_blank", role=UserRole.professor, email="")
    application = await _seed_application(db, suffix="blank", advisor_email="", professor=professor)

    assert await _recipients(db, application) == []


@pytest.mark.asyncio
async def test_other_applications_do_not_leak_in(db: AsyncSession):
    professor = await _seed_user(db, nycu_id="prof_a", role=UserRole.professor, email=ACCOUNT_EMAIL)
    other_prof = await _seed_user(db, nycu_id="prof_b", role=UserRole.professor, email="other@nycu.edu.tw")
    target = await _seed_application(db, suffix="target", advisor_email=PROFILE_EMAIL, professor=professor)
    await _seed_application(db, suffix="other", advisor_email="other.typed@gmail.com", professor=other_prof)

    assert await _recipients(db, target) == sorted([ACCOUNT_EMAIL, PROFILE_EMAIL])


@pytest.mark.asyncio
async def test_profile_naming_the_assigned_professor_mails_both_addresses(db: AsyncSession):
    """Same person, two inboxes: the normal case the UNION exists for."""
    professor = await _seed_user(db, nycu_id="prof_named", role=UserRole.professor, email=ACCOUNT_EMAIL)
    application = await _seed_application(
        db, suffix="named", advisor_email=PROFILE_EMAIL, professor=professor, advisor_nycu_id=professor.nycu_id
    )

    assert await _recipients(db, application) == sorted([ACCOUNT_EMAIL, PROFILE_EMAIL])


@pytest.mark.asyncio
async def test_profile_naming_a_different_professor_is_not_mailed(db: AsyncSession):
    """returned→resubmit after an advisor change: professor_id still points at
    the original reviewer, so the newly named advisor must not get a review
    link that would 403 for them."""
    original = await _seed_user(db, nycu_id="prof_orig", role=UserRole.professor, email=ACCOUNT_EMAIL)
    await _seed_user(db, nycu_id="prof_new", role=UserRole.professor, email="new.prof@nycu.edu.tw")
    application = await _seed_application(
        db, suffix="changed", advisor_email="new.prof@gmail.com", professor=original, advisor_nycu_id="prof_new"
    )

    assert await _recipients(db, application) == [ACCOUNT_EMAIL]

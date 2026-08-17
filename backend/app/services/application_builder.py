"""Shared application-construction helpers.

Single source of truth for logic used by BOTH the student self-submission
path (ApplicationService) and the batch import path (BatchImportService).
Any submitted-application field rule that must stay identical across the
two paths belongs here — that is the module's only admission criterion.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.models.application import Application
from app.models.application_sequence import ApplicationSequence
from app.models.enums import REVIEWABLE_APPLICATION_STATUSES, ApplicationStatus, ReviewStage
from app.models.user import User, UserRole
from app.models.user_profile import UserProfile
from app.utils.i18n import ScholarshipI18n

logger = logging.getLogger(__name__)

# Mirrors FORCED_FIRST_PREFERENCE in
# frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx:
# the manual preference-ordering UI is hidden; MOE (moe_1w) is always the
# first preference when selected alongside other sub-types.
FORCED_FIRST_PREFERENCE = "moe_1w"


def derive_sub_scholarship_type(scholarship_subtype_list: Optional[List[str]]) -> str:
    """Derive the denormalized scalar `sub_scholarship_type` from the selected
    sub-type list: first entry wins, normalized to lowercase; empty → "general".
    """
    if scholarship_subtype_list:
        return scholarship_subtype_list[0].lower()
    return "general"


def validate_sub_type_for_submission(scholarship, sub_scholarship_type: Optional[str]) -> None:
    """Reject the synthetic "general" category on submission for scholarships
    that define real sub-types, and arbitrary sub-types for scholarships that
    define none. Comparison is case-insensitive.
    """
    if scholarship is None:
        return
    real_sub_types = [st.lower() for st in (scholarship.sub_type_list or []) if st and st.lower() != "general"]
    normalized = (sub_scholarship_type or "general").lower()
    if real_sub_types:
        if normalized not in real_sub_types:
            raise ValidationError("此獎學金需選擇申請類別（" + "、".join(real_sub_types) + "），不可使用通用類別")
    elif normalized != "general":
        raise ValidationError("此獎學金不提供申請類別選擇，不可指定子類別")


def order_sub_type_preferences(sub_types: List[str]) -> List[str]:
    """Order a selected sub-type list the way the student wizard does:
    FORCED_FIRST_PREFERENCE (moe_1w) leads when present; the rest keep
    their given order. Returns a new list.
    """
    if FORCED_FIRST_PREFERENCE in sub_types:
        return [FORCED_FIRST_PREFERENCE] + [st for st in sub_types if st != FORCED_FIRST_PREFERENCE]
    return list(sub_types)


def build_submitted_application_values(scholarship, config) -> Dict[str, Any]:
    """Field values every application must carry the moment it is submitted,
    regardless of which path created it.
    """
    return {
        "status": ApplicationStatus.submitted.value,
        "status_name": ScholarshipI18n.get_application_status_text(ApplicationStatus.submitted.value),
        "review_stage": ReviewStage.student_submitted.value,
        "submitted_at": datetime.now(timezone.utc),
        "amount": config.amount,
        "scholarship_name": config.config_name or scholarship.name,
    }


async def generate_app_id(
    db: AsyncSession,
    academic_year: int,
    semester,
    *,
    suffix: str = "",
    commit: bool = True,
) -> str:
    """Generate a sequential application ID with database row locking.

    Format: APP-{academic_year}-{semester_code}-{sequence:05d}{suffix}

    commit=True releases the sequence row lock immediately (student path).
    commit=False keeps the lock until the caller's transaction ends — the
    batch import path relies on this to stay atomic, at the cost of
    blocking online submissions for the duration of the import.
    """
    if semester is None:
        semester = "yearly"
    if hasattr(semester, "value"):
        semester = semester.value

    stmt = (
        select(ApplicationSequence)
        .where(
            and_(
                ApplicationSequence.academic_year == academic_year,
                ApplicationSequence.semester == semester,
            )
        )
        .with_for_update()
    )
    result = await db.execute(stmt)
    seq_record = result.scalar_one_or_none()

    if not seq_record:
        seq_record = ApplicationSequence(academic_year=academic_year, semester=semester, last_sequence=0)
        db.add(seq_record)
        await db.flush()

    seq_record.last_sequence += 1
    sequence_num = seq_record.last_sequence

    if commit:
        await db.commit()

    app_id = ApplicationSequence.format_app_id(academic_year, semester, sequence_num)
    return f"{app_id}{suffix}"


async def assign_professor_from_profile(
    db: AsyncSession, application, user_id: int, profile: Optional[UserProfile] = None
) -> Optional[User]:
    """Auto-assign the reviewing professor from the student's UserProfile.

    Looks up UserProfile.advisor_nycu_id and matches a User with
    role=professor. Returns the professor User or None. Never overwrites
    an already-assigned professor_id. Pass `profile` when the caller has
    already loaded it to skip the redundant SELECT.
    """
    if getattr(application, "professor_id", None):
        return None

    if profile is None:
        profile_stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        profile_result = await db.execute(profile_stmt)
        profile = profile_result.scalar_one_or_none()

    if not profile or not profile.advisor_nycu_id:
        return None

    professor_stmt = select(User).where(
        User.nycu_id == profile.advisor_nycu_id,
        User.role == UserRole.professor,
    )
    professor_result = await db.execute(professor_stmt)
    professor = professor_result.scalar_one_or_none()

    if professor:
        application.professor_id = professor.id
        logger.info(
            "Auto-assigned professor %s to application %s",
            professor.id,
            getattr(application, "app_id", "?"),
        )
    return professor


async def backfill_professor_assignments(db: AsyncSession, professor: Optional[User]) -> int:
    """Claim applications left unassigned because this professor had no account yet.

    :func:`assign_professor_from_profile` runs at submission time and can only
    match an advisor who ALREADY exists as a ``role=professor`` User. When a
    student names an advisor who has never signed in, the application is stored
    with ``professor_id IS NULL`` and never reaches anybody's review queue.

    This repairs those rows the moment the advisor does get an account. It is
    idempotent (already-assigned rows are excluded by ``professor_id IS NULL``),
    so it is safe to run on every professor login and on every professor queue
    load — see the two call sites:

    - :meth:`PortalSSOService.process_portal_login` — first SSO login / any
      later login, right after the account is created or its role is updated.
    - :meth:`ApplicationService.get_professor_applications_paginated` and
      :meth:`ApplicationService.get_professor_review_stats` — fallback for
      professor accounts created outside the SSO path (admin-created,
      pre-authorized) and for advisors named AFTER the professor's first login.

    Assignment (rather than a read-only ``advisor_nycu_id`` join in the queue
    query) is deliberate: every downstream authorization check — opening the
    application, submitting a review, updating it — compares
    ``application.professor_id`` against the caller. A row merely *shown* in the
    queue without being assigned would 403 on the very next click.

    Only :data:`REVIEWABLE_APPLICATION_STATUSES` rows are claimed. Drafts are
    excluded on purpose: they get their professor at submission time from the
    profile as it reads *then*, so pre-assigning one would pin a stale advisor
    if the student edits their profile before submitting.

    Returns the number of applications claimed.
    """
    if professor is None or not professor.id or not professor.nycu_id:
        return 0

    # Compare against enum AND its .value: a SQLite-loaded (or hand-built) User
    # can carry the raw string, and a bare `!= UserRole.professor` would then
    # silently skip a real professor.
    if professor.role not in (UserRole.professor, UserRole.professor.value):
        return 0

    advisee_user_ids = select(UserProfile.user_id).where(UserProfile.advisor_nycu_id == professor.nycu_id)

    # synchronize_session=False: both call sites run this before loading any
    # Application into the session, so there is nothing in the identity map to
    # go stale, and skipping the sync avoids an extra round trip.
    stmt = (
        update(Application)
        .where(
            Application.professor_id.is_(None),
            Application.deleted_at.is_(None),  # never resurface a soft-deleted application
            Application.status.in_(REVIEWABLE_APPLICATION_STATUSES),
            Application.user_id.in_(advisee_user_ids),
        )
        .values(professor_id=professor.id)
        .execution_options(synchronize_session=False)
    )
    result = await db.execute(stmt)
    claimed = result.rowcount or 0

    if claimed:
        logger.info(
            "Backfilled %s unassigned application(s) to professor %s (nycu_id=%s)",
            claimed,
            professor.id,
            professor.nycu_id,
        )
    return claimed

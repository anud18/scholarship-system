"""Shared application-construction helpers.

Single source of truth for logic used by BOTH the student self-submission
path (ApplicationService) and the batch import path (BatchImportService).
Any submitted-application field rule that must stay identical across the
two paths belongs here — that is the module's only admission criterion.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.exceptions import ValidationError
from app.models.application import Application
from app.models.application_round import FIRST_APPLICATION_ROUND, ScholarshipApplicationRound
from app.models.application_sequence import ApplicationSequence
from app.models.enums import PROFESSOR_ACTIONABLE_APPLICATION_STATUSES, ApplicationStatus, ReviewStage
from app.models.scholarship import ScholarshipConfiguration
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


def validate_sub_types_open_in_round(config, application_round: Optional[int], sub_types: List[str]) -> None:
    """Reject sub-types the application's 申請梯次 does not open (多梯次申請).

    Each round opens the sub-types the administrator picked for it; round 1 opens
    every sub-type unless the configuration restricts it.
    """
    from app.services.ranking_groups import round_label

    open_codes = config.open_sub_types_for_round(application_round) if config is not None else None
    if open_codes is None:
        return
    closed = [st for st in sub_types if st and st.lower().strip() not in open_codes]
    if closed:
        label = round_label(application_round)
        opened = "、".join(open_codes) if open_codes else "無"
        raise ValidationError(f"{label}僅開放申請：{opened}；不可申請：{'、'.join(closed)}")


def resolve_imported_application_round(
    config, requested_round: Optional[int], sub_types: List[str], is_renewal: bool = False
) -> int:
    """申請梯次 of an imported row (the 申請梯次 column of 批次匯入 / 補充匯入).

    A blank cell means 第一梯次 only while the configuration has no later round;
    otherwise the column is required. The round must exist and open the row's
    sub-types. Renewals rank in their own group, so their round stays 1.
    """
    if is_renewal:
        return FIRST_APPLICATION_ROUND
    round_numbers = config.application_round_numbers
    choices = "、".join(str(number) for number in round_numbers)
    if requested_round is None:
        if len(round_numbers) > 1:
            raise ValidationError(f"此獎學金設有多個申請梯次，請填寫「申請梯次」（可填：{choices}）")
        requested_round = FIRST_APPLICATION_ROUND
    if requested_round not in round_numbers:
        raise ValidationError(f"申請梯次 {requested_round} 不存在（可填：{choices}）")
    validate_sub_types_open_in_round(config, requested_round, sub_types)
    return requested_round


def order_sub_type_preferences(sub_types: List[str]) -> List[str]:
    """Order a selected sub-type list the way the student wizard does:
    FORCED_FIRST_PREFERENCE (moe_1w) leads when present; the rest keep
    their given order. Matched case/whitespace-insensitively (stored lists are
    free-form strings) and the original spelling is kept. Returns a new list.
    """

    def _is_forced(st: Optional[str]) -> bool:
        return (st or "").lower().strip() == FORCED_FIRST_PREFERENCE

    return [st for st in sub_types if _is_forced(st)] + [st for st in sub_types if not _is_forced(st)]


async def ensure_application_rounds_loaded(db: AsyncSession, config) -> None:
    """Load ``config.application_rounds`` when it is not loaded yet (e.g. a configuration
    created in this session), so resolve_imported_application_round never lazy-loads."""
    state = sa_inspect(config, raiseerr=False)
    if state is not None and "application_rounds" in state.unloaded:
        await db.refresh(config, attribute_names=["application_rounds"])


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

    # 人事代號 is entered uppercased, but account nycu_ids may not be. users.nycu_id
    # is unique only case-sensitively, so prefer an exact match and never let two
    # case-variant accounts raise MultipleResultsFound mid-submit.
    professor_stmt = (
        select(User)
        .where(
            func.upper(User.nycu_id) == profile.advisor_nycu_id.upper(),
            User.role == UserRole.professor,
        )
        .order_by((User.nycu_id == profile.advisor_nycu_id).desc(), User.id)
        .limit(1)
    )
    professor_result = await db.execute(professor_stmt)
    professor = professor_result.scalars().first()

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

    Only rows the professor can still ACT on are claimed. The queue's 待審核
    bucket is "assigned to me and I have not reviewed" with no further gate,
    while ``can_professor_submit_review`` refuses anything outside its status
    and time window — so every row claimed here that the review endpoint would
    refuse is a row parked in 待審核 forever with a 403 on every attempt to
    clear it. Four exclusions, all deliberate:

    - Drafts: they get their professor at submission time from the profile as it
      reads *then*, so pre-assigning one would pin a stale advisor if the
      student edits their profile before submitting.
    - Already-decided applications (approved / partial_approved / rejected) —
      :data:`PROFESSOR_ACTIONABLE_APPLICATION_STATUSES`, not the wider listing
      set.
    - Configurations without a professor stage (``requires_professor_recommendation``
      for initial applications, ``renewal_requires_professor_review`` for
      renewals — the same predicate the professor queue filters on). The
      dashboard badge does NOT apply that filter, so a claimed row on such a
      configuration would count as 1 待審核 that the list never shows.
    - Configurations whose professor review window has already closed. The
      window ``can_professor_submit_review`` enforces is application_start_date →
      professor_review_end (renewal_professor_review_start/_end for renewals),
      skipped when either bound is NULL; a future start is fine, the row simply
      becomes actionable later.

    Returns the number of applications claimed.
    """
    if professor is None or not professor.id or not professor.nycu_id:
        return 0

    # Compare against enum AND its .value: a SQLite-loaded (or hand-built) User
    # can carry the raw string, and a bare `!= UserRole.professor` would then
    # silently skip a real professor.
    if professor.role not in (UserRole.professor, UserRole.professor.value):
        return 0

    advisee_user_ids = select(UserProfile.user_id).where(
        func.upper(UserProfile.advisor_nycu_id) == professor.nycu_id.upper()
    )

    # Configurations on which an application of each kind is professor-actionable:
    # the workflow has a professor stage and its review window has not closed.
    # Mirrors the professor queue's config predicate
    # (ApplicationService.get_professor_applications_paginated) plus the time
    # gate of ApplicationService.can_professor_submit_review.
    now = datetime.now(timezone.utc)
    # 多梯次申請: a later-round application uses its round's professor window,
    # falling back to the general one (ScholarshipConfiguration.review_window_for).
    application_round = aliased(ScholarshipApplicationRound)
    initial_review_end = func.coalesce(
        application_round.professor_review_end, ScholarshipConfiguration.professor_review_end
    )
    initial_actionable = (
        select(ScholarshipConfiguration.id)
        .outerjoin(
            application_round,
            and_(
                application_round.configuration_id == ScholarshipConfiguration.id,
                application_round.round_number == Application.application_round,
            ),
        )
        .where(
            ScholarshipConfiguration.id == Application.scholarship_configuration_id,
            ScholarshipConfiguration.requires_professor_recommendation.is_(True),
            or_(
                ScholarshipConfiguration.application_start_date.is_(None),
                initial_review_end.is_(None),
                initial_review_end >= now,
            ),
        )
        .exists()
    )
    renewal_actionable_configs = select(ScholarshipConfiguration.id).where(
        ScholarshipConfiguration.renewal_requires_professor_review.is_(True),
        or_(
            ScholarshipConfiguration.renewal_professor_review_start.is_(None),
            ScholarshipConfiguration.renewal_professor_review_end.is_(None),
            ScholarshipConfiguration.renewal_professor_review_end >= now,
        ),
    )

    # synchronize_session=False: both call sites run this before loading any
    # Application into the session, so there is nothing in the identity map to
    # go stale, and skipping the sync avoids an extra round trip.
    stmt = (
        update(Application)
        .where(
            Application.professor_id.is_(None),
            Application.deleted_at.is_(None),  # never resurface a soft-deleted application
            Application.status.in_(PROFESSOR_ACTIONABLE_APPLICATION_STATUSES),
            Application.user_id.in_(advisee_user_ids),
            or_(
                and_(Application.is_renewal.is_(False), initial_actionable),
                and_(
                    Application.is_renewal.is_(True),
                    Application.scholarship_configuration_id.in_(renewal_actionable_configs),
                ),
            ),
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

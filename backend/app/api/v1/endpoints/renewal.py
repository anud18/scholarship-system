"""Renewal & Challenge application endpoints.

This module exposes three endpoints under `/renewals`:

- GET  /api/v1/renewals/eligible   — list prior-year approved applications
                                     that may be renewed right now.
- POST /api/v1/renewals/           — create a renewal application from a
                                     specific prior approved application.
- POST /api/v1/renewals/challenge  — create a challenge application from
                                     an approved renewal, targeting a
                                     different sub_type.

Period validation reads `renewal_application_*` and `application_*`
fields from `ScholarshipConfiguration` for the *current* academic year
(matching where the dates actually live in the schema — they are NOT on
`ScholarshipType`).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.deps import get_current_admin_user
from app.core.security import get_current_user, require_admin
from app.db.deps import get_db
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.schemas.renewal import CreateChallengeRequest, CreateRenewalRequest
from app.models.audit_log import AuditAction
from app.services.application_audit_service import ApplicationAuditService
from app.services.application_service import ApplicationService
from app.services.renewal_audit_service import RenewalAuditService
from app.services.renewal_distribution_service import RenewalDistributionService
from app.services.renewal_eligibility_service import RenewalEligibilityService
from app.utils.academic_period import get_current_academic_period

router = APIRouter()


def _current_academic_year() -> int:
    """Return the active ROC academic year."""
    return get_current_academic_period()["academic_year"]


def _to_utc_aware(dt):
    """Normalise a possibly naive datetime to UTC-aware.

    SQLite drops timezone info, so columns declared `DateTime(timezone=True)`
    can come back naive in tests. Assume naive datetimes are already UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def _get_current_year_config(
    db: AsyncSession,
    *,
    scholarship_type_id: int,
    academic_year: int,
    semester,
) -> ScholarshipConfiguration | None:
    """Look up the ScholarshipConfiguration row matching (type, year, semester).

    Semester may be `None` (yearly scholarships); matched exactly.
    """
    stmt = select(ScholarshipConfiguration).where(
        ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
        ScholarshipConfiguration.academic_year == academic_year,
        ScholarshipConfiguration.is_active.is_(True),
    )
    if semester is None:
        stmt = stmt.where(ScholarshipConfiguration.semester.is_(None))
    else:
        stmt = stmt.where(ScholarshipConfiguration.semester == semester)
    return await db.scalar(stmt)


@router.get("/eligible")
async def list_eligible_renewals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the user's prior-year approved applications that may be renewed.

    "May be renewed" means the current-year `ScholarshipConfiguration` for the
    same scholarship_type has its `renewal_application_*` window open.
    """
    current_year = _current_academic_year()
    service = RenewalEligibilityService(db)
    apps = await service.get_eligible_renewals(current_user.id, current_year)

    items = []
    for app in apps:
        # Resolve current-year config for the renewal deadline display.
        config = await _get_current_year_config(
            db,
            scholarship_type_id=app.scholarship_type_id,
            academic_year=current_year,
            semester=app.semester,
        )
        deadline_dt = _to_utc_aware(config.renewal_application_end_date) if config else None
        deadline = deadline_dt.isoformat() if deadline_dt else None
        items.append(
            {
                "previous_application_id": app.id,
                "scholarship_type_id": app.scholarship_type_id,
                "scholarship_type_name": app.scholarship_type_ref.name if app.scholarship_type_ref else None,
                "sub_scholarship_type": app.sub_scholarship_type,
                "target_academic_year": current_year,
                "renewal_year": app.renewal_year or app.academic_year,
                "renewal_deadline": deadline,
            }
        )

    return {
        "success": True,
        "message": "Eligible renewals retrieved",
        "data": items,
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_renewal_application(
    body: CreateRenewalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Create a renewal application from a prior approved application.

    Validations:
      1. Previous application exists.
      2. It belongs to the current user.
      3. Its status is `approved`.
      4. The current-year ScholarshipConfiguration has an active renewal window.
      5. No existing renewal application for the same (user, type, year, semester).
    """
    now = datetime.now(timezone.utc)

    # 1. Load previous application
    prev = await db.scalar(select(Application).where(Application.id == body.previous_application_id))
    if not prev:
        raise HTTPException(status_code=404, detail="先前申請紀錄不存在")
    if prev.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="無權續領他人申請")
    if prev.status != ApplicationStatus.approved:
        raise HTTPException(status_code=400, detail="先前申請尚未核可，無法續領 (prior not approved)")

    # 2. Check renewal period on the *current-year* configuration for the same type.
    current_year = _current_academic_year()
    config = await _get_current_year_config(
        db,
        scholarship_type_id=prev.scholarship_type_id,
        academic_year=current_year,
        semester=prev.semester,
    )
    start = _to_utc_aware(config.renewal_application_start_date) if config else None
    end = _to_utc_aware(config.renewal_application_end_date) if config else None
    if not (start and end and start <= now <= end):
        raise HTTPException(status_code=400, detail="目前不在續領申請期間")

    # 3. Duplicate check (renewal flag set, status != deleted)
    existing = await db.scalar(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.scholarship_type_id == prev.scholarship_type_id,
            Application.academic_year == current_year,
            Application.semester == prev.semester,
            Application.is_renewal.is_(True),
            Application.status != ApplicationStatus.deleted,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="已建立續領申請")

    # 4. Create renewal application
    service = ApplicationService(db)
    new_app = await service.create_renewal_from_previous(
        previous=prev,
        current_user=current_user,
        target_academic_year=current_year,
        renewal_year=prev.renewal_year or prev.academic_year,
    )
    await db.commit()
    await db.refresh(new_app)

    # Audit the creation (issue #973 / G11) — renewal applications previously
    # left no trace while ordinary creations do.
    await ApplicationAuditService(db).log_application_operation(
        application_id=new_app.id,
        action=AuditAction.create,
        user=current_user,
        request=request,
        description=f"建立續領申請 {new_app.app_id}（自 {prev.app_id}）",
        new_values={
            "app_id": new_app.app_id,
            "is_renewal": True,
            "previous_application_id": new_app.previous_application_id,
            "sub_scholarship_type": new_app.sub_scholarship_type,
            "academic_year": new_app.academic_year,
        },
        meta_data={"app_id": new_app.app_id, "renewal": True},
    )

    return {
        "success": True,
        "message": "續領申請已建立",
        "data": {
            "id": new_app.id,
            "app_id": new_app.app_id,
            "is_renewal": new_app.is_renewal,
            "sub_scholarship_type": new_app.sub_scholarship_type,
            "previous_application_id": new_app.previous_application_id,
            "academic_year": new_app.academic_year,
            "renewal_year": new_app.renewal_year,
            "status": new_app.status.value if hasattr(new_app.status, "value") else new_app.status,
        },
    }


@router.post("/challenge", status_code=status.HTTP_201_CREATED)
async def create_challenge_application(
    body: CreateChallengeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Create a challenge application from an approved renewal.

    Validations:
      1. Renewal application exists.
      2. It belongs to the current user.
      3. It is in fact a renewal (`is_renewal=True`).
      4. Its status is `approved`.
      5. `target_sub_type` differs from renewal's `sub_scholarship_type`.
      6. The renewal-year ScholarshipConfiguration has an active general
         application window.
      7. `target_sub_type` exists in `ScholarshipConfiguration.quotas`.
      8. No existing challenge application for the same renewal.
    """
    now = datetime.now(timezone.utc)

    # 1. Load renewal application
    renewal = await db.scalar(select(Application).where(Application.id == body.renewal_application_id))
    if not renewal:
        raise HTTPException(status_code=404, detail="續領申請紀錄不存在")
    if renewal.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="無權挑戰他人續領")
    if not renewal.is_renewal:
        raise HTTPException(status_code=400, detail="目標申請非續領紀錄")
    if renewal.status != ApplicationStatus.approved:
        raise HTTPException(status_code=400, detail="續領申請尚未核可，無法挑戰 (renewal not approved)")

    # 2. sub_type difference check (cheap, do before db lookup)
    if body.target_sub_type == renewal.sub_scholarship_type:
        raise HTTPException(status_code=400, detail="挑戰 sub_type 不能與續領 sub_type 相同")

    # 3. Load configuration for the renewal's (year, semester) — same period.
    config = await _get_current_year_config(
        db,
        scholarship_type_id=renewal.scholarship_type_id,
        academic_year=renewal.academic_year,
        semester=renewal.semester,
    )
    start = _to_utc_aware(config.application_start_date) if config else None
    end = _to_utc_aware(config.application_end_date) if config else None
    if not (start and end and start <= now <= end):
        raise HTTPException(status_code=400, detail="目前不在一般申請期間")

    # 4. Validate target_sub_type exists in configured quotas.
    if config and body.target_sub_type not in (config.quotas or {}):
        raise HTTPException(
            status_code=400,
            detail=f"sub_type '{body.target_sub_type}' 不存在於配置",
        )

    # 5. Duplicate challenge check
    existing = await db.scalar(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.scholarship_type_id == renewal.scholarship_type_id,
            Application.academic_year == renewal.academic_year,
            Application.semester == renewal.semester,
            Application.is_renewal.is_(False),
            Application.challenges_application_id == renewal.id,
            Application.status != ApplicationStatus.deleted,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="已建立挑戰申請")

    # 6. Create challenge application
    service = ApplicationService(db)
    new_app = await service.create_challenge_from_renewal(
        renewal=renewal,
        current_user=current_user,
        target_sub_type=body.target_sub_type,
    )
    await db.commit()
    await db.refresh(new_app)

    # Audit the creation (issue #973 / G11).
    await ApplicationAuditService(db).log_application_operation(
        application_id=new_app.id,
        action=AuditAction.create,
        user=current_user,
        request=request,
        description=f"建立挑戰申請 {new_app.app_id}（挑戰 {renewal.app_id}，目標 {body.target_sub_type}）",
        new_values={
            "app_id": new_app.app_id,
            "challenges_application_id": new_app.challenges_application_id,
            "sub_scholarship_type": new_app.sub_scholarship_type,
            "academic_year": new_app.academic_year,
        },
        meta_data={"app_id": new_app.app_id, "challenge": True},
    )

    return {
        "success": True,
        "message": "挑戰申請已建立",
        "data": {
            "id": new_app.id,
            "app_id": new_app.app_id,
            "is_renewal": new_app.is_renewal,
            "sub_scholarship_type": new_app.sub_scholarship_type,
            "challenges_application_id": new_app.challenges_application_id,
            "academic_year": new_app.academic_year,
            "status": new_app.status.value if hasattr(new_app.status, "value") else new_app.status,
        },
    }


@router.post("/{scholarship_type_id}/auto-distribute")
async def trigger_renewal_auto_distribution(
    scholarship_type_id: int,
    academic_year: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin-triggered: auto-approve renewal applications past their review stage.

    Renewals skip the college_ranking phase by design — once they have cleared
    the reviews the admin enabled for renewals (`renewal_requires_professor_review`
    / `renewal_requires_college_review` on `ScholarshipConfiguration`; possibly
    none), this endpoint flips them from `under_review` (or `submitted` when no
    review is required) to `approved` with `review_stage = quota_distributed`.

    Args:
        scholarship_type_id: Path — scholarship type to process.
        academic_year:        Query — ROC academic year (e.g. 114).

    Returns:
        ApiResponse with data = {approved_count, approved_ids}.
    """
    service = RenewalDistributionService(db)
    result = await service.auto_approve_passed_reviews(
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
    )
    return {
        "success": True,
        "message": "續領自動分發完成",
        "data": result,
    }


@router.get("/distribution-result")
async def get_renewal_distribution_result(
    scholarship_type_id: int,
    academic_year: int,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Return renewal distribution grouped by (sub_type, renewal_year).

    Admin-only. For the given `(scholarship_type_id, academic_year)`:
      - Approved renewals are bucketed into `groups` keyed by
        `(sub_scholarship_type, renewal_year)`. Each application carries
        a `has_challenge` flag indicating whether a downstream challenge
        application (Application_C, `is_renewal=False` with
        `challenges_application_id` set) points at it.
      - Rejected renewals are returned in a flat `rejected` list.
      - A `summary` block totals approved + rejected counts.

    Other statuses (draft, under_review, etc.) are intentionally ignored;
    this endpoint reports a *finalised* distribution view.
    """
    # 1. Load all renewal applications for this (type, year).
    stmt = (
        select(Application)
        .options(joinedload(Application.student))
        .where(
            Application.scholarship_type_id == scholarship_type_id,
            Application.academic_year == academic_year,
            Application.is_renewal.is_(True),
        )
    )
    apps = (await db.execute(stmt)).scalars().unique().all()

    # 2. Pre-compute which renewals have a downstream challenge.
    #    Pass a guaranteed-empty sentinel (-1) when there are no renewals to
    #    keep the `IN ()` clause syntactically valid across dialects.
    renewal_ids = [a.id for a in apps]
    challenge_apps = (
        (await db.execute(select(Application).where(Application.challenges_application_id.in_(renewal_ids or [-1]))))
        .scalars()
        .all()
    )
    has_challenge_set = {ch.challenges_application_id for ch in challenge_apps}

    # 3. Group approved by (sub_type, renewal_year); collect rejected separately.
    grouped: dict[str, dict] = {}
    rejected: list[dict] = []
    for app_row in apps:
        if app_row.status == ApplicationStatus.approved:
            key = f"{app_row.sub_scholarship_type}_{app_row.renewal_year}"
            bucket = grouped.setdefault(
                key,
                {
                    "sub_type": app_row.sub_scholarship_type,
                    "renewal_year": app_row.renewal_year,
                    "applications": [],
                },
            )
            bucket["applications"].append(
                {
                    "id": app_row.id,
                    "app_id": app_row.app_id,
                    "student_name": app_row.student.name if app_row.student else None,
                    "previous_application_id": app_row.previous_application_id,
                    "has_challenge": app_row.id in has_challenge_set,
                }
            )
        elif app_row.status == ApplicationStatus.rejected:
            rejected.append(
                {
                    "id": app_row.id,
                    "student_name": app_row.student.name if app_row.student else None,
                }
            )

    approved_count = sum(len(g["applications"]) for g in grouped.values())
    return {
        "success": True,
        "message": "Renewal distribution result",
        "data": {
            "groups": list(grouped.values()),
            "rejected": rejected,
            "summary": {
                "approved": approved_count,
                "rejected": len(rejected),
            },
        },
    }


@router.get("/audit/renewal-violations")
async def audit_renewal_violations(
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin audit: list approved challenges whose renewal isn't cancelled_by_challenge.

    Implements the spec §12 invariant check. Empty `data` means the system
    is consistent. A non-empty list points at data drift that needs manual
    investigation — typically a renewal that wasn't transitioned during
    `execute_general_distribution`.

    Returns:
        ApiResponse with `data` = list of
        ``{challenge_id, renewal_id, actual_renewal_status}`` dicts.
    """
    service = RenewalAuditService(db)
    violations = await service.find_invariant_violations()
    return {
        "success": True,
        "message": f"Found {len(violations)} violations",
        "data": violations,
    }


# `ScholarshipType` is imported for FastAPI's introspection of the joined model
# in case future endpoint extensions need it; keep import to avoid lazy-import
# surprises during OpenAPI generation.
_ = ScholarshipType

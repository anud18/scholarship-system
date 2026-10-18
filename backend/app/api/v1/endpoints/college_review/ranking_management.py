"""
Ranking Management API Endpoints

Handles:
- Creating and retrieving rankings
- Updating ranking metadata and order
- Finalizing/unfinalizing rankings
- Deleting rankings
- Importing ranking data from Excel
"""

import logging
from typing import Any, Dict, List, Literal, Optional, Tuple
from urllib.parse import quote as _url_quote

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.college_mappings import get_college_name
from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.security import require_college, require_scholarship_manager
from app.db.deps import get_db
from app.models.audit_log import AuditAction, AuditLog
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.student import Academy, Department
from app.models.user import User, UserRole
from app.schemas.college_review import RankingImportItem, RankingOrderUpdate, RankingUpdate
from app.schemas.response import ApiResponse
from app.services.college_ranking_export_service import (
    CollegeRankingExportService,
    ExportRow,
)
from app.services.college_review_service import (
    CollegeReviewError,
    CollegeReviewService,
    InvalidRankingDataError,
    RankingModificationError,
    RankingNotFoundError,
    RankingScopeConflictError,
)
from app.services.department_names import load_department_names
from app.services.email_automation_service import email_automation_service
from app.services.review_service import ReviewService
from app.services.professor_review_export import load_professor_review_data

from app.utils.export_download import XLSX_MEDIA_TYPE
from ._helpers import (
    _check_academic_year_permission,
    _check_scholarship_permission,
    assert_can_manage_ranking,
    load_export_aux_data,
    normalize_semester_value,
)

logger = logging.getLogger(__name__)

# Appended to rank-sequence errors so the message states the rule that was
# broken, not just the symptom. Mirrors the frontend (parse-ranking-sheet.ts).
RANK_SEQUENCE_RULE = "，排名數字不可重複、不可跳號"

router = APIRouter()


@router.get("/rankings")
async def get_rankings(
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Get all rankings for the current user or all if admin"""

    try:
        # Build base query
        stmt = select(CollegeRanking)

        # Apply filters
        if current_user.role not in [UserRole.admin, UserRole.super_admin]:
            # College reviewers see their college's rankings. Scope by college_code (not
            # created_by) so every reviewer of the same college shares the college's
            # rankings (drafts and the finalized one) and different colleges stay
            # isolated — matches create_ranking's scoping (issue #1034).
            stmt = stmt.where(CollegeRanking.college_code == current_user.college_code)

        if academic_year:
            stmt = stmt.where(CollegeRanking.academic_year == academic_year)
        if semester:
            semester_str = str(semester).strip()
            semester_lower = semester_str.lower()
            if semester_lower.startswith("semester."):
                semester_lower = semester_lower.split(".", 1)[1]

            if semester_lower in {"yearly"}:
                stmt = stmt.where(or_(CollegeRanking.semester.is_(None), CollegeRanking.semester == "yearly"))
            else:
                stmt = stmt.where(CollegeRanking.semester == semester_lower)

        # Execute query (stable order: several drafts may share a period)
        result = await db.execute(stmt.order_by(CollegeRanking.id))
        rankings = result.scalars().all()
        settled_ids, roster_referenced_ids = await CollegeReviewService(db).load_ranking_protection(
            ranking.id for ranking in rankings
        )

        # Preload scholarship configurations per (type, year, semester) to avoid N+1 queries
        config_cache: Dict[Tuple[int, int, Optional[str]], Optional[ScholarshipConfiguration]] = {}
        user_college_code = current_user.college_code

        async def get_config_for_ranking(ranking: CollegeRanking) -> Optional[ScholarshipConfiguration]:
            normalized_semester = normalize_semester_value(ranking.semester)
            cache_key = (ranking.scholarship_type_id, ranking.academic_year, normalized_semester)
            if cache_key in config_cache:
                return config_cache[cache_key]

            config_stmt = select(ScholarshipConfiguration).where(
                and_(
                    ScholarshipConfiguration.scholarship_type_id == ranking.scholarship_type_id,
                    ScholarshipConfiguration.academic_year == ranking.academic_year,
                    ScholarshipConfiguration.is_active.is_(True),
                )
            )

            if normalized_semester:
                config_stmt = config_stmt.where(ScholarshipConfiguration.semester == normalized_semester)
            else:
                config_stmt = config_stmt.where(ScholarshipConfiguration.semester.is_(None))

            config_result = await db.execute(config_stmt)
            config_cache[cache_key] = config_result.scalar_one_or_none()
            return config_cache[cache_key]

        # Format response
        rankings_data = []
        for ranking in rankings:
            college_quota: Optional[int] = None
            # Always load the config so we can surface college_review_end on
            # each ranking item — this lets the frontend display the deadline
            # banner before any specific ranking has been selected.
            config = await get_config_for_ranking(ranking)

            if user_college_code:
                if config and config.has_college_quota and config.quotas:
                    if ranking.sub_type_code == "default":
                        # Sum all quotas for this college across sub-types
                        college_quota = config.get_college_total_quota(user_college_code) or None
                    else:
                        quota_value: Optional[int] = None
                        possible_keys: List[str] = []
                        if ranking.sub_type_code:
                            possible_keys.extend(
                                [
                                    ranking.sub_type_code,
                                    ranking.sub_type_code.lower(),
                                    ranking.sub_type_code.upper(),
                                ]
                            )

                        # Preserve order while de-duplicating
                        seen_keys = set()
                        ordered_keys = []
                        for key in possible_keys:
                            if key not in seen_keys:
                                seen_keys.add(key)
                                ordered_keys.append(key)

                        for key in ordered_keys:
                            sub_quota_map = config.quotas.get(key)
                            if isinstance(sub_quota_map, dict) and user_college_code in sub_quota_map:
                                quota_value = sub_quota_map[user_college_code]
                                break

                        college_quota = quota_value if quota_value is not None else None

            normalized_ranking_semester = normalize_semester_value(ranking.semester)

            rankings_data.append(
                {
                    "id": ranking.id,
                    "ranking_name": ranking.ranking_name,
                    "scholarship_type_id": ranking.scholarship_type_id,
                    "sub_type_code": ranking.sub_type_code,
                    "college_code": ranking.college_code,
                    "academic_year": ranking.academic_year,
                    "semester": normalized_ranking_semester,
                    "total_applications": ranking.total_applications,
                    "total_quota": ranking.total_quota,
                    "college_quota": college_quota,
                    "allocated_count": ranking.allocated_count,
                    "is_finalized": ranking.is_finalized,
                    "allow_college_view_distribution": bool(config and config.allow_college_view_distribution),
                    "ranking_status": ranking.ranking_status,
                    "distribution_executed": ranking.distribution_executed,
                    # Distributed or holding allocation results: blocks creating
                    # another ranking in the scope and is never deleted.
                    "is_settled": ranking.id in settled_ids,
                    # Used by a 造冊 roster: never deleted.
                    "is_roster_referenced": ranking.id in roster_referenced_ids,
                    "created_at": ranking.created_at.isoformat(),
                    "finalized_at": ranking.finalized_at.isoformat() if ranking.finalized_at else None,
                    "college_review_end": (
                        config.college_review_end.isoformat() if config and config.college_review_end else None
                    ),
                }
            )

        return ApiResponse(
            success=True, message=f"Retrieved {len(rankings_data)} rankings successfully", data=rankings_data
        )

    except ValueError as e:
        logger.warning("Invalid query parameters for rankings", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid query parameters") from e
    except CollegeReviewError as e:
        logger.exception("College review error retrieving rankings")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except Exception as e:
        logger.exception("Unexpected error retrieving rankings")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve rankings"
        ) from e


@router.post("/rankings")
async def create_ranking(
    scholarship_type_id: int = Body(..., description="Scholarship type ID"),
    sub_type_code: str = Body(..., description="Sub-type code"),
    academic_year: int = Body(..., description="Academic year"),
    semester: Optional[str] = Body(None, description="Semester"),
    ranking_name: Optional[str] = Body(None, description="Custom ranking name"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Create a NEW draft ranking of the caller's college for a scholarship sub-type and period.

    A college may keep several draft rankings per (scholarship type, sub-type,
    academic year, semester) and compare them; 確認排名 (finalize) keeps one and
    deletes the others. Returns HTTP 409 while the caller's scope holds a finalized
    ranking (unlock it first) or a distributed one (sync it instead).
    """

    try:
        service = CollegeReviewService(db)
        # #63: block ranking writes once college-review deadline has passed
        # (admins / super_admins bypass).
        await service.assert_ranking_within_deadline(scholarship_type_id, academic_year, semester, current_user)

        ranking = await service.create_ranking(
            scholarship_type_id=scholarship_type_id,
            sub_type_code=sub_type_code,
            academic_year=academic_year,
            semester=semester,
            creator_id=current_user.id,
            ranking_name=ranking_name,
        )
        # Commit before building the response so the row is visible to any
        # read-after-write query the caller makes immediately after receiving
        # the HTTP 200 (e.g. direct pool.query in the E2E test suite — see
        # issue #199). get_db will commit again on context exit but that is a
        # no-op on an already-clean session. Mirrors the fix in PR #200.
        await db.commit()

        return ApiResponse(
            success=True,
            message="Ranking created successfully",
            data={
                "id": ranking.id,
                "ranking_name": ranking.ranking_name,
                "scholarship_type_id": ranking.scholarship_type_id,
                "total_applications": ranking.total_applications,
                "total_quota": ranking.total_quota,
                "sub_type_code": ranking.sub_type_code,
                "academic_year": ranking.academic_year,
                "semester": normalize_semester_value(ranking.semester),
                "is_finalized": bool(ranking.is_finalized),
                "created_at": ranking.created_at.isoformat(),
            },
        )

    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RankingScopeConflictError as e:
        logger.info("Ranking creation refused by its scope: %s", e)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except ValueError as e:
        logger.warning("Invalid ranking creation data", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid ranking data") from e
    except CollegeReviewError as e:
        logger.exception("College review error creating ranking")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except Exception as e:
        logger.exception("Unexpected error creating ranking")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create ranking") from e


@router.get("/rankings/{ranking_id}")
async def get_ranking(
    request: Request, ranking_id: int, current_user: User = Depends(require_college), db: AsyncSession = Depends(get_db)
):
    """Get a ranking with all its items"""

    try:
        service = CollegeReviewService(db)
        ranking = await service.get_ranking(ranking_id)

        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # College-scope the detail read: a reviewer may only see their own college's
        # ranking (admins may see any). Prevents cross-college access to student PII /
        # rejection reasons via ranking-id enumeration.
        assert_can_manage_ranking(ranking, current_user)

        # Build sub-type metadata for UI display
        sub_type_metadata_map: Dict[str, Dict[str, str]] = {}
        if ranking.scholarship_type and getattr(ranking.scholarship_type, "sub_type_configs", None):
            for config in ranking.scholarship_type.sub_type_configs:
                if not config.sub_type_code:
                    continue
                label = config.name or config.sub_type_code
                label_en = config.name_en or label
                sub_type_metadata_map[config.sub_type_code] = {
                    "code": config.sub_type_code,
                    "label": label,
                    "label_en": label_en,
                }

        if ranking.sub_type_code and ranking.sub_type_code not in sub_type_metadata_map:
            fallback_label = ranking.sub_type_code
            sub_type_metadata_map[ranking.sub_type_code] = {
                "code": ranking.sub_type_code,
                "label": fallback_label,
                "label_en": fallback_label,
            }

        def _meta_for_sub_type(code: Optional[str]) -> Dict[str, str]:
            if not code:
                code = "unallocated"
            if code in sub_type_metadata_map:
                return sub_type_metadata_map[code]
            sub_type_metadata_map[code] = {
                "code": code,
                "label": code,
                "label_en": code,
            }
            return sub_type_metadata_map[code]

        # Calculate college-specific quota from matrix
        college_quota: Optional[int] = None
        college_quota_breakdown: Dict[str, Dict[str, Any]] = {}
        user_college_code = current_user.college_code

        normalized_ranking_semester = normalize_semester_value(ranking.semester)

        # Fetch scholarship config once — used for quota calculation AND deadline banner (#91)
        _cfg_stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == ranking.scholarship_type_id,
                ScholarshipConfiguration.academic_year == ranking.academic_year,
                ScholarshipConfiguration.is_active.is_(True),
            )
        )
        if normalized_ranking_semester:
            _cfg_stmt = _cfg_stmt.where(ScholarshipConfiguration.semester == normalized_ranking_semester)
        else:
            _cfg_stmt = _cfg_stmt.where(ScholarshipConfiguration.semester.is_(None))
        _cfg_result = await db.execute(_cfg_stmt)
        config = _cfg_result.scalar_one_or_none()

        if user_college_code:
            if config and config.has_college_quota and isinstance(config.quotas, dict):

                def _record_quota(sub_type_code: str, quota_value: Any) -> None:
                    meta = _meta_for_sub_type(sub_type_code)
                    try:
                        numeric_quota = int(quota_value)
                    except (TypeError, ValueError):
                        try:
                            numeric_quota = int(float(quota_value))
                        except (TypeError, ValueError):
                            numeric_quota = 0
                    college_quota_breakdown[sub_type_code] = {
                        "code": meta["code"],
                        "label": meta["label"],
                        "label_en": meta["label_en"],
                        "quota": numeric_quota,
                    }
                    return numeric_quota

                if ranking.sub_type_code == "default":
                    subtotal = 0
                    for sub_type_code, college_quotas in config.quotas.items():
                        if not isinstance(college_quotas, dict):
                            continue
                        if user_college_code not in college_quotas:
                            continue
                        subtotal += _record_quota(sub_type_code, college_quotas[user_college_code])
                    if subtotal > 0:
                        college_quota = subtotal
                else:
                    possible_keys: List[str] = []
                    if ranking.sub_type_code:
                        possible_keys.extend(
                            [
                                ranking.sub_type_code,
                                ranking.sub_type_code.lower(),
                                ranking.sub_type_code.upper(),
                            ]
                        )

                    seen_keys = set()
                    ordered_keys = []
                    for key in possible_keys:
                        if key not in seen_keys:
                            seen_keys.add(key)
                            ordered_keys.append(key)

                    for key in ordered_keys:
                        sub_quota_map = config.quotas.get(key)
                        if isinstance(sub_quota_map, dict) and user_college_code in sub_quota_map:
                            numeric_quota = _record_quota(ranking.sub_type_code, sub_quota_map[user_college_code])
                            college_quota = numeric_quota
                            break

        # Collect all unique department codes for batch query
        department_codes = set()
        for item in ranking.items:
            if item.application and item.application.student_data:
                student_data = item.application.student_data
                if isinstance(student_data, dict):
                    dept_code = student_data.get("std_depno") or student_data.get("dept_code")
                    if dept_code:
                        department_codes.add(dept_code)

        # Query all departments with academy relationship to avoid N+1 queries
        department_map = {}
        if department_codes:
            dept_stmt = (
                select(Department)
                .options(selectinload(Department.academy))
                .where(Department.code.in_(department_codes))
            )
            dept_result = await db.execute(dept_stmt)
            departments = dept_result.scalars().all()

            # Build map with department name and academy information
            department_map = {
                dept.code: {
                    "name": dept.name,
                    "academy_code": dept.academy_code,
                    "academy_name": dept.academy.name if dept.academy else None,
                }
                for dept in departments
            }

        # Load review status for every application in ONE query. This used to be
        # one round-trip per ranking item, which made large rankings slow to open.
        review_service = ReviewService(db)
        review_status_cache = await review_service.get_subtype_cumulative_status_bulk(
            item.application_id for item in ranking.items if item.application_id
        )

        logger.info(f"Loaded review status for {len(review_status_cache)} applications in ranking {ranking_id}")

        # Format ranking items
        items = []
        for item in sorted(ranking.items, key=lambda x: x.rank_position):
            # Skip deleted applications
            if item.application and (item.application.status == "deleted" or item.application.deleted_at is not None):
                continue

            student_data = (
                item.application.student_data
                if item.application.student_data and isinstance(item.application.student_data, dict)
                else {}
            )
            student_name_raw = (
                student_data.get("std_cname")
                or student_data.get("std_ename")
                or student_data.get("name")
                or student_data.get("student_name")
            )
            student_name = str(student_name_raw) if student_name_raw else "學生"

            student_id_raw = (
                student_data.get("std_stdcode") or student_data.get("nycu_id") or student_data.get("student_id")
            )
            student_id = str(student_id_raw) if student_id_raw is not None else None

            # Extract department and academy information
            department_code = student_data.get("dept_code") or student_data.get("std_depno") or "N/A"

            # Get department info from database
            dept_info = department_map.get(department_code) if department_code and department_code != "N/A" else None

            # Extract department name
            department_name = student_data.get("dep_depname") or (dept_info["name"] if dept_info else None)

            # Extract academy code and name from Department.academy relationship
            academy_code = dept_info["academy_code"] if dept_info else None
            academy_name = student_data.get("aca_cname") or (dept_info["academy_name"] if dept_info else None)

            items.append(
                {
                    "id": item.id,
                    "rank_position": item.rank_position,
                    "display_rank": len(items) + 1,  # Dynamic display rank (skips deleted applications)
                    "is_allocated": item.is_allocated,
                    "status": item.status,
                    "college_rejected": item.college_rejected,
                    "student_name": student_name,
                    "student_id": student_id,
                    # Lightweight DTO with minimal student exposure
                    "application": {
                        "id": item.application.id,
                        "app_id": item.application.app_id,
                        "status": item.application.status,
                        "scholarship_type_id": item.application.scholarship_type_id,
                        "sub_type": item.application.sub_scholarship_type,
                        "is_renewal": item.application.is_renewal,
                        "renewal_year": item.application.renewal_year,
                        # Eligible sub-types that student applied for, with review status
                        "eligible_subtypes": (
                            [
                                {
                                    "code": subtype,
                                    "is_rejected": review_status_cache.get(item.application.id, {})
                                    .get(subtype, {})
                                    .get("status")
                                    == "rejected",
                                    "rejected_by": review_status_cache.get(item.application.id, {})
                                    .get(subtype, {})
                                    .get("rejected_by"),
                                    "rejection_reason": review_status_cache.get(item.application.id, {})
                                    .get(subtype, {})
                                    .get("comments"),
                                }
                                for subtype in (item.application.scholarship_subtype_list or [])
                            ]
                        ),
                        # #68: 國籍/身分 — expose only the two snapshot keys the
                        # ranking table reads, not the full SIS snapshot.
                        "student_data": {
                            "std_nation": student_data.get("std_nation") or student_data.get("nationality"),
                            "std_identity": (
                                student_data.get("std_identity")
                                if student_data.get("std_identity") is not None
                                else student_data.get("identity")
                            ),
                        },
                        # Minimal student info - only what's needed for ranking display
                        "student_info": {
                            "display_name": student_name,
                            "student_id": student_id,
                            "student_id_masked": (
                                f"{student_id[:3]}***" if student_id and isinstance(student_id, str) else "N/A"
                            ),
                            "dept_code": (
                                student_data.get("std_depno", "N/A")[:3]
                                if isinstance(student_data.get("std_depno"), str)
                                else "N/A"
                            ),
                            "term_count": student_data.get("term_count") or student_data.get("std_termcount"),
                        },
                        # Add academy and department information
                        "department_code": department_code,
                        "department_name": department_name,
                        "academy_code": academy_code,
                        "academy_name": academy_name,
                    },
                }
            )

        # Pending + stale come from ONE eligibility query (see compute_ranking_diff).
        diff = await service.compute_ranking_diff(ranking)

        return ApiResponse(
            success=True,
            message="Ranking retrieved successfully",
            data={
                "id": ranking.id,
                "ranking_name": ranking.ranking_name,
                "scholarship_type_id": ranking.scholarship_type_id,
                "sub_type_code": ranking.sub_type_code,
                "academic_year": ranking.academic_year,
                "semester": normalized_ranking_semester,
                "total_applications": len(items),
                "total_quota": ranking.total_quota,
                "college_quota": college_quota,
                "college_quota_breakdown": college_quota_breakdown,
                "allocated_count": ranking.allocated_count,
                "is_finalized": ranking.is_finalized,
                "allow_college_view_distribution": bool(config and config.allow_college_view_distribution),
                "ranking_status": ranking.ranking_status,
                "distribution_executed": ranking.distribution_executed,
                "sub_type_metadata": list(sub_type_metadata_map.values()),
                "items": items,
                # Drive the 同步申請名單 reminder: eligible applications not yet in
                # this ranking, and ranked ones no longer eligible (withdrawn /
                # deleted / sub-type, college or term changed). Both 0 once the
                # ranking is finalized AND distributed.
                "pending_application_count": len(diff.pending_application_ids),
                "stale_application_count": len(diff.stale_application_ids),
                "created_at": ranking.created_at.isoformat(),
                "college_review_end": (
                    config.college_review_end.isoformat() if config and config.college_review_end else None
                ),
            },
        )

    except HTTPException:
        raise
    except RankingNotFoundError as e:
        logger.warning("Ranking not found", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except CollegeReviewError as e:
        logger.exception("College review error retrieving ranking")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except Exception as e:
        logger.exception("Unexpected error retrieving ranking")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve ranking"
        ) from e


@router.put("/rankings/{ranking_id}")
async def update_ranking(
    ranking_id: int,
    ranking_update: RankingUpdate,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Update ranking metadata (name, etc.)"""

    try:
        # Get ranking. FOR UPDATE serialises with a concurrent finalize, which may
        # delete this draft (missing ⇒ 404) or lock it.
        stmt = select(CollegeRanking).where(CollegeRanking.id == ranking_id).with_for_update()
        result = await db.execute(stmt)
        ranking = result.scalar_one_or_none()

        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Check permissions - the owning college's reviewers or an admin can update
        assert_can_manage_ranking(ranking, current_user)

        # Check if ranking is finalized - cannot update finalized rankings
        if ranking.is_finalized:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot update finalized ranking")

        # Update ranking name
        ranking.ranking_name = ranking_update.ranking_name
        await db.commit()
        await db.refresh(ranking)

        return ApiResponse(
            success=True,
            message="Ranking updated successfully",
            data={
                "id": ranking.id,
                "ranking_name": ranking.ranking_name,
                "updated_at": ranking.updated_at.isoformat(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error updating ranking")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update ranking") from e


@router.put("/rankings/{ranking_id}/order")
async def update_ranking_order(
    request: Request,
    ranking_id: int,
    new_order: List[RankingOrderUpdate],
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Update the ranking order of applications"""

    try:
        service = CollegeReviewService(db)
        # #63: block once college-review deadline has passed (admins bypass).
        await service.assert_ranking_within_deadline_by_ranking(ranking_id, current_user)

        # Authorize: only the owning college's reviewers or an admin may reorder. This
        # write path previously had no ownership check, so any college reviewer could
        # reorder another college's ranking (and overwrite Application.final_ranking_position).
        ranking_row = (
            await db.execute(select(CollegeRanking).where(CollegeRanking.id == ranking_id))
        ).scalar_one_or_none()
        if not ranking_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")
        assert_can_manage_ranking(ranking_row, current_user)

        # G8 (#970): capture the prior order — rank overwrites previously left
        # no trace, so 「核配當時的名次」 could not be reconstructed.
        prior_rows = await db.execute(
            select(
                CollegeRankingItem.id,
                CollegeRankingItem.application_id,
                CollegeRankingItem.rank_position,
            ).where(CollegeRankingItem.ranking_id == ranking_id)
        )
        prior = prior_rows.all()
        old_order = {str(app_id): pos for _item_id, app_id, pos in prior}
        item_to_app = {item_id: app_id for item_id, app_id, _pos in prior}

        ranking = await service.update_ranking_order(
            ranking_id=ranking_id, new_order=[item.model_dump() for item in new_order]
        )

        db.add(
            AuditLog.create_log(
                user_id=current_user.id,
                action=AuditAction.update.value,
                resource_type="college_ranking",
                resource_id=str(ranking_id),
                description=f"ranking order updated ({len(new_order)} item(s))",
                old_values={"rank_positions": old_order},
                # RankingOrderUpdate carries item_id/position (NOT application_id/
                # rank_position) — reading the wrong keys here 500'd EVERY valid
                # reorder request since the G8 audit block landed. Key new_values by
                # application_id (via the prior-rows mapping) so old/new stay comparable.
                new_values={
                    "rank_positions": {
                        str(item_to_app.get(i["item_id"], f"item:{i['item_id']}")): i.get("position")
                        for i in (item.model_dump() for item in new_order)
                    }
                },
            )
        )
        await db.commit()

        return ApiResponse(
            success=True,
            message="Ranking order updated successfully",
            data={"id": ranking.id, "updated_at": ranking.updated_at.isoformat()},
        )

    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RankingNotFoundError as e:
        logger.warning("Ranking not found for order update", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RankingModificationError as e:
        logger.warning("Cannot modify ranking", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except InvalidRankingDataError as e:
        logger.warning("Invalid ranking data", exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except CollegeReviewError as e:
        logger.exception("College review error during ranking update")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error updating ranking order")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update ranking order"
        ) from e


@router.post("/rankings/{ranking_id}/sync")
async def sync_ranking(
    ranking_id: int,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """同步申請名單: bring a non-finalized ranking in line with the current applications.

    Eligible applications not yet in the ranking are added (renewals after the last
    ranked renewal, others at the end but ahead of any trailing college-rejected 'N'
    rows) and ranked ones that are no longer eligible are removed; positions are
    renumbered 1..n. A ranking whose distribution was executed (unlocked for
    補充匯入) is append-only: new rows go after the last position. 409 while finalized.
    """

    try:
        ranking_check = (
            await db.execute(select(CollegeRanking).where(CollegeRanking.id == ranking_id))
        ).scalar_one_or_none()
        if not ranking_check:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Only the owning college's reviewers or an admin may sync.
        assert_can_manage_ranking(ranking_check, current_user)

        service = CollegeReviewService(db)
        # #63: block once college-review deadline has passed (admins bypass).
        await service.assert_ranking_within_deadline_by_ranking(ranking_id, current_user)

        result = await service.sync_ranking(ranking_id)
        added_ids = result.added_application_ids
        removed_ids = result.removed_application_ids

        new_rows = await db.execute(
            select(CollegeRankingItem.application_id, CollegeRankingItem.rank_position).where(
                CollegeRankingItem.ranking_id == ranking_id
            )
        )
        new_order = {str(app_id): pos for app_id, pos in new_rows.all()}

        db.add(
            AuditLog.create_log(
                user_id=current_user.id,
                action=AuditAction.update.value,
                resource_type="college_ranking",
                resource_id=str(ranking_id),
                description=f"ranking synced with application list (+{len(added_ids)} / -{len(removed_ids)})",
                # G8 (#970): sync renumbers a draft, so keep the prior order reconstructable
                # (snapshot taken by the service under the ranking's row lock).
                old_values={"rank_positions": result.previous_rank_positions},
                new_values={
                    "added_application_ids": added_ids,
                    "removed_application_ids": removed_ids,
                    "rank_positions": new_order,
                },
            )
        )
        await db.commit()

        if added_ids or removed_ids:
            message = f"已加入 {len(added_ids)} 位新申請者、移除 {len(removed_ids)} 筆已不符合的申請"
        else:
            message = "排名已與申請名單一致"

        return ApiResponse(
            success=True,
            message=message,
            data={
                "id": result.ranking.id,
                "added_application_count": len(added_ids),
                "removed_application_count": len(removed_ids),
                "total_applications": result.ranking.total_applications,
            },
        )

    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RankingNotFoundError as e:
        logger.warning("Ranking not found for sync", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RankingModificationError as e:
        logger.warning("Cannot sync ranking", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except CollegeReviewError as e:
        logger.exception("College review error during ranking sync")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error syncing ranking")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to sync ranking") from e


async def _resolve_college_name(db: AsyncSession, college_code: Optional[str]) -> str:
    """Resolve a college code to its display name, academies table first.

    The static COLLEGE_MAPPINGS table lagged the real academy names for a long
    time, so the DB is the authority and the static map is only a fallback.
    """
    if not college_code:
        return ""

    result = await db.execute(select(Academy.name).where(Academy.code == college_code))
    name = result.scalar_one_or_none()
    if name:
        return name

    return get_college_name(college_code) or college_code


async def _notify_college_ranking_submitted(db: AsyncSession, ranking: CollegeRanking, finalizer: User) -> None:
    """Emit the college_review_submitted trigger for a just-finalized ranking."""
    scholarship_name = ""
    if ranking.scholarship_type_id:
        result = await db.execute(select(ScholarshipType.name).where(ScholarshipType.id == ranking.scholarship_type_id))
        scholarship_name = result.scalar_one_or_none() or ""

    await email_automation_service.trigger_college_ranking_submitted(
        db=db,
        ranking_data={
            "ranking_id": ranking.id,
            "college_code": ranking.college_code,
            "college_name": await _resolve_college_name(db, ranking.college_code),
            "ranking_name": ranking.ranking_name or f"排名 #{ranking.id}",
            "scholarship_type": scholarship_name,
            "scholarship_type_id": ranking.scholarship_type_id,
            "sub_type_code": ranking.sub_type_code or "",
            "academic_year": str(ranking.academic_year or ""),
            "semester": normalize_semester_value(ranking.semester) or "全學年",
            "total_applications": str(ranking.total_applications or 0),
            "finalized_by": finalizer.name or finalizer.email or "",
            "finalized_at": (ranking.finalized_at.strftime("%Y-%m-%d %H:%M") if ranking.finalized_at else ""),
        },
    )


@router.post("/rankings/{ranking_id}/finalize")
async def finalize_ranking(
    ranking_id: int,
    expected_sibling_ids: Optional[List[int]] = Body(
        None,
        embed=True,
        description=(
            "IDs of the other rankings in the scope the user confirmed deleting. When given, "
            "any other ranking in the scope refuses the lock with 409."
        ),
    ),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Finalize (lock) a ranking and delete the other rankings of its scope.

    Only the finalized ranking survives; while it stays locked no new ranking can be
    created. Returns 409 (nothing deleted) when another ranking of the scope is
    already finalized, was distributed or is used by a payment roster, or is not in
    `expected_sibling_ids` (created after the user's list was loaded).
    """

    try:
        from app.models.audit_log import AuditAction, AuditLog

        # Get ranking to check ownership
        stmt = select(CollegeRanking).where(CollegeRanking.id == ranking_id)
        result = await db.execute(stmt)
        ranking_check = result.scalar_one_or_none()

        if not ranking_check:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Check permissions - the owning college's reviewers or an admin can finalize
        assert_can_manage_ranking(ranking_check, current_user)

        # Capture old state for audit log
        old_values = {
            "is_finalized": ranking_check.is_finalized,
            "ranking_status": ranking_check.ranking_status,
        }

        service = CollegeReviewService(db)
        # #63: block once college-review deadline has passed (admins bypass).
        await service.assert_ranking_within_deadline_by_ranking(ranking_id, current_user)
        result = await service.finalize_ranking(
            ranking_id=ranking_id,
            finalizer_id=current_user.id,
            expected_sibling_ids=expected_sibling_ids,
        )
        ranking = result.ranking
        deleted_ranking_ids = [deleted.id for deleted in result.deleted_rankings]

        # Log the finalize ranking operation
        new_values = {
            "is_finalized": ranking.is_finalized,
            "ranking_status": ranking.ranking_status,
            "finalized_at": ranking.finalized_at.isoformat() if ranking.finalized_at else None,
            "deleted_ranking_ids": deleted_ranking_ids,
        }

        # Extract request metadata
        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None

        # One delete_ranking row per superseded ranking, carrying its final order
        # (G8 #970: a deleted ranking's order must stay reconstructable).
        for deleted in result.deleted_rankings:
            db.add(
                AuditLog.create_log(
                    user_id=current_user.id,
                    action=AuditAction.delete_ranking.value,
                    resource_type="ranking",
                    resource_id=str(deleted.id),
                    description=(
                        f"Deleted ranking: {deleted.ranking_name} (superseded when ranking {ranking.id} was finalized)"
                    ),
                    old_values={
                        "ranking_name": deleted.ranking_name,
                        "total_applications": deleted.total_applications,
                        "rank_positions": deleted.rank_positions,
                    },
                    ip_address=ip_address,
                    user_agent=user_agent,
                    status="success",
                )
            )

        audit_log = AuditLog.create_log(
            user_id=current_user.id,
            action=AuditAction.finalize_ranking.value,
            resource_type="ranking",
            resource_id=str(ranking.id),
            description=f"Finalized ranking: {ranking.ranking_name}",
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
            status="success",
        )
        db.add(audit_log)
        await db.commit()

        # Notify the owning college that its ranking has been sent. Wrapped so a
        # mail failure can never turn a successful finalize into a 500.
        try:
            await _notify_college_ranking_submitted(db, ranking, current_user)
        except Exception:
            logger.exception("Failed to trigger college ranking submitted email for ranking %s", ranking.id)

        return ApiResponse(
            success=True,
            message="Ranking finalized successfully",
            data={
                "id": ranking.id,
                "is_finalized": ranking.is_finalized,
                "finalized_at": ranking.finalized_at.isoformat(),
                "ranking_status": ranking.ranking_status,
                "deleted_ranking_ids": deleted_ranking_ids,
                "deleted_ranking_count": len(deleted_ranking_ids),
            },
        )

    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RankingNotFoundError as e:
        logger.warning("Ranking not found for finalization", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RankingModificationError as e:
        logger.warning("Cannot finalize ranking", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except RankingScopeConflictError as e:
        logger.warning("Finalize refused by the ranking scope", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except IntegrityError as e:
        # Defensive: the partial unique index (another ranking of the scope got
        # locked concurrently). The service's scope lock normally prevents it.
        logger.warning("Finalize hit a constraint conflict for ranking %s", ranking_id, exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此學年度／學期已有其他鎖定的排名，請重新整理後再試",
        ) from e
    except CollegeReviewError as e:
        logger.exception("College review error during finalization")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error finalizing ranking")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to finalize ranking"
        ) from e


@router.post("/rankings/{ranking_id}/unfinalize")
async def unfinalize_ranking(
    ranking_id: int,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Unfinalize a ranking (makes it editable again)"""

    try:
        from app.models.audit_log import AuditAction, AuditLog

        # Get ranking to check ownership
        stmt = select(CollegeRanking).where(CollegeRanking.id == ranking_id)
        result = await db.execute(stmt)
        ranking_check = result.scalar_one_or_none()

        if not ranking_check:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Check permissions - the owning college's reviewers or an admin can unfinalize
        assert_can_manage_ranking(ranking_check, current_user)

        # Capture old state for audit log
        old_values = {
            "is_finalized": ranking_check.is_finalized,
            "ranking_status": ranking_check.ranking_status,
        }

        service = CollegeReviewService(db)
        # #63: block once college-review deadline has passed (admins bypass).
        await service.assert_ranking_within_deadline_by_ranking(ranking_id, current_user)
        ranking = await service.unfinalize_ranking(ranking_id=ranking_id)

        # Log the unfinalize ranking operation
        new_values = {
            "is_finalized": ranking.is_finalized,
            "ranking_status": ranking.ranking_status,
        }

        # Extract request metadata
        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None

        audit_log = AuditLog.create_log(
            user_id=current_user.id,
            action=AuditAction.unfinalize_ranking.value,
            resource_type="ranking",
            resource_id=str(ranking.id),
            description=f"Unfinalized ranking: {ranking.ranking_name}",
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
            status="success",
        )
        db.add(audit_log)
        await db.commit()

        return ApiResponse(
            success=True,
            message="Ranking unfinalized successfully",
            data={
                "id": ranking.id,
                "is_finalized": ranking.is_finalized,
                "ranking_status": ranking.ranking_status,
            },
        )

    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RankingNotFoundError as e:
        logger.warning("Ranking not found for unfinalization", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RankingModificationError as e:
        logger.warning("Cannot unfinalize ranking", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except CollegeReviewError as e:
        logger.exception("College review error during unfinalization")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unexpected error unfinalizing ranking")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to unfinalize ranking"
        ) from e


@router.delete("/rankings/{ranking_id}")
async def delete_ranking(
    ranking_id: int,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Delete a draft ranking

    The owning college's reviewers or an admin can delete a ranking. Finalized
    rankings must be unlocked first (409); rankings whose distribution was executed
    or that a payment roster uses are never deleted (409).
    """

    try:
        from app.models.audit_log import AuditAction, AuditLog

        # Get ranking
        stmt = select(CollegeRanking).where(CollegeRanking.id == ranking_id)
        result = await db.execute(stmt)
        ranking = result.scalar_one_or_none()

        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Check permissions - the owning college's reviewers or an admin can delete
        assert_can_manage_ranking(ranking, current_user)

        # #63: deleting is a ranking write too — create is deadline-gated, so a
        # post-deadline delete could strand the college without the draft it needs.
        service = CollegeReviewService(db)
        await service.assert_ranking_within_deadline_by_ranking(ranking_id, current_user)

        # Capture ranking information for audit log before deletion
        old_values = {
            "ranking_name": ranking.ranking_name,
            "scholarship_type_id": ranking.scholarship_type_id,
            "sub_type_code": ranking.sub_type_code,
            "academic_year": ranking.academic_year,
            "semester": ranking.semester,
            "total_applications": ranking.total_applications,
            "is_finalized": ranking.is_finalized,
            "ranking_status": ranking.ranking_status,
        }

        # The service re-checks under the scope lock: finalized ⇒ 409, settled or
        # roster-referenced ⇒ 409; items are deleted before the ranking row.
        deleted = await service.delete_ranking(ranking_id)
        old_values["rank_positions"] = deleted.rank_positions

        # Log the delete ranking operation before committing
        ip_address = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None

        audit_log = AuditLog.create_log(
            user_id=current_user.id,
            action=AuditAction.delete_ranking.value,
            resource_type="ranking",
            resource_id=str(ranking_id),
            description=f"Deleted ranking: {deleted.ranking_name}",
            old_values=old_values,
            ip_address=ip_address,
            user_agent=user_agent,
            status="success",
        )
        db.add(audit_log)
        await db.commit()

        return ApiResponse(
            success=True,
            message=f"Ranking '{deleted.ranking_name}' deleted successfully",
            data={"ranking_id": ranking_id},
        )

    except AuthorizationError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RankingNotFoundError as e:
        logger.warning("Ranking not found for deletion", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except RankingModificationError as e:
        logger.warning("Cannot delete finalized ranking", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except RankingScopeConflictError as e:
        logger.warning("Deletion refused for a settled or roster-referenced ranking", exc_info=True)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except IntegrityError as e:
        # Defensive: a payment roster FK. The service's FOR UPDATE row lock makes a
        # concurrent roster insert wait, so this should not fire after the check.
        logger.warning("Delete hit a constraint conflict for ranking %s", ranking_id, exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="此排名已執行分發或已用於造冊，無法刪除"
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error deleting ranking {ranking_id}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete ranking") from e


@router.post("/rankings/{ranking_id}/import-excel")
async def import_ranking_from_excel(
    ranking_id: int,
    import_data: List[RankingImportItem],
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """
    Import ranking data parsed from the 學生資料彙整表 Excel.

    Takes a JSON body (List[RankingImportItem]); the frontend parses the workbook
    (學號 → student_id, 學生中文姓名 → student_name, 學院初審會議之學院排序 → rank_position).
    rank_position accepts positive integers (1-based, consecutive, no duplicates) or "N" (rejected).
    Student IDs must exactly match the ranking's application set.
    """
    try:
        logger.info(f"User {current_user.id} importing {len(import_data)} rankings for ranking_id={ranking_id}")

        # Load ranking with items. FOR UPDATE serialises with a concurrent finalize,
        # which may delete this draft (missing ⇒ 404) or lock it.
        stmt = (
            select(CollegeRanking)
            .options(selectinload(CollegeRanking.items).selectinload(CollegeRankingItem.application))
            .where(CollegeRanking.id == ranking_id)
            .with_for_update()
        )
        result = await db.execute(stmt)
        ranking = result.scalar_one_or_none()

        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        # Check permissions - the owning college's reviewers or an admin can import
        assert_can_manage_ranking(ranking, current_user)

        # #63 / #1081 finding H: block once the college-review deadline has passed
        # (admins bypass). import-excel was the one ranking-mutation path missing
        # this guard that update_ranking_order / bulk-reject / reject all apply,
        # so a college user could reorder ranks or flip college_rejected on a
        # non-finalized ranking after the deadline.
        service = CollegeReviewService(db)
        await service.assert_ranking_within_deadline_by_ranking(ranking_id, current_user)

        if ranking.is_finalized:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot modify finalized ranking")

        # --- Validation ---
        errors = []

        # 1. Check for duplicate student IDs in import data
        seen_student_ids: set = set()
        duplicate_student_ids: list = []
        for item in import_data:
            if item.student_id in seen_student_ids:
                duplicate_student_ids.append(item.student_id)
            seen_student_ids.add(item.student_id)
        if duplicate_student_ids:
            errors.append(f"匯入資料中學號重複：{', '.join(sorted(set(duplicate_student_ids)))}")

        # 2. Collect ranking system student IDs
        system_student_ids = set()
        student_id_to_item = {}
        for rank_item in ranking.items:
            app = rank_item.application
            if not app or not app.student_data:
                continue
            sid = app.student_data.get("std_stdcode") or app.student_data.get("student_id")
            if sid:
                system_student_ids.add(sid)
                student_id_to_item[sid] = rank_item

        # 3. Strict student matching
        import_student_ids = seen_student_ids
        extra_ids = import_student_ids - system_student_ids
        missing_ids = system_student_ids - import_student_ids
        if extra_ids:
            errors.append(f"以下學號不在申請清單中：{', '.join(sorted(extra_ids))}")
        if missing_ids:
            errors.append(f"以下學號未包含在匯入檔案中：{', '.join(sorted(missing_ids))}")

        # 4. Validate rank sequence
        integer_ranks = []
        for item in import_data:
            if isinstance(item.rank_position, int):
                integer_ranks.append(item.rank_position)

        # Check duplicates
        rank_counts: Dict[int, int] = {}
        for r in integer_ranks:
            rank_counts[r] = rank_counts.get(r, 0) + 1
        duplicates = [str(r) for r, count in sorted(rank_counts.items()) if count > 1]
        if duplicates:
            errors.append(f"排名重複：{', '.join(duplicates)}{RANK_SEQUENCE_RULE}")

        # Check consecutive from 1
        if integer_ranks and not duplicates:
            expected = set(range(1, len(integer_ranks) + 1))
            actual = set(integer_ranks)
            missing_ranks = expected - actual
            if missing_ranks:
                errors.append(
                    f"排名不連續：缺少第 {', '.join(str(r) for r in sorted(missing_ranks))} 名{RANK_SEQUENCE_RULE}"
                )

        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="\n".join(errors),
            )

        # --- Apply updates ---
        updated_count = 0
        rejected_count = 0
        num_ranked = len(integer_ranks)

        import_map = {item.student_id: item for item in import_data}

        # Track rejected index for assigning positions after ranked students.
        # college_rejected=True is the college-level "N" marker. status stays
        # 'ranked' so admin retains ability to allocate.
        rejected_index = 0
        # G8 (#970): snapshot prior state — the import overwrites ranks and
        # college_rejected flags in place.
        prior_ranks = {
            sid: {"rank_position": ri.rank_position, "college_rejected": ri.college_rejected}
            for sid, ri in student_id_to_item.items()
        }
        for sid, rank_item in student_id_to_item.items():
            if sid not in import_map:
                continue
            import_item = import_map[sid]
            if import_item.rank_position == "N":
                rejected_index += 1
                rank_item.rank_position = num_ranked + rejected_index
                rank_item.status = "ranked"
                rank_item.college_rejected = True
                rejected_count += 1
            else:
                rank_item.rank_position = import_item.rank_position
                rank_item.status = "ranked"
                rank_item.college_rejected = False
            updated_count += 1

        ranking.total_applications = len(ranking.items)

        db.add(
            AuditLog.create_log(
                user_id=current_user.id,
                action=AuditAction.import_.value,
                resource_type="college_ranking",
                resource_id=str(ranking_id),
                description=(f"ranking import-excel: {updated_count} updated, {rejected_count} rejected (N)"),
                old_values={"rank_positions": prior_ranks},
                new_values={
                    "rank_positions": {
                        sid: {
                            "rank_position": ri.rank_position,
                            "college_rejected": ri.college_rejected,
                        }
                        for sid, ri in student_id_to_item.items()
                    }
                },
            )
        )
        await db.commit()

        return ApiResponse(
            success=True,
            message=f"排名匯入成功。更新 {updated_count} 筆（其中 {rejected_count} 筆拒絕）。",
            data={
                "ranking_id": ranking_id,
                "updated_count": updated_count,
                "rejected_count": rejected_count,
                "total_imported": len(import_data),
            },
        )

    except HTTPException:
        raise
    except AuthorizationError as e:
        # e.g. the #1081-H college-review deadline guard — must surface as 403,
        # not get swallowed into the generic 500 below.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except Exception as e:
        logger.exception("Error importing ranking data")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to import ranking data",
        ) from e


@router.get("/rankings/{ranking_id}/export-excel")
async def export_ranking_excel(
    ranking_id: int,
    request: Request,
    template: bool = Query(False, description="Render the rank column blank, as a fill-in import template"),
    format: Literal["xlsx", "pdf"] = Query("xlsx", description="Output format: xlsx (default) or pdf"),
    current_user: User = Depends(require_scholarship_manager),
    db: AsyncSession = Depends(get_db),
):
    """Generate the 學生資料彙整表 for a ranking, as Excel (default) or PDF.

    Auth: admin/super_admin OR a college user whose `college_code` matches the
    ranking's own `college_code` (authoritative per-college ownership).
    """

    # A PDF template makes no sense — a template is meant to be filled in and
    # re-imported, which only the xlsx path supports.
    if template and format == "pdf":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="範本僅支援 Excel 格式")

    # 1. Load ranking + items with applications
    stmt = (
        select(CollegeRanking)
        .where(CollegeRanking.id == ranking_id)
        .options(
            selectinload(CollegeRanking.items).selectinload(CollegeRankingItem.application),
            selectinload(CollegeRanking.scholarship_type).selectinload(ScholarshipType.sub_type_configs),
            selectinload(CollegeRanking.creator),
        )
    )
    ranking = (await db.execute(stmt)).scalar_one_or_none()
    if ranking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該學院排序資料")

    # 2. Authorization — admin OK; college users must own this ranking's college.
    # Use the authoritative ranking.college_code (immutable snapshot), not the live
    # creator.college_code, so authz stays correct if the creator is later reassigned.
    assert_can_manage_ranking(ranking, current_user)

    # 2b. Scholarship + academic-year permission checks (mirrors export_package.py pattern)
    if not await _check_scholarship_permission(current_user, ranking.scholarship_type_id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限存取此獎學金類型")
    if not await _check_academic_year_permission(current_user, ranking.academic_year, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限存取此學年度")

    # 3-5. Bulk-load aux data (dynamic fields, sub-type labels, accounts, advisors)
    items_sorted = sorted(ranking.items or [], key=lambda x: x.rank_position)
    apps_in_ranking = [item.application for item in items_sorted if item.application is not None]

    dynamic_fields, sub_type_labels, account_number_by_user, advisor_string_by_user = await load_export_aux_data(
        db,
        scholarship_type=ranking.scholarship_type,
        applications=apps_in_ranking,
    )
    professor_review = await load_professor_review_data(
        db, scholarship_type=ranking.scholarship_type, applications=apps_in_ranking
    )

    export_rows = [
        ExportRow(
            rank_position=None if template else item.rank_position,
            application=item.application,
            bank_account=account_number_by_user.get(item.application.user_id),
            advisor_names=advisor_string_by_user.get(item.application.user_id),
        )
        for item in items_sorted
        if item.application is not None
    ]

    # 6. Title + sheet name + filename
    scholarship_name = (
        ranking.scholarship_type.name if ranking.scholarship_type and ranking.scholarship_type.name else "獎學金"
    )
    title = f"{ranking.academic_year}學年度{scholarship_name}學生資料彙整表"
    sheet_name = f"{ranking.academic_year}學年"

    # College name in filename — use the current college user's college_code for
    # college users; admins fall back to "全校" if the creator has no code.
    college_label = (
        current_user.college_code
        if current_user.role not in (UserRole.admin, UserRole.super_admin)
        else (getattr(ranking.creator, "college_code", None) or "全校")
    )
    template_suffix = "_範本" if template else ""
    extension = format  # Literal["xlsx", "pdf"] — extension IS the format
    base_filename = (
        f"{ranking.academic_year}學年度{scholarship_name}學生資料彙整表"
        f"_{college_label}{template_suffix}.{extension}"
    )
    encoded = _url_quote(base_filename, safe="")

    # 7. Render the workbook (xlsx) or PDF — both share the same columns/rows.
    # The blank 學院用印 column is for stamping the finished ranking, so the
    # fill-in import template leaves it out.
    service = CollegeRankingExportService()
    include_college_seal = not template
    department_names = await load_department_names(db)
    if format == "pdf":
        payload = service.build_pdf(
            rows=export_rows,
            dynamic_fields=dynamic_fields,
            sub_type_labels=sub_type_labels,
            title=title,
            include_college_seal=include_college_seal,
            professor_review=professor_review,
            department_names=department_names,
        )
        media_type = "application/pdf"
    else:
        payload = service.build_workbook(
            rows=export_rows,
            dynamic_fields=dynamic_fields,
            sub_type_labels=sub_type_labels,
            title=title,
            sheet_name=sheet_name,
            include_college_seal=include_college_seal,
            professor_review=professor_review,
            department_names=department_names,
        )
        media_type = XLSX_MEDIA_TYPE

    # 8. Audit the PII access (issue #73): business confirmed Excel must show
    # the full std_pid, so every export that includes plaintext IDs is logged.
    exported_app_ids = [r.application.id for r in export_rows if r.application is not None]
    try:
        audit_log = AuditLog(
            user_id=current_user.id,
            action=AuditAction.pii_access.value,
            resource_type="college_ranking",
            resource_id=str(ranking_id),
            resource_name=base_filename,
            description=(
                f"匯出學生資料彙整表（{'範本，' if template else ''}含身分證字號明文）: "
                f"ranking_id={ranking_id}, records={len(exported_app_ids)}"
            ),
            ip_address=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
            request_method=request.method,
            request_url=str(request.url.path),
            status="success",
            meta_data={
                "ranking_id": ranking_id,
                "scholarship_type_id": (ranking.scholarship_type.id if ranking.scholarship_type else None),
                "academic_year": ranking.academic_year,
                "record_count": len(exported_app_ids),
                "application_ids": exported_app_ids,
                "pii_fields": ["std_pid"],
                "export_format": extension,
                "is_template": template,
            },
        )
        db.add(audit_log)
        await db.commit()
    except Exception:  # noqa: BLE001 — audit failure must not block download
        logger.exception("Failed to record pii_access audit log for ranking %s", ranking_id)
        await db.rollback()

    return StreamingResponse(
        iter([payload]),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "Content-Length": str(len(payload)),
        },
    )

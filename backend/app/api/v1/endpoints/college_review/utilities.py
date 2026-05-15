"""
Utilities & Statistics API Endpoints

Handles:
- College review statistics
- Available combinations for filtering
- Sub-type translations
- Managed college information
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import require_college
from app.db.deps import get_db
from app.models.application import Application
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipStatus, ScholarshipType
from app.models.student import Academy
from app.models.user import AdminScholarship, User
from app.schemas.response import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/statistics")
async def get_review_statistics(
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """College review statistics scoped to the caller's scholarship permissions.

    Aggregates reviewer-recommendation counts from the unified ApplicationReview
    + ApplicationReviewItem tables (CLAUDE.md §7: no scoring system, recommendation-only).

    Filters to scholarship_types this college user has permission for (via
    AdminScholarship). Returns per-scholarship totals plus a system-wide rollup.
    """
    # Scope: which scholarship_types this college user can see.
    permission_rows = await db.execute(
        select(AdminScholarship.scholarship_id).where(AdminScholarship.admin_id == current_user.id)
    )
    allowed_scholarship_ids = [row[0] for row in permission_rows.fetchall()]

    if not allowed_scholarship_ids:
        logger.warning(
            "College user %s (id=%s) has no scholarship permissions; returning empty statistics.",
            current_user.nycu_id,
            current_user.id,
        )
        return {
            "success": True,
            "message": "查詢成功",
            "data": {
                "per_scholarship": [],
                "totals": {
                    "applications": 0,
                    "reviews": 0,
                    "items_by_recommendation": {},
                    "reviews_by_recommendation": {},
                },
            },
        }

    # ─── Per-scholarship breakdown ────────────────────────────────────────
    # Applications count per scholarship_type (scoped to allowed types).
    app_count_rows = await db.execute(
        select(Application.scholarship_type_id, func.count(Application.id))
        .where(Application.scholarship_type_id.in_(allowed_scholarship_ids))
        .group_by(Application.scholarship_type_id)
    )
    apps_per_type: dict[int, int] = {row[0]: row[1] for row in app_count_rows.fetchall()}

    # Review-level recommendation counts (top-level recommendation derived per CLAUDE.md §7):
    # 'approve' | 'partial_approve' | 'reject'.
    review_rec_rows = await db.execute(
        select(
            Application.scholarship_type_id,
            ApplicationReview.recommendation,
            func.count(ApplicationReview.id),
        )
        .join(Application, ApplicationReview.application_id == Application.id)
        .where(Application.scholarship_type_id.in_(allowed_scholarship_ids))
        .group_by(Application.scholarship_type_id, ApplicationReview.recommendation)
    )
    reviews_per_type: dict[int, dict[str, int]] = {}
    for st_id, rec, count in review_rec_rows.fetchall():
        reviews_per_type.setdefault(st_id, {})[rec] = count

    # Item-level recommendation counts ('approve' | 'reject'), bucketed by sub_type_code.
    item_rec_rows = await db.execute(
        select(
            Application.scholarship_type_id,
            ApplicationReviewItem.sub_type_code,
            ApplicationReviewItem.recommendation,
            func.count(ApplicationReviewItem.id),
        )
        .join(ApplicationReview, ApplicationReviewItem.review_id == ApplicationReview.id)
        .join(Application, ApplicationReview.application_id == Application.id)
        .where(Application.scholarship_type_id.in_(allowed_scholarship_ids))
        .group_by(
            Application.scholarship_type_id,
            ApplicationReviewItem.sub_type_code,
            ApplicationReviewItem.recommendation,
        )
    )
    items_per_type: dict[int, dict[str, dict[str, int]]] = {}
    for st_id, sub_type, rec, count in item_rec_rows.fetchall():
        bucket = items_per_type.setdefault(st_id, {}).setdefault(sub_type, {})
        bucket[rec] = count

    # Pull scholarship-type names so the response is human-readable
    # without a second round trip from the caller.
    name_rows = await db.execute(
        select(ScholarshipType.id, ScholarshipType.code, ScholarshipType.name, ScholarshipType.name_en).where(
            ScholarshipType.id.in_(allowed_scholarship_ids)
        )
    )
    name_index = {row[0]: {"code": row[1], "name": row[2], "name_en": row[3] or row[2]} for row in name_rows.fetchall()}

    per_scholarship = []
    for st_id in allowed_scholarship_ids:
        info = name_index.get(st_id) or {"code": None, "name": None, "name_en": None}
        per_scholarship.append(
            {
                "scholarship_type_id": st_id,
                "code": info["code"],
                "name": info["name"],
                "name_en": info["name_en"],
                "applications": apps_per_type.get(st_id, 0),
                "reviews_by_recommendation": reviews_per_type.get(st_id, {}),
                "items_by_sub_type_and_recommendation": items_per_type.get(st_id, {}),
            }
        )

    # ─── System-wide totals (scoped to allowed types) ─────────────────────
    total_apps = sum(apps_per_type.values())
    total_reviews_by_rec: dict[str, int] = {}
    for buckets in reviews_per_type.values():
        for rec, count in buckets.items():
            total_reviews_by_rec[rec] = total_reviews_by_rec.get(rec, 0) + count

    total_items_by_rec: dict[str, int] = {}
    for sub_type_map in items_per_type.values():
        for rec_map in sub_type_map.values():
            for rec, count in rec_map.items():
                total_items_by_rec[rec] = total_items_by_rec.get(rec, 0) + count

    return {
        "success": True,
        "message": "查詢成功",
        "data": {
            "per_scholarship": per_scholarship,
            "totals": {
                "applications": total_apps,
                "reviews": sum(total_reviews_by_rec.values()),
                "reviews_by_recommendation": total_reviews_by_rec,
                "items_by_recommendation": total_items_by_rec,
            },
        },
    }


@router.get("/available-combinations")
async def get_available_combinations(current_user: User = Depends(require_college), db: AsyncSession = Depends(get_db)):
    """Get available combinations of scholarship types, academic years, and semesters from configurations"""

    try:
        logger.info(f"College user {current_user.nycu_id} (ID: {current_user.id}) requesting available combinations")

        # Get scholarship IDs that the user has permission to access
        permission_query = select(AdminScholarship.scholarship_id).where(AdminScholarship.admin_id == current_user.id)
        permission_result = await db.execute(permission_query)
        allowed_scholarship_ids = [row[0] for row in permission_result.fetchall()]

        logger.info(
            f"User {current_user.nycu_id} (ID: {current_user.id}) has permission for "
            f"{len(allowed_scholarship_ids)} scholarship(s): {allowed_scholarship_ids}"
        )

        # If user has specific permissions, filter by those
        # If user has no permissions set (empty list), show no scholarships
        if allowed_scholarship_ids:
            scholarship_query = select(ScholarshipType).where(
                ScholarshipType.status == "active", ScholarshipType.id.in_(allowed_scholarship_ids)
            )
        else:
            # No specific permissions - for college users without permissions, show no scholarships
            logger.warning(
                f"College user {current_user.nycu_id} (ID: {current_user.id}, College: {current_user.college_code}) "
                f"has no scholarship permissions set. Please contact administrator."
            )
            scholarship_query = select(ScholarshipType).where(ScholarshipType.id == -1)  # No results

        scholarship_result = await db.execute(scholarship_query)
        scholarship_types_objs = scholarship_result.scalars().all()

        scholarship_types = [
            {
                "id": st.id,
                "code": st.code,
                "name": st.name,
                "name_en": st.name_en if st.name_en else st.name,
            }
            for st in scholarship_types_objs
        ]
        logger.info(f"Returning {len(scholarship_types)} scholarship types for user {current_user.id}")

        # Query distinct academic years and semesters from active configurations
        # Filter by scholarship permissions
        if allowed_scholarship_ids:
            config_query = select(ScholarshipConfiguration).where(
                ScholarshipConfiguration.is_active,
                ScholarshipConfiguration.scholarship_type_id.in_(allowed_scholarship_ids),
            )
        else:
            config_query = select(ScholarshipConfiguration).where(ScholarshipConfiguration.id == -1)  # No results

        config_result = await db.execute(config_query)
        configs = config_result.scalars().all()

        # Collect unique academic years and semesters from configurations
        academic_years_set = set()
        semesters_set = set()
        has_yearly_scholarships = False

        for config in configs:
            if config.academic_year:
                academic_years_set.add(config.academic_year)

            if config.semester:
                # Semester is an enum, get its value
                raw_value = config.semester.value if hasattr(config.semester, "value") else str(config.semester)
                value_lower = raw_value.lower()
                if value_lower in {"yearly"}:
                    has_yearly_scholarships = True
                else:
                    semesters_set.add(value_lower)  # Keep lowercase to match database enum
            else:
                # No semester means yearly scholarship
                has_yearly_scholarships = True

        academic_years = sorted(list(academic_years_set))
        semester_strings = sorted(list(semesters_set))

        # Add a special "yearly" option if there are yearly scholarships (lowercase to match database)
        if has_yearly_scholarships:
            semester_strings.append("yearly")

        response_data = {
            "scholarship_types": scholarship_types,
            "academic_years": academic_years,
            "semesters": sorted(list(set(semester_strings))),  # Remove duplicates and sort
        }

        logger.info(
            f"Retrieved {len(scholarship_types)} scholarship types, {len(academic_years)} years, {len(semester_strings)} semesters"
        )

        return ApiResponse(success=True, message="Available combinations retrieved successfully", data=response_data)

    except Exception as e:
        logger.exception("Error retrieving available combinations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available combinations from database",
        ) from e


@router.get("/active-config")
async def get_active_config(
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    academic_year: int = Query(..., description="Academic year (民國)"),
    semester: Optional[str] = Query(None, description="Semester: first / second / yearly (or omit for yearly)"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Return active scholarship configuration metadata (currently the
    college-review deadline) for a specific (scholarship_type, year, semester).

    Used by the ranking page to surface the deadline banner before any
    ranking has been selected or created — the deadline is a property of
    the configuration, not of any individual ranking.

    Returns success=True with `data.college_review_end=None` when no config
    matches; the caller decides whether to display a banner.
    """
    try:
        # Yearly cycles store semester as either NULL or "yearly" — match both.
        sem_raw = (semester or "").strip().lower()
        if sem_raw.startswith("semester."):
            sem_raw = sem_raw.split(".", 1)[1]
        is_yearly = sem_raw in {"", "yearly"}

        conditions = [
            ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
            ScholarshipConfiguration.academic_year == academic_year,
            ScholarshipConfiguration.is_active.is_(True),
        ]
        if is_yearly:
            conditions.append(
                or_(
                    ScholarshipConfiguration.semester.is_(None),
                    ScholarshipConfiguration.semester == "yearly",
                )
            )
        else:
            conditions.append(ScholarshipConfiguration.semester == sem_raw)

        stmt = select(ScholarshipConfiguration).where(*conditions).limit(1)
        config = (await db.execute(stmt)).scalar_one_or_none()

        return ApiResponse(
            success=True,
            message="Active config retrieved",
            data={
                "scholarship_type_id": scholarship_type_id,
                "academic_year": academic_year,
                "semester": "yearly" if is_yearly else sem_raw,
                "college_review_end": (
                    config.college_review_end.isoformat() if config and config.college_review_end else None
                ),
                "college_review_start": (
                    config.college_review_start.isoformat() if config and config.college_review_start else None
                ),
            },
        )
    except Exception as e:
        logger.exception("Error retrieving active config")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve active scholarship configuration",
        ) from e


@router.get("/sub-type-translations")
async def get_sub_type_translations(
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """
    Get sub-type name translations for all supported languages from database

    Returns a dictionary with Chinese and English translations for all active sub-type configurations
    """

    try:
        # Get all active scholarship types with their sub-type configurations
        stmt = (
            select(ScholarshipType)
            .options(selectinload(ScholarshipType.sub_type_configs))
            .where(ScholarshipType.status == ScholarshipStatus.active.value)
        )
        result = await db.execute(stmt)
        scholarships = result.scalars().all()

        # Build translations from database
        translations = {"zh": {}, "en": {}}

        for scholarship in scholarships:
            # Get sub-type configurations for this scholarship
            for config in scholarship.sub_type_configs:
                if config.is_active:
                    # Add Chinese translation
                    translations["zh"][config.sub_type_code] = config.name
                    # Add English translation
                    translations["en"][config.sub_type_code] = config.name_en if config.name_en else config.name

        return ApiResponse(
            success=True,
            message="Sub-type translations retrieved successfully from database",
            data=translations,
        )

    except Exception as e:
        logger.exception("Error retrieving sub-type translations")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve sub-type translations: {str(e)}",
        ) from e


@router.get("/managed-college")
async def get_managed_college(
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the college that the current college user has management permission for

    Uses the college_code field directly from the User model, which should be set
    when college users are created or assigned to colleges.
    """

    try:
        logger.info(
            f"College user {current_user.nycu_id} (ID: {current_user.id}) requesting managed college information"
        )

        # Check if user has college_code set
        if not current_user.college_code:
            logger.warning(
                f"College user {current_user.nycu_id} (ID: {current_user.id}) has no college_code assigned. "
                f"Please contact administrator to assign a college."
            )
            return ApiResponse(success=True, message="No college assigned to this user", data=None)

        # Get college information from Academy table
        academy_stmt = select(Academy).where(Academy.code == current_user.college_code)
        academy_result = await db.execute(academy_stmt)
        academy = academy_result.scalar_one_or_none()

        if not academy:
            logger.error(
                f"College code '{current_user.college_code}' assigned to user {current_user.nycu_id} "
                f"(ID: {current_user.id}) not found in Academy table"
            )
            return ApiResponse(
                success=True, message=f"College information not found for code: {current_user.college_code}", data=None
            )

        # Get scholarship count for this user
        admin_scholarships_stmt = select(AdminScholarship).where(AdminScholarship.admin_id == current_user.id)
        admin_scholarships_result = await db.execute(admin_scholarships_stmt)
        admin_scholarships = admin_scholarships_result.scalars().all()

        # Return managed college information
        managed_college_data = {
            "code": academy.code,
            "name": academy.name,
            "name_en": academy.name_en or academy.name,
            "scholarship_count": len(admin_scholarships),
        }

        logger.info(
            f"User {current_user.nycu_id} (ID: {current_user.id}) manages college: {academy.code} ({academy.name}) "
            f"with {len(admin_scholarships)} scholarship permission(s)"
        )

        return ApiResponse(success=True, message="Managed college retrieved successfully", data=managed_college_data)

    except Exception as e:
        logger.error(
            f"Error retrieving managed college for user {current_user.nycu_id} (ID: {current_user.id}): {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve managed college: {str(e)}"
        ) from e

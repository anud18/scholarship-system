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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import require_college
from app.db.deps import get_db
from app.models.application import Application
from app.models.college_review import CollegeReview
from app.models.scholarship import ScholarshipConfiguration, ScholarshipStatus, ScholarshipType
from app.models.student import Academy
from app.models.user import AdminScholarship, User, UserRole
from app.schemas.response import ApiResponse
from app.services.college_review_service import CollegeReviewError

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/statistics")
async def get_college_review_statistics(
    academic_year: Optional[int] = Query(None, description="Filter by academic year"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Get college review statistics"""

    try:
        # Build statistics query
        base_query = select(CollegeReview)

        if current_user.role not in [UserRole.admin, UserRole.super_admin]:
            # Non-admin users can only see their own reviews
            base_query = base_query.where(CollegeReview.reviewer_id == current_user.id)

        # Apply filters
        if academic_year or semester:
            from sqlalchemy.orm import join

            base_query = base_query.select_from(
                join(CollegeReview, Application, CollegeReview.application_id == Application.id)
            )

            if academic_year:
                base_query = base_query.where(Application.academic_year == academic_year)
            if semester:
                base_query = base_query.where(Application.semester == semester)

        # Execute query and calculate statistics
        result = await db.execute(base_query)
        reviews = result.scalars().all()

        total_reviews = len(reviews)
        approved_count = len([r for r in reviews if r.recommendation == "approve"])
        rejected_count = len([r for r in reviews if r.recommendation == "reject"])
        conditional_count = len([r for r in reviews if r.recommendation == "conditional"])

        avg_ranking_score = (
            sum(r.ranking_score for r in reviews if r.ranking_score) / len([r for r in reviews if r.ranking_score])
            if reviews
            else 0
        )

        statistics = {
            "total_reviews": total_reviews,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "conditional_count": conditional_count,
            "approval_rate": (approved_count / total_reviews * 100) if total_reviews > 0 else 0,
            "average_ranking_score": round(avg_ranking_score, 2),
            "breakdown_by_recommendation": {
                "approve": approved_count,
                "reject": rejected_count,
                "conditional": conditional_count,
            },
        }

        return ApiResponse(success=True, message="College review statistics retrieved successfully", data=statistics)

    except ValueError as e:
        logger.warning(f"Invalid statistics parameters: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid parameters: {str(e)}")
    except CollegeReviewError as e:
        logger.error(f"College review error retrieving statistics: {str(e)}")
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error retrieving statistics: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve statistics")


@router.get("/available-combinations")
async def get_available_combinations(current_user: User = Depends(require_college), db: AsyncSession = Depends(get_db)):
    """Get available combinations of scholarship types, academic years, and semesters from configurations"""

    try:
        logger.info("College user requesting available combinations from configurations")

        # Get scholarship IDs that the user has permission to access
        permission_query = select(AdminScholarship.scholarship_id).where(AdminScholarship.admin_id == current_user.id)
        permission_result = await db.execute(permission_query)
        allowed_scholarship_ids = [row[0] for row in permission_result.fetchall()]

        logger.info(f"User {current_user.id} has permission for scholarships: {allowed_scholarship_ids}")

        # If user has specific permissions, filter by those
        # If user has no permissions set (empty list), show all (for backward compatibility or super admin)
        if allowed_scholarship_ids:
            scholarship_query = select(ScholarshipType).where(
                ScholarshipType.status == "active", ScholarshipType.id.in_(allowed_scholarship_ids)
            )
        else:
            # No specific permissions - could mean all or none depending on your business logic
            # For college users without permissions, show no scholarships
            logger.warning(f"College user {current_user.id} has no scholarship permissions set")
            scholarship_query = select(ScholarshipType).where(ScholarshipType.id == -1)  # No results

        scholarship_result = await db.execute(scholarship_query)
        scholarship_types_objs = scholarship_result.scalars().all()

        scholarship_types = [
            {
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
                    semesters_set.add(value_lower.upper())
            else:
                # No semester means yearly scholarship
                has_yearly_scholarships = True

        academic_years = sorted(list(academic_years_set))
        semester_strings = sorted(list(semesters_set))

        # Add a special "YEARLY" option if there are yearly scholarships
        if has_yearly_scholarships:
            semester_strings.append("YEARLY")

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
        logger.error(f"Error retrieving available combinations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available combinations from database",
        )


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
        logger.error(f"Error retrieving sub-type translations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve sub-type translations: {str(e)}",
        )


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
        logger.info(f"User {current_user.id} requesting managed college information")

        # Check if user has college_code set
        if not current_user.college_code:
            logger.warning(f"College user {current_user.id} has no college_code assigned")
            return ApiResponse(success=True, message="No college assigned to this user", data=None)

        # Get college information from Academy table
        academy_stmt = select(Academy).where(Academy.code == current_user.college_code)
        academy_result = await db.execute(academy_stmt)
        academy = academy_result.scalar_one_or_none()

        if not academy:
            logger.error(f"College code {current_user.college_code} not found in Academy table")
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

        logger.info(f"User {current_user.id} manages college: {academy.code} ({academy.name})")

        return ApiResponse(success=True, message="Managed college retrieved successfully", data=managed_college_data)

    except Exception as e:
        logger.error(f"Error retrieving managed college for user {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve managed college: {str(e)}"
        )

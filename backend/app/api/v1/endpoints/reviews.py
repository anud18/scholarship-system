"""
Review API Endpoints

統一審查系統的 API 端點
Multi-role review operations (professor, college, admin)
"""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import DatabaseError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.security import get_current_user
from app.db.deps import get_db
from app.models.application import Application
from app.models.audit_log import AuditAction
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.user import User
from app.schemas.response import ApiResponse
from app.schemas.review import ReviewCreate, ReviewItemResponse, ReviewResponse, ReviewSubmitRequest
from app.services.application_audit_service import ApplicationAuditService
from app.services.college_review_service import CollegeReviewService
from app.services.review_service import ReviewService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/reviews", status_code=status.HTTP_201_CREATED)
async def create_review(
    review_data: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    創建新的審查記錄

    - 驗證審查者權限
    - 創建 ApplicationReview 和 ApplicationReviewItem
    - 自動計算 recommendation 和 comments
    - 更新 Application.decision_reason（如果有拒絕）
    - 更新 Application.status（根據累積狀態）
    """
    review_service = ReviewService(db)

    # 檢查申請是否存在
    application = await db.get(Application, review_data.application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="申請不存在")

    # 取得可審查的子項目
    reviewable_subtypes = await review_service.get_reviewable_subtypes(review_data.application_id, current_user.role)

    logger.info(
        f"[Create Review] Application {review_data.application_id} - User {current_user.id} ({current_user.role})"
    )
    logger.info(f"[Create Review] Reviewable sub-types: {reviewable_subtypes}")
    logger.info(f"[Create Review] Submitted items: {[item.sub_type_code for item in review_data.items]}")

    # 驗證所有待審查的子項目都在可審查列表中
    # Normalize submitted codes to lowercase and strip whitespace
    for item in review_data.items:
        normalized_code = item.sub_type_code.lower().strip() if item.sub_type_code else item.sub_type_code
        logger.info(f"[Create Review] Checking item: original='{item.sub_type_code}', normalized='{normalized_code}'")

        if normalized_code not in reviewable_subtypes:
            logger.warning(f"[Create Review] Authorization failed: '{normalized_code}' not in {reviewable_subtypes}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"您無權審查子項目 '{item.sub_type_code}'（該子項目可能已被前位審查者拒絕）"
            )

        # Update the item with normalized code
        item.sub_type_code = normalized_code

    # 驗證拒絕時是否有評論
    for item in review_data.items:
        if item.recommendation == "reject" and not item.comments:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"拒絕子項目 '{item.sub_type_code}' 時必須提供評論")

    # 計算整體建議
    items_dict = [item.model_dump() for item in review_data.items]
    overall_recommendation = await review_service.calculate_overall_recommendation(items_dict)

    # 組合評論
    combined_comments = await review_service.combine_comments(items_dict)

    # 創建審查記錄
    reviewed_at = datetime.utcnow()
    new_review = ApplicationReview(
        application_id=review_data.application_id,
        reviewer_id=current_user.id,
        recommendation=overall_recommendation,
        comments=combined_comments,
        reviewed_at=reviewed_at,
    )
    db.add(new_review)
    await db.flush()

    # 創建子項目審查記錄
    for item in review_data.items:
        review_item = ApplicationReviewItem(
            review_id=new_review.id,
            sub_type_code=item.sub_type_code,
            recommendation=item.recommendation,
            comments=item.comments,
        )
        db.add(review_item)

    # 更新 Application.decision_reason
    await review_service.update_decision_reason(application, current_user, items_dict, reviewed_at)

    # 更新 Application.status
    await review_service.update_application_status(review_data.application_id)

    await db.commit()
    await db.refresh(new_review)

    # 載入關聯資料
    stmt = (
        select(ApplicationReview)
        .where(ApplicationReview.id == new_review.id)
        .options(joinedload(ApplicationReview.reviewer), joinedload(ApplicationReview.items))
    )
    result = await db.execute(stmt)
    review_with_relations = result.scalar_one()

    return {
        "success": True,
        "message": "審查記錄創建成功",
        "data": {
            "id": review_with_relations.id,
            "application_id": review_with_relations.application_id,
            "reviewer_id": review_with_relations.reviewer_id,
            "reviewer_name": review_with_relations.reviewer.name,
            "reviewer_role": review_with_relations.reviewer.role,
            "recommendation": review_with_relations.recommendation,
            "comments": review_with_relations.comments,
            "reviewed_at": review_with_relations.reviewed_at.isoformat(),
            "created_at": review_with_relations.created_at.isoformat(),
            "items": [
                {
                    "id": item.id,
                    "review_id": item.review_id,
                    "sub_type_code": item.sub_type_code,
                    "recommendation": item.recommendation,
                    "comments": item.comments,
                }
                for item in review_with_relations.items
            ],
        },
    }


@router.get("/reviews/{review_id}")
async def get_review(
    review_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    取得審查記錄詳情
    """
    stmt = (
        select(ApplicationReview)
        .where(ApplicationReview.id == review_id)
        .options(joinedload(ApplicationReview.reviewer), joinedload(ApplicationReview.items))
    )
    result = await db.execute(stmt)
    review = result.scalar_one_or_none()

    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="審查記錄不存在")

    return {
        "success": True,
        "message": "審查記錄取得成功",
        "data": {
            "id": review.id,
            "application_id": review.application_id,
            "reviewer_id": review.reviewer_id,
            "reviewer_name": review.reviewer.name,
            "reviewer_role": review.reviewer.role,
            "recommendation": review.recommendation,
            "comments": review.comments,
            "reviewed_at": review.reviewed_at.isoformat(),
            "created_at": review.created_at.isoformat(),
            "items": [
                {
                    "id": item.id,
                    "review_id": item.review_id,
                    "sub_type_code": item.sub_type_code,
                    "recommendation": item.recommendation,
                    "comments": item.comments,
                }
                for item in review.items
            ],
        },
    }


@router.get("/applications/{application_id}/reviews")
async def get_application_reviews(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    取得申請的所有審查記錄
    """
    # 檢查申請是否存在
    application = await db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="申請不存在")

    # 查詢所有審查記錄
    stmt = (
        select(ApplicationReview)
        .where(ApplicationReview.application_id == application_id)
        .options(joinedload(ApplicationReview.reviewer), joinedload(ApplicationReview.items))
        .order_by(ApplicationReview.reviewed_at.desc())
    )
    result = await db.execute(stmt)
    reviews = result.scalars().all()

    return {
        "success": True,
        "message": "審查記錄取得成功",
        "data": [
            {
                "id": review.id,
                "application_id": review.application_id,
                "reviewer_id": review.reviewer_id,
                "reviewer_name": review.reviewer.name,
                "reviewer_role": review.reviewer.role,
                "recommendation": review.recommendation,
                "comments": review.comments,
                "reviewed_at": review.reviewed_at.isoformat(),
                "created_at": review.created_at.isoformat(),
                "items": [
                    {
                        "id": item.id,
                        "review_id": item.review_id,
                        "sub_type_code": item.sub_type_code,
                        "recommendation": item.recommendation,
                        "comments": item.comments,
                    }
                    for item in review.items
                ],
            }
            for review in reviews
        ],
    }


@router.get("/applications/{application_id}/review-status")
async def get_application_review_status(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    取得申請的審查狀態

    包含：
    - 整體審查狀態（基於累積的子項目狀態）
    - 每個子項目的累積狀態
    - decision_reason
    - 所有審查記錄
    """
    review_service = ReviewService(db)

    # 檢查申請是否存在
    application = await db.get(Application, application_id)
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="申請不存在")

    # 取得子項目累積狀態
    subtype_statuses = await review_service.get_subtype_cumulative_status(application_id)

    # 計算整體狀態
    overall_status = "pending"
    if subtype_statuses:
        all_approved = all(status["status"] == "approved" for status in subtype_statuses.values())
        all_rejected = all(status["status"] == "rejected" for status in subtype_statuses.values())
        any_rejected = any(status["status"] == "rejected" for status in subtype_statuses.values())

        if all_approved:
            overall_status = "approved"
        elif all_rejected:
            overall_status = "rejected"
        elif any_rejected:
            overall_status = "partial_approve"

    # 查詢所有審查記錄
    stmt = (
        select(ApplicationReview)
        .where(ApplicationReview.application_id == application_id)
        .options(joinedload(ApplicationReview.reviewer), joinedload(ApplicationReview.items))
        .order_by(ApplicationReview.reviewed_at.desc())
    )
    result = await db.execute(stmt)
    reviews = result.scalars().all()

    return {
        "success": True,
        "message": "審查狀態取得成功",
        "data": {
            "application_id": application_id,
            "overall_status": overall_status,
            "decision_reason": application.decision_reason,
            "subtype_statuses": subtype_statuses,
            "reviews": [
                {
                    "id": review.id,
                    "application_id": review.application_id,
                    "reviewer_id": review.reviewer_id,
                    "reviewer_name": review.reviewer.name,
                    "reviewer_role": review.reviewer.role,
                    "recommendation": review.recommendation,
                    "comments": review.comments,
                    "reviewed_at": review.reviewed_at.isoformat(),
                    "created_at": review.created_at.isoformat(),
                    "items": [
                        {
                            "id": item.id,
                            "review_id": item.review_id,
                            "sub_type_code": item.sub_type_code,
                            "recommendation": item.recommendation,
                            "comments": item.comments,
                        }
                        for item in review.items
                    ],
                }
                for review in reviews
            ],
        },
    }


@router.get("/applications/{application_id}/reviewable-subtypes")
async def get_reviewable_subtypes(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    取得當前用戶可審查的子項目列表

    規則：
    - 教授：可審查所有子項目
    - 學院：只能審查「教授未拒絕」的子項目
    - 管理員：只能審查「教授和學院都未拒絕」的子項目
    """
    review_service = ReviewService(db)

    # 檢查申請是否存在
    stmt = (
        select(Application)
        .where(Application.id == application_id)
        .options(joinedload(Application.scholarship_configuration))
    )
    result = await db.execute(stmt)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="申請不存在")

    # 取得所有子項目
    all_subtypes = application.scholarship_subtype_list or []
    if not all_subtypes:
        all_subtypes = ["default"]

    # 取得可審查的子項目
    reviewable_subtypes = await review_service.get_reviewable_subtypes(application_id, current_user.role)

    # 取得子項目累積狀態
    subtype_statuses = await review_service.get_subtype_cumulative_status(application_id)

    return {
        "success": True,
        "message": "可審查子項目取得成功",
        "data": {
            "application_id": application_id,
            "current_user_role": current_user.role,
            "reviewable_subtypes": reviewable_subtypes,
            "all_subtypes": all_subtypes,
            "subtype_statuses": subtype_statuses,
        },
    }


# ========== Multi-Role Review Endpoints (Professor, College, Admin) ==========


@router.post("/applications/{application_id}/review")
async def submit_application_review(
    request: Request,
    application_id: int,
    review_data: ReviewSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit review for an application (professor, college, or admin)

    Role-based permissions:
    - Professor: can review all sub-types
    - College: can review sub-types not rejected by professor
    - Admin: can review sub-types not rejected by professor or college

    Permission filtering handled by ReviewService.get_reviewable_subtypes()
    """

    # Multi-role authorization check
    if not (
        current_user.is_professor()
        or current_user.is_college()
        or current_user.is_admin()
        or current_user.is_super_admin()
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Professor, college, or admin role required for application review",
        )

    # Validate application_id
    if application_id <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid application ID")

    try:
        # Use unified ReviewService for creating/updating reviews
        review_service = ReviewService(db)

        # Get reviewable sub-types for this user to validate permissions
        reviewable_subtypes = await review_service.get_reviewable_subtypes(application_id, current_user.role)

        logger.info(f"[Review Submit] Application {application_id} - User {current_user.id} ({current_user.role})")
        logger.info(f"[Review Submit] Reviewable sub-types: {reviewable_subtypes}")
        logger.info(f"[Review Submit] Submitted items: {[item.sub_type_code for item in review_data.items]}")

        # Validate all submitted sub-types are reviewable by this user
        # Normalize submitted codes to lowercase and strip whitespace
        for item in review_data.items:
            normalized_code = item.sub_type_code.lower().strip() if item.sub_type_code else item.sub_type_code
            logger.info(
                f"[Review Submit] Checking item: original='{item.sub_type_code}', normalized='{normalized_code}'"
            )

            if normalized_code not in reviewable_subtypes:
                logger.warning(
                    f"[Review Submit] Authorization failed: '{normalized_code}' not in {reviewable_subtypes}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"You are not authorized to review sub-type '{item.sub_type_code}' (may have been rejected by previous reviewer)",
                )

            # Update the item with normalized code
            item.sub_type_code = normalized_code

        # Validate reject items have comments
        for item in review_data.items:
            if item.recommendation == "reject" and not item.comments:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Comments required when rejecting sub-type '{item.sub_type_code}'",
                )

        # Create review using unified format with sub-type items
        items_data = [item.model_dump() for item in review_data.items]
        review = await review_service.create_review(
            application_id=application_id,
            reviewer_id=current_user.id,
            items=items_data,
        )

        # Log the review operation with role-specific action
        audit_service = ApplicationAuditService(db)
        action_map = {
            "professor": AuditAction.professor_review,
            "college": AuditAction.college_review,
            "admin": AuditAction.admin_review,
            "super_admin": AuditAction.admin_review,
        }
        # Normalize role to string value for dictionary lookup
        role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role).lower()
        audit_action = action_map.get(role_str, AuditAction.college_review)

        await audit_service.log_application_operation(
            application_id=application_id,
            action=audit_action,
            user=current_user,
            request=request,
            description=f"{role_str.replace('_', ' ').title()} review created with recommendation: {review.recommendation}",
            new_values={
                "recommendation": review.recommendation,
                "items_count": len(review.items),
                "sub_types": [item.sub_type_code for item in review.items],
            },
            status="success",
        )

        # Build response with unified format
        review_response = ReviewResponse(
            id=review.id,
            application_id=review.application_id,
            reviewer_id=review.reviewer_id,
            recommendation=review.recommendation,
            comments=review.comments,
            reviewed_at=review.reviewed_at,
            created_at=review.created_at,
            items=[
                ReviewItemResponse(
                    id=item.id,
                    review_id=item.review_id,
                    sub_type_code=item.sub_type_code,
                    recommendation=item.recommendation,
                    comments=item.comments,
                )
                for item in review.items
            ],
        )

        # Trigger auto-redistribution for rankings (college/admin reviews only)
        redistribution_info = None
        if current_user.is_college() or current_user.is_admin() or current_user.is_super_admin():
            college_review_service = CollegeReviewService(db)
            redistribution_info = await college_review_service.auto_redistribute_after_status_change(
                application_id=application_id, executor_id=current_user.id
            )
            logger.info(f"Auto-redistribution completed for application {application_id}: {redistribution_info}")

        response_data = review_response.model_dump()
        if redistribution_info:
            response_data["redistribution_info"] = redistribution_info

        return ApiResponse(
            success=True,
            message="Review created successfully",
            data=response_data,
        )

    except HTTPException:
        # Re-raise FastAPI HTTPException as-is (preserves status code and detail)
        raise
    except ValueError as e:
        logger.warning(f"Invalid review data for application {application_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid review data: {str(e)}")
    except PermissionError as e:
        logger.warning(f"Permission denied for review creation by user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to review this application")
    except IntegrityError as e:
        logger.error(f"Database integrity error creating review for application {application_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Review creation conflicts with existing data")
    except DatabaseError as e:
        logger.error(f"Database error creating review for application {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database service temporarily unavailable"
        )
    except Exception as e:
        logger.error(f"Unexpected error creating review for application {application_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while creating the review",
        )


@router.get("/applications/{application_id}/review")
async def get_user_application_review(
    request: Request,
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current user's review for an application (multi-role)

    Returns the most recent review by this user for this application.
    Used by professor, college, and admin to view their own submitted reviews.
    """
    logger.info(f"User {current_user.id} ({current_user.role}) requesting review for application {application_id}")

    try:
        review_service = ReviewService(db)
        review = await review_service.get_review_by_application_and_reviewer(
            application_id=application_id, reviewer_id=current_user.id
        )

        if not review:
            # Return null for no review found - frontend handles this gracefully
            return {
                "success": True,
                "message": "查詢成功",
                "data": None,
            }

        # Return unified format response
        review_response = ReviewResponse(
            id=review.id,
            application_id=review.application_id,
            reviewer_id=review.reviewer_id,
            recommendation=review.recommendation,
            comments=review.comments,
            reviewed_at=review.reviewed_at,
            created_at=review.created_at,
            items=[
                ReviewItemResponse(
                    id=item.id,
                    review_id=item.review_id,
                    sub_type_code=item.sub_type_code,
                    recommendation=item.recommendation,
                    comments=item.comments,
                )
                for item in review.items
            ],
        )

        return {
            "success": True,
            "message": "查詢成功",
            "data": review_response.model_dump(),
        }

    except Exception as e:
        logger.error(f"Error fetching user review: {str(e)}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while fetching review",
        )


@router.get("/applications/{application_id}/sub-types")
async def get_application_reviewable_sub_types(
    request: Request,
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get reviewable sub-types for an application (multi-role)

    Returns sub-types that the current user is authorized to review,
    with localized labels (zh/en) from database configuration.

    Role-based filtering:
    - Professor: all sub-types
    - College: sub-types not rejected by professor
    - Admin: sub-types not rejected by professor or college
    """
    logger.info(f"User {current_user.id} ({current_user.role}) requesting sub-types for application {application_id}")

    try:
        from app.services.application_service import ApplicationService

        service = ApplicationService(db)
        sub_types = await service.get_application_available_sub_types(application_id)

        logger.info(f"Found {len(sub_types)} sub-types for application {application_id}")
        return {
            "success": True,
            "message": "查詢成功",
            "data": sub_types,
        }

    except Exception as e:
        logger.error(f"Error fetching application sub-types: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurred while fetching sub-types",
        )

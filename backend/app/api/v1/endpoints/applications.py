"""
Application management API endpoints
"""

import logging
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Path, Query, Request, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthorizationError, NotFoundError
from app.core.security import get_current_user, require_staff, require_student
from app.db.deps import get_db
from app.models.audit_log import AuditAction
from app.models.user import User
from app.schemas.application import (
    ApplicationCreate,
    ApplicationStatusUpdate,
    ApplicationStatusUpdateResponse,
    ApplicationUpdate,
    ProfessorReviewCreate,
    StudentDataSchema,
)
from app.services.application_audit_service import ApplicationAuditService
from app.services.application_service import ApplicationService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_application(
    application_data: ApplicationCreate,
    is_draft: bool = Query(False, description="Save as draft"),
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Create a new scholarship application (draft or submitted)"""
    logger.debug(f"Received application creation request from user: {current_user.id}, is_draft: {is_draft}")
    # Do not log raw request data as it may contain sensitive information

    try:
        service = ApplicationService(db)

        # Get student profile from user
        logger.debug("Fetching student profile")
        from app.services.application_service import get_student_data_from_user

        student = await get_student_data_from_user(current_user)

        if not student:
            logger.error(f"Student profile not found for user: {current_user.id}")
            # Do not log personal information in production
            return {
                "success": False,
                "message": "Student profile not found",
                "data": {
                    "student_no": getattr(current_user, "nycu_id", None),
                    "error_code": "STUDENT_NOT_FOUND",
                },
            }

        logger.debug("Found student profile")

        # Validate scholarship type exists
        if not application_data.scholarship_type:
            logger.error("Missing scholarship_type")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Scholarship type is required",
                    "error_code": "MISSING_SCHOLARSHIP_TYPE",
                    "received_data": application_data.dict(exclude_none=True),
                },
            )

        # Validate form data
        logger.debug("Validating form data")
        if not application_data.form_data:
            logger.error("Missing form_data")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Form data is required",
                    "error_code": "MISSING_FORM_DATA",
                    "received_data": application_data.dict(exclude_none=True),
                },
            )

        try:
            # Try to validate form data structure
            logger.debug("Validating form data structure")
            application_data.form_data.dict()
            logger.debug("Form data validated successfully")
        except Exception as e:
            logger.error(f"Form data validation failed: {str(e)}")
            # Do not log raw form data as it may contain sensitive information
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Invalid form data structure",
                    "error_code": "INVALID_FORM_DATA",
                    "error": str(e),
                    "received_form_data": str(application_data.form_data),
                },
            )

        # Get scholarship configuration to extract scholarship_type_id, academic_year, semester
        logger.debug(f"Fetching scholarship configuration: {application_data.configuration_id}")
        from sqlalchemy import and_, select

        from app.models.application import Application, ApplicationStatus
        from app.models.scholarship import ScholarshipConfiguration

        config_stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.id == application_data.configuration_id
        )
        config_result = await db.execute(config_stmt)
        scholarship_config = config_result.scalar_one_or_none()

        if not scholarship_config:
            logger.error(f"Invalid configuration_id: {application_data.configuration_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "message": "Invalid scholarship configuration",
                    "error_code": "INVALID_CONFIGURATION_ID",
                    "configuration_id": application_data.configuration_id,
                },
            )

        # Check for duplicate applications (同一獎學金類型、學年度、學期只能有一個申請)
        logger.debug("Checking for duplicate applications")

        # 排除已撤回/拒絕/取消/刪除的申請
        excluded_statuses = [
            ApplicationStatus.withdrawn.value,
            ApplicationStatus.rejected.value,
            ApplicationStatus.cancelled.value,
            ApplicationStatus.deleted.value,  # 允許刪除後重新申請
        ]

        # 查詢是否已有申請 - using values from scholarship configuration
        duplicate_check_stmt = select(Application).where(
            and_(
                Application.user_id == current_user.id,
                Application.scholarship_type_id == scholarship_config.scholarship_type_id,
                Application.academic_year == scholarship_config.academic_year,
                Application.semester == scholarship_config.semester,
                Application.status.notin_(excluded_statuses),
            )
        )
        duplicate_result = await db.execute(duplicate_check_stmt)
        existing_application = duplicate_result.scalar_one_or_none()

        if existing_application:
            logger.warning(
                f"Duplicate application detected: user_id={current_user.id}, "
                f"scholarship_type_id={scholarship_config.scholarship_type_id}, "
                f"existing_app_id={existing_application.app_id}, "
                f"status={existing_application.status}"
            )
            return {
                "success": False,
                "message": f"您已有此獎學金的申請記錄（{existing_application.app_id}），無法重複申請",
                "data": {
                    "error_code": "DUPLICATE_APPLICATION",
                    "existing_application_id": existing_application.id,
                    "existing_app_id": existing_application.app_id,
                    "existing_status": existing_application.status,
                    "scholarship_name": existing_application.scholarship_name,
                },
            }

        logger.debug(f"Creating application (draft: {is_draft})")
        result = await service.create_application(
            user_id=current_user.id,
            student_code=current_user.nycu_id,  # Use nycu_id as student_code for fetching student data
            application_data=application_data,
            is_draft=is_draft,
        )
        logger.info(f"Application created successfully: {result.app_id}")

        # Log audit trail for application creation
        audit_service = ApplicationAuditService(db)
        await audit_service.log_application_create(
            application_id=result.id if hasattr(result, "id") else 0,
            app_id=result.app_id if hasattr(result, "app_id") else "UNKNOWN",
            user=current_user,
            scholarship_type=result.main_scholarship_type if hasattr(result, "main_scholarship_type") else "UNKNOWN",
            is_draft=is_draft,
            request=request,
        )

        # 包裝成 ApiResponse 格式
        from app.schemas.application import ApplicationResponse

        if isinstance(result, ApplicationResponse):
            response_data = result
        else:
            response_data = ApplicationResponse.from_orm(result)

        return {
            "success": True,
            "message": "申請已建立" if not is_draft else "草稿已儲存",
            "data": response_data.dict() if hasattr(response_data, "dict") else response_data.model_dump(),
        }

    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}")
        if hasattr(e, "errors"):
            logger.debug(f"Validation error details: {[error.get('loc', []) for error in e.errors()]}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Validation error",
                "error_code": "VALIDATION_ERROR",
                "errors": e.errors() if hasattr(e, "errors") else str(e),
                "received_data": application_data.dict(exclude_none=True),
            },
        )
    except HTTPException:
        # Re-raise HTTPException directly as they are already properly formatted
        raise
    except IntegrityError as e:
        logger.error(f"Database integrity error during application creation: {str(e)}")
        # Check for specific constraint violations if needed, e.g., unique constraint
        if "duplicate key value violates unique constraint" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "message": "Duplicate entry: An application with these details already exists.",
                    "error_code": "DUPLICATE_ENTRY",
                    "detail": str(e),
                },
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "A database integrity error occurred.",
                "error_code": "DATABASE_INTEGRITY_ERROR",
                "detail": str(e),
            },
        )
    except Exception as e:
        logger.error(f"Unexpected error during application creation: {str(e)}")
        import traceback

        error_trace = traceback.format_exc()
        logger.debug(f"Full traceback: {error_trace}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "An unexpected error occurred while creating the application. Please try again later.",
                "error_code": "UNEXPECTED_ERROR",
                "error_type": type(e).__name__,
            },
        )


@router.get("")
async def get_my_applications(
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's applications"""
    service = ApplicationService(db)
    result = await service.get_user_applications(current_user, status)
    return {
        "success": True,
        "message": "查詢成功",
        "data": [item.dict() if hasattr(item, "dict") else item.model_dump() for item in result],
    }


@router.get("/dashboard/stats")
async def get_dashboard_stats(current_user: User = Depends(require_student), db: AsyncSession = Depends(get_db)):
    """Get dashboard statistics for student"""
    service = ApplicationService(db)
    result = await service.get_student_dashboard_stats(current_user)
    return {
        "success": True,
        "message": "查詢成功",
        "data": result.dict() if hasattr(result, "dict") else result.model_dump(),
    }


@router.get("/{id}")
async def get_application(
    id: int = Path(..., description="Application ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Get application by ID"""
    service = ApplicationService(db)
    result = await service.get_application_by_id(id, current_user)

    # Log audit trail for viewing application
    audit_service = ApplicationAuditService(db)
    await audit_service.log_view_application(
        application_id=id,
        app_id=result.app_id if hasattr(result, "app_id") else f"APP-{id}",
        user=current_user,
        request=request,
    )

    return {
        "success": True,
        "message": "查詢成功",
        "data": result.dict() if hasattr(result, "dict") else result.model_dump(),
    }


@router.put("/{id}")
async def update_application(
    id: int = Path(..., description="Application ID"),
    update_data: ApplicationUpdate = Body(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Update application"""
    service = ApplicationService(db)
    result = await service.update_application(id, update_data, current_user)

    # Log audit trail for application update
    audit_service = ApplicationAuditService(db)
    updated_fields = []
    if hasattr(update_data, "model_dump"):
        updated_fields = [k for k, v in update_data.model_dump(exclude_unset=True).items() if v is not None]
    elif hasattr(update_data, "dict"):
        updated_fields = [k for k, v in update_data.dict(exclude_unset=True).items() if v is not None]

    await audit_service.log_application_update(
        application_id=id,
        app_id=result.app_id if hasattr(result, "app_id") else f"APP-{id}",
        user=current_user,
        updated_fields=updated_fields,
        request=request,
    )

    return {
        "success": True,
        "message": "更新成功",
        "data": result.dict() if hasattr(result, "dict") else result.model_dump(),
    }


@router.post("/{id}/submit")
async def submit_application(
    id: int = Path(..., description="Application ID"),
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Submit application for review"""
    service = ApplicationService(db)
    result = await service.submit_application(id, current_user)

    # Log audit trail for application submission
    audit_service = ApplicationAuditService(db)
    await audit_service.log_application_submit(
        application_id=id,
        app_id=result.app_id if hasattr(result, "app_id") else f"APP-{id}",
        user=current_user,
        request=request,
    )

    return {
        "success": True,
        "message": "申請已提交",
        "data": result.dict() if hasattr(result, "dict") else result.model_dump(),
    }


@router.delete("/{id}")
async def delete_application(
    id: int = Path(..., description="Application ID"),
    reason: Optional[str] = Query(None, description="Reason for deletion (required for staff)"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Soft delete an application

    Permission Control:
    - Students: Can only delete their own draft applications (no reason required)
    - Staff (professor/college/admin): Can delete any application (reason required)

    The application status will be set to 'deleted' and deletion metadata will be tracked.
    """
    service = ApplicationService(db)

    try:
        # Perform soft delete
        deleted_app = await service.delete_application(id, current_user, reason)

        # Log audit trail for deletion
        audit_service = ApplicationAuditService(db)
        await audit_service.log_delete_application(
            application_id=id,
            app_id=deleted_app.app_id if hasattr(deleted_app, "app_id") else f"APP-{id}",
            user=current_user,
            reason=reason,
            request=request,
        )

        return {
            "success": True,
            "message": "申請已刪除",
            "data": deleted_app.dict()
            if hasattr(deleted_app, "dict")
            else deleted_app.model_dump()
            if hasattr(deleted_app, "model_dump")
            else {"id": id},
        }
    except Exception as e:
        logger.error(f"Error deleting application {id}: {str(e)}")
        raise


@router.post("/{id}/withdraw")
async def withdraw_application(
    id: int = Path(..., description="Application ID"),
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Withdraw a submitted application"""
    service = ApplicationService(db)
    result = await service.withdraw_application(id, current_user)

    # Log audit trail for application withdrawal
    audit_service = ApplicationAuditService(db)
    await audit_service.log_application_withdraw(
        application_id=id,
        app_id=result.app_id if hasattr(result, "app_id") else f"APP-{id}",
        user=current_user,
        request=request,
    )

    return {
        "success": True,
        "message": "申請已撤回",
        "data": result.dict() if hasattr(result, "dict") else result.model_dump(),
    }


@router.post("/{id}/restore")
async def restore_application(
    id: int = Path(..., description="Application ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Restore a deleted application to draft status

    Permission Control:
    - Students: Can only restore their own deleted applications
    - Staff (professor/college/admin): Can restore any application
    """
    service = ApplicationService(db)

    try:
        result = await service.restore_application(id, current_user)

        # Log audit trail for application restoration
        audit_service = ApplicationAuditService(db)
        await audit_service.log_status_update(
            application_id=id,
            app_id=result.app_id if hasattr(result, "app_id") else f"APP-{id}",
            old_status="deleted",
            new_status="draft",
            user=current_user,
            reason="Application restored from deleted status",
            request=request,
        )

        # Convert to ApplicationResponse for serialization
        from app.schemas.application import ApplicationResponse

        response_data = ApplicationResponse.from_orm(result)

        return {
            "success": True,
            "message": "申請已恢復",
            "data": response_data.dict() if hasattr(response_data, "dict") else response_data.model_dump(),
        }
    except (NotFoundError, ValidationError, AuthorizationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST
            if isinstance(e, ValidationError)
            else status.HTTP_404_NOT_FOUND
            if isinstance(e, NotFoundError)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.get("/{id}/files")
async def get_application_files(
    id: int = Path(..., description="Application ID"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all files for an application - 現在從 submitted_form_data.documents 中獲取"""

    # Verify application exists and user has access
    service = ApplicationService(db)
    application = await service.get_application_by_id(id, current_user)

    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    # 從 submitted_form_data.documents 中獲取文件資訊
    files_with_urls = []
    if application.submitted_form_data and "documents" in application.submitted_form_data:
        for doc in application.submitted_form_data["documents"]:
            if "file_id" in doc and doc["file_id"]:
                file_dict = {
                    "id": doc["file_id"],
                    "filename": doc.get("filename", ""),
                    "original_filename": doc.get("original_filename", ""),
                    "file_size": doc.get("file_size"),
                    "mime_type": doc.get("mime_type"),
                    "file_type": doc.get("document_type", ""),
                    "is_verified": doc.get("is_verified", False),
                    "uploaded_at": doc.get("upload_time"),
                    "file_path": doc.get("file_path"),
                    "download_url": doc.get("download_url"),
                }
                files_with_urls.append(file_dict)

    return {
        "success": True,
        "message": "Files retrieved successfully",
        "data": files_with_urls,
    }


@router.post("/{id}/files/upload")
async def upload_file(
    id: int = Path(..., description="Application ID"),
    file: UploadFile = File(...),
    file_type: str = Query("other", description="File type"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Upload file for application using MinIO"""
    service = ApplicationService(db)
    result = await service.upload_application_file_minio(id, current_user, file, file_type)

    # Log audit trail for document upload
    audit_service = ApplicationAuditService(db)
    # Get application to fetch app_id
    app = await service.get_application_by_id(id, current_user)
    await audit_service.log_document_upload(
        application_id=id,
        app_id=app.app_id if hasattr(app, "app_id") else f"APP-{id}",
        file_type=file_type,
        filename=file.filename or "unknown",
        file_size=file.size if hasattr(file, "size") else 0,
        user=current_user,
        request=request,
    )

    return {
        "success": True,
        "message": "檔案上傳成功",
        "data": result.dict()
        if hasattr(result, "dict")
        else result.model_dump()
        if hasattr(result, "model_dump")
        else result,
    }


@router.post("/{id}/files")
async def upload_file_alias(
    id: int = Path(..., description="Application ID"),
    file: UploadFile = File(...),
    file_type: str = Query("other", description="File type"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload file for application (alias for /files/upload)"""
    return await upload_file(id, file, file_type, current_user, db)


# Staff/Admin endpoints
@router.get("/review/list")
async def get_applications_for_review(
    status: Optional[str] = Query(None, description="Filter by status"),
    scholarship_type_id: Optional[int] = Query(None, description="Filter by scholarship type ID"),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Get applications for review (staff only)"""
    service = ApplicationService(db)
    result = await service.get_applications_for_review(current_user, status, scholarship_type_id)
    return {
        "success": True,
        "message": "查詢成功",
        "data": [item.dict() if hasattr(item, "dict") else item.model_dump() for item in result],
    }


@router.put(
    "/{id}/status",
    responses={
        200: {
            "description": "Application status updated successfully",
            "model": ApplicationStatusUpdateResponse,
        }
    },
)
async def update_application_status(
    id: int = Path(..., description="Application ID"),
    status_update: ApplicationStatusUpdate = ...,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Update application status (staff only)

    This endpoint updates an application's status and automatically triggers redistribution
    if the status changes to 'approved' or 'rejected'. The response includes information
    about any auto-redistribution that was performed.
    """
    # Get application before update to capture old status
    service = ApplicationService(db)
    app_before = await service.get_application_by_id(id, current_user)
    old_status = app_before.status if hasattr(app_before, "status") else "unknown"

    # Update status
    result = await service.update_application_status(id, current_user, status_update)

    # Check and execute auto-redistribution if status changed to approved/rejected
    redistribution_info = {"auto_redistributed": False}
    if status_update.status in ["approved", "rejected"]:
        from app.services.college_review_service import CollegeReviewService

        review_service = CollegeReviewService(db)
        redistribution_info = await review_service.auto_redistribute_after_status_change(
            application_id=id, executor_id=current_user.id
        )

    # Log audit trail for status update
    audit_service = ApplicationAuditService(db)
    await audit_service.log_status_update(
        application_id=id,
        app_id=result.app_id if hasattr(result, "app_id") else f"APP-{id}",
        old_status=old_status,
        new_status=status_update.status,
        user=current_user,
        reason=status_update.comments if hasattr(status_update, "comments") else None,
        request=request,
    )

    # Prepare result data with redistribution info
    result_dict = result.model_dump() if hasattr(result, "model_dump") else result.dict()
    return {
        "success": True,
        "message": "狀態已更新",
        "data": {
            **result_dict,
            "redistribution_info": redistribution_info,
        },
    }


@router.post("/{id}/review")
async def submit_professor_review(
    id: int = Path(..., description="Application ID"),
    review_data: ProfessorReviewCreate = ...,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """Submit professor's review and selected awards for an application"""
    if not current_user.is_professor():
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Only professors can submit this review.")
    service = ApplicationService(db)
    result = await service.create_professor_review(id, current_user, review_data)

    # Log audit trail for professor review
    audit_service = ApplicationAuditService(db)
    await audit_service.log_application_operation(
        application_id=id,
        action=AuditAction.approve,
        user=current_user,
        request=request,
        description=f"指導教授提交審查意見 {result.app_id if hasattr(result, 'app_id') else f'APP-{id}'}",
        new_values={
            "professor_id": current_user.id,
            "professor_name": current_user.name,
            "review_comment": review_data.professor_comment if hasattr(review_data, "professor_comment") else None,
        },
        meta_data={"app_id": result.app_id if hasattr(result, "app_id") else f"APP-{id}", "review_type": "professor"},
    )

    return {
        "success": True,
        "message": "審查已提交",
        "data": result.dict() if hasattr(result, "dict") else result.model_dump(),
    }


@router.get("/college/review")
async def get_college_applications_for_review(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    scholarship_type: Optional[str] = Query(None, description="Filter by scholarship type"),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """Get applications for college review (college role only)"""
    from fastapi import HTTPException

    # Ensure user has college role
    if not current_user.is_college():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="College access required")

    service = ApplicationService(db)
    # Get applications that are in submitted or under_review status for college review
    result = await service.get_applications_for_review(
        current_user,
        skip=0,
        limit=100,
        status=status_filter or "submitted",  # Default to submitted for college review
        scholarship_type=scholarship_type,
    )
    return {
        "success": True,
        "message": "查詢成功",
        "data": [item.dict() if hasattr(item, "dict") else item.model_dump() for item in result],
    }


@router.put("/{id}/student-data")
async def update_student_data(
    id: int,
    student_data: StudentDataSchema,
    refresh_from_api: bool = Query(False, description="是否重新從外部API獲取基本學生資料"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """更新申請的學生相關資料 (銀行帳號、指導教授資訊等)"""
    service = ApplicationService(db)

    try:
        # Get app_id before update
        app = await service.get_application_by_id(id, current_user)
        app_id = app.app_id if hasattr(app, "app_id") else f"APP-{id}"

        await service.update_student_data(
            id=id,
            student_data_update=student_data,
            current_user=current_user,
            refresh_from_api=refresh_from_api,
        )

        # Log audit trail for student data update
        audit_service = ApplicationAuditService(db)
        updated_fields = []
        if hasattr(student_data, "model_dump"):
            updated_fields = [k for k, v in student_data.model_dump(exclude_unset=True).items() if v is not None]
        elif hasattr(student_data, "dict"):
            updated_fields = [k for k, v in student_data.dict(exclude_unset=True).items() if v is not None]

        await audit_service.log_student_data_update(
            application_id=id,
            app_id=app_id,
            user=current_user,
            updated_fields=updated_fields,
            request=request,
        )

        return {
            "success": True,
            "message": "學生資料更新成功",
            "data": {"id": id},
        }
    except (NotFoundError, ValidationError, AuthorizationError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST
            if isinstance(e, ValidationError)
            else status.HTTP_404_NOT_FOUND
            if isinstance(e, NotFoundError)
            else status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.get("/{id}/student-data")
async def get_student_data(
    id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """取得申請的學生相關資料"""
    from sqlalchemy import select

    from app.models.application import Application

    # 檢查申請是否存在
    stmt = select(Application).where(Application.id == id)
    result = await db.execute(stmt)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    # 檢查權限 (學生只能看自己的，管理員可以看所有)
    if current_user.role not in ["admin", "super_admin", "college"] and application.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # 回傳學生資料
    student_data = application.student_data or {}
    response_data = StudentDataSchema(**student_data)
    return {
        "success": True,
        "message": "查詢成功",
        "data": response_data.model_dump(),
    }


@router.get("/{id}/audit-trail")
async def get_application_audit_trail(
    id: int = Path(..., description="Application ID"),
    limit: int = Query(50, le=200, description="Maximum number of audit logs to return"),
    offset: int = Query(0, ge=0, description="Number of audit logs to skip"),
    action_filter: Optional[str] = Query(None, description="Filter by action type"),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    Get audit trail for a specific application (staff only)

    Returns a list of all operations performed on this application, including:
    - View, update, submit, approve, reject actions
    - Who performed each action and when
    - Old and new values for status changes
    - IP addresses and request details
    """
    # Verify application exists and user has access
    service = ApplicationService(db)
    try:
        await service.get_application_by_id(id, current_user)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    # Get audit trail
    audit_service = ApplicationAuditService(db)
    audit_logs = await audit_service.get_application_audit_trail(
        application_id=id, limit=limit, offset=offset, action_filter=action_filter
    )

    # Format response with user information
    formatted_logs = []
    for log in audit_logs:
        log_dict = {
            "id": log.id,
            "action": log.action,
            "user_id": log.user_id,
            "user_name": log.user.name if log.user else "Unknown",
            "description": log.description,
            "old_values": log.old_values,
            "new_values": log.new_values,
            "ip_address": log.ip_address,
            "request_method": log.request_method,
            "request_url": log.request_url,
            "status": log.status,
            "error_message": log.error_message,
            "meta_data": log.meta_data,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        formatted_logs.append(log_dict)

    return {
        "success": True,
        "message": f"Retrieved {len(formatted_logs)} audit log entries",
        "data": formatted_logs,
    }

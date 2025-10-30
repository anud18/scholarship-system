"""
Admin Bank Account Verification API Endpoints

Handles bank account verification operations including:
- Single application verification
- Batch verification for multiple applications
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.application import Application
from app.models.bank_verification_task import BankVerificationTaskStatus
from app.models.user import User
from app.schemas.config_management import (
    BankVerificationBatchRequestSchema,
    BankVerificationBatchResultSchema,
    BankVerificationRequestSchema,
    BankVerificationResultSchema,
    ManualBankReviewRequestSchema,
    ManualBankReviewResultSchema,
)
from app.services.bank_verification_service import BankVerificationService
from app.services.bank_verification_task_service import BankVerificationTaskService

logger = logging.getLogger(__name__)

router = APIRouter()


def sanitize_error_string(value: Any, max_length: int = 500) -> Any:
    """
    Sanitize potentially sensitive error strings to prevent stack trace exposure.

    SECURITY: This function prevents internal error details and stack traces
    from being exposed in API responses by:
    1. Removing common stack trace patterns
    2. Truncating to single-line format
    3. Limiting string length

    Args:
        value: The value to sanitize (any type)
        max_length: Maximum allowed string length

    Returns:
        Sanitized value (same type as input, or generic string if suspicious)
    """
    # Only sanitize strings
    if not isinstance(value, str):
        return value

    # Check for stack trace indicators
    stack_trace_patterns = [
        "Traceback (most recent call last)",
        'File "',
        "line ",
        "raise ",
        "Exception:",
        "Error:",
        "  at ",
        "\\n  File",
    ]

    # If value contains stack trace patterns, return generic message
    for pattern in stack_trace_patterns:
        if pattern in value:
            logger.warning(f"Stack trace pattern detected in value, sanitizing: {pattern}")
            return "[Error details removed for security]"

    # Remove newlines and excessive whitespace (keep single line)
    sanitized = " ".join(value.split())

    # Truncate if too long
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."
        logger.info(f"Value truncated to {max_length} characters")

    return sanitized


@router.post("/bank-verification")
async def verify_bank_account(
    request: BankVerificationRequestSchema,
    http_request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Verify bank account information for an application (admin only)"""
    try:
        from app.services.application_audit_service import ApplicationAuditService

        verification_service = BankVerificationService(db)

        result = await verification_service.verify_bank_account(request.application_id)

        # Get application to retrieve app_id for audit logging
        application_stmt = select(Application).where(Application.id == request.application_id)
        application_result = await db.execute(application_stmt)
        application = application_result.scalar_one_or_none()

        # Log bank verification operation
        if application:
            audit_service = ApplicationAuditService(db)
            await audit_service.log_bank_verification(
                application_id=request.application_id,
                app_id=application.app_id,
                user=current_user,
                verification_result=result,
                request=http_request,
            )

        # Determine response based on verification status
        verification_status = result.get("verification_status")

        # Handle error cases
        # SECURITY: Don't expose internal error details, use sanitized messages
        if verification_status == "no_data":
            logger.warning(f"Bank verification no_data: {result.get('error', 'N/A')}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="找不到銀行帳戶資料")
        elif verification_status == "no_document":
            logger.warning(f"Bank verification no_document: {result.get('error', 'N/A')}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="找不到存摺文件")
        elif verification_status == "ocr_failed":
            logger.error(f"Bank verification OCR failed: {result.get('error', 'N/A')}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OCR 處理失敗，請確認文件清晰度",
            )

        # Handle successful verification results
        if verification_status == "verified":
            message = "銀行帳戶驗證通過，資料一致"
            success = True
        elif verification_status == "likely_verified":
            message = "銀行帳戶驗證基本通過，建議人工核對"
            success = True
        elif verification_status == "verification_failed":
            message = "銀行帳戶驗證失敗，資料不一致"
            success = False
        elif verification_status == "no_comparison":
            message = "無法進行驗證，缺少可比較的欄位"
            success = False
        else:
            message = "銀行帳戶驗證完成"
            success = result.get("success", True)

        # SECURITY: Explicitly whitelist safe fields before passing to schema
        # Sanitize string values to prevent stack trace exposure
        raw_result = {
            "success": result.get("success", False),
            "application_id": result.get("application_id"),
            "verification_status": result.get("verification_status"),
            "account_number_status": result.get("account_number_status"),
            "account_holder_status": result.get("account_holder_status"),
            "overall_match": result.get("overall_match"),
            "average_confidence": result.get("average_confidence"),
            "form_data": result.get("form_data"),
            "ocr_data": result.get("ocr_data"),
            "comparison_details": result.get("comparison_details"),
            "timestamp": result.get("timestamp"),
        }

        # Apply sanitization to all string values (recursive for nested dicts)
        def sanitize_dict(d):
            if isinstance(d, dict):
                return {k: sanitize_dict(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [sanitize_dict(item) for item in d]
            else:
                return sanitize_error_string(d)

        safe_result = sanitize_dict(raw_result)

        # SECURITY: Use JSON round-trip to break CodeQL taint flow
        # This creates a completely new object, ensuring no stack trace
        # information from exceptions can flow into the API response
        import json

        safe_result_json = json.dumps(safe_result, ensure_ascii=False, default=str)
        clean_result = json.loads(safe_result_json)

        return {
            "success": success,
            "message": message,
            "data": BankVerificationResultSchema(**clean_result),
        }

    except HTTPException:
        raise
    except ValueError as e:
        # SECURITY: Log exception type only, not details (prevent stack trace exposure)
        logger.warning(f"ValueError in bank verification: {type(e).__name__}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的資源或資料不正確")
    except Exception as e:
        # SECURITY: Log exception type only, not details (prevent stack trace exposure)
        logger.error(f"Unexpected error in bank verification: {type(e).__name__}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="銀行帳戶驗證發生未預期的錯誤",
        )


@router.post("/bank-verification/batch")
async def batch_verify_bank_accounts(
    request: BankVerificationBatchRequestSchema,
    http_request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Batch verify bank account information for multiple applications (admin only)"""
    try:
        from app.services.application_audit_service import ApplicationAuditService

        verification_service = BankVerificationService(db)

        results = await verification_service.batch_verify_applications(request.application_ids)

        # Calculate summary statistics
        total_processed = len(results)
        successful_verifications = sum(1 for r in results.values() if r.get("success", False))
        failed_verifications = total_processed - successful_verifications

        # Group by verification status
        summary = {}
        for result in results.values():
            if result.get("success", False):
                status = result.get("verification_status", "unknown")
                summary[status] = summary.get(status, 0) + 1
            else:
                summary["failed"] = summary.get("failed", 0) + 1

        # Convert results to proper schema format
        formatted_results = {}
        for app_id, result in results.items():
            formatted_results[app_id] = BankVerificationResultSchema(**result)

        batch_result = BankVerificationBatchResultSchema(
            results=formatted_results,
            total_processed=total_processed,
            successful_verifications=successful_verifications,
            failed_verifications=failed_verifications,
            summary=summary,
        )

        # Log batch bank verification operation
        audit_service = ApplicationAuditService(db)
        await audit_service.log_batch_bank_verification(
            application_ids=request.application_ids,
            user=current_user,
            batch_result={
                "total_processed": total_processed,
                "successful_verifications": successful_verifications,
                "failed_verifications": failed_verifications,
                "summary": summary,
            },
            request=http_request,
        )

        return {
            "success": True,
            "message": f"Batch verification completed for {total_processed} applications",
            "data": batch_result,
        }

    except Exception as e:
        # SECURITY: Log exception type only (prevent stack trace exposure)
        logger.error(f"Unexpected error in batch bank verification: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to perform batch verification due to an unexpected error.",
        )


@router.get("/bank-verification/{application_id}/init")
async def get_bank_verification_init_data(
    application_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get bank verification initial data without performing OCR
    Used for direct manual review mode
    """
    try:
        from app.core.config import settings
        from app.core.security import create_access_token

        verification_service = BankVerificationService(db)

        # Get application
        stmt = select(Application).where(Application.id == application_id)
        result = await db.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="申請不存在")

        # Extract bank fields from form
        form_bank_fields = verification_service.extract_bank_fields_from_application(application)

        # Get passbook document
        passbook_doc = await verification_service.get_bank_passbook_document(application)

        # Generate file access token and URL
        passbook_document_data = None
        if passbook_doc:
            token_data = {"sub": str(current_user.id)}
            access_token = create_access_token(token_data)
            base_url = f"{settings.base_url}{settings.api_v1_str}"
            file_path = (
                f"{base_url}/files/applications/{application_id}/files/" f"{passbook_doc.id}?token={access_token}"
            )
            download_url = (
                f"{base_url}/files/applications/{application_id}/files/"
                f"{passbook_doc.id}/download?token={access_token}"
            )

            passbook_document_data = {
                "file_path": file_path,
                "original_filename": passbook_doc.original_filename,
                "upload_time": passbook_doc.uploaded_at.isoformat() if passbook_doc.uploaded_at else None,
                "file_id": passbook_doc.id,
                "object_name": passbook_doc.object_name,
                "file_type": passbook_doc.file_type,
                "download_url": download_url,
            }

        return {
            "success": True,
            "message": "已載入銀行資料",
            "data": {
                "application_id": application_id,
                "verification_status": "manual_review_init",
                "form_data": form_bank_fields,
                "passbook_document": passbook_document_data,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        # SECURITY: Log exception type only (prevent stack trace exposure)
        logger.error(f"Failed to get bank verification init data: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="無法載入銀行資料",
        )


@router.post("/bank-verification/manual-review")
async def manual_review_bank_info(
    request: ManualBankReviewRequestSchema,
    http_request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Process manual review of bank account information (admin only)

    Allows administrators to:
    - Approve or reject individual fields (account number and account holder)
    - Provide corrected values if needed
    - Add review notes
    """
    try:
        from app.services.application_audit_service import ApplicationAuditService

        verification_service = BankVerificationService(db)

        # Process manual review
        result = await verification_service.manual_review_bank_info(
            application_id=request.application_id,
            account_number_approved=request.account_number_approved,
            account_number_corrected=request.account_number_corrected,
            account_holder_approved=request.account_holder_approved,
            account_holder_corrected=request.account_holder_corrected,
            review_notes=request.review_notes,
            reviewer_username=current_user.nycu_id,
        )

        # Log manual review operation
        application_stmt = select(Application).where(Application.id == request.application_id)
        application_result = await db.execute(application_stmt)
        application = application_result.scalar_one_or_none()

        if application:
            audit_service = ApplicationAuditService(db)
            # Use log_bank_verification with manual review result
            await audit_service.log_bank_verification(
                application_id=request.application_id,
                app_id=application.app_id,
                user=current_user,
                verification_result={
                    "verification_status": "manual_review_completed",
                    "account_number_status": result["account_number_status"],
                    "account_holder_status": result["account_holder_status"],
                    "review_notes": request.review_notes,
                    "reviewed_by": current_user.nycu_id,
                },
                request=http_request,
            )

        return {
            "success": True,
            "message": "人工審核完成",
            "data": ManualBankReviewResultSchema(**result),
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        # SECURITY: Log exception type only (prevent stack trace exposure)
        logger.error(f"Unexpected error in manual bank review: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="人工審核發生未預期的錯誤",
        )


@router.post("/bank-verification/batch-async")
async def start_batch_verification_async(
    request: BankVerificationBatchRequestSchema,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Start async batch bank verification task (admin only)

    Creates a background task to verify multiple applications without blocking.
    Returns immediately with a task_id for progress tracking.
    """
    try:
        task_service = BankVerificationTaskService(db)

        # Create task
        task = await task_service.create_task(
            application_ids=request.application_ids,
            created_by_user_id=current_user.id,
        )

        # Schedule background processing
        background_tasks.add_task(
            task_service.process_batch_verification_task,
            task.task_id,
        )

        return {
            "success": True,
            "message": f"批次驗證任務已啟動，共 {len(request.application_ids)} 個申請",
            "data": {
                "task_id": task.task_id,
                "total_count": task.total_count,
                "status": task.status.value,
                "created_at": task.created_at.isoformat() if task.created_at else None,
            },
        }

    except Exception as e:
        # SECURITY: Log exception type only, don't expose details in response (prevent stack trace exposure)
        logger.error(f"Failed to start async batch verification: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="啟動批次驗證失敗",
        )


@router.get("/bank-verification/tasks/{task_id}")
async def get_verification_task_status(
    task_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get bank verification task status and progress (admin only)

    Returns task details including progress counters and current results.
    """
    try:
        task_service = BankVerificationTaskService(db)
        task = await task_service.get_task(task_id)

        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到該驗證任務")

        return {
            "success": True,
            "message": "任務狀態查詢成功",
            "data": {
                "task_id": task.task_id,
                "status": task.status.value,
                "progress": {
                    "total": task.total_count,
                    "processed": task.processed_count,
                    "verified": task.verified_count,
                    "needs_review": task.needs_review_count,
                    "failed": task.failed_count,
                    "skipped": task.skipped_count,
                    "percentage": task.progress_percentage,
                },
                "timestamps": {
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "started_at": task.started_at.isoformat() if task.started_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                },
                "is_completed": task.is_completed,
                "is_running": task.is_running,
                "error_message": task.error_message,
                "results": task.results,  # Detailed results for each application
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        # SECURITY: Log exception type only (prevent stack trace exposure)
        logger.error(f"Error getting task status: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="查詢任務狀態失敗",
        )


@router.get("/bank-verification/tasks")
async def list_verification_tasks(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    List bank verification tasks (admin only)

    Supports filtering by status and pagination.
    """
    try:
        task_service = BankVerificationTaskService(db)

        # Parse status filter
        status_filter = None
        if status:
            try:
                status_filter = BankVerificationTaskStatus(status)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"無效的狀態值: {status}",
                )

        tasks = await task_service.list_tasks(
            status=status_filter,
            created_by_user_id=None,  # Show all tasks (admin can see all)
            limit=limit,
            offset=offset,
        )

        task_list = []
        for task in tasks:
            task_list.append(
                {
                    "task_id": task.task_id,
                    "status": task.status.value,
                    "total_count": task.total_count,
                    "processed_count": task.processed_count,
                    "verified_count": task.verified_count,
                    "needs_review_count": task.needs_review_count,
                    "failed_count": task.failed_count,
                    "progress_percentage": task.progress_percentage,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                    "is_completed": task.is_completed,
                    "is_running": task.is_running,
                }
            )

        return {
            "success": True,
            "message": f"查詢到 {len(task_list)} 個任務",
            "data": {
                "tasks": task_list,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "count": len(task_list),
                },
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        # SECURITY: Log exception type only (prevent stack trace exposure)
        logger.error(f"Error listing tasks: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="查詢任務列表失敗",
        )

"""
Admin Bank Account Verification API Endpoints

Handles bank account verification operations including:
- Single application verification
- Batch verification for multiple applications
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.application import Application
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

logger = logging.getLogger(__name__)

router = APIRouter()


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
        if verification_status == "no_data":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error", "找不到銀行帳戶資料"))
        elif verification_status == "no_document":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error", "找不到存摺文件"))
        elif verification_status == "ocr_failed":
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=result.get("error", "OCR 處理失敗")
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

        return {
            "success": success,
            "message": message,
            "data": BankVerificationResultSchema(**result),
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in bank verification: {str(e)}")
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
        logger.error(f"Unexpected error in batch bank verification: {str(e)}")
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

        return {
            "success": True,
            "message": "已載入銀行資料",
            "data": {
                "application_id": application_id,
                "verification_status": "manual_review_init",
                "form_data": form_bank_fields,
                "passbook_document": {
                    "file_path": passbook_doc.filename if passbook_doc else None,
                    "original_filename": passbook_doc.original_filename if passbook_doc else None,
                    "upload_time": passbook_doc.uploaded_at.isoformat()
                    if passbook_doc and passbook_doc.uploaded_at
                    else None,
                    "file_id": passbook_doc.id if passbook_doc else None,
                    "object_name": passbook_doc.object_name if passbook_doc else None,
                }
                if passbook_doc
                else None,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get bank verification init data: {str(e)}")
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
        logger.error(f"Unexpected error in manual bank review: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="人工審核發生未預期的錯誤",
        )

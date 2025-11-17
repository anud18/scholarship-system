"""
Document Request API endpoints
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.security import require_staff, require_student
from app.db.deps import get_db
from app.models.application import Application
from app.models.document_request import DocumentRequest, DocumentRequestStatus
from app.models.user import User
from app.schemas.document_request import (
    DocumentRequestCancel,
    DocumentRequestCreate,
    DocumentRequestFulfill,
    DocumentRequestListItem,
    DocumentRequestResponse,
    StudentDocumentRequestResponse,
)
from app.services.application_audit_service import ApplicationAuditService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/applications/{application_id}/document-requests", status_code=status.HTTP_201_CREATED)
async def create_document_request(
    application_id: int = Path(..., description="Application ID"),
    request_data: DocumentRequestCreate = ...,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Create a document request for an application (staff only)

    Staff members can request additional documents from students for their applications.
    The student will be notified via email and can fulfill the request by uploading documents.
    """
    # Verify application exists
    stmt = select(Application).where(Application.id == application_id)
    result = await db.execute(stmt)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    # Create document request
    document_request = DocumentRequest(
        application_id=application_id,
        requested_by_id=current_user.id,
        requested_at=datetime.now(timezone.utc),
        requested_documents=request_data.requested_documents,
        reason=request_data.reason,
        notes=request_data.notes,
        status=DocumentRequestStatus.pending.value,
    )

    db.add(document_request)
    await db.commit()
    await db.refresh(document_request)

    # Log audit trail
    audit_service = ApplicationAuditService(db)
    # Convert document list to dict format for audit logging
    documents_for_audit = [{"type": doc_type} for doc_type in request_data.requested_documents]
    await audit_service.log_document_request(
        application_id=application_id,
        app_id=application.app_id,
        requested_documents=documents_for_audit,
        user=current_user,
        request_message=request_data.reason,
        request=request,
    )

    # 觸發補件要求事件（會觸發自動化郵件規則）
    try:
        from app.services.email_automation_service import email_automation_service

        # Get student email from application
        stmt_student = (
            select(Application).options(joinedload(Application.student)).where(Application.id == application_id)
        )
        result_student = await db.execute(stmt_student)
        app_with_user = result_student.scalar_one_or_none()

        if app_with_user and app_with_user.student:
            student_data = app_with_user.student_data or {}
            student_email = student_data.get("email") or app_with_user.student.email
            student_name = student_data.get("name") or app_with_user.student.name

            await email_automation_service.trigger_supplement_requested(
                db=db,
                application_id=application.id,
                request_data={
                    "app_id": application.app_id,
                    "student_name": student_name,
                    "student_email": student_email,
                    "requested_documents": request_data.requested_documents,
                    "reason": request_data.reason,
                    "notes": request_data.notes or "",
                    "requester_name": current_user.name or current_user.email,
                    "deadline": "",  # Add if deadline field exists in DocumentRequest model
                    "scholarship_type": application.scholarship_name,
                    "scholarship_type_id": application.scholarship_type_id,
                    "request_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                },
            )
            logger.info(f"Document request automation triggered for {student_email}")
    except Exception as e:
        # Log error but don't fail the request creation
        logger.error(f"Failed to trigger supplement request automation: {e}")

    # Build response
    response_data = DocumentRequestResponse.model_validate(document_request)
    response_data.requested_by_name = current_user.name
    response_data.application_app_id = application.app_id

    return {
        "success": True,
        "message": "文件補件要求已建立",
        "data": response_data.model_dump(),
    }


@router.get("/applications/{application_id}/document-requests")
async def list_application_document_requests(
    application_id: int = Path(..., description="Application ID"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    """
    List all document requests for an application (staff only)

    Returns all document requests made for the specified application,
    optionally filtered by status (pending, fulfilled, cancelled).
    """
    # Verify application exists and user has access
    stmt = select(Application).where(Application.id == application_id)
    result = await db.execute(stmt)
    application = result.scalar_one_or_none()

    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    # Build query for document requests
    stmt = (
        select(DocumentRequest)
        .options(joinedload(DocumentRequest.requested_by))
        .where(DocumentRequest.application_id == application_id)
    )

    if status_filter:
        stmt = stmt.where(DocumentRequest.status == status_filter)

    stmt = stmt.order_by(DocumentRequest.created_at.desc())

    result = await db.execute(stmt)
    document_requests = result.scalars().all()

    # Build response
    response_list = []
    for doc_req in document_requests:
        item = DocumentRequestListItem.model_validate(doc_req)
        item.application_app_id = application.app_id
        item.requested_by_name = doc_req.requested_by.name if doc_req.requested_by else "Unknown"
        response_list.append(item)

    return {
        "success": True,
        "message": "查詢成功",
        "data": [item.model_dump() for item in response_list],
    }


@router.get("/document-requests/my-requests")
async def get_my_document_requests(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all document requests for the current student (student only)

    Returns all pending document requests across all of the student's applications.
    Students can use this to see what additional documents they need to upload.
    """
    # Build query for student's document requests
    stmt = (
        select(DocumentRequest)
        .join(Application, Application.id == DocumentRequest.application_id)
        .options(
            joinedload(DocumentRequest.requested_by),
            joinedload(DocumentRequest.application),
        )
        .where(Application.user_id == current_user.id)
    )

    if status_filter:
        stmt = stmt.where(DocumentRequest.status == status_filter)
    else:
        # By default, only show pending requests for students
        stmt = stmt.where(DocumentRequest.status == DocumentRequestStatus.pending.value)

    stmt = stmt.order_by(DocumentRequest.created_at.desc())

    result = await db.execute(stmt)
    document_requests = result.scalars().all()

    # Build response with application context
    response_list = []
    for doc_req in document_requests:
        item = StudentDocumentRequestResponse(
            id=doc_req.id,
            application_id=doc_req.application_id,
            application_app_id=doc_req.application.app_id,
            scholarship_type_name=doc_req.application.scholarship_name,
            academic_year=doc_req.application.academic_year,
            semester=doc_req.application.semester,
            requested_by_name=doc_req.requested_by.name if doc_req.requested_by else "Unknown",
            requested_at=doc_req.requested_at,
            requested_documents=doc_req.requested_documents,
            reason=doc_req.reason,
            notes=doc_req.notes,
            status=doc_req.status,
            created_at=doc_req.created_at,
        )
        response_list.append(item)

    return {
        "success": True,
        "message": "查詢成功",
        "data": [item.model_dump() for item in response_list],
    }


@router.patch("/document-requests/{request_id}/fulfill")
async def fulfill_document_request(
    request_id: int = Path(..., description="Document request ID"),
    fulfill_data: Optional[DocumentRequestFulfill] = None,
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Mark a document request as fulfilled (student only)

    Students can mark a document request as fulfilled after they have uploaded
    the requested documents. This updates the request status and timestamps.
    """
    # Get document request with application
    stmt = (
        select(DocumentRequest).options(joinedload(DocumentRequest.application)).where(DocumentRequest.id == request_id)
    )
    result = await db.execute(stmt)
    document_request = result.scalar_one_or_none()

    if not document_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document request not found")

    # Verify student owns the application
    if document_request.application.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only fulfill document requests for your own applications",
        )

    # Verify request is in pending status
    if document_request.status != DocumentRequestStatus.pending.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot fulfill request with status: {document_request.status}",
        )

    # Update status to fulfilled
    document_request.status = DocumentRequestStatus.fulfilled.value
    document_request.fulfilled_at = datetime.now(timezone.utc)

    if fulfill_data and fulfill_data.notes:
        document_request.notes = (document_request.notes or "") + f"\n學生備註: {fulfill_data.notes}"

    await db.commit()
    await db.refresh(document_request)

    # Log audit trail
    audit_service = ApplicationAuditService(db)
    await audit_service.log_document_upload(
        application_id=document_request.application_id,
        app_id=document_request.application.app_id,
        file_type="document_request_fulfillment",
        filename="fulfilled",
        file_size=0,
        user=current_user,
        request=request,
    )

    # Build response
    response_data = DocumentRequestResponse.model_validate(document_request)
    response_data.application_app_id = document_request.application.app_id

    return {
        "success": True,
        "message": "文件補件已完成",
        "data": response_data.model_dump(),
    }


@router.patch("/document-requests/{request_id}/cancel")
async def cancel_document_request(
    request_id: int = Path(..., description="Document request ID"),
    cancel_data: DocumentRequestCancel = ...,
    current_user: User = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
):
    """
    Cancel a document request (staff only)

    Staff members can cancel a pending document request if it's no longer needed
    (e.g., application was rejected, or documents were uploaded through another channel).
    """
    # Get document request with application
    stmt = (
        select(DocumentRequest).options(joinedload(DocumentRequest.application)).where(DocumentRequest.id == request_id)
    )
    result = await db.execute(stmt)
    document_request = result.scalar_one_or_none()

    if not document_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document request not found")

    # Verify request is in pending status
    if document_request.status != DocumentRequestStatus.pending.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel request with status: {document_request.status}",
        )

    # Update status to cancelled
    document_request.status = DocumentRequestStatus.cancelled.value
    document_request.cancelled_at = datetime.now(timezone.utc)
    document_request.cancelled_by_id = current_user.id
    document_request.cancellation_reason = cancel_data.cancellation_reason

    await db.commit()
    await db.refresh(document_request)

    # Log audit trail
    audit_service = ApplicationAuditService(db)
    # Create a custom audit log for cancellation
    await audit_service.log_status_update(
        application_id=document_request.application_id,
        app_id=document_request.application.app_id,
        old_status="document_request_pending",
        new_status="document_request_cancelled",
        user=current_user,
        reason=cancel_data.cancellation_reason,
        request=request,
    )

    # Build response
    response_data = DocumentRequestResponse.model_validate(document_request)
    response_data.requested_by_name = document_request.requested_by.name if document_request.requested_by else "Unknown"
    response_data.cancelled_by_name = current_user.name
    response_data.application_app_id = document_request.application.app_id

    return {
        "success": True,
        "message": "文件補件要求已取消",
        "data": response_data.model_dump(),
    }

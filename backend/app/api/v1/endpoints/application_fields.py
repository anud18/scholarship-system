"""
Application field configuration API endpoints
"""

import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.path_security import validate_upload_file
from app.core.security import get_current_user, require_admin
from app.models.application_field import ApplicationDocument
from app.models.user import User
from app.schemas.application_field import (
    ApplicationDocumentCreate,
    ApplicationDocumentResponse,
    ApplicationDocumentUpdate,
    ApplicationFieldCreate,
    ApplicationFieldResponse,
    ApplicationFieldUpdate,
    ScholarshipFormConfigResponse,
)
from app.schemas.response import ApiResponse
from app.services.application_field_service import ApplicationFieldService

router = APIRouter()
logger = logging.getLogger(__name__)


# Application Field endpoints
@router.get("/fields/{scholarship_type}")
async def get_fields_by_scholarship_type(
    scholarship_type: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Get all fields for a scholarship type"""
    service = ApplicationFieldService(db)
    fields = await service.get_fields_by_scholarship_type(scholarship_type)

    return ApiResponse(success=True, message=f"Fields retrieved for {scholarship_type}", data=fields)


@router.post("/fields")
async def create_field(
    field_data: ApplicationFieldCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """Create a new application field"""
    service = ApplicationFieldService(db)
    field = await service.create_field(field_data, current_user.id)

    return ApiResponse(success=True, message="Application field created successfully", data=field)


@router.put("/fields/{field_id}")
async def update_field(
    field_id: int,
    field_data: ApplicationFieldUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update an application field"""
    service = ApplicationFieldService(db)
    field = await service.update_field(field_id, field_data, current_user.id)

    if not field:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application field not found")

    return ApiResponse(success=True, message="Application field updated successfully", data=field)


@router.delete("/fields/{field_id}")
async def delete_field(field_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """Delete an application field"""
    service = ApplicationFieldService(db)
    success = await service.delete_field(field_id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application field not found")

    return ApiResponse(success=True, message="Application field deleted successfully", data=True)


# Application Document endpoints
@router.get("/documents/{scholarship_type}")
async def get_documents_by_scholarship_type(
    scholarship_type: str, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    """Get all documents for a scholarship type"""
    service = ApplicationFieldService(db)
    documents = await service.get_documents_by_scholarship_type(scholarship_type)

    return ApiResponse(success=True, message=f"Documents retrieved for {scholarship_type}", data=documents)


@router.post("/documents")
async def create_document(
    document_data: ApplicationDocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Create a new application document"""
    service = ApplicationFieldService(db)
    document = await service.create_document(document_data, current_user.id)

    return ApiResponse(success=True, message="Application document created successfully", data=document)


@router.put("/documents/{document_id}")
async def update_document(
    document_id: int,
    document_data: ApplicationDocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update an application document"""
    service = ApplicationFieldService(db)
    document = await service.update_document(document_id, document_data, current_user.id)

    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application document not found")

    return ApiResponse(success=True, message="Application document updated successfully", data=document)


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """Delete an application document"""
    service = ApplicationFieldService(db)
    success = await service.delete_document(document_id)

    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application document not found")

    return ApiResponse(success=True, message="Application document deleted successfully", data=True)


# Combined form configuration endpoints
@router.get("/form-config/{scholarship_type}")
async def get_scholarship_form_config(
    scholarship_type: str,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get complete form configuration for a scholarship type"""
    try:
        logger.debug(f"API: Getting form config for {scholarship_type}")
        service = ApplicationFieldService(db)

        # 管理員可以看到所有欄位（包括停用的），其他用戶只能看到啟用的
        is_admin = current_user.role in ["admin", "super_admin"]
        should_include_inactive = include_inactive or is_admin

        config = await service.get_scholarship_form_config(
            scholarship_type, should_include_inactive, user_id=current_user.id
        )

        logger.info(f"API: Form config retrieved successfully for {scholarship_type}")
        return ApiResponse(success=True, message=f"Form configuration retrieved for {scholarship_type}", data=config)
    except Exception as e:
        logger.error(f"API: Error getting form config for {scholarship_type}: {str(e)}")
        # 返回空的配置而不是拋出異常
        empty_config = ScholarshipFormConfigResponse(scholarship_type=scholarship_type, fields=[], documents=[])
        return ApiResponse(
            success=True, message=f"Form configuration retrieved for {scholarship_type} (empty)", data=empty_config
        )


class FormConfigSaveRequest(BaseModel):
    """Schema for saving form configuration"""

    fields: List[Dict[str, Any]]
    documents: List[Dict[str, Any]]


@router.post("/form-config/{scholarship_type}")
async def save_scholarship_form_config(
    scholarship_type: str,
    config_data: FormConfigSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Save complete form configuration for a scholarship type"""
    service = ApplicationFieldService(db)

    config = await service.save_scholarship_form_config(
        scholarship_type=scholarship_type,
        fields_data=config_data.fields,
        documents_data=config_data.documents,
        user_id=current_user.id,
    )

    return ApiResponse(success=True, message=f"Form configuration saved for {scholarship_type}", data=config)


# Example file management endpoints
@router.post("/documents/{document_id}/upload-example")
async def upload_document_example(
    document_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload example file for an application document

    Args:
        document_id: Application document ID
        file: Example file to upload
        current_user: Current authenticated admin user
        db: Database session

    Returns:
        ApiResponse with uploaded file object name
    """
    # SECURITY: Comprehensive file validation (CLAUDE.md triple validation)
    # Read file first for size validation
    file_content = await file.read()
    file_size = len(file_content)

    validate_upload_file(
        filename=file.filename,
        allowed_extensions=[".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"],
        max_size_mb=10,
        file_size=file_size,
        allow_unicode=True,
    )

    # Get document from database
    stmt = select(ApplicationDocument).where(ApplicationDocument.id == document_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Application document not found")

    try:
        from app.services.minio_service import minio_service

        # Generate object name with timestamp
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_extension = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "pdf"
        object_name = f"examples/document_{document_id}_{timestamp}.{file_extension}"

        # Note: file_content already read above for validation

        # Upload to MinIO
        minio_service.client.put_object(
            bucket_name=minio_service.default_bucket,
            object_name=object_name,
            data=io.BytesIO(file_content),
            length=len(file_content),
            content_type=file.content_type or "application/octet-stream",
        )

        # Delete old example file if exists
        if document.example_file_url:
            try:
                minio_service.client.remove_object(
                    bucket_name=minio_service.default_bucket, object_name=document.example_file_url
                )
            except Exception as e:
                logger.warning(f"Failed to delete old example file: {str(e)}")

        # Update database with new object name
        document.example_file_url = object_name
        document.updated_by = current_user.id
        await db.commit()

        return ApiResponse(success=True, message="範例文件上傳成功", data={"example_file_url": object_name})

    except Exception as e:
        logger.error(f"Failed to upload example file: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"範例文件上傳失敗: {str(e)}")


@router.get("/documents/{document_id}/example")
async def get_document_example(
    document_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Get example file for an application document and proxy download from MinIO

    Args:
        document_id: Application document ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Streaming response with file content
    """
    # Get document from database
    stmt = select(ApplicationDocument).where(ApplicationDocument.id == document_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document or not document.example_file_url:
        raise HTTPException(status_code=404, detail="範例文件不存在")

    try:
        from app.services.minio_service import minio_service

        # Download from MinIO
        response = minio_service.client.get_object(
            bucket_name=minio_service.default_bucket, object_name=document.example_file_url
        )

        file_content = response.read()

        # Determine content type based on file extension
        file_extension = document.example_file_url.rsplit(".", 1)[-1].lower()
        content_type_map = {
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
        }
        content_type = content_type_map.get(file_extension, "application/octet-stream")

        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename*=UTF-8''{document.document_name}_example.{file_extension}"
            },
        )

    except Exception as e:
        logger.error(f"Failed to get example file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"範例文件讀取失敗: {str(e)}")


@router.delete("/documents/{document_id}/example")
async def delete_document_example(
    document_id: int, current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """
    Delete example file for an application document

    Args:
        document_id: Application document ID
        current_user: Current authenticated admin user
        db: Database session

    Returns:
        ApiResponse with success status
    """
    # Get document from database
    stmt = select(ApplicationDocument).where(ApplicationDocument.id == document_id)
    result = await db.execute(stmt)
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Application document not found")

    if not document.example_file_url:
        raise HTTPException(status_code=404, detail="範例文件不存在")

    try:
        from app.services.minio_service import minio_service

        # Delete from MinIO
        minio_service.client.remove_object(
            bucket_name=minio_service.default_bucket, object_name=document.example_file_url
        )

        # Clear database field
        document.example_file_url = None
        document.updated_by = current_user.id
        await db.commit()

        return ApiResponse(success=True, message="範例文件刪除成功", data=True)

    except Exception as e:
        logger.error(f"Failed to delete example file: {str(e)}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"範例文件刪除失敗: {str(e)}")

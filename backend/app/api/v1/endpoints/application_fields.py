"""
Application field configuration API endpoints
"""

import logging
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.core.deps import get_db
from app.core.security import require_admin, get_current_user
from app.models.user import User
from app.services.application_field_service import ApplicationFieldService
from app.schemas.application_field import (
    ApplicationFieldCreate, ApplicationFieldUpdate, ApplicationFieldResponse,
    ApplicationDocumentCreate, ApplicationDocumentUpdate, ApplicationDocumentResponse,
    ScholarshipFormConfigResponse
)
from app.schemas.response import ApiResponse

router = APIRouter()
logger = logging.getLogger(__name__)


# Application Field endpoints
@router.get("/fields/{scholarship_type}", response_model=ApiResponse[List[ApplicationFieldResponse]])
async def get_fields_by_scholarship_type(
    scholarship_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all fields for a scholarship type"""
    service = ApplicationFieldService(db)
    fields = await service.get_fields_by_scholarship_type(scholarship_type)
    
    return ApiResponse(
        success=True,
        message=f"Fields retrieved for {scholarship_type}",
        data=fields
    )


@router.post("/fields", response_model=ApiResponse[ApplicationFieldResponse])
async def create_field(
    field_data: ApplicationFieldCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new application field"""
    service = ApplicationFieldService(db)
    field = await service.create_field(field_data, current_user.id)
    
    return ApiResponse(
        success=True,
        message="Application field created successfully",
        data=field
    )


@router.put("/fields/{field_id}", response_model=ApiResponse[ApplicationFieldResponse])
async def update_field(
    field_id: int,
    field_data: ApplicationFieldUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update an application field"""
    service = ApplicationFieldService(db)
    field = await service.update_field(field_id, field_data, current_user.id)
    
    if not field:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application field not found"
        )
    
    return ApiResponse(
        success=True,
        message="Application field updated successfully",
        data=field
    )


@router.delete("/fields/{field_id}", response_model=ApiResponse[bool])
async def delete_field(
    field_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete an application field"""
    service = ApplicationFieldService(db)
    success = await service.delete_field(field_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application field not found"
        )
    
    return ApiResponse(
        success=True,
        message="Application field deleted successfully",
        data=True
    )


# Application Document endpoints
@router.get("/documents/{scholarship_type}", response_model=ApiResponse[List[ApplicationDocumentResponse]])
async def get_documents_by_scholarship_type(
    scholarship_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all documents for a scholarship type"""
    service = ApplicationFieldService(db)
    documents = await service.get_documents_by_scholarship_type(scholarship_type)
    
    return ApiResponse(
        success=True,
        message=f"Documents retrieved for {scholarship_type}",
        data=documents
    )


@router.post("/documents", response_model=ApiResponse[ApplicationDocumentResponse])
async def create_document(
    document_data: ApplicationDocumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Create a new application document"""
    service = ApplicationFieldService(db)
    document = await service.create_document(document_data, current_user.id)
    
    return ApiResponse(
        success=True,
        message="Application document created successfully",
        data=document
    )


@router.put("/documents/{document_id}", response_model=ApiResponse[ApplicationDocumentResponse])
async def update_document(
    document_id: int,
    document_data: ApplicationDocumentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update an application document"""
    service = ApplicationFieldService(db)
    document = await service.update_document(document_id, document_data, current_user.id)
    
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application document not found"
        )
    
    return ApiResponse(
        success=True,
        message="Application document updated successfully",
        data=document
    )


@router.delete("/documents/{document_id}", response_model=ApiResponse[bool])
async def delete_document(
    document_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Delete an application document"""
    service = ApplicationFieldService(db)
    success = await service.delete_document(document_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application document not found"
        )
    
    return ApiResponse(
        success=True,
        message="Application document deleted successfully",
        data=True
    )


# Combined form configuration endpoints
@router.get("/form-config/{scholarship_type}", response_model=ApiResponse[ScholarshipFormConfigResponse])
async def get_scholarship_form_config(
    scholarship_type: str,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get complete form configuration for a scholarship type"""
    try:
        logger.debug(f"API: Getting form config for {scholarship_type}")
        service = ApplicationFieldService(db)
        
        # 管理員可以看到所有欄位（包括停用的），其他用戶只能看到啟用的
        is_admin = current_user.role in ["admin", "super_admin"]
        should_include_inactive = include_inactive or is_admin
        
        config = await service.get_scholarship_form_config(
            scholarship_type, 
            should_include_inactive,
            user_id=current_user.id
        )
        
        logger.info(f"API: Form config retrieved successfully for {scholarship_type}")
        return ApiResponse(
            success=True,
            message=f"Form configuration retrieved for {scholarship_type}",
            data=config
        )
    except Exception as e:
        logger.error(f"API: Error getting form config for {scholarship_type}: {str(e)}")
        # 返回空的配置而不是拋出異常
        empty_config = ScholarshipFormConfigResponse(
            scholarship_type=scholarship_type,
            fields=[],
            documents=[]
        )
        return ApiResponse(
            success=True,
            message=f"Form configuration retrieved for {scholarship_type} (empty)",
            data=empty_config
        )


class FormConfigSaveRequest(BaseModel):
    """Schema for saving form configuration"""
    fields: List[Dict[str, Any]]
    documents: List[Dict[str, Any]]


@router.post("/form-config/{scholarship_type}", response_model=ApiResponse[ScholarshipFormConfigResponse])
async def save_scholarship_form_config(
    scholarship_type: str,
    config_data: FormConfigSaveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Save complete form configuration for a scholarship type"""
    service = ApplicationFieldService(db)
    
    config = await service.save_scholarship_form_config(
        scholarship_type=scholarship_type,
        fields_data=config_data.fields,
        documents_data=config_data.documents,
        user_id=current_user.id
    )
    
    return ApiResponse(
        success=True,
        message=f"Form configuration saved for {scholarship_type}",
        data=config
    ) 
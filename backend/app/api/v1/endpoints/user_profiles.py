"""
User Profile Management API endpoints
"""

import base64
import io
import logging
import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_admin
from app.db.deps import get_db
from app.models.user import User
from app.schemas.user_profile import (
    AdvisorInfoUpdate,
    BankDocumentPhotoUpload,
    BankInfoUpdate,
    ProfileHistoryResponse,
    UserProfileCreate,
    UserProfileResponse,
    UserProfileUpdate,
)
from app.services.user_profile_service import UserProfileService

router = APIRouter()
logger = logging.getLogger(__name__)


def get_client_info(request: Request) -> tuple[Optional[str], Optional[str]]:
    """Extract client IP address and user agent from request"""
    # Get real IP address (considering proxy headers)
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.headers.get("X-Real-IP")
        or request.client.host
        if request.client
        else None
    )

    user_agent = request.headers.get("User-Agent")

    return client_ip, user_agent


@router.get("/me")
async def get_my_profile(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get current user's complete profile (read-only + editable data)"""
    service = UserProfileService(db)
    profile = await service.get_complete_user_profile(current_user)

    return {"success": True, "message": "個人資料獲取成功", "data": profile}


@router.post("/me", status_code=status.HTTP_201_CREATED)
async def create_my_profile(
    profile_data: UserProfileCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create user profile for current user"""
    service = UserProfileService(db)
    client_ip, user_agent = get_client_info(request)

    try:
        profile = await service.create_user_profile(
            user_id=current_user.id,
            profile_data=profile_data,
            ip_address=client_ip,
            user_agent=user_agent,
        )

        return {
            "success": True,
            "message": "個人資料建立成功",
            "data": UserProfileResponse.model_validate(profile),
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.put("/me")
async def update_my_profile(
    profile_data: UserProfileUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile"""
    service = UserProfileService(db)
    client_ip, user_agent = get_client_info(request)

    profile = await service.update_user_profile(
        user_id=current_user.id,
        profile_data=profile_data,
        change_reason="使用者主動更新個人資料",
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return {
        "success": True,
        "message": "個人資料更新成功",
        "data": UserProfileResponse.model_validate(profile),
    }


@router.put("/me/bank-info")
async def update_my_bank_info(
    bank_data: BankInfoUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's bank account information"""
    service = UserProfileService(db)
    client_ip, user_agent = get_client_info(request)

    # Convert to UserProfileUpdate
    update_data = UserProfileUpdate(bank_code=bank_data.bank_code, account_number=bank_data.account_number)

    profile = await service.update_user_profile(
        user_id=current_user.id,
        profile_data=update_data,
        change_reason=bank_data.change_reason or "更新銀行帳戶資訊",
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return {
        "success": True,
        "message": "銀行帳戶資訊更新成功",
        "data": {
            "bank_code": profile.bank_code,
            "account_number": profile.account_number,
            "bank_document_photo_url": profile.bank_document_photo_url,
            "has_complete_bank_info": profile.has_complete_bank_info,
        },
    }


@router.put("/me/advisor-info")
async def update_my_advisor_info(
    advisor_data: AdvisorInfoUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's advisor information"""
    service = UserProfileService(db)
    client_ip, user_agent = get_client_info(request)

    # Convert to UserProfileUpdate
    update_data = UserProfileUpdate(
        advisor_name=advisor_data.advisor_name,
        advisor_email=advisor_data.advisor_email,
        advisor_nycu_id=advisor_data.advisor_nycu_id,
    )

    profile = await service.update_user_profile(
        user_id=current_user.id,
        profile_data=update_data,
        change_reason=advisor_data.change_reason or "更新指導教授資訊",
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return {
        "success": True,
        "message": "指導教授資訊更新成功",
        "data": {
            "advisor_name": profile.advisor_name,
            "advisor_email": profile.advisor_email,
            "advisor_nycu_id": profile.advisor_nycu_id,
            "has_advisor_info": profile.has_advisor_info,
        },
    }


@router.post("/me/bank-document")
async def upload_bank_document(
    photo_data: str,
    filename: str,
    content_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload bank document photo (base64 encoded)"""
    service = UserProfileService(db)

    try:
        document_upload = BankDocumentPhotoUpload(photo_data=photo_data, filename=filename, content_type=content_type)

        document_url = await service.upload_bank_document_to_minio(
            user_id=current_user.id, document_upload=document_upload
        )

        return {
            "success": True,
            "message": "銀行帳戶證明文件上傳成功",
            "data": {"document_url": document_url},
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/me/bank-document/file")
async def upload_bank_document_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload bank document via file upload"""
    service = UserProfileService(db)

    logger.info(
        f"Bank document upload request - File: {file.filename}, Content-Type: {file.content_type}, User ID: {current_user.id}"
    )

    # Validate file type - accept images and PDF
    accepted_types = ["image/", "application/pdf"]
    if not file.content_type or not any(file.content_type.startswith(t) for t in accepted_types):
        logger.warning(f"File type rejected: {file.content_type}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"只接受圖片檔案 (JPG, PNG, WebP) 或 PDF 文件。收到: {file.content_type}",
        )

    # Validate file size (max 10MB)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    file_content = await file.read()
    logger.debug(f"File size: {len(file_content)} bytes")

    if len(file_content) > MAX_FILE_SIZE:
        logger.warning(f"File too large: {len(file_content)} > {MAX_FILE_SIZE}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"檔案大小不能超過10MB。當前檔案: {len(file_content)/1024/1024:.1f}MB",
        )

    try:
        # Convert to base64
        document_data_base64 = base64.b64encode(file_content).decode("utf-8")
        logger.debug(f"Base64 data length: {len(document_data_base64)}")

        document_upload = BankDocumentPhotoUpload(
            photo_data=document_data_base64,
            filename=file.filename or "bank_document.jpg",
            content_type=file.content_type,
        )
        logger.debug("Created BankDocumentPhotoUpload successfully")

        document_url = await service.upload_bank_document_to_minio(
            user_id=current_user.id, document_upload=document_upload
        )
        logger.info(f"Upload to MinIO successful: {document_url}")

        return {
            "success": True,
            "message": "銀行帳戶證明文件上傳成功",
            "data": {"document_url": document_url},
        }
    except ValueError as e:
        logger.error(f"ValueError in upload: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in upload: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"上傳失敗: {str(e)}")


@router.delete("/me/bank-document")
async def delete_bank_document(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Delete bank document"""
    service = UserProfileService(db)

    success = await service.delete_bank_document(current_user.id)

    if success:
        return {"success": True, "message": "銀行帳戶證明文件刪除成功"}
    else:
        return {"success": False, "message": "沒有找到銀行帳戶證明文件"}


@router.get("/me/history")
async def get_my_profile_history(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get profile change history"""
    service = UserProfileService(db)
    history = await service.get_profile_history(current_user.id)

    return {
        "success": True,
        "message": "異動紀錄獲取成功",
        "data": [ProfileHistoryResponse.model_validate(entry) for entry in history],
    }


@router.delete("/me")
async def delete_my_profile(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Delete current user's profile data"""
    service = UserProfileService(db)

    success = await service.delete_user_profile(current_user.id)

    if success:
        return {"success": True, "message": "個人資料刪除成功"}
    else:
        return {"success": False, "message": "沒有找到個人資料"}


# ==================== File serving endpoint ====================


@router.get("/files/bank_documents/{filename}")
async def get_bank_document(filename: str, db: AsyncSession = Depends(get_db)):
    """Serve bank documents from MinIO"""
    # Validate filename to prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="無效的檔案名稱")

    # Additional validation: ensure filename only contains allowed characters
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="檔案名稱包含無效字元")

    try:
        # Try to serve from MinIO first (new approach)
        # We need to figure out the full object path from the filename
        # For now, we'll try to find it by searching for the filename in user profile records
        from sqlalchemy import select

        from app.models.user_profile import UserProfile
        from app.services.minio_service import minio_service

        # Search for the document in user profiles
        stmt = select(UserProfile).where(UserProfile.bank_document_photo_url.like(f"%{filename}%"))
        result = await db.execute(stmt)
        profile = result.scalar_one_or_none()

        if profile:
            # Try to construct the MinIO object path
            # Format: user-profiles/{user_id}/bank-documents/{filename}
            object_name = f"user-profiles/{profile.user_id}/bank-documents/{filename}"

            try:
                # Get file from MinIO
                response = minio_service.get_file_stream(object_name)

                # Determine content type
                content_type = "application/octet-stream"
                if filename.lower().endswith((".jpg", ".jpeg")):
                    content_type = "image/jpeg"
                elif filename.lower().endswith(".png"):
                    content_type = "image/png"
                elif filename.lower().endswith(".webp"):
                    content_type = "image/webp"
                elif filename.lower().endswith(".pdf"):
                    content_type = "application/pdf"

                return StreamingResponse(
                    io.BytesIO(response.read()),
                    media_type=content_type,
                    headers={
                        "Content-Disposition": f"inline; filename={filename}",
                        "Cache-Control": "max-age=3600",  # Cache for 1 hour
                    },
                )

            except Exception:
                # If MinIO fails, try fallback to local storage
                pass

        # Fallback to local storage (backward compatibility)
        upload_base = os.environ.get("UPLOAD_BASE_DIR", "uploads")
        bank_docs_dir = os.environ.get("BANK_DOCUMENTS_DIR", "bank_documents")
        file_path = os.path.join(upload_base, bank_docs_dir, filename)

        # Ensure the resolved path is still within the expected directory
        resolved_path = os.path.abspath(file_path)
        expected_dir = os.path.abspath(os.path.join(upload_base, bank_docs_dir))
        if not resolved_path.startswith(expected_dir):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="存取被拒絕")

        if not os.path.exists(resolved_path):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="證明文件不存在")

        return FileResponse(resolved_path)

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="檔案服務發生錯誤")


# ==================== Admin endpoints ====================


@router.get("/admin/incomplete", dependencies=[Depends(require_admin)])
async def get_incomplete_profiles(current_user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    """Get users with incomplete profiles (admin only)"""
    service = UserProfileService(db)
    incomplete_users = await service.get_users_with_incomplete_profiles()

    return {
        "success": True,
        "message": "不完整個人資料列表獲取成功",
        "data": {"total_incomplete": len(incomplete_users), "users": incomplete_users},
    }


@router.get("/admin/{user_id}", dependencies=[Depends(require_admin)])
async def get_user_profile_by_id(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get user profile by ID (admin only)"""
    # Get the target user
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.id == user_id))
    target_user = result.scalar_one_or_none()

    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="使用者不存在")

    service = UserProfileService(db)
    profile = await service.get_complete_user_profile(target_user)

    return {"success": True, "message": "使用者個人資料獲取成功", "data": profile}


@router.get("/admin/{user_id}/history", dependencies=[Depends(require_admin)])
async def get_user_profile_history_by_id(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get user profile history by ID (admin only)"""
    service = UserProfileService(db)
    history = await service.get_profile_history(user_id)

    return {
        "success": True,
        "message": "使用者個人資料異動紀錄獲取成功",
        "data": [ProfileHistoryResponse.model_validate(entry) for entry in history],
    }

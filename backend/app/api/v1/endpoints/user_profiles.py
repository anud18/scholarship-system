"""
User Profile Management API endpoints
"""

import base64
import io
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.path_security import validate_filename_strict
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
from app.services.ocr_service import get_ocr_service
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
    update_data = UserProfileUpdate(account_number=bank_data.account_number)

    profile = await service.update_user_profile(
        user_id=current_user.id,
        profile_data=update_data,
        change_reason=bank_data.change_reason or "更新銀行帳戶資訊",
        ip_address=client_ip,
        user_agent=user_agent,
    )

    return {
        "success": True,
        "message": "郵局帳號資訊更新成功",
        "data": {
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
        f"Bank document upload request - File: {file.filename}, "
        f"Content-Type: {file.content_type}, User ID: {current_user.id}"
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
    # SECURITY: Comprehensive filename validation (CLAUDE.md triple validation)
    validate_filename_strict(filename, allow_unicode=True)

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
        storage_directory = os.path.join(upload_base, bank_docs_dir)

        # SECURITY: Break CodeQL taint flow by validating against directory listing
        # Filename is already validated by validate_filename_strict() above
        # Now check if it exists in the directory (source of truth is filesystem, not user input)
        if not os.path.exists(storage_directory):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="儲存目錄不存在")

        # List all files in the directory
        try:
            available_files = os.listdir(storage_directory)
        except OSError:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="無法讀取儲存目錄")

        # Check if the requested file exists in the directory
        # This breaks taint flow: we're using the filename from directory listing, not from user input
        if filename not in available_files:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="證明文件不存在")

        # Get the safe filename from the directory listing (breaks taint flow)
        safe_filename = available_files[available_files.index(filename)]

        # Construct path using the safe filename from directory listing
        file_path = os.path.join(storage_directory, safe_filename)

        return FileResponse(file_path)

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


@router.post("/bank-passbook-ocr")
async def extract_bank_info_from_passbook(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Extract bank account information from passbook image using Gemini OCR

    This endpoint accepts an image file of a bank passbook and uses Google's Gemini AI
    to extract bank account details like bank name, bank code, account number, etc.
    """
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be an image (JPEG, PNG, etc.)",
            )

        # Check file size (max 10MB)
        file_content = await file.read()
        if len(file_content) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size must be less than 10MB",
            )

        # Get OCR service
        try:
            ocr_service = get_ocr_service()
        except Exception as e:
            logger.error(f"OCR service initialization failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OCR service is not available. Please contact administrator.",
            )

        # Extract bank information
        try:
            result = await ocr_service.extract_bank_info_from_image(file_content)

            # Log successful extraction or failure
            logger.info(
                f"Bank OCR completed for user {current_user.id} with confidence: {result.get('confidence', 0)}; Success: {result.get('success', False)}"
            )

            # SECURITY: Explicitly whitelist safe fields to avoid exposing error details
            safe_result = {
                "success": result.get("success", False),
                "confidence": result.get("confidence"),
                "bank_name": result.get("bank_name"),
                "bank_code": result.get("bank_code"),
                "branch_name": result.get("branch_name"),
                "branch_code": result.get("branch_code"),
                "account_number": result.get("account_number"),
                "account_holder": result.get("account_holder"),
                "extracted_text": result.get("extracted_text"),
            }

            # Only return data if extraction was successful
            if result.get("success", False):
                response_data = {
                    "success": True,
                    "message": "銀行資訊提取成功",
                    "data": safe_result,
                }
                # Add suggestion for manual review if confidence is low
                if result.get("confidence", 0) < 0.8:
                    response_data["warning"] = "提取結果信心度較低，建議人工檢查提取的資訊是否正確"
                return response_data
            else:
                # Do not expose any internal error information, show generic message
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="無法辨識銀行資訊。請確認圖片格式正確且清晰可讀。",
                )

        except Exception as e:
            logger.error(f"Bank OCR failed for user {current_user.id}: {str(e)}")
            # SECURITY: Don't expose internal error details to client
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="無法處理圖片。請確認圖片格式正確且清晰可讀。",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in bank OCR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during processing",
        )


@router.post("/document-ocr")
async def extract_text_from_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Extract text from any document image using Gemini OCR

    This endpoint accepts an image file and uses Google's Gemini AI
    to extract all visible text content.
    """
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must be an image (JPEG, PNG, etc.)",
            )

        # Check file size (max 10MB)
        file_content = await file.read()
        if len(file_content) > 10 * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File size must be less than 10MB",
            )

        # Get OCR service
        try:
            ocr_service = get_ocr_service()
        except Exception as e:
            logger.error(f"OCR service initialization failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="OCR service is not available. Please contact administrator.",
            )

        # Extract text
        try:
            result = await ocr_service.extract_general_text_from_image(file_content)

            # Log successful extraction
            logger.info(
                f"Document OCR completed for user {current_user.id} with confidence: {result.get('confidence', 0)}"
            )

            # SECURITY: Explicitly whitelist safe fields to avoid exposing error details
            safe_result = {
                "success": result.get("success", False),
                "confidence": result.get("confidence"),
                "extracted_text": result.get("extracted_text"),
            }

            return {
                "success": True,
                "message": "文字提取成功" if result.get("success") else "文字提取失敗",
                "data": safe_result,
            }

        except Exception as e:
            logger.error(f"Document OCR failed for user {current_user.id}: {str(e)}")
            # SECURITY: Don't expose internal error details to client
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="無法處理圖片。請確認圖片格式正確且清晰可讀。",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in document OCR: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during processing",
        )

"""
File proxy endpoints for secure file access
"""

import logging
import os
import urllib.parse
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import verify_token
from app.db.deps import get_db
from app.models.application import Application, ApplicationFile
from app.models.user import User, UserRole
from app.services.auth_service import AuthService
from app.services.minio_service import minio_service
from app.utils.application_helpers import get_college_code_from_data

logger = logging.getLogger(__name__)
router = APIRouter()

# SECURITY: never echo the client-supplied MIME type back on our own origin.
# ApplicationFile.mime_type / .content_type are persisted verbatim from the
# uploader's multipart part header (application_service.py), and upload
# validation only checks the file *extension*. Serving an attacker-chosen
# "text/html" or "image/svg+xml" with Content-Disposition: inline would execute
# script same-origin against a reviewer's session — and this FastAPI response
# bypasses the Next.js middleware CSP entirely. Derive the type from the
# already-validated extension instead, and fall back to a non-renderable type.
_SAFE_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_FALLBACK_CONTENT_TYPE = "application/octet-stream"


def _safe_content_type(filename: Optional[str]) -> str:
    """Map a stored filename to a safe, non-scriptable Content-Type."""
    _, ext = os.path.splitext((filename or "").strip().rstrip(". ").lower())
    return _SAFE_CONTENT_TYPES.get(ext, _FALLBACK_CONTENT_TYPE)


def _assert_college_may_access(current_user: User, application: Application, file_id: int) -> None:
    """Restrict a 學院 reviewer to applications from their own college.

    The project's access model scopes college staff by ``std_academyno`` (see
    college_review_service). This branch previously fell through to an
    unconditional ``pass`` for UserRole.college, letting College-A staff stream
    any other college's transcripts and bank passbooks by walking file ids.
    """
    user_college = (current_user.college_code or "").strip()
    owner_college = (get_college_code_from_data(application.student_data or {}) or "").strip()
    if not user_college or user_college != owner_college:
        logger.warning(
            "SECURITY: college user attempted cross-college file access",
            extra={
                "user_id": current_user.id,
                "user_college": user_college,
                "owner_college": owner_college,
                "file_id": file_id,
                "application_id": application.id,
            },
        )
        # 404 rather than 403 so the response does not confirm the file exists.
        raise HTTPException(status_code=404, detail="File not found")


@router.get("/applications/{application_id}/files/{file_id}")
async def get_file_proxy(
    application_id: int = Path(..., description="Application ID"),
    file_id: int = Path(..., description="File ID"),
    # JWTs from this system are dot-separated base64url segments. Constrain
    # length + charset at the FastAPI layer so malformed / oversized strings
    # 422 before they reach verify_token() and get DoS-tested for free.
    token: Optional[str] = Query(None, description="Access token", max_length=2048, pattern=r"^[A-Za-z0-9._-]+$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Proxy endpoint to securely serve files from MinIO
    """
    try:
        # Manual token verification for direct file access
        if not token:
            raise HTTPException(status_code=401, detail="Access token required")

        try:
            payload = verify_token(token)
            user_id = int(payload.get("sub"))
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid token") from exc

        # Get user from token
        auth_service = AuthService(db)
        user_result = await auth_service.get_user_by_id(user_id)
        if not user_result:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")

        current_user = user_result

        # Verify file exists and user has access
        stmt = (
            select(ApplicationFile)
            .options(selectinload(ApplicationFile.application))
            .join(Application)
            .where(and_(ApplicationFile.id == file_id, Application.id == application_id))
        )
        result = await db.execute(stmt)
        file_record = result.scalar_one_or_none()

        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")

        # Check access permissions
        application = file_record.application

        # Check access permissions based on role
        if current_user.role == UserRole.student:
            # Students can only access their own files
            if application.user_id != current_user.id:
                logger.warning(
                    "SECURITY: student attempted to access another user's file",
                    extra={
                        "user_id": current_user.id,
                        "file_id": file_id,
                        "owner_user_id": application.user_id,
                        "application_id": application.id,
                    },
                )
                raise HTTPException(status_code=403, detail="Access denied")
        elif current_user.role == UserRole.professor:
            # Professors can access files from their students
            if not current_user.can_access_student_data(application.user_id, "view_applications"):
                logger.warning(
                    "SECURITY: professor lacked relationship to access student file",
                    extra={
                        "user_id": current_user.id,
                        "file_id": file_id,
                        "student_user_id": application.user_id,
                        "application_id": application.id,
                    },
                )
                raise HTTPException(status_code=403, detail="Access denied - no relationship with student")
        elif current_user.role == UserRole.college:
            # College staff are scoped to their own college's applicants.
            _assert_college_may_access(current_user, application, file_id)
        elif current_user.role in (UserRole.admin, UserRole.super_admin):
            # Admin and Super Admin can access any file
            pass
        else:
            # Other roles are not allowed
            logger.warning(
                "SECURITY: unexpected role attempted file access",
                extra={
                    "user_id": current_user.id,
                    "role": str(current_user.role),
                    "file_id": file_id,
                },
            )
            raise HTTPException(status_code=403, detail="Access denied")

        # Get file stream from MinIO
        if not file_record.object_name:
            raise HTTPException(status_code=404, detail="File object not found")

        file_stream = minio_service.get_file_stream(file_record.object_name)

        # Determine content type from the validated extension, never from the
        # client-supplied MIME stored at upload time (see _safe_content_type).
        content_type = _safe_content_type(file_record.filename)

        # Create streaming response
        def generate():
            try:
                for chunk in file_stream.stream(1024 * 1024):  # 1MB chunks
                    yield chunk
            finally:
                file_stream.close()
                file_stream.release_conn()

        # Handle filename encoding for non-ASCII characters (e.g., Chinese)
        encoded_filename = urllib.parse.quote(file_record.filename, safe="")

        # Only render inline for types we recognise as safe; anything unknown is
        # forced to download so the browser never renders it in our origin.
        disposition = "inline" if content_type != _FALLBACK_CONTENT_TYPE else "attachment"

        headers = {
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{encoded_filename}",
            "Cache-Control": "private, max-age=3600",  # Cache for 1 hour
            "X-Content-Type-Options": "nosniff",
        }

        return StreamingResponse(generate(), media_type=content_type, headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving file {file_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e


@router.get("/applications/{application_id}/files/{file_id}/download")
async def download_file_proxy(
    application_id: int = Path(..., description="Application ID"),
    file_id: int = Path(..., description="File ID"),
    # JWTs from this system are dot-separated base64url segments. Constrain
    # length + charset at the FastAPI layer so malformed / oversized strings
    # 422 before they reach verify_token() and get DoS-tested for free.
    token: Optional[str] = Query(None, description="Access token", max_length=2048, pattern=r"^[A-Za-z0-9._-]+$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Force download endpoint for files
    """
    try:
        # Manual token verification for direct file access
        if not token:
            raise HTTPException(status_code=401, detail="Access token required")

        try:
            payload = verify_token(token)
            user_id = int(payload.get("sub"))
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid token") from exc

        # Get user from token
        auth_service = AuthService(db)
        user_result = await auth_service.get_user_by_id(user_id)
        if not user_result:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")

        current_user = user_result

        # Verify file exists and user has access (same logic as above)
        stmt = (
            select(ApplicationFile)
            .options(selectinload(ApplicationFile.application))
            .join(Application)
            .where(and_(ApplicationFile.id == file_id, Application.id == application_id))
        )
        result = await db.execute(stmt)
        file_record = result.scalar_one_or_none()

        if not file_record:
            raise HTTPException(status_code=404, detail="File not found")

        # Check access permissions
        application = file_record.application

        # Check access permissions based on role
        if current_user.role == UserRole.student:
            # Students can only access their own files
            if application.user_id != current_user.id:
                logger.warning(
                    "SECURITY: student attempted to access another user's file",
                    extra={
                        "user_id": current_user.id,
                        "file_id": file_id,
                        "owner_user_id": application.user_id,
                        "application_id": application.id,
                    },
                )
                raise HTTPException(status_code=403, detail="Access denied")
        elif current_user.role == UserRole.professor:
            # Professors can access files from their students
            if not current_user.can_access_student_data(application.user_id, "view_applications"):
                logger.warning(
                    "SECURITY: professor lacked relationship to access student file",
                    extra={
                        "user_id": current_user.id,
                        "file_id": file_id,
                        "student_user_id": application.user_id,
                        "application_id": application.id,
                    },
                )
                raise HTTPException(status_code=403, detail="Access denied - no relationship with student")
        elif current_user.role == UserRole.college:
            # College staff are scoped to their own college's applicants.
            _assert_college_may_access(current_user, application, file_id)
        elif current_user.role in (UserRole.admin, UserRole.super_admin):
            # Admin and Super Admin can access any file
            pass
        else:
            # Other roles are not allowed
            logger.warning(
                "SECURITY: unexpected role attempted file access",
                extra={
                    "user_id": current_user.id,
                    "role": str(current_user.role),
                    "file_id": file_id,
                },
            )
            raise HTTPException(status_code=403, detail="Access denied")

        # Get file stream from MinIO
        if not file_record.object_name:
            raise HTTPException(status_code=404, detail="File object not found")

        file_stream = minio_service.get_file_stream(file_record.object_name)

        # Determine content type from the validated extension, never from the
        # client-supplied MIME stored at upload time (see _safe_content_type).
        content_type = _safe_content_type(file_record.filename)

        # Create streaming response with download headers
        def generate():
            try:
                for chunk in file_stream.stream(1024 * 1024):  # 1MB chunks
                    yield chunk
            finally:
                file_stream.close()
                file_stream.release_conn()

        # Handle filename encoding for non-ASCII characters (e.g., Chinese)
        encoded_filename = urllib.parse.quote(file_record.filename, safe="")

        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
        }

        return StreamingResponse(generate(), media_type=content_type, headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file {file_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from e

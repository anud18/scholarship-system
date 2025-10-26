"""
Path Security Utilities

Implements CLAUDE.md triple validation for file path security:
1. Check for path traversal patterns (.., /, \\)
2. Regex validation for allowed characters
3. Absolute path resolution and prefix verification
"""

import os
import re
from typing import Optional

from fastapi import HTTPException, status


def validate_filename_strict(filename: str, allow_unicode: bool = False) -> None:
    """
    Strict filename validation following CLAUDE.md standards.

    Implements triple validation:
    1. Path traversal pattern check
    2. Character whitelist validation
    3. Length validation

    Args:
        filename: The filename to validate
        allow_unicode: If True, allows Unicode characters (for Chinese filenames).
                      If False, only allows ASCII alphanumeric, underscore, hyphen, and dot.

    Raises:
        HTTPException: If validation fails
    """
    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="檔案名稱不得為空 / Filename cannot be empty")

    # Validation 1: Check for path traversal patterns
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無效的檔案名稱：包含路徑字元 / Invalid filename: contains path characters",
        )

    # Validation 2: Character whitelist validation
    if allow_unicode:
        # For Unicode support: block only dangerous characters
        dangerous_chars = ["|", "<", ">", ":", '"', "?", "*"]
        if any(char in filename for char in dangerous_chars):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="檔案名稱包含無效字元 / Filename contains invalid characters"
            )
    else:
        # Strict ASCII-only validation (CLAUDE.md standard)
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", filename):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="檔案名稱僅允許英數字、底線、連字號和點 / Filename must contain only alphanumeric, underscore, hyphen, and dot",
            )

    # Validation 3: Length validation
    if len(filename) > 255:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="檔案名稱過長 / Filename too long (max 255 characters)"
        )


def validate_path_in_directory(file_path: str, expected_directory: str) -> None:
    """
    Validate that a file path resolves to within an expected directory.

    This is the third layer of CLAUDE.md path security validation.

    Args:
        file_path: The full file path to validate
        expected_directory: The directory that the file must be within

    Raises:
        HTTPException: If the resolved path is not within the expected directory
    """
    # Resolve to absolute paths
    resolved_path = os.path.abspath(file_path)
    expected_dir = os.path.abspath(expected_directory)

    # Check if resolved path starts with expected directory
    if not resolved_path.startswith(expected_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="存取被拒絕：檔案路徑超出允許範圍 / Access denied: file path outside allowed directory",
        )


def validate_object_name_minio(object_name: str) -> None:
    """
    Validate MinIO object name for security.

    MinIO object names are internal paths, so we apply strict validation.

    Args:
        object_name: The MinIO object name to validate

    Raises:
        HTTPException: If validation fails
    """
    if not object_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="物件名稱不得為空 / Object name cannot be empty")

    # Check for absolute path (should be relative)
    if object_name.startswith("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無效的物件名稱：不應為絕對路徑 / Invalid object name: should not be absolute path",
        )

    # Check for path traversal in any part of the path
    parts = object_name.split("/")
    for part in parts:
        if part == ".." or part == ".":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="無效的物件名稱：包含路徑遍歷 / Invalid object name: contains path traversal",
            )

        # Each part should not be empty (avoid double slashes)
        if not part:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="無效的物件名稱：路徑格式錯誤 / Invalid object name: malformed path"
            )


def secure_filename(filename: str, allow_unicode: bool = False) -> str:
    """
    Sanitize a filename by removing/replacing unsafe characters.

    This is a utility function for cases where you want to accept
    potentially unsafe filenames and make them safe, rather than
    rejecting them outright.

    Args:
        filename: The original filename
        allow_unicode: Whether to preserve Unicode characters

    Returns:
        A sanitized filename
    """
    # Remove path components
    filename = os.path.basename(filename)

    if allow_unicode:
        # Replace dangerous characters with underscores
        dangerous_chars = ["/", "\\", "..", "|", "<", ">", ":", '"', "?", "*"]
        for char in dangerous_chars:
            filename = filename.replace(char, "_")
    else:
        # Keep only alphanumeric, underscore, hyphen, and dot
        filename = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", filename)

    # Remove multiple consecutive underscores
    filename = re.sub(r"_+", "_", filename)

    # Remove leading/trailing underscores and dots
    filename = filename.strip("_.")

    # Ensure filename is not empty
    if not filename:
        filename = "unnamed_file"

    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        max_name_length = 255 - len(ext)
        filename = name[:max_name_length] + ext

    return filename


def validate_upload_file(
    filename: Optional[str],
    allowed_extensions: Optional[list[str]] = None,
    max_size_mb: Optional[int] = None,
    file_size: Optional[int] = None,
    allow_unicode: bool = False,
) -> str:
    """
    Comprehensive upload file validation.

    Args:
        filename: The filename to validate
        allowed_extensions: List of allowed file extensions (e.g., ['.pdf', '.jpg'])
        max_size_mb: Maximum file size in MB
        file_size: Actual file size in bytes
        allow_unicode: Whether to allow Unicode filenames

    Returns:
        The validated filename

    Raises:
        HTTPException: If validation fails
    """
    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="檔案名稱不得為空 / Filename cannot be empty")

    # Apply strict filename validation
    validate_filename_strict(filename, allow_unicode=allow_unicode)

    # Check file extension
    if allowed_extensions:
        file_lower = filename.lower()
        if not any(file_lower.endswith(ext.lower()) for ext in allowed_extensions):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"不支援的檔案類型，僅允許: {', '.join(allowed_extensions)} / "
                f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}",
            )

    # Check file size
    if max_size_mb and file_size:
        max_size_bytes = max_size_mb * 1024 * 1024
        if file_size > max_size_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"檔案過大，最大允許 {max_size_mb}MB / " f"File too large, maximum {max_size_mb}MB",
            )

    return filename

"""
Batch Import API endpoints for college staff

Provides endpoints for uploading, validating, and confirming
offline application data imports.
"""

import os
import re
from io import BytesIO
from typing import List, Optional

import magic
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.deps import get_db
from app.models.batch_import import BatchImport
from app.models.enums import BatchImportStatus
from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole
from app.schemas.batch_import import (
    BatchDocumentUploadResponse,
    BatchDocumentUploadResult,
    BatchImportConfirmRequest,
    BatchImportConfirmResponse,
    BatchImportDetailResponse,
    BatchImportHistoryItem,
    BatchImportHistoryResponse,
    BatchImportRevalidateResponse,
    BatchImportUpdateRecordRequest,
    BatchImportUploadResponse,
)
from app.services.batch_import_service import BatchImportService

router = APIRouter()


def require_college_role(current_user: User = Depends(get_current_user)) -> User:
    """Dependency to require college role or super admin"""
    if current_user.role not in [UserRole.college, UserRole.super_admin]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="此功能僅限學院角色使用",
        )
    return current_user


@router.post("/upload-data")
async def upload_batch_import_data(
    file: UploadFile = File(..., description="Excel或CSV檔案"),
    scholarship_type: str = Query(..., description="獎學金類型代碼"),
    academic_year: int = Query(..., description="學年度", ge=100, le=200),
    semester: Optional[str] = Query(None, description="學期"),
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    上傳批次匯入資料檔案（Excel/CSV）

    **流程**:
    1. 上傳 Excel/CSV 檔案
    2. 系統解析並驗證資料
    3. 返回預覽資料與驗證摘要
    4. 待確認後執行匯入

    **權限**: 僅限 college 角色
    """
    service = BatchImportService(db)

    # Validate scholarship type
    stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()

    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"獎學金類型 {scholarship_type} 不存在",
        )

    # Get college code from user (skip for super_admin)
    college_code = current_user.college_code
    if not college_code and current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="使用者未設定學院代碼",
        )

    # Read file content
    file_content = await file.read()

    # Validate file size (10MB max)
    from app.core.config import settings

    if len(file_content) > settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"檔案大小超過限制 ({settings.max_file_size / 1024 / 1024:.1f}MB)",
        )

    # Validate file type using python-magic for accurate MIME detection
    mime_type = magic.from_buffer(file_content, mime=True)

    # Allowed MIME types for Excel and CSV files
    allowed_mime_types = {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        "application/vnd.ms-excel",  # .xls
        "application/x-ole-storage",  # .xls (alternative)
        "text/csv",  # .csv
        "text/plain",  # .csv (sometimes detected as plain text)
        "application/csv",  # .csv (alternative)
    }

    if mime_type not in allowed_mime_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"不支援的檔案格式 ({mime_type})，請上傳 Excel (.xlsx, .xls) 或 CSV 檔案",
        )

    # Additional validation: Try to parse the file structure
    try:
        if mime_type.startswith("application/vnd"):
            # Verify it's a valid Excel file by attempting to read metadata
            pd.read_excel(BytesIO(file_content), nrows=0)
        elif "csv" in mime_type or mime_type == "text/plain":
            # Verify it's a valid CSV/text file
            pd.read_csv(BytesIO(file_content), nrows=0)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"檔案結構驗證失敗: {str(e)}",
        )

    # Parse and validate
    parsed_data, validation_errors = await service.parse_excel_file(
        file_content=file_content,
        scholarship_type_id=scholarship.id,
        academic_year=academic_year,
        semester=semester,
    )

    # Bulk validation for performance optimization
    if parsed_data:
        # Collect all student IDs
        student_ids = [row_data["student_id"] for row_data in parsed_data]

        # Perform bulk validation (single query instead of N queries)
        permission_results, duplicate_results = await service.bulk_validate_permissions_and_duplicates(
            student_ids=student_ids,
            college_code=college_code or "",
            scholarship_type_id=scholarship.id,
            academic_year=academic_year,
            semester=semester,
        )

        # Process validation results
        for idx, row_data in enumerate(parsed_data):
            student_id = row_data["student_id"]
            row_number = idx + 2  # Excel row number (1-indexed + header row)

            # Check college permission (skip for super_admin)
            if current_user.role != UserRole.super_admin:
                is_valid, error_msg = permission_results.get(student_id, (False, "未知錯誤"))
                if not is_valid:
                    validation_errors.append(
                        {
                            "row_number": row_number,
                            "student_id": student_id,
                            "field": "college_code",
                            "error_type": "permission_error",
                            "message": error_msg,
                        }
                    )

            # Check duplicate
            is_duplicate, error_msg = duplicate_results.get(student_id, (False, None))
            if is_duplicate:
                validation_errors.append(
                    {
                        "row_number": row_number,
                        "student_id": student_id,
                        "field": "duplicate",
                        "error_type": "duplicate_application",
                        "message": error_msg,
                    }
                )

    # Create batch import record
    batch_import = await service.create_batch_import_record(
        importer_id=current_user.id,
        college_code=college_code or "admin",  # Use special value for super_admin (max 10 chars)
        scholarship_type_id=scholarship.id,
        academic_year=academic_year,
        semester=semester,
        file_name=file.filename,
        total_records=len(parsed_data),
    )

    # Upload original file to MinIO for later download/preview
    from app.services.minio_service import MinIOService

    try:
        minio_service = MinIOService()
        object_name = f"batch-imports/{batch_import.id}/{file.filename}"
        file_buffer = BytesIO(file_content)
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if file.filename.endswith(".xlsx")
            else "application/vnd.ms-excel"
            if file.filename.endswith(".xls")
            else "text/csv"
        )

        minio_service.client.put_object(
            bucket_name=settings.minio_bucket,
            object_name=object_name,
            data=file_buffer,
            length=len(file_content),
            content_type=content_type,
        )
        batch_import.file_path = object_name
    except Exception as e:
        # Log error but don't fail the upload if MinIO is unavailable
        import logging

        logging.error(f"Failed to upload batch import file to MinIO: {e}")

    # Store parsed data for confirm step
    batch_import.parsed_data = {
        "data": parsed_data,
        "errors": [
            {
                "row_number": e.get("row_number") if isinstance(e, dict) else e.row_number,
                "student_id": e.get("student_id") if isinstance(e, dict) else e.student_id,
                "field": e.get("field") if isinstance(e, dict) else e.field,
                "error_type": e.get("error_type") if isinstance(e, dict) else e.error_type,
                "message": e.get("message") if isinstance(e, dict) else e.message,
            }
            for e in validation_errors
        ],
    }

    await db.commit()

    # Return preview (first 10 rows) and validation summary
    # Transform error structure to match frontend expectations
    frontend_errors = [
        {
            "row": e.get("row_number") if isinstance(e, dict) else e.row_number,
            "field": e.get("field") if isinstance(e, dict) else getattr(e, "field", None),
            "message": e.get("message") if isinstance(e, dict) else getattr(e, "message", str(e)),
        }
        for e in validation_errors[:20]  # Limit preview errors
    ]

    response_data = BatchImportUploadResponse(
        batch_id=batch_import.id,
        file_name=file.filename,
        total_records=len(parsed_data),
        preview_data=parsed_data[:10],
        validation_summary={
            "valid_count": len(parsed_data) - len(validation_errors),
            "invalid_count": len(validation_errors),
            "warnings": [],  # No warnings for now
            "errors": frontend_errors,
        },
    )

    return {
        "success": True,
        "message": "檔案上傳成功" if len(validation_errors) == 0 else f"檔案上傳完成，發現 {len(validation_errors)} 個驗證錯誤",
        "data": response_data.model_dump(),
    }


@router.patch("/{batch_id}/records")
async def update_batch_record(
    batch_id: int,
    request: BatchImportUpdateRecordRequest,
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    更新批次匯入中的單筆記錄

    **流程**:
    1. 驗證批次記錄存在且為 pending 狀態
    2. 更新指定索引的記錄
    3. 返回更新結果

    **權限**: College 角色僅能編輯自己上傳的批次
    """
    # Get batch import record
    batch_import = await db.get(BatchImport, batch_id)
    if not batch_import:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"批次匯入記錄 {batch_id} 不存在",
        )

    # Verify ownership (skip for super_admin)
    if batch_import.importer_id != current_user.id and current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="僅能編輯自己上傳的批次匯入",
        )

    # Check status
    if batch_import.import_status != BatchImportStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"此批次狀態為 {batch_import.import_status.value}，無法編輯",
        )

    # Check if parsed_data exists
    if not batch_import.parsed_data or "data" not in batch_import.parsed_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="批次匯入資料已過期或不存在",
        )

    parsed_data = batch_import.parsed_data["data"]

    # Validate record index
    if request.record_index >= len(parsed_data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"記錄索引 {request.record_index} 超出範圍（總共 {len(parsed_data)} 筆）",
        )

    # Update the record
    for key, value in request.updates.items():
        parsed_data[request.record_index][key] = value

    # Update in database
    batch_import.parsed_data["data"] = parsed_data
    await db.commit()

    return {
        "success": True,
        "message": "記錄更新成功",
        "data": {"updated_record": parsed_data[request.record_index]},
    }


@router.post("/{batch_id}/validate")
async def revalidate_batch_import(
    batch_id: int,
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    重新驗證批次匯入資料

    **流程**:
    1. 驗證批次記錄存在且為 pending 狀態
    2. 重新執行所有驗證規則
    3. 更新 parsed_data 中的錯誤列表
    4. 返回驗證摘要

    **權限**: College 角色僅能驗證自己上傳的批次
    """
    # Get batch import record
    batch_import = await db.get(BatchImport, batch_id)
    if not batch_import:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"批次匯入記錄 {batch_id} 不存在",
        )

    # Verify ownership (skip for super_admin)
    if batch_import.importer_id != current_user.id and current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="僅能驗證自己上傳的批次匯入",
        )

    # Check status
    if batch_import.import_status != BatchImportStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"此批次狀態為 {batch_import.import_status.value}，無法重新驗證",
        )

    # Check if parsed_data exists
    if not batch_import.parsed_data or "data" not in batch_import.parsed_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="批次匯入資料已過期或不存在",
        )

    parsed_data = batch_import.parsed_data["data"]
    service = BatchImportService(db)
    validation_errors = []

    # Get college code from user
    college_code = current_user.college_code

    # Re-validate all records
    for row_data in parsed_data:
        # Check college permission (skip for super_admin)
        if current_user.role != UserRole.super_admin:
            is_valid, error_msg = await service.validate_college_permission(
                student_id=row_data.get("student_id"),
                college_code=college_code,
                dept_code=row_data.get("dept_code"),
            )
            if not is_valid:
                validation_errors.append(
                    {
                        "row_number": parsed_data.index(row_data) + 2,
                        "student_id": row_data.get("student_id"),
                        "field": "college_code",
                        "error_type": "permission_error",
                        "message": error_msg,
                    }
                )

        # Check duplicate
        is_duplicate, error_msg = await service.check_duplicate_application(
            student_id=row_data.get("student_id"),
            scholarship_type_id=batch_import.scholarship_type_id,
            academic_year=batch_import.academic_year,
            semester=batch_import.semester,
        )
        if is_duplicate:
            validation_errors.append(
                {
                    "row_number": parsed_data.index(row_data) + 2,
                    "student_id": row_data.get("student_id"),
                    "field": "duplicate",
                    "error_type": "duplicate_application",
                    "message": error_msg,
                }
            )

    # Update parsed_data with new errors
    batch_import.parsed_data["errors"] = validation_errors
    await db.commit()

    response_data = BatchImportRevalidateResponse(
        batch_id=batch_id,
        total_records=len(parsed_data),
        valid_count=len(parsed_data) - len(validation_errors),
        invalid_count=len(validation_errors),
        errors=[
            {
                "row": e.get("row_number"),
                "field": e.get("field"),
                "message": e.get("message"),
            }
            for e in validation_errors[:20]  # Limit preview errors
        ],
    )

    return {
        "success": True,
        "message": "驗證完成" if len(validation_errors) == 0 else f"驗證完成，發現 {len(validation_errors)} 個錯誤",
        "data": response_data.model_dump(),
    }


@router.delete("/{batch_id}/records/{record_index}")
async def delete_batch_record(
    batch_id: int,
    record_index: int,
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    刪除批次匯入中的單筆記錄

    **流程**:
    1. 驗證批次記錄存在且為 pending 狀態
    2. 刪除指定索引的記錄
    3. 更新總筆數
    4. 返回刪除結果

    **權限**: College 角色僅能刪除自己上傳的批次中的記錄
    """
    # Get batch import record
    batch_import = await db.get(BatchImport, batch_id)
    if not batch_import:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"批次匯入記錄 {batch_id} 不存在",
        )

    # Verify ownership (skip for super_admin)
    if batch_import.importer_id != current_user.id and current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="僅能刪除自己上傳的批次匯入中的記錄",
        )

    # Check status
    if batch_import.import_status != BatchImportStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"此批次狀態為 {batch_import.import_status.value}，無法刪除記錄",
        )

    # Check if parsed_data exists
    if not batch_import.parsed_data or "data" not in batch_import.parsed_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="批次匯入資料已過期或不存在",
        )

    parsed_data = batch_import.parsed_data["data"]

    # Validate record index
    if record_index >= len(parsed_data):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"記錄索引 {record_index} 超出範圍（總共 {len(parsed_data)} 筆）",
        )

    # Delete the record
    deleted_record = parsed_data.pop(record_index)

    # Update total_records count
    batch_import.total_records = len(parsed_data)
    batch_import.parsed_data["data"] = parsed_data

    # Also remove any validation errors for this record and adjust row numbers
    if "errors" in batch_import.parsed_data:
        errors = batch_import.parsed_data["errors"]
        # Remove errors for the deleted row
        errors = [e for e in errors if e.get("row_number") != record_index + 2]
        # Adjust row numbers for records after the deleted one
        for e in errors:
            if e.get("row_number") > record_index + 2:
                e["row_number"] -= 1
        batch_import.parsed_data["errors"] = errors

    await db.commit()

    return {
        "success": True,
        "message": "記錄刪除成功",
        "data": {
            "deleted_record": deleted_record,
            "remaining_records": len(parsed_data),
        },
    }


@router.post("/{batch_id}/documents")
async def upload_batch_documents(
    batch_id: int,
    file: UploadFile = File(..., description="包含所有文件的 ZIP 檔案"),
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    批次上傳文件（ZIP 格式）

    **檔案命名規則**: `{學號}_文件類型.pdf`
    - 範例: `111111111_transcript.pdf`, `222222222_id_card.pdf`

    **支援的文件類型**:
    - transcript: 成績單
    - id_card: 身份證
    - bank_book: 存摺封面
    - other: 其他文件

    **流程**:
    1. 上傳 ZIP 檔案
    2. 解壓並驗證檔案命名
    3. 匹配學號到批次匯入的申請
    4. 上傳文件到 MinIO
    5. 建立 ApplicationFile 記錄

    **權限**: College 角色僅能為自己的批次上傳文件
    """
    import zipfile
    from io import BytesIO

    from app.core.config import settings
    from app.models.application import Application, ApplicationFile
    from app.services.minio_service import MinIOService

    # Get batch import record
    batch_import = await db.get(BatchImport, batch_id)
    if not batch_import:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"批次匯入記錄 {batch_id} 不存在",
        )

    # Verify ownership (skip for super_admin)
    if batch_import.importer_id != current_user.id and current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="僅能為自己的批次上傳文件",
        )

    # Check if batch is confirmed (has created applications)
    if batch_import.import_status not in [BatchImportStatus.completed, BatchImportStatus.partial]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"批次狀態為 {batch_import.import_status.value}，必須先確認匯入才能上傳文件",
        )

    # Read ZIP file
    zip_content = await file.read()

    # Validate file size (100MB max)
    if len(zip_content) > 100 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="ZIP 檔案大小不能超過 100MB",
        )

    # Validate ZIP file
    try:
        zip_file = zipfile.ZipFile(BytesIO(zip_content))
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="無效的 ZIP 檔案",
        )

    # ZIP bomb protection
    # 1. Check file count limit (max 1000 files)
    file_count = len(zip_file.filelist)
    if file_count > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ZIP 檔案包含過多檔案 ({file_count})，最多允許 1000 個檔案",
        )

    # 2. Check total uncompressed size and compression ratio
    compressed_size = len(zip_content)
    total_uncompressed_size = sum(file_info.file_size for file_info in zip_file.filelist)

    # Max uncompressed size: 100MB
    max_uncompressed_size = 100 * 1024 * 1024
    if total_uncompressed_size > max_uncompressed_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ZIP 解壓縮後大小 ({total_uncompressed_size / 1024 / 1024:.1f}MB) 超過限制 (100MB)",
        )

    # Max compression ratio: 100:1
    if compressed_size > 0 and total_uncompressed_size / compressed_size > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ZIP 壓縮比過高 ({total_uncompressed_size / compressed_size:.1f}:1)，可能為 ZIP 炸彈攻擊",
        )

    # Document type mapping
    doc_type_map = {
        "transcript": "transcript",
        "成績單": "transcript",
        "id_card": "id_card",
        "身份證": "id_card",
        "bank_book": "bank_book",
        "存摺": "bank_book",
        "other": "other",
        "其他": "other",
    }

    results: List[BatchDocumentUploadResult] = []
    matched_count = 0
    unmatched_count = 0
    error_count = 0

    # Get all applications from this batch
    applications_stmt = select(Application).where(Application.batch_import_id == batch_id)
    applications_result = await db.execute(applications_stmt)
    applications = applications_result.scalars().all()

    # Create student_id to application mapping
    student_app_map = {app.student_id: app for app in applications}

    # Initialize MinIO service
    minio_service = MinIOService()

    # Process each file in ZIP
    for file_info in zip_file.filelist:
        # Skip directories
        if file_info.is_dir():
            continue

        file_name = file_info.filename

        # Path traversal prevention
        # 1. Check for directory traversal patterns
        if ".." in file_name or file_name.startswith("/") or file_name.startswith("\\"):
            results.append(
                BatchDocumentUploadResult(
                    student_id="",
                    file_name=file_name,
                    document_type="unknown",
                    status="error",
                    message="檔案路徑包含非法字元（目錄遍歷攻擊）",
                )
            )
            error_count += 1
            continue

        # 2. Normalize path and validate it stays within bounds
        normalized_path = os.path.normpath(file_name)
        if normalized_path.startswith("..") or os.path.isabs(normalized_path):
            results.append(
                BatchDocumentUploadResult(
                    student_id="",
                    file_name=file_name,
                    document_type="unknown",
                    status="error",
                    message="檔案路徑驗證失敗",
                )
            )
            error_count += 1
            continue

        # Skip __MACOSX and other hidden files
        if file_name.startswith("__MACOSX") or file_name.startswith("."):
            continue

        # Extract file
        try:
            file_data = zip_file.read(file_name)
        except Exception as e:
            results.append(
                BatchDocumentUploadResult(
                    student_id="",
                    file_name=file_name,
                    document_type="unknown",
                    status="error",
                    message=f"無法讀取檔案: {str(e)}",
                )
            )
            error_count += 1
            continue

        # Parse filename: {student_id}_{doc_type}.{ext}
        base_name = file_name.split("/")[-1]  # Get filename without path
        match = re.match(r"^([A-Za-z0-9]+)_(.+)\.(pdf|jpg|jpeg|png)$", base_name, re.IGNORECASE)

        if not match:
            results.append(
                BatchDocumentUploadResult(
                    student_id="",
                    file_name=file_name,
                    document_type="unknown",
                    status="error",
                    message="檔名格式錯誤，應為: {學號}_文件類型.pdf",
                )
            )
            unmatched_count += 1
            continue

        student_id, doc_type_str, file_ext = match.groups()

        # Sanitize and validate student_id
        # Only allow alphanumeric characters and underscores
        if not re.match(r"^[A-Za-z0-9_]{1,20}$", student_id):
            results.append(
                BatchDocumentUploadResult(
                    student_id=student_id,
                    file_name=file_name,
                    document_type="unknown",
                    status="error",
                    message="學號格式無效，僅允許英數字和底線，最長20字元",
                )
            )
            error_count += 1
            continue

        # Map document type
        doc_type = doc_type_map.get(doc_type_str.lower(), "other")

        # Find application
        app = student_app_map.get(student_id)
        if not app:
            results.append(
                BatchDocumentUploadResult(
                    student_id=student_id,
                    file_name=file_name,
                    document_type=doc_type,
                    status="error",
                    message="找不到對應的申請記錄",
                )
            )
            unmatched_count += 1
            continue

        # Validate file size (10MB max per file)
        if len(file_data) > 10 * 1024 * 1024:
            results.append(
                BatchDocumentUploadResult(
                    student_id=student_id,
                    file_name=file_name,
                    document_type=doc_type,
                    status="error",
                    message="檔案大小超過 10MB",
                    application_id=app.id,
                )
            )
            error_count += 1
            continue

        # Upload to MinIO
        try:
            object_name = f"applications/{app.id}/{doc_type}_{base_name}"
            file_buffer = BytesIO(file_data)

            minio_service.client.put_object(
                bucket_name=settings.minio_bucket,
                object_name=object_name,
                data=file_buffer,
                length=len(file_data),
                content_type=(f"application/{file_ext}" if file_ext.lower() == "pdf" else f"image/{file_ext.lower()}"),
            )

            # Create ApplicationFile record
            app_file = ApplicationFile(
                application_id=app.id,
                file_type=doc_type,
                file_name=base_name,
                object_name=object_name,
                file_size=len(file_data),
                uploaded_by=current_user.id,
            )
            db.add(app_file)

            results.append(
                BatchDocumentUploadResult(
                    student_id=student_id,
                    file_name=file_name,
                    document_type=doc_type,
                    status="success",
                    message="上傳成功",
                    application_id=app.id,
                )
            )
            matched_count += 1

        except Exception as e:
            results.append(
                BatchDocumentUploadResult(
                    student_id=student_id,
                    file_name=file_name,
                    document_type=doc_type,
                    status="error",
                    message=f"上傳失敗: {str(e)}",
                    application_id=app.id,
                )
            )
            error_count += 1

    # Commit all ApplicationFile records
    await db.commit()

    response_data = BatchDocumentUploadResponse(
        batch_id=batch_id,
        total_files=len(results),
        matched_count=matched_count,
        unmatched_count=unmatched_count,
        error_count=error_count,
        results=results[:50],  # Limit to 50 results in response
    )

    return {
        "success": True,
        "message": f"文件上傳完成：成功 {matched_count} 筆，失敗 {error_count + unmatched_count} 筆",
        "data": response_data.model_dump(),
    }


@router.post("/{batch_id}/confirm")
async def confirm_batch_import(
    batch_id: int,
    request: BatchImportConfirmRequest,
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    確認執行批次匯入

    **流程**:
    1. 驗證批次記錄
    2. 檢查權限（College 角色僅能確認自己上傳的批次，Super Admin 可確認所有批次）
    3. 建立所有申請記錄
    4. 更新批次狀態

    **權限**: College 角色僅能確認自己上傳的批次，Super Admin 可確認所有批次
    """
    # Get batch import record
    batch_import = await db.get(BatchImport, batch_id)
    if not batch_import:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"批次匯入記錄 {batch_id} 不存在",
        )

    # Verify ownership (skip for super_admin)
    if batch_import.importer_id != current_user.id and current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="僅能確認自己上傳的批次匯入",
        )

    # Check status
    if batch_import.import_status != BatchImportStatus.pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"此批次狀態為 {batch_import.import_status.value}，無法再次確認",
        )

    if not request.confirm:
        # Cancel the batch
        batch_import.import_status = BatchImportStatus.cancelled.value
        await db.commit()
        response_data = BatchImportConfirmResponse(
            batch_id=batch_id,
            success_count=0,
            failed_count=0,
            errors=[],
            created_application_ids=[],
        )
        return {
            "success": True,
            "message": "批次匯入已取消",
            "data": response_data.model_dump(),
        }

    # Check if parsed_data exists
    if not batch_import.parsed_data or "data" not in batch_import.parsed_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="批次匯入資料已過期或不存在，請重新上傳",
        )

    # Get parsed data
    parsed_data = batch_import.parsed_data["data"]
    service = BatchImportService(db)

    # Update status to processing
    batch_import.import_status = BatchImportStatus.processing.value
    await db.commit()

    # Create applications with transaction rollback on error
    from app.core.exceptions import BatchImportError

    try:
        created_ids, creation_errors = await service.create_applications_from_batch(
            batch_import=batch_import,
            parsed_data=parsed_data,
            scholarship_type_id=batch_import.scholarship_type_id,
            academic_year=batch_import.academic_year,
            semester=batch_import.semester,
        )

        # Update batch import status
        await service.update_batch_import_status(
            batch_import=batch_import,
            success_count=len(created_ids),
            failed_count=len(creation_errors),
            errors=creation_errors,
            status="completed" if len(creation_errors) == 0 else "partial",
        )

        response_data = BatchImportConfirmResponse(
            batch_id=batch_id,
            success_count=len(created_ids),
            failed_count=len(creation_errors),
            errors=[
                {
                    "row_number": e.row_number,
                    "student_id": e.student_id,
                    "field": e.field,
                    "error_type": e.error_type,
                    "message": e.message,
                }
                for e in creation_errors
            ],
            created_application_ids=created_ids,
        )

        return {
            "success": True,
            "message": "批次匯入成功" if len(creation_errors) == 0 else f"批次匯入完成，部分失敗 ({len(creation_errors)} 筆錯誤)",
            "data": response_data.model_dump(),
        }

    except BatchImportError as e:
        # Re-raise to let the global exception handler deal with it
        # Batch status has already been updated to 'failed' in the service
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.message,
        )


@router.get("/history")
async def get_batch_import_history(
    skip: int = Query(0, ge=0, description="跳過筆數"),
    limit: int = Query(20, ge=1, le=100, description="每頁筆數"),
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    查詢批次匯入歷史記錄

    **權限**: College 角色僅能查看自己上傳的記錄，Super Admin 可查看所有記錄
    """
    # Query batch imports - only show confirmed imports (exclude pending)
    # Pending imports are temporary and should not appear in history until confirmed
    confirmed_statuses = [
        BatchImportStatus.completed,
        BatchImportStatus.partial,
        BatchImportStatus.failed,
        BatchImportStatus.cancelled,
    ]

    if current_user.role == UserRole.super_admin:
        # Super admin can see all confirmed batch imports
        stmt = (
            select(BatchImport)
            .where(BatchImport.import_status.in_(confirmed_statuses))
            .order_by(desc(BatchImport.created_at))
            .offset(skip)
            .limit(limit)
        )
        count_stmt = select(BatchImport).where(BatchImport.import_status.in_(confirmed_statuses))
    else:
        # College role can only see their own confirmed imports
        stmt = (
            select(BatchImport)
            .where(
                BatchImport.importer_id == current_user.id,
                BatchImport.import_status.in_(confirmed_statuses),
            )
            .order_by(desc(BatchImport.created_at))
            .offset(skip)
            .limit(limit)
        )
        count_stmt = select(BatchImport).where(
            BatchImport.importer_id == current_user.id,
            BatchImport.import_status.in_(confirmed_statuses),
        )

    result = await db.execute(stmt)
    batch_imports = result.scalars().all()

    # Count total
    count_result = await db.execute(count_stmt)
    total = len(count_result.scalars().all())

    # Build response
    items = []
    for batch in batch_imports:
        items.append(
            BatchImportHistoryItem(
                id=batch.id,
                college_code=batch.college_code,
                scholarship_type_id=batch.scholarship_type_id,
                academic_year=batch.academic_year,
                semester=batch.semester,
                file_name=batch.file_name,
                total_records=batch.total_records,
                success_count=batch.success_count,
                failed_count=batch.failed_count,
                import_status=batch.import_status.value if batch.import_status else "unknown",
                created_at=batch.created_at,
                importer_name=batch.importer.name if batch.importer else None,
            )
        )

    response_data = BatchImportHistoryResponse(total=total, items=items)
    return {
        "success": True,
        "message": "查詢成功",
        "data": response_data.model_dump(),
    }


@router.get("/{batch_id}/details")
async def get_batch_import_details(
    batch_id: int,
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    查詢批次匯入詳細資訊

    **權限**: College 角色僅能查看自己上傳的記錄，Super Admin 可查看所有記錄
    """
    # Get batch import
    batch_import = await db.get(BatchImport, batch_id)
    if not batch_import:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"批次匯入記錄 {batch_id} 不存在",
        )

    # Verify ownership (skip for super_admin)
    if batch_import.importer_id != current_user.id and current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="僅能查看自己上傳的批次匯入記錄",
        )

    # Get created applications IDs using explicit query (avoid lazy loading)
    from app.models.application import Application

    app_stmt = select(Application.id).where(Application.batch_import_id == batch_id)
    app_result = await db.execute(app_stmt)
    created_app_ids = [row[0] for row in app_result.fetchall()]

    # Get importer name using explicit query (avoid lazy loading)
    importer_name = None
    if batch_import.importer_id:
        importer_stmt = select(User.name).where(User.id == batch_import.importer_id)
        importer_result = await db.execute(importer_stmt)
        importer_name = importer_result.scalar_one_or_none()

    response_data = BatchImportDetailResponse(
        id=batch_import.id,
        college_code=batch_import.college_code,
        scholarship_type_id=batch_import.scholarship_type_id,
        academic_year=batch_import.academic_year,
        semester=batch_import.semester,
        file_name=batch_import.file_name,
        file_path=batch_import.file_path,
        total_records=batch_import.total_records,
        success_count=batch_import.success_count,
        failed_count=batch_import.failed_count,
        error_summary=batch_import.error_summary,
        import_status=batch_import.import_status.value if batch_import.import_status else "unknown",
        created_at=batch_import.created_at,
        updated_at=batch_import.updated_at,
        importer_name=importer_name,
        created_applications=created_app_ids,
    )

    return {
        "success": True,
        "message": "查詢成功",
        "data": response_data.model_dump(),
    }


@router.get("/{batch_id}/download")
async def download_batch_import_file(
    batch_id: int,
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    下載批次匯入的原始 Excel 檔案

    **權限**: College 角色僅能下載自己上傳的檔案，Super Admin 可下載所有檔案
    """
    from app.services.minio_service import MinIOService

    # Get batch import
    batch_import = await db.get(BatchImport, batch_id)
    if not batch_import:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"批次匯入記錄 {batch_id} 不存在",
        )

    # Verify ownership (skip for super_admin)
    if batch_import.importer_id != current_user.id and current_user.role != UserRole.super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="僅能下載自己上傳的批次匯入檔案",
        )

    # Check if file exists
    if not batch_import.file_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="原始檔案不存在（可能是舊版本匯入或檔案已被刪除）",
        )

    # Get file from MinIO
    try:
        from app.core.config import settings

        minio_service = MinIOService()
        file_data = minio_service.get_file(bucket_name=settings.minio_bucket, object_name=batch_import.file_path)

        # Determine content type
        if batch_import.file_name.endswith(".xlsx"):
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif batch_import.file_name.endswith(".xls"):
            content_type = "application/vnd.ms-excel"
        else:
            content_type = "text/csv"

        # Return file as download
        from urllib.parse import quote

        encoded_filename = quote(batch_import.file_name, encoding="utf-8")

        return StreamingResponse(
            BytesIO(file_data),
            media_type=content_type,
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
        )
    except Exception as e:
        import logging

        logging.error(f"Failed to download batch import file from MinIO: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="下載檔案時發生錯誤",
        )


@router.delete("/{batch_id}")
async def delete_batch_import(
    batch_id: int,
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    刪除批次匯入記錄及其所有相關申請

    **權限**: College 角色僅能刪除自己上傳的批次，Admin/Super Admin 可刪除所有批次
    """
    import logging

    from app.core.config import settings
    from app.services.minio_service import MinIOService

    logger = logging.getLogger(__name__)

    # Get batch import with related applications
    stmt = select(BatchImport).where(BatchImport.id == batch_id)
    result = await db.execute(stmt)
    batch_import = result.scalar_one_or_none()

    if not batch_import:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"批次匯入記錄 {batch_id} 不存在",
        )

    # Verify ownership (skip for admin/super_admin)
    if current_user.role not in [UserRole.admin, UserRole.super_admin]:
        if batch_import.importer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="僅能刪除自己上傳的批次匯入記錄",
            )

    # Get applications using explicit query (avoid lazy loading)
    from app.models.application import Application

    app_stmt = select(Application).where(Application.batch_import_id == batch_id)
    app_result = await db.execute(app_stmt)
    applications = app_result.scalars().all()

    # Get application count for response
    application_count = len(applications)

    # Delete related applications
    for application in applications:
        await db.delete(application)

    # Delete MinIO file if exists
    if batch_import.file_path:
        try:
            minio_service = MinIOService()
            minio_service.delete_file(bucket_name=settings.minio_bucket, object_name=batch_import.file_path)
        except Exception as e:
            logger.warning(f"Failed to delete batch import file from MinIO: {e}")
            # Continue with batch deletion even if MinIO deletion fails

    # Delete batch import record
    await db.delete(batch_import)
    await db.commit()

    return {
        "success": True,
        "message": f"成功刪除批次匯入記錄及其 {application_count} 個申請",
        "data": {
            "batch_id": batch_id,
            "deleted_applications": application_count,
        },
    }


@router.get("/template")
async def download_batch_import_template(
    scholarship_type: str = Query(..., description="獎學金類型代碼"),
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    下載批次匯入範例 Excel 檔案

    **範例檔案包含**:
    - 必要欄位: 學號, 學生姓名
    - 可選欄位: 郵局帳號
    - 子類型欄位: 根據獎學金類型動態生成（使用繁體中文）
    - 自訂欄位: 根據 ApplicationField 配置動態生成（使用繁體中文）

    **權限**: 僅限 college 角色
    """
    from app.models.application_field import ApplicationField

    # Validate scholarship type
    stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()

    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"獎學金類型 {scholarship_type} 不存在",
        )

    # Define base columns (Traditional Chinese)
    columns = [
        "學號",  # student_id - 必填
        "學生姓名",  # student_name - 必填
        "郵局帳號",  # postal_account - 可選
    ]

    # Mapping for internal use (Chinese to English)
    column_mapping = {
        "學號": "student_id",
        "學生姓名": "student_name",
        "郵局帳號": "postal_account",
    }

    # Sub-type label mapping
    sub_type_labels = {
        "nstc": "國科會",
        "moe_1w": "教育部配合款1萬",
        "moe_2w": "教育部配合款2萬",
    }

    # Add sub_type columns if scholarship has sub types (Traditional Chinese)
    if scholarship.sub_type_list:
        for sub_type_code in scholarship.sub_type_list:
            label = sub_type_labels.get(sub_type_code, sub_type_code)
            columns.append(label)
            column_mapping[label] = f"sub_type_{sub_type_code}"

    # Query custom fields for this scholarship type
    custom_fields_stmt = (
        select(ApplicationField)
        .where(ApplicationField.scholarship_type == scholarship.code)
        .where(ApplicationField.is_active)
        .order_by(ApplicationField.display_order)
    )
    custom_fields_result = await db.execute(custom_fields_stmt)
    custom_fields = custom_fields_result.scalars().all()

    # Add custom field columns (Traditional Chinese)
    for field in custom_fields:
        columns.append(field.field_label)  # Use Chinese label
        column_mapping[field.field_label] = f"custom_{field.field_name}"

    # Create sample data (2 example rows)
    sample_data = [
        {
            "學號": "111111111",
            "學生姓名": "王小明",
            "郵局帳號": "1234567890123",
        },
        {
            "學號": "222222222",
            "學生姓名": "陳小華",
            "郵局帳號": "9876543210987",
        },
    ]

    # Add sub_type sample values if applicable
    if scholarship.sub_type_list:
        for i, row in enumerate(sample_data):
            for j, sub_type_code in enumerate(scholarship.sub_type_list):
                label = sub_type_labels.get(sub_type_code, sub_type_code)
                # First row has first sub_type as Y, second row has second sub_type as Y
                row[label] = "Y" if i == j else ""

    # Add custom field sample values
    for field in custom_fields:
        for i, row in enumerate(sample_data):
            # Provide sample values based on field type
            if field.field_type == "text":
                row[field.field_label] = f"範例{field.field_label}{i + 1}"
            elif field.field_type == "number":
                row[field.field_label] = 100 + i
            elif field.field_type == "select":
                # Use first option if available
                if field.field_options and len(field.field_options) > 0:
                    row[field.field_label] = field.field_options[0].get("label", "")
                else:
                    row[field.field_label] = ""
            elif field.field_type == "checkbox":
                row[field.field_label] = "Y" if i == 0 else ""
            else:
                row[field.field_label] = ""

    # Create DataFrame
    df = pd.DataFrame(sample_data, columns=columns)

    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="批次匯入範例")

        # Auto-adjust column widths
        from openpyxl.utils import get_column_letter

        worksheet = writer.sheets["批次匯入範例"]
        for idx, col in enumerate(df.columns, 1):
            # Calculate max length for this column
            column_values = df[col].astype(str).tolist()

            # Collect all content in this column (header + all data)
            all_content = [str(col)] + column_values

            # Calculate max character length
            max_length = max(len(text) for text in all_content) if all_content else 0

            # Count Chinese characters in each cell and find the max
            # Chinese characters need approximately 2x the width of English characters
            max_chinese_in_cell = (
                max(sum(1 for c in text if "\u4e00" <= c <= "\u9fff") for text in all_content) if all_content else 0
            )

            # Adjusted width calculation:
            # - Base width from character count
            # - Add extra width for Chinese characters (they're wider)
            # - Add padding
            adjusted_width = max_length + max_chinese_in_cell * 1.2 + 2

            # Apply width to column
            column_letter = get_column_letter(idx)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    output.seek(0)

    # Return as downloadable file with Chinese filename
    from urllib.parse import quote

    filename = f"{scholarship.name}_批次匯入範例.xlsx"
    encoded_filename = quote(filename, encoding="utf-8")

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )

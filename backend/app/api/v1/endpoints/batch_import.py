"""
Batch Import API endpoints for college staff

Provides endpoints for uploading, validating, and confirming
offline application data imports.
"""

from io import BytesIO
from typing import Optional

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
    BatchImportConfirmRequest,
    BatchImportConfirmResponse,
    BatchImportDetailResponse,
    BatchImportHistoryItem,
    BatchImportHistoryResponse,
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


@router.post("/upload-data", response_model=BatchImportUploadResponse)
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

    # Validate file type using magic bytes
    # Excel .xlsx files start with PK (ZIP signature: 50 4B)
    # Excel .xls files start with D0 CF 11 E0 (OLE2 signature)
    # CSV files are text, check if it's valid UTF-8/text
    is_valid_type = False

    if len(file_content) >= 4:
        magic_bytes = file_content[:4]
        if magic_bytes[:2] == b"PK":  # .xlsx (ZIP-based)
            is_valid_type = True
        elif magic_bytes == b"\xD0\xCF\x11\xE0":  # .xls (OLE2-based)
            is_valid_type = True
        else:
            # Try to decode as text for CSV
            try:
                file_content.decode("utf-8")
                is_valid_type = True
            except UnicodeDecodeError:
                try:
                    file_content.decode("big5")  # Try Big5 for traditional Chinese
                    is_valid_type = True
                except UnicodeDecodeError:
                    pass

    if not is_valid_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="不支援的檔案格式，請上傳 Excel (.xlsx, .xls) 或 CSV 檔案",
        )

    # Parse and validate
    parsed_data, validation_errors = await service.parse_excel_file(
        file_content=file_content,
        scholarship_type_id=scholarship.id,
        academic_year=academic_year,
        semester=semester,
    )

    # Additional validations
    for row_data in parsed_data:
        # Check college permission (skip for super_admin)
        if current_user.role != UserRole.super_admin:
            is_valid, error_msg = await service.validate_college_permission(
                student_id=row_data["student_id"],
                college_code=college_code,
                dept_code=row_data.get("dept_code"),
            )
            if not is_valid:
                validation_errors.append(
                    {
                        "row_number": parsed_data.index(row_data) + 2,
                        "student_id": row_data["student_id"],
                        "field": "college_code",
                        "error_type": "permission_error",
                        "message": error_msg,
                    }
                )

        # Check duplicate
        is_duplicate, error_msg = await service.check_duplicate_application(
            student_id=row_data["student_id"],
            scholarship_type_id=scholarship.id,
            academic_year=academic_year,
            semester=semester,
        )
        if is_duplicate:
            validation_errors.append(
                {
                    "row_number": parsed_data.index(row_data) + 2,
                    "student_id": row_data["student_id"],
                    "field": "duplicate",
                    "error_type": "duplicate_application",
                    "message": error_msg,
                }
            )

    # Create batch import record
    batch_import = await service.create_batch_import_record(
        importer_id=current_user.id,
        college_code=college_code or "super_admin",  # Use special value for super_admin
        scholarship_type_id=scholarship.id,
        academic_year=academic_year,
        semester=semester,
        file_name=file.filename,
        total_records=len(parsed_data),
    )

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
    return BatchImportUploadResponse(
        batch_id=batch_import.id,
        file_name=file.filename,
        total_records=len(parsed_data),
        preview_data=parsed_data[:10],
        validation_summary={
            "total_errors": len(validation_errors),
            "has_errors": len(validation_errors) > 0,
            "errors": validation_errors[:20],  # Limit preview errors
        },
    )


@router.post("/{batch_id}/confirm", response_model=BatchImportConfirmResponse)
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
    if batch_import.import_status != BatchImportStatus.pending.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"此批次狀態為 {batch_import.import_status}，無法再次確認",
        )

    if not request.confirm:
        # Cancel the batch
        batch_import.import_status = BatchImportStatus.cancelled.value
        await db.commit()
        return BatchImportConfirmResponse(
            batch_id=batch_id,
            success_count=0,
            failed_count=0,
            errors=[],
            created_application_ids=[],
        )

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

        return BatchImportConfirmResponse(
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

    except BatchImportError as e:
        # Re-raise to let the global exception handler deal with it
        # Batch status has already been updated to 'failed' in the service
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=e.message,
        )


@router.get("/history", response_model=BatchImportHistoryResponse)
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
    # Query batch imports
    if current_user.role == UserRole.super_admin:
        # Super admin can see all batch imports
        stmt = select(BatchImport).order_by(desc(BatchImport.created_at)).offset(skip).limit(limit)
        count_stmt = select(BatchImport)
    else:
        # College role can only see their own
        stmt = (
            select(BatchImport)
            .where(BatchImport.importer_id == current_user.id)
            .order_by(desc(BatchImport.created_at))
            .offset(skip)
            .limit(limit)
        )
        count_stmt = select(BatchImport).where(BatchImport.importer_id == current_user.id)

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
                import_status=batch.import_status,
                created_at=batch.created_at,
                importer_name=batch.importer.name if batch.importer else None,
            )
        )

    return BatchImportHistoryResponse(total=total, items=items)


@router.get("/{batch_id}/details", response_model=BatchImportDetailResponse)
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

    # Get created applications
    created_app_ids = [app.id for app in batch_import.applications]

    return BatchImportDetailResponse(
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
        import_status=batch_import.import_status,
        created_at=batch_import.created_at,
        updated_at=batch_import.updated_at,
        importer_name=batch_import.importer.name if batch_import.importer else None,
        created_applications=created_app_ids,
    )


@router.get("/template")
async def download_batch_import_template(
    scholarship_type: str = Query(..., description="獎學金類型代碼"),
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    """
    下載批次匯入範例 Excel 檔案

    **範例檔案包含**:
    - 必要欄位: student_id, student_name
    - 可選欄位: dept_code, bank_account, account_holder, bank_name,
                supervisor_id, supervisor_name, supervisor_email,
                contact_phone, contact_address, gpa, class_ranking, dept_ranking
    - 子類型欄位: 根據獎學金類型動態生成 sub_type_* 欄位

    **權限**: 僅限 college 角色
    """
    # Validate scholarship type
    stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
    result = await db.execute(stmt)
    scholarship = result.scalar_one_or_none()

    if not scholarship:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"獎學金類型 {scholarship_type} 不存在",
        )

    # Define base columns
    columns = [
        "student_id",  # 必填
        "student_name",  # 必填
        "dept_code",
        "bank_account",
        "account_holder",
        "bank_name",
        "supervisor_id",
        "supervisor_name",
        "supervisor_email",
        "contact_phone",
        "contact_address",
        "gpa",
        "class_ranking",
        "dept_ranking",
    ]

    # Add sub_type columns if scholarship has sub types
    if scholarship.sub_type_list:
        for sub_type_code in scholarship.sub_type_list:
            columns.append(f"sub_type_{sub_type_code}")

    # Create sample data (2 example rows)
    sample_data = [
        {
            "student_id": "111111111",
            "student_name": "王小明",
            "dept_code": "5201",
            "bank_account": "1234567890123",
            "account_holder": "王小明",
            "bank_name": "台灣銀行",
            "supervisor_id": "T123456",
            "supervisor_name": "李教授",
            "supervisor_email": "professor@example.com",
            "contact_phone": "0912345678",
            "contact_address": "新竹市大學路1001號",
            "gpa": 3.8,
            "class_ranking": 1,
            "dept_ranking": 5,
        },
        {
            "student_id": "222222222",
            "student_name": "陳小華",
            "dept_code": "5202",
            "bank_account": "9876543210987",
            "account_holder": "陳小華",
            "bank_name": "第一銀行",
            "supervisor_id": "T234567",
            "supervisor_name": "張教授",
            "supervisor_email": "prof.zhang@example.com",
            "contact_phone": "0923456789",
            "contact_address": "新竹市光復路二段101號",
            "gpa": 3.9,
            "class_ranking": 2,
            "dept_ranking": 3,
        },
    ]

    # Add sub_type sample values if applicable
    if scholarship.sub_type_list:
        for i, row in enumerate(sample_data):
            for j, sub_type_code in enumerate(scholarship.sub_type_list):
                # First row has first sub_type as Y, second row has second sub_type as Y
                row[f"sub_type_{sub_type_code}"] = "Y" if i == j else ""

    # Create DataFrame
    df = pd.DataFrame(sample_data, columns=columns)

    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="批次匯入範例")

    output.seek(0)

    # Return as downloadable file
    filename = f"batch_import_template_{scholarship_type}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )

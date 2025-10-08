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
        .where(ApplicationField.is_active == True)
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

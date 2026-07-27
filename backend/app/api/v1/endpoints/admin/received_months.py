"""Admin endpoints: 匯入已領月份數 (preview / confirm / cancel).

Mounted under /admin/received-months. Driven by the 「匯入已領月份數」 dialog on
the 學生領獎紀錄查詢 page.
"""

import logging
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.db.deps import get_db
from app.models.user import User
from app.services.received_months_import_service import ReceivedMonthsImportService
from app.services.received_months_template import build_received_months_template

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_EXTENSION = ".xlsx"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TEMPLATE_FILENAME = "獲獎生已領月份統計表_範例.xlsx"


@router.get("/template")
async def download_received_months_template(
    current_user: User = Depends(require_admin),
):
    """Download the example workbook for 匯入已領月份數.

    Binary download, so this returns the file rather than the usual
    {success, message, data} envelope.
    """
    encoded_filename = quote(TEMPLATE_FILENAME, encoding="utf-8")
    return StreamingResponse(
        BytesIO(build_received_months_template()),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"},
    )


@router.post("/preview")
async def preview_received_months_import(
    scholarship_type_id: int = Form(..., description="Scholarship type the file belongs to"),
    file: UploadFile = File(..., description="國科會 獲獎生已領月份統計表 (.xlsx)"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Parse an upload and stage it for review. Writes nothing to the ledger.

    ScholarshipException is mapped to its HTTP status by the global handler in
    app.main; only the extension check needs to raise directly.
    """
    if not file.filename or not file.filename.lower().endswith(ALLOWED_EXTENSION):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="請上傳 Excel 檔案 (.xlsx)",
        )

    content = await file.read()
    service = ReceivedMonthsImportService()
    import_run = await service.preview(
        db,
        content=content,
        file_name=file.filename,
        scholarship_type_id=scholarship_type_id,
        importer_id=current_user.id,
    )

    parsed = import_run.parsed_data or {}
    return {
        "success": True,
        "message": f"已解析 {import_run.total_rows} 筆資料，尚未匯入",
        "data": {
            "import_id": import_run.id,
            "file_name": import_run.file_name,
            "scholarship_type_id": import_run.scholarship_type_id,
            "total_rows": import_run.total_rows,
            "valid_rows": import_run.valid_rows,
            "warning_rows": import_run.warning_rows,
            "error_rows": import_run.error_rows,
            "headers": parsed.get("headers", []),
            "rows": parsed.get("rows", []),
        },
    }


@router.post("/{import_id}/confirm")
async def confirm_received_months_import(
    import_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Commit a staged import into the ledger."""
    service = ReceivedMonthsImportService()
    result = await service.confirm(db, import_id, importer_id=current_user.id)
    return {
        "success": True,
        "message": f"成功匯入 {result['created'] + result['updated']} 位學生"
        f"（新增 {result['created']}，更新 {result['updated']}）",
        "data": result,
    }


@router.post("/{import_id}/cancel")
async def cancel_received_months_import(
    import_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Discard a staged import without touching the ledger."""
    service = ReceivedMonthsImportService()
    await service.cancel(db, import_id)
    return {
        "success": True,
        "message": "已取消匯入",
        "data": {"import_id": import_id},
    }

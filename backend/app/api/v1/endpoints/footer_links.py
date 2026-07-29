"""Admin-managed footer 相關連結 (Related Links).

Each entry is either an external URL or an uploaded document (PDF / Office /
ODF) streamed back through this API — never a direct MinIO URL.
"""

import io
import logging
import uuid
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.document_formats import (
    REFERENCE_DOC_EXTENSIONS,
    content_type_for_extension,
    extension_for_filename,
)
from app.core.path_security import validate_upload_file
from app.core.security import get_current_user, require_admin
from app.db.deps import get_db
from app.models.footer_link import FooterLink, FooterLinkType
from app.models.user import User
from app.schemas.footer_link import (
    MAX_TITLE_LENGTH,
    FooterLinkCreate,
    FooterLinkReorderRequest,
    FooterLinkResponse,
    FooterLinkUpdate,
)
from app.services.minio_service import minio_service

router = APIRouter()
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE_MB = 10


def _serialize(link: FooterLink) -> dict:
    return FooterLinkResponse.model_validate(link).model_dump(mode="json")


def _is_admin(user: User) -> bool:
    """Same predicate `require_admin` enforces on the write endpoints.

    Reuses the model helpers rather than string-matching roles so the read
    gates below can never drift from the write gates.
    """
    return user.is_admin() or user.is_super_admin()


async def _get_link_or_404(db: AsyncSession, link_id: int) -> FooterLink:
    result = await db.execute(select(FooterLink).where(FooterLink.id == link_id))
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="連結不存在")
    return link


async def _next_sort_order(db: AsyncSession) -> int:
    max_order = (await db.execute(select(func.max(FooterLink.sort_order)))).scalar()
    return (max_order + 1) if max_order is not None else 0


@router.get("")
async def list_footer_links(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List footer links ordered by sort_order then id.

    Any authenticated user may read. ``include_inactive`` is honoured for
    admins only — a non-admin always gets the active (publicly shown) set,
    so a hidden link cannot leak through the query parameter.
    """
    stmt = select(FooterLink)
    if not (include_inactive and _is_admin(current_user)):
        stmt = stmt.where(FooterLink.is_active.is_(True))
    stmt = stmt.order_by(FooterLink.sort_order.asc(), FooterLink.id.asc())

    result = await db.execute(stmt)
    links = result.scalars().all()
    return {
        "success": True,
        "message": "OK",
        "data": [_serialize(link) for link in links],
    }


@router.post("")
async def create_footer_link(
    payload: FooterLinkCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create an external-URL footer link. Admin only."""
    link = FooterLink(
        title_zh=payload.title_zh,
        title_en=payload.title_en,
        link_type=FooterLinkType.url,
        url=payload.url,
        is_active=payload.is_active,
        sort_order=await _next_sort_order(db),
        created_by=current_user.id,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)

    logger.info(
        "footer link created (url) id=%s by user_id=%s",
        link.id,
        current_user.id,
        extra={"actor_user_id": current_user.id, "footer_link_id": link.id},
    )

    return {"success": True, "message": "已新增", "data": _serialize(link)}


@router.post("/upload")
async def upload_footer_link_file(
    file: UploadFile = File(...),
    title_zh: str = Form(...),
    title_en: Optional[str] = Form(None),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a file-backed footer link by uploading a document. Admin only."""
    stripped_zh = (title_zh or "").strip()
    if not stripped_zh:
        raise HTTPException(status_code=400, detail="標題不得為空")
    if len(stripped_zh) > MAX_TITLE_LENGTH:
        raise HTTPException(status_code=400, detail=f"標題不得超過 {MAX_TITLE_LENGTH} 字")

    stripped_en = (title_en or "").strip() or None
    if stripped_en and len(stripped_en) > MAX_TITLE_LENGTH:
        raise HTTPException(status_code=400, detail=f"英文標題不得超過 {MAX_TITLE_LENGTH} 字")

    file_content = await file.read()
    validate_upload_file(
        filename=file.filename,
        allowed_extensions=REFERENCE_DOC_EXTENSIONS,
        max_size_mb=MAX_UPLOAD_SIZE_MB,
        file_size=len(file_content),
        allow_unicode=True,
    )

    ext = extension_for_filename(file.filename or "")
    object_name = f"footer-links/link_{uuid.uuid4().hex}{ext}"
    # Derive from the validated extension — never persist file.content_type.
    # That header is client-supplied, and this document is later streamed back
    # with `Content-Disposition: inline` from our own origin, so a .pdf
    # declared text/html would render as an attacker-controlled page.
    content_type = content_type_for_extension(ext)

    minio_service.client.put_object(
        bucket_name=minio_service.default_bucket,
        object_name=object_name,
        data=io.BytesIO(file_content),
        length=len(file_content),
        content_type=content_type,
    )

    link = FooterLink(
        title_zh=stripped_zh,
        title_en=stripped_en,
        link_type=FooterLinkType.file,
        object_name=object_name,
        original_filename=file.filename or "",
        content_type=content_type,
        file_size=len(file_content),
        is_active=True,
        sort_order=await _next_sort_order(db),
        created_by=current_user.id,
    )
    db.add(link)

    try:
        await db.commit()
    except Exception:
        # Don't leave an unreferenced object behind if the row never lands.
        await db.rollback()
        try:
            minio_service.client.remove_object(minio_service.default_bucket, object_name)
        except Exception:
            logger.warning(
                "Failed to clean up orphaned footer link object %s",
                object_name,
                exc_info=True,
            )
        raise

    await db.refresh(link)

    logger.info(
        "footer link created (file) id=%s by user_id=%s",
        link.id,
        current_user.id,
        extra={"actor_user_id": current_user.id, "footer_link_id": link.id},
    )

    return {"success": True, "message": "上傳成功", "data": _serialize(link)}


# NOTE: declared before /{link_id} so "reorder" is not captured as a path param.
@router.patch("/reorder")
async def reorder_footer_links(
    payload: FooterLinkReorderRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Persist a new display order. Admin only."""
    requested_ids = [item.id for item in payload.items]
    result = await db.execute(select(FooterLink).where(FooterLink.id.in_(requested_ids)))
    links = {link.id: link for link in result.scalars().all()}

    missing = [link_id for link_id in requested_ids if link_id not in links]
    if missing:
        raise HTTPException(status_code=400, detail=f"ids not found: {missing}")

    for item in payload.items:
        links[item.id].sort_order = item.sort_order

    await db.commit()

    return {
        "success": True,
        "message": "已重新排序",
        "data": {"updated": len(payload.items)},
    }


@router.patch("/{link_id}")
async def update_footer_link(
    link_id: int,
    payload: FooterLinkUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a footer link's titles, URL, or visibility. Admin only."""
    link = await _get_link_or_404(db, link_id)

    if payload.url is not None and link.link_type != FooterLinkType.url:
        raise HTTPException(
            status_code=400,
            detail="檔案類型的連結無法設定網址，請刪除後重新上傳",
        )

    if payload.title_zh is not None:
        link.title_zh = payload.title_zh
    # title_en is nullable: an explicit blank string clears it (normalized to
    # None by the schema), so we can't distinguish "clear" from "absent" here.
    # Clearing is the useful behaviour and matches the admin form.
    if "title_en" in payload.model_fields_set:
        link.title_en = payload.title_en
    if payload.url is not None:
        link.url = payload.url
    if payload.is_active is not None:
        link.is_active = payload.is_active

    await db.commit()
    await db.refresh(link)

    return {"success": True, "message": "已更新", "data": _serialize(link)}


@router.delete("/{link_id}")
async def delete_footer_link(
    link_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a footer link, removing its stored file when present. Admin only."""
    link = await _get_link_or_404(db, link_id)
    object_name = link.object_name

    await db.delete(link)
    await db.commit()

    if object_name:
        try:
            minio_service.client.remove_object(minio_service.default_bucket, object_name)
        except Exception:
            logger.warning(
                "Failed to remove footer link object %s from MinIO",
                object_name,
                exc_info=True,
            )

    logger.info(
        "footer link deleted id=%s by user_id=%s",
        link_id,
        current_user.id,
        extra={"actor_user_id": current_user.id, "footer_link_id": link_id},
    )

    return {"success": True, "message": "已刪除", "data": {"deleted": True}}


@router.get("/{link_id}/file")
async def stream_footer_link_file(
    link_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream a file-backed footer link's document. Any authenticated user.

    Inactive links stay readable for admins only so a hidden document isn't
    still fetchable by a student holding a stale URL.
    """
    link = await _get_link_or_404(db, link_id)

    if link.link_type != FooterLinkType.file or not link.object_name:
        raise HTTPException(status_code=404, detail="此連結沒有檔案")
    if not link.is_active and not _is_admin(current_user):
        raise HTTPException(status_code=404, detail="連結不存在")

    response = None
    try:
        response = minio_service.client.get_object(
            bucket_name=minio_service.default_bucket,
            object_name=link.object_name,
        )
        file_content = response.read()
    except Exception as e:
        logger.exception("Failed to fetch footer link file")
        raise HTTPException(status_code=500, detail="無法取得文件") from e
    finally:
        if response is not None:
            response.close()
            response.release_conn()

    download_name = link.original_filename or link.object_name.split("/")[-1]
    encoded_name = quote(download_name, safe="")

    return StreamingResponse(
        io.BytesIO(file_content),
        media_type=link.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
            # Content-Length is REQUIRED: without it the frontend PDF viewer
            # mis-reads the stream and reports a bogus "password protected".
            "Content-Length": str(len(file_content)),
            "Accept-Ranges": "bytes",
            "X-Content-Type-Options": "nosniff",
        },
    )


__all__: List[str] = ["router"]

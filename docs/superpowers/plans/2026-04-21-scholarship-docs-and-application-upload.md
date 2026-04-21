# Scholarship Docs Display & Application Document Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add system-wide 獎學金要點 / 申請文件範例檔 documents (admin-uploaded, shown to students and reviewers), plus a per-application 申請文件 upload field with submission preview.

**Architecture:** Reuse the existing `system_settings` table (key-value store) for the two global file object_names. Add `application_document_url` column to `applications`. New backend endpoints handle MinIO upload/proxy; a Next.js proxy route mirrors the existing `preview-terms` pattern for file delivery.

**Tech Stack:** FastAPI, SQLAlchemy (async), Alembic, MinIO, Next.js App Router, React, shadcn/ui

---

## File Map

**Backend — create:**
- `backend/alembic/versions/XXXX_add_application_document_url.py` — migration: add column

**Backend — modify:**
- `backend/app/models/application.py` — add `application_document_url` column
- `backend/app/schemas/application.py` — expose field in response schema
- `backend/app/api/v1/endpoints/system_settings.py` — add upload + file-serve + public-docs endpoints
- `backend/app/api/v1/endpoints/applications.py` — add application document upload/delete endpoints

**Frontend — create:**
- `frontend/app/api/v1/system-settings/file/[key]/route.ts` — Next.js proxy for global docs

**Frontend — modify:**
- `frontend/lib/api/modules/system-settings.ts` — add `getPublicDocs`, `uploadRegulations`, `uploadSampleDocument`
- `frontend/lib/api/modules/applications.ts` — add `uploadApplicationDocument`, `deleteApplicationDocument`
- `frontend/components/student-wizard/steps/NoticeAgreementStep.tsx` — reference docs buttons
- `frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx` — application doc upload + preview
- `frontend/components/professor-review-component.tsx` — regulations link button
- `frontend/components/college/review/ApplicationReviewPanel.tsx` — regulations link button
- `frontend/components/admin-management-interface.tsx` — system docs upload section

---

## Task 1: Migration — Add `application_document_url` to applications

**Files:**
- Create: `backend/alembic/versions/XXXX_add_application_document_url.py`

- [ ] **Step 1: Generate migration file**

```bash
cd /home/howard/ss_main/scholarship-system
docker compose -f docker-compose.dev.yml exec backend alembic revision --autogenerate -m "add_application_document_url_to_applications"
```

Expected: a new file created under `backend/alembic/versions/`.

- [ ] **Step 2: Replace auto-generated body with safe existence-checked version**

Open the newly created file and replace the `upgrade()` / `downgrade()` with:

```python
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("applications")]
    if "application_document_url" not in columns:
        op.add_column(
            "applications",
            sa.Column("application_document_url", sa.String(500), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("applications")]
    if "application_document_url" in columns:
        op.drop_column("applications", "application_document_url")
```

- [ ] **Step 3: Apply migration**

```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

Expected output ends with: `Running upgrade ... -> <revision>, add_application_document_url_to_applications`

- [ ] **Step 4: Verify column exists**

```bash
docker compose -f docker-compose.dev.yml exec db psql -U postgres -d scholarship_db -c "\d applications" | grep application_document
```

Expected: `application_document_url | character varying(500) |`

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat: add application_document_url column to applications"
```

---

## Task 2: Update Application Model and Schema

**Files:**
- Modify: `backend/app/models/application.py`
- Modify: `backend/app/schemas/application.py`

- [ ] **Step 1: Add column to SQLAlchemy model**

In `backend/app/models/application.py`, find the `document_status` column (around line 163) and add after it:

```python
    application_document_url = Column(String(500), nullable=True)  # 申請文件
```

- [ ] **Step 2: Expose field in ApplicationResponse schema**

Open `backend/app/schemas/application.py` and find the response schema class (likely `ApplicationResponse` or similar). Add:

```python
application_document_url: Optional[str] = None
```

Check which schema class is used in `GET /applications/{id}` — search for `ApplicationResponse` or `application_response` in `applications.py`. Add the field there.

- [ ] **Step 3: Verify backend starts without errors**

```bash
docker compose -f docker-compose.dev.yml restart backend
docker compose -f docker-compose.dev.yml logs backend --tail=20
```

Expected: No `ImportError` or `AttributeError`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/application.py backend/app/schemas/application.py
git commit -m "feat: expose application_document_url in application model and schema"
```

---

## Task 3: Backend — Application Document Upload/Delete Endpoints

**Files:**
- Modify: `backend/app/api/v1/endpoints/applications.py`

- [ ] **Step 1: Add upload endpoint**

At the end of `backend/app/api/v1/endpoints/applications.py`, add:

```python
@router.post("/{application_id}/application-document")
async def upload_application_document(
    application_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """Upload 申請文件 for a specific application (student only, must own the application)."""
    import io
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.core.path_security import validate_upload_file
    from app.models.application import Application
    from app.services.minio_service import minio_service

    # Fetch and authorize
    stmt = select(Application).where(
        Application.id == application_id,
        Application.user_id == current_user.id,
        Application.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="申請單不存在或無權限")

    allowed_extensions = [".pdf", ".jpg", ".jpeg", ".png"]
    file_content = await file.read()
    validate_upload_file(
        filename=file.filename,
        allowed_extensions=allowed_extensions,
        max_size_mb=10,
        file_size=len(file_content),
        allow_unicode=True,
    )

    ext = ""
    if file.filename:
        for e in allowed_extensions:
            if file.filename.lower().endswith(e):
                ext = e
                break

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    object_name = f"application-documents/{application_id}_{timestamp}{ext}"

    minio_service.client.put_object(
        bucket_name=minio_service.default_bucket,
        object_name=object_name,
        data=io.BytesIO(file_content),
        length=len(file_content),
        content_type=file.content_type or "application/octet-stream",
    )

    application.application_document_url = object_name
    await db.commit()

    return {
        "success": True,
        "message": "申請文件上傳成功",
        "data": {"application_document_url": object_name},
    }


@router.delete("/{application_id}/application-document")
async def delete_application_document(
    application_id: int,
    current_user: User = Depends(require_student),
    db: AsyncSession = Depends(get_db),
):
    """Delete 申請文件 for a specific application."""
    from sqlalchemy import select

    from app.models.application import Application

    stmt = select(Application).where(
        Application.id == application_id,
        Application.user_id == current_user.id,
        Application.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="申請單不存在或無權限")

    application.application_document_url = None
    await db.commit()

    return {"success": True, "message": "申請文件已刪除", "data": None}
```

- [ ] **Step 2: Restart backend and verify endpoints appear**

```bash
docker compose -f docker-compose.dev.yml restart backend
curl -s http://localhost:8000/openapi.json | python3 -c "import sys,json; paths=json.load(sys.stdin)['paths']; [print(p) for p in paths if 'application-document' in p]"
```

Expected output includes:
```
/api/v1/applications/{application_id}/application-document
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/endpoints/applications.py
git commit -m "feat: add application document upload and delete endpoints"
```

---

## Task 4: Backend — System Settings File Upload and Serve Endpoints

**Files:**
- Modify: `backend/app/api/v1/endpoints/system_settings.py`

- [ ] **Step 1: Add imports at the top of system_settings.py**

After the existing imports, add:

```python
from fastapi import File, UploadFile
from fastapi.responses import StreamingResponse
```

- [ ] **Step 2: Add the three new endpoints at the end of system_settings.py**

```python
_ALLOWED_DOC_KEYS = {"regulations_url", "sample_document_url"}


@router.get("/public-docs")
async def get_public_docs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return the object_names for 獎學金要點 and 申請文件範例檔.
    Accessible by any authenticated user (students, professors, college, admin).
    """
    from sqlalchemy import select

    from app.models.system_setting import SystemSetting

    stmt = select(SystemSetting).where(SystemSetting.key.in_(list(_ALLOWED_DOC_KEYS)))
    result = await db.execute(stmt)
    rows = result.scalars().all()
    data = {row.key: row.value for row in rows}
    return {"success": True, "message": "OK", "data": data}


@router.post("/upload/{doc_key}")
async def upload_system_doc(
    doc_key: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a global system document (獎學金要點 or 申請文件範例檔).
    Stores object_name in system_settings under the given key.
    Admin only.
    """
    import io
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.core.path_security import validate_upload_file
    from app.models.system_setting import ConfigCategory, ConfigDataType, SystemSetting
    from app.services.minio_service import minio_service

    if doc_key not in _ALLOWED_DOC_KEYS:
        raise HTTPException(status_code=400, detail=f"Invalid doc_key. Allowed: {_ALLOWED_DOC_KEYS}")

    allowed_extensions = [".pdf", ".doc", ".docx"]
    file_content = await file.read()
    validate_upload_file(
        filename=file.filename,
        allowed_extensions=allowed_extensions,
        max_size_mb=10,
        file_size=len(file_content),
        allow_unicode=True,
    )

    ext = ""
    if file.filename:
        for e in allowed_extensions:
            if file.filename.lower().endswith(e):
                ext = e
                break

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    object_name = f"system-docs/{doc_key}_{timestamp}{ext}"

    minio_service.client.put_object(
        bucket_name=minio_service.default_bucket,
        object_name=object_name,
        data=io.BytesIO(file_content),
        length=len(file_content),
        content_type=file.content_type or "application/octet-stream",
    )

    # Upsert into system_settings
    stmt = select(SystemSetting).where(SystemSetting.key == doc_key)
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = object_name
        setting.last_modified_by = current_user.id
    else:
        setting = SystemSetting(
            key=doc_key,
            value=object_name,
            category=ConfigCategory.file_storage,
            data_type=ConfigDataType.string,
            description="獎學金要點" if doc_key == "regulations_url" else "申請文件範例檔",
            is_sensitive=False,
            is_readonly=False,
            allow_empty=True,
            last_modified_by=current_user.id,
        )
        db.add(setting)

    await db.commit()
    return {"success": True, "message": "上傳成功", "data": {"key": doc_key, "object_name": object_name}}


@router.get("/file/{doc_key}")
async def get_system_doc_file(
    doc_key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Proxy a global system document from MinIO.
    Accessible by any authenticated user.
    """
    import io

    from sqlalchemy import select

    from app.models.system_setting import SystemSetting
    from app.services.minio_service import minio_service

    if doc_key not in _ALLOWED_DOC_KEYS:
        raise HTTPException(status_code=400, detail="Invalid doc_key")

    stmt = select(SystemSetting).where(SystemSetting.key == doc_key)
    result = await db.execute(stmt)
    setting = result.scalar_one_or_none()

    if not setting or not setting.value:
        raise HTTPException(status_code=404, detail="文件尚未上傳")

    try:
        response = minio_service.client.get_object(
            bucket_name=minio_service.default_bucket,
            object_name=setting.value,
        )
        file_content = response.read()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"無法取得文件: {str(e)}")

    content_type = "application/pdf"
    if setting.value.endswith(".doc"):
        content_type = "application/msword"
    elif setting.value.endswith(".docx"):
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    return StreamingResponse(
        io.BytesIO(file_content),
        media_type=content_type,
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{doc_key}.pdf"},
    )
```

- [ ] **Step 3: Add `get_current_user` to imports in system_settings.py**

The file currently imports `require_admin`. Add `get_current_user`:

```python
from app.core.security import require_admin, get_current_user
```

- [ ] **Step 4: Restart and verify**

```bash
docker compose -f docker-compose.dev.yml restart backend
curl -s http://localhost:8000/openapi.json | python3 -c "import sys,json; paths=json.load(sys.stdin)['paths']; [print(p) for p in paths if 'system-settings' in p and ('public' in p or 'upload' in p or 'file' in p)]"
```

Expected output includes:
```
/api/v1/system-settings/public-docs
/api/v1/system-settings/upload/{doc_key}
/api/v1/system-settings/file/{doc_key}
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/system_settings.py
git commit -m "feat: add system doc upload, serve, and public-docs endpoints"
```

---

## Task 5: Frontend — Next.js Proxy for System Settings Files

**Files:**
- Create: `frontend/app/api/v1/system-settings/file/[key]/route.ts`

- [ ] **Step 1: Create the directory**

```bash
mkdir -p /home/howard/ss_main/scholarship-system/frontend/app/api/v1/system-settings/file/\[key\]
```

- [ ] **Step 2: Create the proxy route**

Create `frontend/app/api/v1/system-settings/file/[key]/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";

const ALLOWED_KEYS = new Set(["regulations_url", "sample_document_url"]);

export async function GET(
  request: NextRequest,
  { params }: { params: { key: string } }
) {
  try {
    const { key } = params;

    if (!ALLOWED_KEYS.has(key)) {
      return NextResponse.json({ error: "Invalid key" }, { status: 400 });
    }

    const queryToken = request.nextUrl.searchParams.get("token");
    const authHeader = request.headers.get("authorization");
    const cookieToken =
      request.cookies.get("access_token")?.value ||
      request.cookies.get("auth_token")?.value;
    const token = queryToken || authHeader?.replace("Bearer ", "") || cookieToken;

    if (!token) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const baseUrl =
      process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL;
    if (!baseUrl) {
      return NextResponse.json(
        { error: "Backend not configured" },
        { status: 500 }
      );
    }

    let parsedUrl: URL;
    try {
      parsedUrl = new URL(baseUrl);
    } catch {
      return NextResponse.json(
        { error: "Invalid backend URL" },
        { status: 500 }
      );
    }

    const allowedHostnames = ["backend", "ss.test.nycu.edu.tw"];
    if (!allowedHostnames.includes(parsedUrl.hostname)) {
      return NextResponse.json(
        { error: "Untrusted backend hostname" },
        { status: 500 }
      );
    }

    const backendUrl = new URL(
      `/api/v1/system-settings/file/${key}`,
      baseUrl
    ).toString();

    const response = await fetch(backendUrl, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      return NextResponse.json(
        { error: "Failed to fetch document" },
        { status: response.status }
      );
    }

    const fileBuffer = await response.arrayBuffer();
    const contentType =
      response.headers.get("content-type") || "application/pdf";
    const contentDisposition =
      response.headers.get("content-disposition") || "inline";

    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": contentDisposition,
        "Content-Length": fileBuffer.byteLength.toString(),
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=3600",
      },
    });
  } catch {
    return NextResponse.json(
      { error: "Failed to retrieve document" },
      { status: 500 }
    );
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/api/v1/system-settings/
git commit -m "feat: add Next.js proxy route for system settings documents"
```

---

## Task 6: Frontend — API Client Additions

**Files:**
- Modify: `frontend/lib/api/modules/system-settings.ts`
- Modify: `frontend/lib/api/modules/applications.ts`

- [ ] **Step 1: Add methods to system-settings API module**

In `frontend/lib/api/modules/system-settings.ts`, inside the returned object of `createSystemSettingsApi()`, add after `getAuditLogs`:

```typescript
    /**
     * Get public doc object_names (regulations_url, sample_document_url).
     * Accessible by any authenticated user.
     */
    getPublicDocs: async (): Promise<
      ApiResponse<{ regulations_url?: string; sample_document_url?: string }>
    > => {
      const response = await (typedClient.raw.GET as any)(
        "/api/v1/system-settings/public-docs"
      );
      return toApiResponse(response);
    },

    /**
     * Upload 獎學金要點 (admin only).
     */
    uploadRegulations: async (
      file: File
    ): Promise<ApiResponse<{ key: string; object_name: string }>> => {
      const formData = new FormData();
      formData.append("file", file);
      const baseUrl =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const token = localStorage.getItem("auth_token") || "";
      const res = await fetch(
        `${baseUrl}/api/v1/system-settings/upload/regulations_url`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        }
      );
      const json = await res.json();
      return json;
    },

    /**
     * Upload 申請文件範例檔 (admin only).
     */
    uploadSampleDocument: async (
      file: File
    ): Promise<ApiResponse<{ key: string; object_name: string }>> => {
      const formData = new FormData();
      formData.append("file", file);
      const baseUrl =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const token = localStorage.getItem("auth_token") || "";
      const res = await fetch(
        `${baseUrl}/api/v1/system-settings/upload/sample_document_url`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        }
      );
      const json = await res.json();
      return json;
    },
```

- [ ] **Step 2: Add application document methods**

Open `frontend/lib/api/modules/applications.ts`. Find the end of the returned object and add:

```typescript
    /**
     * Upload 申請文件 for a specific application.
     */
    uploadApplicationDocument: async (
      applicationId: number,
      file: File
    ): Promise<ApiResponse<{ application_document_url: string }>> => {
      const formData = new FormData();
      formData.append("file", file);
      const baseUrl =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const token = localStorage.getItem("auth_token") || "";
      const res = await fetch(
        `${baseUrl}/api/v1/applications/${applicationId}/application-document`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        }
      );
      const json = await res.json();
      return json;
    },

    /**
     * Delete 申請文件 for a specific application.
     */
    deleteApplicationDocument: async (
      applicationId: number
    ): Promise<ApiResponse<null>> => {
      const response = await (typedClient.raw.DELETE as any)(
        `/api/v1/applications/${applicationId}/application-document`
      );
      return toApiResponse(response);
    },
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /home/howard/ss_main/scholarship-system/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: No errors related to the new methods.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/modules/system-settings.ts frontend/lib/api/modules/applications.ts
git commit -m "feat: add system-settings and application document API client methods"
```

---

## Task 7: Frontend — NoticeAgreementStep Reference Docs

**Files:**
- Modify: `frontend/components/student-wizard/steps/NoticeAgreementStep.tsx`

- [ ] **Step 1: Add state and data-fetching**

After the existing imports, the component currently opens with `useState`. Add the new import and state:

```typescript
// Add to imports at top
import { api } from "@/lib/api";
import { FilePreviewDialog } from "@/components/file-preview-dialog";

// Inside the component, after const [hasReadNotice, setHasReadNotice] = ...
const [publicDocs, setPublicDocs] = useState<{
  regulations_url?: string;
  sample_document_url?: string;
}>({});
const [previewFile, setPreviewFile] = useState<{
  url: string;
  filename: string;
  type: string;
} | null>(null);
const [showPreview, setShowPreview] = useState(false);

useEffect(() => {
  api.systemSettings.getPublicDocs().then((res) => {
    if (res.success && res.data) setPublicDocs(res.data);
  });
}, []);
```

- [ ] **Step 2: Add helper to open preview**

Inside the component, add:

```typescript
const handleOpenDoc = (key: "regulations_url" | "sample_document_url", label: string) => {
  const token = localStorage.getItem("auth_token") || "";
  const url = `/api/v1/system-settings/file/${key}?token=${encodeURIComponent(token)}`;
  setPreviewFile({ url, filename: label, type: "application/pdf" });
  setShowPreview(true);
};
```

- [ ] **Step 3: Add i18n strings**

In both `zh` and `en` objects inside the `notices` constant, add:

```typescript
// zh
referenceDocs: "參考文件",
regulations: "獎學金要點",
sampleDocument: "申請文件範例檔",
notProvided: "尚未提供",

// en
referenceDocs: "Reference Documents",
regulations: "Scholarship Regulations",
sampleDocument: "Sample Application Documents",
notProvided: "Not available",
```

- [ ] **Step 4: Add reference docs UI block**

In the JSX, find the Important Notice Alert and the Notice Content Card. Insert the new block **between** them (after the Alert, before the `<Card className="border-2">`):

```tsx
{/* Reference Documents */}
<div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
  <p className="text-sm font-semibold text-blue-900 mb-3">{t.referenceDocs}</p>
  <div className="flex gap-3">
    <Button
      variant="outline"
      size="sm"
      onClick={() => handleOpenDoc("regulations_url", t.regulations)}
      disabled={!publicDocs.regulations_url}
      className="flex items-center gap-2"
    >
      <FileText className="h-4 w-4" />
      {t.regulations}
      {!publicDocs.regulations_url && (
        <span className="text-xs text-gray-400 ml-1">({t.notProvided})</span>
      )}
    </Button>
    <Button
      variant="outline"
      size="sm"
      onClick={() => handleOpenDoc("sample_document_url", t.sampleDocument)}
      disabled={!publicDocs.sample_document_url}
      className="flex items-center gap-2"
    >
      <FileText className="h-4 w-4" />
      {t.sampleDocument}
      {!publicDocs.sample_document_url && (
        <span className="text-xs text-gray-400 ml-1">({t.notProvided})</span>
      )}
    </Button>
  </div>
</div>
```

- [ ] **Step 5: Add FilePreviewDialog at bottom of JSX**

Just before the closing `</div>` of the component return:

```tsx
<FilePreviewDialog
  open={showPreview}
  onClose={() => setShowPreview(false)}
  file={previewFile}
  locale={locale}
/>
```

- [ ] **Step 6: Add missing React hooks import**

Make sure `useEffect` is imported from React if not already:

```typescript
import React, { useState, useEffect } from "react";
```

- [ ] **Step 7: Verify TypeScript**

```bash
cd /home/howard/ss_main/scholarship-system/frontend && npx tsc --noEmit 2>&1 | grep NoticeAgreement
```

Expected: No errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/student-wizard/steps/NoticeAgreementStep.tsx
git commit -m "feat: add reference docs buttons to NoticeAgreementStep"
```

---

## Task 8: Frontend — ScholarshipApplicationStep Application Document Upload

**Files:**
- Modify: `frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx`

- [ ] **Step 1: Add new state variables**

Find the block of bank document state variables (around line 113–128):

```typescript
const [bankDocumentFiles, setBankDocumentFiles] = useState<File[]>([]);
const [existingBankDocument, setExistingBankDocument] = useState<...
```

Add immediately after the bank document state block:

```typescript
const [applicationDocumentFiles, setApplicationDocumentFiles] = useState<File[]>([]);
const [existingApplicationDocument, setExistingApplicationDocument] = useState<string | null>(null);
const [showAppDocPreview, setShowAppDocPreview] = useState(false);
const [appDocPreviewFile, setAppDocPreviewFile] = useState<{
  url: string;
  filename: string;
  type: string;
} | null>(null);
```

- [ ] **Step 2: Add i18n strings**

In the `t.zh` object (around line 148), add after `deleteBankDoc`:

```typescript
applicationDocument: "申請文件",
applicationDocumentUploaded: "申請文件已上傳",
deleteAppDoc: "刪除",
```

In the `t.en` object, add after `deleteBankDoc`:

```typescript
applicationDocument: "Application Document",
applicationDocumentUploaded: "Application document uploaded",
deleteAppDoc: "Delete",
```

- [ ] **Step 3: Load existing application document**

In the `useEffect` that loads editing application data (around line 400), after loading bank document data, add logic to set `existingApplicationDocument` from `editingApplication.application_document_url` if present:

```typescript
if (editingApplication.application_document_url) {
  setExistingApplicationDocument(editingApplication.application_document_url);
}
```

- [ ] **Step 4: Add preview handler**

Find `handlePreviewBankDocument` (around line 342). Add a similar function after it:

```typescript
const handlePreviewAppDocument = () => {
  if (!existingApplicationDocument) return;
  const filename =
    existingApplicationDocument.split("/").pop()?.split("?")[0] ||
    "application_document";
  const token = localStorage.getItem("auth_token") || "";
  const previewParams = new URLSearchParams({
    fileId: filename,
    filename,
    type: "application_document",
    token,
    userId: String(userId),
  });
  const previewUrl = `/api/v1/preview?${previewParams.toString()}`;
  let fileTypeDisplay = "other";
  if (filename.toLowerCase().endsWith(".pdf")) fileTypeDisplay = "application/pdf";
  else if ([".jpg", ".jpeg", ".png"].some((ext) => filename.toLowerCase().endsWith(ext)))
    fileTypeDisplay = "image";
  setAppDocPreviewFile({ url: previewUrl, filename, type: fileTypeDisplay });
  setShowAppDocPreview(true);
};
```

- [ ] **Step 5: Add upload to handleSavePersonalInfo and handleSubmit**

**Case A: editing existing application** — upload in `handleSavePersonalInfo`, after the bank document upload block (around line 324):

```typescript
if (applicationDocumentFiles.length > 0 && editingApplication?.id) {
  const appDocResp = await api.applications.uploadApplicationDocument(
    editingApplication.id,
    applicationDocumentFiles[0]
  );
  if (!appDocResp.success)
    throw new Error(appDocResp.message || "Failed to upload application document");
  setExistingApplicationDocument(appDocResp.data?.application_document_url || null);
  setApplicationDocumentFiles([]);
}
```

**Case B: new application** — in `handleSubmit` (or `handleSaveDraft`), after the application is created and an ID is returned, add the same upload call using the new application's `id`. Search for the `createApplication(...)` call, capture its return value, and upload:

```typescript
// after: const createdApp = await createApplication(...)
if (applicationDocumentFiles.length > 0 && createdApp?.id) {
  await api.applications.uploadApplicationDocument(
    createdApp.id,
    applicationDocumentFiles[0]
  );
}
```

Inspect `handleSubmit` / `handleSaveDraft` in the file to find the exact location — the pattern is `createApplication({...})` returning an application object with an `id`.

- [ ] **Step 6: Add delete handler**

After `handleDeleteBankDocument`, add:

```typescript
const handleDeleteAppDocument = async () => {
  if (!editingApplication?.id) return;
  try {
    const response = await api.applications.deleteApplicationDocument(
      editingApplication.id
    );
    if (response.success) {
      toast.success(locale === "zh" ? "申請文件已刪除" : "Document deleted");
      setExistingApplicationDocument(null);
    } else {
      throw new Error(response.message || "Delete failed");
    }
  } catch (err: any) {
    toast.error(err.message || "刪除失敗");
  }
};
```

- [ ] **Step 7: Add upload UI in JSX**

Find the bank document upload section (the `<Card>` containing 存摺封面). Add the application document UI directly below it, before the closing `</CardContent>` of the personal info card:

```tsx
{/* Application Document Upload */}
<div className="mt-6 pt-6 border-t">
  <h4 className="font-semibold text-gray-800 mb-4 flex items-center gap-2">
    <FileText className="h-5 w-5 text-nycu-blue-600" />
    {text.applicationDocument}
  </h4>

  {existingApplicationDocument ? (
    <div className="flex items-center gap-3 p-3 bg-green-50 rounded-lg border border-green-200">
      <CheckCircle className="h-5 w-5 text-green-600 flex-shrink-0" />
      <span className="text-sm text-green-800 flex-1">
        {text.applicationDocumentUploaded}
      </span>
      <Button
        variant="ghost"
        size="sm"
        onClick={handlePreviewAppDocument}
        className="text-nycu-blue-600"
      >
        <Eye className="h-4 w-4 mr-1" />
        {text.preview}
      </Button>
      <Button
        variant="ghost"
        size="sm"
        onClick={handleDeleteAppDocument}
        className="text-red-600"
      >
        <X className="h-4 w-4 mr-1" />
        {text.deleteAppDoc}
      </Button>
    </div>
  ) : (
    <FileUpload
      onFilesChange={setApplicationDocumentFiles}
      acceptedTypes={[".pdf", ".jpg", ".jpeg", ".png"]}
      maxFiles={1}
      maxSizeMB={10}
    />
  )}
  <p className="text-xs text-gray-500 mt-2">{text.fileFormats}</p>
  <p className="text-xs text-gray-500">{text.fileSizeLimit}</p>
</div>
```

- [ ] **Step 8: Add FilePreviewDialog for app document**

Find the `<FilePreviewDialog>` for the bank document preview (around line 1418). Add another one after it:

```tsx
<FilePreviewDialog
  open={showAppDocPreview}
  onClose={() => setShowAppDocPreview(false)}
  file={appDocPreviewFile}
  locale={locale}
/>
```

- [ ] **Step 9: Verify TypeScript**

```bash
cd /home/howard/ss_main/scholarship-system/frontend && npx tsc --noEmit 2>&1 | grep ScholarshipApplication
```

Expected: No errors.

- [ ] **Step 10: Commit**

```bash
git add frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx
git commit -m "feat: add application document upload field to ScholarshipApplicationStep"
```

---

## Task 9: Frontend — Submit Preview Dialog Enhancements

**Files:**
- Modify: `frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx`

- [ ] **Step 1: Add "uploaded documents" section to submit preview**

In the submit preview Dialog (starts around line 1426), find the `<Separator />` after the Personal Info section (around line 1548). Insert a new section **after** that separator and **before** the Scholarship Info section:

```tsx
{/* Uploaded Documents */}
<div>
  <h3 className="text-sm font-semibold text-gray-500 mb-2">
    {locale === "zh" ? "上傳文件" : "Uploaded Documents"}
  </h3>
  <div className="space-y-2 text-sm bg-gray-50 rounded-lg p-4">
    {/* Passbook */}
    <div className="flex items-center justify-between">
      <span className="text-gray-500">
        {locale === "zh" ? "存摺封面" : "Passbook Cover"}
      </span>
      <div className="flex items-center gap-2">
        {existingBankDocument ? (
          <>
            <CheckCircle className="h-4 w-4 text-green-600" />
            <span className="text-green-700 font-medium">
              {locale === "zh" ? "已上傳" : "Uploaded"}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={handlePreviewBankDocument}
              className="h-6 px-2 text-nycu-blue-600"
            >
              <Eye className="h-3 w-3 mr-1" />
              {locale === "zh" ? "預覽" : "Preview"}
            </Button>
          </>
        ) : (
          <>
            <AlertCircle className="h-4 w-4 text-amber-500" />
            <span className="text-amber-700">
              {locale === "zh" ? "未上傳" : "Not uploaded"}
            </span>
          </>
        )}
      </div>
    </div>

    {/* Application Document */}
    <div className="flex items-center justify-between">
      <span className="text-gray-500">
        {locale === "zh" ? "申請文件" : "Application Document"}
      </span>
      <div className="flex items-center gap-2">
        {existingApplicationDocument ? (
          <>
            <CheckCircle className="h-4 w-4 text-green-600" />
            <span className="text-green-700 font-medium">
              {locale === "zh" ? "已上傳" : "Uploaded"}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={handlePreviewAppDocument}
              className="h-6 px-2 text-nycu-blue-600"
            >
              <Eye className="h-3 w-3 mr-1" />
              {locale === "zh" ? "預覽" : "Preview"}
            </Button>
          </>
        ) : (
          <>
            <AlertCircle className="h-4 w-4 text-amber-500" />
            <span className="text-amber-700">
              {locale === "zh" ? "未上傳" : "Not uploaded"}
            </span>
          </>
        )}
      </div>
    </div>
  </div>
</div>

<Separator />
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /home/howard/ss_main/scholarship-system/frontend && npx tsc --noEmit 2>&1 | grep -c "error"
```

Expected: `0`

- [ ] **Step 3: Commit**

```bash
git add frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx
git commit -m "feat: add document upload status to submit preview dialog"
```

---

## Task 10: Frontend — Professor Review Regulations Link

**Files:**
- Modify: `frontend/components/professor-review-component.tsx`

- [ ] **Step 1: Add state and data-fetching at top of component**

Find the existing state declarations near the top of `ProfessorReviewComponent`. Add:

```typescript
import { FilePreviewDialog } from "@/components/file-preview-dialog";
// ...inside component:
const [regulationsUrl, setRegulationsUrl] = useState<string | null>(null);
const [showRegulations, setShowRegulations] = useState(false);
const [regulationsFile, setRegulationsFile] = useState<{
  url: string;
  filename: string;
  type: string;
} | null>(null);

useEffect(() => {
  api.systemSettings.getPublicDocs().then((res) => {
    if (res.success && res.data?.regulations_url)
      setRegulationsUrl(res.data.regulations_url);
  });
}, []);

const handleViewRegulations = () => {
  const token = localStorage.getItem("auth_token") || "";
  const url = `/api/v1/system-settings/file/regulations_url?token=${encodeURIComponent(token)}`;
  setRegulationsFile({ url, filename: "獎學金要點", type: "application/pdf" });
  setShowRegulations(true);
};
```

- [ ] **Step 2: Add button in page header**

Find the page header area (the `<div>` or `<Card>` containing the page title like "教授審核" or "Professor Review"). Add the button in the top-right area:

```tsx
<Button
  variant="outline"
  size="sm"
  onClick={handleViewRegulations}
  disabled={!regulationsUrl}
  className="flex items-center gap-2"
>
  <FileText className="h-4 w-4" />
  {locale === "zh" ? "查看獎學金要點" : "View Regulations"}
</Button>
```

- [ ] **Step 3: Add FilePreviewDialog**

Before the closing `</>` or `</div>` of the component return:

```tsx
<FilePreviewDialog
  open={showRegulations}
  onClose={() => setShowRegulations(false)}
  file={regulationsFile}
  locale={locale}
/>
```

- [ ] **Step 4: Verify TypeScript**

```bash
cd /home/howard/ss_main/scholarship-system/frontend && npx tsc --noEmit 2>&1 | grep professor-review
```

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/professor-review-component.tsx
git commit -m "feat: add regulations link to professor review panel"
```

---

## Task 11: Frontend — College Review Regulations Link

**Files:**
- Modify: `frontend/components/college/review/ApplicationReviewPanel.tsx`

- [ ] **Step 1: Add state, data-fetching, and handler**

Same pattern as Task 10. Add to the top of `ApplicationReviewPanel`:

```typescript
import { FilePreviewDialog } from "@/components/file-preview-dialog";
// inside component:
const [regulationsUrl, setRegulationsUrl] = useState<string | null>(null);
const [showRegulations, setShowRegulations] = useState(false);
const [regulationsFile, setRegulationsFile] = useState<{
  url: string;
  filename: string;
  type: string;
} | null>(null);

useEffect(() => {
  api.systemSettings.getPublicDocs().then((res) => {
    if (res.success && res.data?.regulations_url)
      setRegulationsUrl(res.data.regulations_url);
  });
}, []);

const handleViewRegulations = () => {
  const token = localStorage.getItem("auth_token") || "";
  const url = `/api/v1/system-settings/file/regulations_url?token=${encodeURIComponent(token)}`;
  setRegulationsFile({ url, filename: "獎學金要點", type: "application/pdf" });
  setShowRegulations(true);
};
```

- [ ] **Step 2: Add button in panel header**

Find the panel header area and add:

```tsx
<Button
  variant="outline"
  size="sm"
  onClick={handleViewRegulations}
  disabled={!regulationsUrl}
  className="flex items-center gap-2"
>
  <FileText className="h-4 w-4" />
  查看獎學金要點
</Button>
```

- [ ] **Step 3: Add FilePreviewDialog**

```tsx
<FilePreviewDialog
  open={showRegulations}
  onClose={() => setShowRegulations(false)}
  file={regulationsFile}
  locale={locale}
/>
```

Note: If `ApplicationReviewPanel` does not accept a `locale` prop, use `"zh"` as a literal default. Check the component's props interface and add `locale?: "zh" | "en"` if needed.

- [ ] **Step 4: Verify TypeScript**

```bash
cd /home/howard/ss_main/scholarship-system/frontend && npx tsc --noEmit 2>&1 | grep ApplicationReviewPanel
```

Expected: No errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/college/review/ApplicationReviewPanel.tsx
git commit -m "feat: add regulations link to college review panel"
```

---

## Task 12: Frontend — Admin System Docs Management UI

**Files:**
- Modify: `frontend/components/admin-management-interface.tsx`

- [ ] **Step 1: Add state near the top of AdminManagementInterface**

```typescript
// inside AdminManagementInterface component
const [regulationsFile, setRegulationsFile] = useState<File | null>(null);
const [sampleDocFile, setSampleDocFile] = useState<File | null>(null);
const [uploadingRegulations, setUploadingRegulations] = useState(false);
const [uploadingSampleDoc, setUploadingSampleDoc] = useState(false);
const [currentRegulationsName, setCurrentRegulationsName] = useState<string>("");
const [currentSampleDocName, setCurrentSampleDocName] = useState<string>("");

useEffect(() => {
  api.systemSettings.getPublicDocs().then((res) => {
    if (res.success && res.data) {
      if (res.data.regulations_url)
        setCurrentRegulationsName(res.data.regulations_url.split("/").pop() || "");
      if (res.data.sample_document_url)
        setCurrentSampleDocName(res.data.sample_document_url.split("/").pop() || "");
    }
  });
}, []);
```

- [ ] **Step 2: Add upload handlers**

```typescript
const handleUploadRegulations = async () => {
  if (!regulationsFile) return;
  setUploadingRegulations(true);
  try {
    const res = await api.systemSettings.uploadRegulations(regulationsFile);
    if (res.success) {
      toast.success("獎學金要點上傳成功");
      setCurrentRegulationsName(res.data?.object_name?.split("/").pop() || "");
      setRegulationsFile(null);
    } else {
      toast.error(res.message || "上傳失敗");
    }
  } catch {
    toast.error("上傳失敗");
  } finally {
    setUploadingRegulations(false);
  }
};

const handleUploadSampleDoc = async () => {
  if (!sampleDocFile) return;
  setUploadingSampleDoc(true);
  try {
    const res = await api.systemSettings.uploadSampleDocument(sampleDocFile);
    if (res.success) {
      toast.success("申請文件範例檔上傳成功");
      setCurrentSampleDocName(res.data?.object_name?.split("/").pop() || "");
      setSampleDocFile(null);
    } else {
      toast.error(res.message || "上傳失敗");
    }
  } catch {
    toast.error("上傳失敗");
  } finally {
    setUploadingSampleDoc(false);
  }
};
```

- [ ] **Step 3: Add system docs tab/section**

The admin management interface uses `<Tabs>`. Find the `<TabsList>` (it has tabs like "用戶管理", "系統設定", etc.) and add a new tab trigger:

```tsx
<TabsTrigger value="system-docs">系統文件</TabsTrigger>
```

Then add the corresponding `<TabsContent value="system-docs">`:

```tsx
<TabsContent value="system-docs">
  <Card>
    <CardHeader>
      <CardTitle className="flex items-center gap-2">
        <FileText className="h-5 w-5" />
        系統文件管理
      </CardTitle>
      <CardDescription>
        上傳供學生及審核人員參閱的全域文件
      </CardDescription>
    </CardHeader>
    <CardContent className="space-y-8">
      {/* 獎學金要點 */}
      <div className="space-y-3">
        <Label className="text-base font-semibold">獎學金要點</Label>
        {currentRegulationsName && (
          <p className="text-sm text-gray-600">
            目前檔案：<span className="font-mono">{currentRegulationsName}</span>
          </p>
        )}
        <div className="flex items-center gap-3">
          <Input
            type="file"
            accept=".pdf,.doc,.docx"
            onChange={(e) => setRegulationsFile(e.target.files?.[0] || null)}
            className="max-w-xs"
          />
          <Button
            onClick={handleUploadRegulations}
            disabled={!regulationsFile || uploadingRegulations}
          >
            {uploadingRegulations ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" />上傳中...</>
            ) : (
              <><Upload className="h-4 w-4 mr-2" />上傳</>
            )}
          </Button>
        </div>
      </div>

      {/* 申請文件範例檔 */}
      <div className="space-y-3">
        <Label className="text-base font-semibold">申請文件範例檔</Label>
        {currentSampleDocName && (
          <p className="text-sm text-gray-600">
            目前檔案：<span className="font-mono">{currentSampleDocName}</span>
          </p>
        )}
        <div className="flex items-center gap-3">
          <Input
            type="file"
            accept=".pdf,.doc,.docx"
            onChange={(e) => setSampleDocFile(e.target.files?.[0] || null)}
            className="max-w-xs"
          />
          <Button
            onClick={handleUploadSampleDoc}
            disabled={!sampleDocFile || uploadingSampleDoc}
          >
            {uploadingSampleDoc ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" />上傳中...</>
            ) : (
              <><Upload className="h-4 w-4 mr-2" />上傳</>
            )}
          </Button>
        </div>
      </div>
    </CardContent>
  </Card>
</TabsContent>
```

- [ ] **Step 4: Add missing imports if needed**

Ensure the file imports `Loader2` from `lucide-react` (it already imports `Upload`). Check and add:

```typescript
import { ..., Loader2 } from "lucide-react";
```

Also ensure `toast` from `sonner` is imported:

```typescript
import { toast } from "sonner";
```

- [ ] **Step 5: Verify TypeScript**

```bash
cd /home/howard/ss_main/scholarship-system/frontend && npx tsc --noEmit 2>&1 | grep -c "error"
```

Expected: `0`

- [ ] **Step 6: Commit**

```bash
git add frontend/components/admin-management-interface.tsx
git commit -m "feat: add system docs management tab to admin interface"
```

---

## Task 13: End-to-End Smoke Test

- [ ] **Step 1: Start the dev stack**

```bash
docker compose -f docker-compose.dev.yml up -d
```

- [ ] **Step 2: Admin uploads 獎學金要點**

1. Log in as admin
2. Navigate to admin → 系統文件
3. Upload a PDF as 獎學金要點
4. Confirm success toast

- [ ] **Step 3: Student sees document in notice step**

1. Log in as student
2. Start a new application
3. Verify 「獎學金要點」button is enabled in the reference docs section
4. Click it — PDF should open in preview dialog

- [ ] **Step 4: Student uploads application document in step 3**

1. Proceed to step 3 (填寫資料與申請獎學金)
2. Upload a file in the 申請文件 section
3. Save personal info
4. Verify the file appears as 已上傳

- [ ] **Step 5: Verify submit preview shows documents**

1. Click 「提交申請」
2. In the preview dialog, verify 上傳文件 section shows:
   - 存摺封面: ✅ 已上傳 [預覽]
   - 申請文件: ✅ 已上傳 [預覽]

- [ ] **Step 6: Professor/college can view regulations**

1. Log in as professor
2. Navigate to professor review
3. Verify 「查看獎學金要點」button is enabled
4. Click it — PDF opens

- [ ] **Step 7: Final commit if any last-minute fixes**

```bash
git add -p
git commit -m "fix: smoke test corrections"
```

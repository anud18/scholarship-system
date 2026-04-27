# 獎學金文件展示與申請文件上傳 Design Spec

**Date**: 2026-04-21  
**Scope**: Student application UI, professor/college review UI, admin backend

---

## Overview

Three feature areas:

1. **Global reference documents** — 獎學金要點 and 申請文件範例檔, system-wide files uploaded by admin and shown to students in the notice step and to professors/college reviewers via a link.
2. **Application document upload** — A fixed upload field on the application form where students upload their 申請文件, stored on the application record.
3. **Submit preview enhancements** — The pre-submission preview dialog shows passbook cover and application document upload status with inline preview.

---

## Backend

### New Table: `system_settings`

```sql
id          SERIAL PRIMARY KEY
key         VARCHAR(100) UNIQUE NOT NULL
value       TEXT                         -- MinIO object_name
description VARCHAR(200)
updated_at  TIMESTAMP WITH TIME ZONE DEFAULT now()
updated_by  INTEGER REFERENCES users(id)
```

Seed two rows on migration:
- `key = "regulations_url"`, description = "獎學金要點文件"
- `key = "sample_document_url"`, description = "申請文件範例檔"

### New API: `/api/v1/system-settings/`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/system-settings/` | Any authenticated | Return all settings (key + value) |
| POST | `/system-settings/upload/regulations` | Admin | Upload 獎學金要點 to MinIO, update row |
| POST | `/system-settings/upload/sample-document` | Admin | Upload 申請文件範例檔 to MinIO, update row |
| GET | `/system-settings/file/{key}` | Any authenticated | Proxy file from MinIO |

All upload endpoints follow the existing MinIO upload pattern (store `object_name`, not full URL).  
`GET /file/{key}` validates the key is one of the two allowed values before proxying.

### `applications` Table — New Column

```sql
application_document_url VARCHAR(500) NULL
```

Alembic migration with existence check (per project standards).

### New Application File Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/applications/{id}/application-document` | Student (owner) | Upload 申請文件, store object_name |
| DELETE | `/applications/{id}/application-document` | Student (owner) | Remove 申請文件 |

---

## Frontend

### 1. NoticeAgreementStep (Step 0)

**Data loading**: On mount, fetch `GET /api/v1/system-settings/` and extract `regulations_url` and `sample_document_url`.

**New UI block** — placed between the Important Notice Alert and the numbered notice list:

```
┌─────────────────────────────────────────────┐
│ 參考文件                                      │
│  [📄 獎學金要點]   [📄 申請文件範例檔]          │
└─────────────────────────────────────────────┘
```

- Each button opens `FilePreviewDialog` with the file proxied through `/api/v1/system-settings/file/{key}`.
- If the value is empty (not yet uploaded), button is `disabled` with tooltip "尚未提供".
- Both zh/en locale strings added.

### 2. ScholarshipApplicationStep (Step 3) — Upload Field

**New state variables** (same pattern as passbook):
```typescript
const [applicationDocumentFiles, setApplicationDocumentFiles] = useState<File[]>([]);
const [existingApplicationDocument, setExistingApplicationDocument] = useState<string | null>(null);
const [showAppDocPreview, setShowAppDocPreview] = useState(false);
const [appDocPreviewFile, setAppDocPreviewFile] = useState<{ url: string; filename: string; type: string } | null>(null);
```

**UI**: Placed directly below the 存摺封面 section in the bank info card. Same layout — label, FileUpload component, preview/delete buttons for existing document.

**Save logic**: On save personal info (`handleSavePersonalInfo`), if `applicationDocumentFiles.length > 0` and an application draft exists, call `POST /applications/{id}/application-document`. If no draft yet, upload after draft creation.

**i18n keys added** (zh + en):
- `applicationDocument`, `applicationDocumentUploaded`, `deleteAppDoc`

### 3. Submit Preview Dialog Enhancements

New section **「上傳文件」** added after the Personal Info section and before the Warning alert:

```
上傳文件
┌──────────────────────────────────────┐
│ 存摺封面    ✅ 已上傳 [預覽]           │
│ 申請文件    ✅ 已上傳 [預覽]           │
└──────────────────────────────────────┘
```

- ✅ / ❌ status based on whether `existingBankDocument` / `existingApplicationDocument` is non-null.
- 「預覽」button opens `FilePreviewDialog` inline (reuses existing preview handlers).
- If not uploaded, shows ❌ 未上傳 (no preview button).

### 4. Professor Review UI

**File**: `components/professor-review-component.tsx`

Add a「查看獎學金要點」button in the page header area (top-right of the review panel). Clicking opens `FilePreviewDialog` with the file from `/api/v1/system-settings/file/regulations_url`.

Button is disabled if `regulations_url` is empty.

### 5. College Review UI

**File**: `components/college/review/ApplicationReviewPanel.tsx`

Same as professor UI — add「查看獎學金要點」button in the panel header.

### 6. Admin Backend — System Settings UI

In the existing admin dashboard, add a **「系統設定」** tab (or section within an existing settings area).

Each file has:
- Current filename display (extracted from `object_name`) or "尚未上傳"
- Upload button → file picker → `POST` to the appropriate upload endpoint
- Preview button if file exists

---

## Next.js Proxy Routes

Two new proxy routes following existing patterns (`/app/api/v1/preview-terms/route.ts`):

- `/app/api/v1/system-settings/file/[key]/route.ts` — proxies to backend, passes auth token via query param

---

## Data Flow

```
Admin uploads → POST /system-settings/upload/{type}
             → MinIO stores file, DB stores object_name

Student views → GET /system-settings/ (object_name returned)
             → Click button → GET /system-settings/file/{key}
             → Next.js proxy → Backend → MinIO → file stream

Student uploads application doc → POST /applications/{id}/application-document
                                → MinIO stores file
                                → applications.application_document_url = object_name
```

---

## Out of Scope

- Per-scholarship 獎學金要點 (future: can be added as `scholarship_types.regulations_url`)
- Application document required/optional validation (treat as optional for now)
- Admin delete for system setting files (upload overwrites)

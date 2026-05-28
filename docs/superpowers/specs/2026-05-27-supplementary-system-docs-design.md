# Supplementary System Documents — Design Spec

**Date**: 2026-05-27
**Author**: anud18 (collaboration with Claude)
**Status**: Implemented

---

## 1. Problem

Admin can currently upload exactly two global documents for students to view on the application page:

- `regulations_url` — 獎學金要點 (PDF only; scroll-gate enforced before student can agree)
- `sample_document_url` — 申請文件範例檔 (PDF/DOC/DOCX preview)

Both are hardcoded in backend (`_ALLOWED_DOC_KEYS` set in `backend/app/api/v1/endpoints/system_settings.py:87`), in the admin UI (`SystemDocsPanel.tsx` `SLOTS` array), in the student wizard (`NoticeAgreementStep.tsx`), and in the two Next.js proxy routes (`file-proxy/route.ts`, `upload-proxy/route.ts`).

Admins want to publish additional reference documents (FAQ, sample bank cover, payment templates, etc.) without code changes per document.

---

## 2. Goal & Non-Goals

### Goal

Allow admins to upload an arbitrary number of **supplementary reference documents** that appear on the student application page (in the `Notice Agreement` step) alongside the existing `申請文件範例檔` row, ordered by admin-controlled drag-and-drop sort.

### Non-Goals

- Replacing or generalizing the two fixed slots (`regulations_url`, `sample_document_url` stay as-is)
- Localized titles per supplementary doc (admin enters one `title`, shown to all locales)
- Published/draft state — uploading publishes immediately; deleting hides + removes the MinIO object
- Per-document file-format whitelist — supplementary docs accept the same set as `sample_document_url` (PDF/DOC/DOCX, ≤10 MB)
- Per-document placement on different wizard steps — all supplementary docs render only inside the 參考文件 list in `NoticeAgreementStep`
- File-replace operation — to swap content, admin must delete + re-upload
- Download analytics / view counters

---

## 3. Data Model

New table `supplementary_docs`:

```sql
CREATE TABLE supplementary_docs (
    id                SERIAL PRIMARY KEY,
    title             VARCHAR(200) NOT NULL,        -- admin-defined label shown to students
    object_name       VARCHAR(500) NOT NULL,        -- MinIO key, e.g. "system-docs/supp_<uuid>.pdf"
    original_filename VARCHAR(500) NOT NULL,
    content_type      VARCHAR(100) NOT NULL,
    file_size         INTEGER      NOT NULL,
    sort_order        INTEGER      NOT NULL DEFAULT 0,
    created_by        INTEGER      REFERENCES users(id),
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX idx_supp_docs_sort ON supplementary_docs(sort_order);
```

### Notes

- `title` is shown verbatim to students (no localization layer)
- `object_name` format: `system-docs/supp_<uuid4>.<ext>` (uuid prevents collision; keeps the existing `system-docs/` MinIO prefix used by `regulations_url` / `sample_document_url`)
- `sort_order` is unique within payload only at write time (no DB unique constraint — race-tolerant)
- `file_size` enforced ≤ 10 MB at upload time
- No FK references from other tables; this is a standalone resource

### Alembic Migration

File: `backend/alembic/versions/add_supplementary_docs_001_add_supplementary_docs_table.py`

```python
def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "supplementary_docs" not in inspector.get_table_names():
        op.create_table(
            "supplementary_docs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("object_name", sa.String(500), nullable=False),
            sa.Column("original_filename", sa.String(500), nullable=False),
            sa.Column("content_type", sa.String(100), nullable=False),
            sa.Column("file_size", sa.Integer(), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("idx_supp_docs_sort", "supplementary_docs", ["sort_order"])

def downgrade() -> None:
    op.drop_index("idx_supp_docs_sort", table_name="supplementary_docs")
    op.drop_table("supplementary_docs")
```

Existence-check pattern per `CLAUDE.md` migration rule.

---

## 4. Backend API

All endpoints live under `/api/v1/system-settings/` (alongside existing fixed-slot endpoints). All responses follow the standard `{success, message, data}` envelope per `CLAUDE.md` § 5.

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET`    | `/supplementary-docs`               | authenticated | List all docs ordered by `sort_order ASC, id ASC` |
| `POST`   | `/supplementary-docs`               | admin         | Multipart upload: `file` + `title` form fields → creates row + MinIO object |
| `PATCH`  | `/supplementary-docs/{id}`          | admin         | Body `{title}` — update title only |
| `DELETE` | `/supplementary-docs/{id}`          | admin         | Remove DB row + best-effort delete MinIO object |
| `PATCH`  | `/supplementary-docs/reorder`       | admin         | Body `[{id, sort_order}, ...]` — bulk update |
| `GET`    | `/supplementary-docs/{id}/file`     | authenticated | Stream file inline from MinIO (mirrors `GET /file/{doc_key}` for fixed slots) |

### Validation

- **File**: reuse `app.core.path_security.validate_upload_file()` with `allowed_extensions=[".pdf", ".doc", ".docx"]`, `max_size_mb=10`, `allow_unicode=True`
- **Title**: non-empty after `.strip()`, ≤ 200 chars
- **Reorder body**: every `id` must exist (404 if not); `sort_order` values must be unique within the payload (400 otherwise); empty payload rejected with 400
- **No magic-byte enforcement** — supplementary docs are previewed via `FilePreviewDialog`, not embedded `react-pdf` (only `regulations_url` needs the strict PDF check)

### Delete behavior

Match the pattern at `backend/app/api/v1/endpoints/system_settings.py:217-225`:

1. Delete DB row first (commits transaction)
2. Then `minio_service.client.remove_object(...)` wrapped in try/except → `logger.warning` on failure (orphaned object acceptable)

### Concurrent reorder

Single admin user base — no locking. Last write wins. If two admins reorder simultaneously the later PATCH overwrites the earlier; the frontend's optimistic UI will reflect the last successful response.

---

## 5. Frontend — Admin UI

### File changes

- **Edit** `frontend/components/admin/system-docs/SystemDocsPanel.tsx` — append new `<SupplementaryDocsList />` section below the existing 2-slot grid (current file already ~460 LOC, near the 800 cap, so extract the new logic into its own component)
- **New** `frontend/components/admin/system-docs/SupplementaryDocsList.tsx` — drag-sortable list with row actions
- **New** `frontend/components/admin/system-docs/AddSupplementaryDocDialog.tsx` — upload dialog (title input + file dropzone)
- **Edit** `frontend/lib/api/modules/system-settings.ts` — add `supplementaryDocs` namespace (see § 7)

### Layout

```
┌─ 系統文件管理 ─────────────────────────────────────┐
│  [獎學金要點 slot]    [申請文件範例檔 slot]      │  ← unchanged fixed grid
├──────────────────────────────────────────────────┤
│  補充參考文件                          [+ 新增]   │  ← new section
│  ┌─────────────────────────────────────────────┐ │
│  │ ☰ [icon] FAQ.pdf       [預覽][編輯標題][刪除]│ │
│  │ ☰ [icon] 範本.docx     [預覽][編輯標題][刪除]│ │
│  └─────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

### Interactions

- **Add**: `[+ 新增]` opens `AddSupplementaryDocDialog`. Dialog has:
  - Title input (required, ≤ 200 chars, validated client-side)
  - Drop-zone (mirrors the existing fixed-slot drop UX — reuse styling from `SystemDocsPanel`)
  - File constraint: `.pdf,.doc,.docx`, ≤ 10 MB (matched in client `<input accept>`)
  - Submit calls `POST /supplementary-docs`; toast on success, refetch list
- **Drag**: uses `@dnd-kit/core` + `@dnd-kit/sortable` (verify presence; if absent, add to dependencies as part of the plan)
  - Optimistic reorder in local state
  - On drop, debounce ~300 ms, then send full new order via `PATCH /reorder`
  - Disable drag while the PATCH is in-flight; show a small spinner
  - On error: rollback local order, show toast
- **Edit title**: small inline popover (or compact dialog) with input + save/cancel; calls `PATCH /supplementary-docs/{id}` with `{title}`
- **Preview**: opens the same `FilePreviewDialog` used by fixed slots, URL built via the new `buildSuppDocFileProxyUrl(id)` helper
- **Delete**: confirm dialog with text "刪除後學生將無法看到此檔案，確定？" → calls `DELETE`, optimistic remove with rollback on error

### Empty state

When the list is empty: show a single placeholder row "目前尚無補充參考文件，點擊「新增」上傳。"

---

## 6. Frontend — Student UI

### File change

**Edit** `frontend/components/student-wizard/steps/NoticeAgreementStep.tsx`. Specifically the sample-doc block currently at lines 304–321.

### Replace with 參考文件 list section

```
┌─ 參考文件 ──────────────────────────────────────┐
│  ┌────────────────────────────────────────────┐ │
│  │ [icon] 申請文件範例檔            [預覽]    │ │
│  │ [icon] FAQ.pdf                   [預覽]    │ │
│  │ [icon] 繳費範本.docx             [預覽]    │ │
│  └────────────────────────────────────────────┘ │
└────────────────────────────────────────────────┘
```

### Rendering rules

- Section header: `參考文件` (locale-aware: `Reference Documents` in `en`)
- The existing `sample_document_url` row stays **first** (locked position; admin-defined supplementary docs cannot reorder above it)
- Supplementary docs follow in `sort_order` from the API
- Each row clickable → opens the existing `FilePreviewDialog` with the same `previewMimeType()` and proxy-URL pattern
- **Empty handling**:
  - If `sample_document_url` is unset AND supplementary list is empty → hide the whole 參考文件 section
  - If `sample_document_url` is unset but supplementary docs exist → show section with just the supplementary docs (no "尚未提供" placeholder)
  - If `sample_document_url` is set and supplementary list is empty → show only the sample row

### Locale copy changes

In `NOTICES.zh` and `NOTICES.en` (the static object at the top of the file):

- **Remove** `sampleDocumentRow` ("需要參考申請文件格式？" / "Need to see the application document format?") — the new section uses a section header instead
- **Add** new key `referenceDocsHeader`: `參考文件` / `Reference Documents`
- **Keep** `sampleDocumentLabel`: `申請文件範例檔` / `Sample Application Documents` (still used as the row label for the fixed sample doc)
- **Keep** `sampleDocumentNotProvided`: only used inside the row if needed (likely removed — see empty handling above)

### Data fetching

Extend the existing `useEffect` (around lines 209–225) to fetch both endpoints in parallel:

```ts
Promise.all([
  api.systemSettings.getPublicDocs(),
  api.systemSettings.supplementaryDocs.list(),
])
  .then(([docsRes, suppRes]) => {
    if (docsRes.success && docsRes.data) setPublicDocs(docsRes.data);
    if (suppRes.success && suppRes.data) setSupplementaryDocs(suppRes.data);
  })
  .catch((err) => { /* same error handling pattern as today */ })
  .finally(() => setDocsLoaded(true));
```

The 獎學金要點 scroll-gate block (current lines 323–372) remains untouched — only the 參考文件 area changes.

---

## 7. API Client (Frontend) + Next.js Proxies

### API client extension

In `frontend/lib/api/modules/system-settings.ts`, add:

```ts
export type SupplementaryDoc = {
  id: number;
  title: string;
  object_name: string;
  original_filename: string;
  content_type: string;
  file_size: number;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

export function buildSuppDocFileProxyUrl(id: number, objectName?: string): string {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') || '' : '';
  const cacheBuster = encodeURIComponent((objectName || '').split('/').pop() || String(id));
  return `/api/v1/system-settings/supp-file-proxy?id=${id}&token=${encodeURIComponent(token)}&v=${cacheBuster}`;
}

// inside createSystemSettingsApi() returned object:
supplementaryDocs: {
  list:        () => Promise<ApiResponse<SupplementaryDoc[]>>,
  upload:      (file: File, title: string) => Promise<ApiResponse<SupplementaryDoc>>,
  updateTitle: (id: number, title: string) => Promise<ApiResponse<SupplementaryDoc>>,
  delete:      (id: number) => Promise<ApiResponse<{ deleted: boolean }>>,
  reorder:     (items: Array<{ id: number; sort_order: number }>) => Promise<ApiResponse<{ updated: number }>>,
}
```

`upload` posts multipart to the new `supp-upload-proxy` route (parallel to current `upload-proxy`).

### Next.js proxy — new routes (parallel to existing, kept separate per Section 4 choice **B2**)

- **New** `frontend/app/api/v1/system-settings/supp-file-proxy/route.ts`
  - Mirror `file-proxy/route.ts` exactly: hostname allowlist (`backend`, `ss.test.nycu.edu.tw`), token extraction (query / header / cookie), header forwarding (`Content-Type`, `Content-Disposition`, `Content-Length`, `Accept-Ranges`, `Cache-Control: private, max-age=3600`)
  - Replace `ALLOWED_KEYS` check with: parse `?id=` as integer, reject if not a positive int
  - Backend URL: `/api/v1/system-settings/supplementary-docs/{id}/file`
- **New** `frontend/app/api/v1/system-settings/supp-upload-proxy/route.ts`
  - Mirror `upload-proxy/route.ts`
  - No `ALLOWED_KEYS` (any admin upload is valid for supp docs)
  - Backend URL: `/api/v1/system-settings/supplementary-docs`
  - Forward the multipart body intact (`file` + `title` form fields)

Existing `file-proxy/route.ts` and `upload-proxy/route.ts` stay unchanged.

---

## 8. Tests

### Backend (`backend/app/tests/test_supplementary_docs.py`)

1. List empty → returns `{success:true, data:[]}`
2. List returns rows sorted by `sort_order ASC, id ASC`
3. Upload as admin → row created in DB; MinIO `put_object` called once; response contains generated id + object_name
4. Upload as non-admin (e.g. student or college) → 403
5. Upload `.exe` (or any extension outside whitelist) → 400 with `path_security`'s validation message
6. Upload 11 MB file → 400
7. Title of 201 chars → 400 (validated server-side, not just client)
8. Title with only whitespace → 400
9. `DELETE /{id}` removes the row and calls `minio_service.client.remove_object` (mock to assert call); returns `{success:true}` even if MinIO call raises (best-effort cleanup pattern)
10. `DELETE` on nonexistent id → 404
11. `PATCH /reorder` updates all rows; verify new ordering returned by subsequent `GET`
12. `PATCH /reorder` with a missing id → 400, no rows changed (atomic transaction)
13. `PATCH /reorder` with duplicate `sort_order` values within the payload → 400
14. `GET /{id}/file` as authenticated student → 200, streams MinIO content, correct `Content-Disposition: inline; filename*=UTF-8''<encoded>`
15. `GET /{id}/file` for nonexistent id → 404
16. `PATCH /{id}` updates title only; `object_name` / file unchanged

### Frontend

- **New** `frontend/components/admin/system-docs/__tests__/SupplementaryDocsList.test.tsx`
  - Renders list rows from props
  - Calls `reorder` API on drag-end with the new full ordering
  - Optimistic update, rollback on error
  - Delete confirmation flow → calls API → row removed from UI
- **Extend** `frontend/components/__tests__/notice-agreement-step.test.tsx`
  - Supplementary docs rendered inside 參考文件 list after the sample doc row
  - Section hidden when both sources empty
  - Section shown with only supplementary docs when sample is missing
  - Clicking a supplementary row opens `FilePreviewDialog` with the expected URL

### Tooling

- Run `cd frontend && npm run api:generate` after backend endpoints are merged; commit the regenerated `frontend/lib/api/generated/schema.d.ts` per `CLAUDE.md` § 8

---

## 9. Edge Cases & Risks

| Case | Handling |
|------|----------|
| Concurrent drag-reorder by two admins | Last write wins; no locking. Acceptable for our admin volume. |
| MinIO `remove_object` failure on delete | Log warning, leave orphan object. Matches existing pattern in `system_settings.py:217-225`. |
| Unicode filename | Preserved end-to-end via `validate_upload_file(allow_unicode=True)` + `Content-Disposition: filename*=UTF-8''<encoded>`. |
| Drag during slow PATCH | Lock the list (disable drag handles) while PATCH is in flight; show inline spinner. |
| Title with embedded HTML / script | Rendered via React (auto-escaped). No `dangerouslySetInnerHTML` anywhere on this path. |
| Cache after replace | Replace flow is delete + re-upload → new id → fresh proxy URL → no stale cache (the `v=` cache-buster also helps). |
| Migration on fresh DB | Existence check guards against re-create errors when running `./scripts/reset_database.sh`. |

---

## 10. Out of Scope (explicit)

- Published / draft state — upload is immediately public; deletion is the only "hide"
- Per-doc placement on different wizard steps
- Localized titles per doc
- Per-doc file-format overrides
- File replacement (delete + re-upload only)
- Download / view analytics

---

## 11. File Touch List

### Backend

- `backend/app/models/supplementary_doc.py` (new) — SQLAlchemy model
- `backend/app/schemas/supplementary_doc.py` (new) — Pydantic create / update / response schemas
- `backend/app/api/v1/endpoints/system_settings.py` (edit) — add 6 endpoints
- `backend/alembic/versions/add_supplementary_docs_001_*.py` (new)
- `backend/app/tests/test_supplementary_docs.py` (new)

### Frontend

- `frontend/components/admin/system-docs/SystemDocsPanel.tsx` (edit — append section)
- `frontend/components/admin/system-docs/SupplementaryDocsList.tsx` (new)
- `frontend/components/admin/system-docs/AddSupplementaryDocDialog.tsx` (new)
- `frontend/components/student-wizard/steps/NoticeAgreementStep.tsx` (edit — replace sample-doc row with 參考文件 list)
- `frontend/lib/api/modules/system-settings.ts` (edit — add `supplementaryDocs` namespace + `buildSuppDocFileProxyUrl`)
- `frontend/app/api/v1/system-settings/supp-file-proxy/route.ts` (new)
- `frontend/app/api/v1/system-settings/supp-upload-proxy/route.ts` (new)
- `frontend/lib/api/generated/schema.d.ts` (regenerated)
- `frontend/components/admin/system-docs/__tests__/SupplementaryDocsList.test.tsx` (new)
- `frontend/components/__tests__/notice-agreement-step.test.tsx` (extend)

### Dependency check

- `@dnd-kit/core`, `@dnd-kit/sortable` — verify presence in `frontend/package.json`; add as part of the implementation plan if missing.

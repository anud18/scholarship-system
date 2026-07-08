# Design: Admin-configurable document display/upload flags + 申請文件 note

Date: 2026-07-08
Status: Approved

## Problem

1. The scholarship-list cards (student portal) automatically show every
   `is_required && is_active` document in the「必要文件」box. Admins cannot
   control which documents are presented there.
2. In wizard step 3 (填寫資料與申請獎學金), every active document gets an
   upload widget and every required document is enforced at submit. Admins
   cannot mark a document as "informational only" (e.g. submitted on paper).
3. The hardcoded「申請文件」upload section at the bottom of step 3 has no
   explanatory text, and admins have no way to add one.

## Decisions (confirmed with user)

- Per-document control via **two independent switches** (not a single flag).
- The 申請文件 note is **per scholarship** (not a global system setting).

## Feature A — two per-document switches

Add two Boolean columns to `application_documents`, both defaulting to
`true` so existing behavior is unchanged:

| Column | Meaning |
|---|---|
| `display_in_list` | When `false`, the document does not appear in the scholarship-list card's 必要文件/選填文件 boxes. |
| `requires_upload` | When `false`, step 3 renders no upload widget for the document and it is excluded from required-document validation. |

### Backend
- Alembic migration adding both columns (`server_default="true"`, with
  existence checks per project migration rules).
- `ApplicationDocument` model: two new `Column(Boolean, default=True,
  nullable=False, server_default="true")`.
- `ApplicationDocumentCreate` / `ApplicationDocumentUpdate` schemas and the
  document response include both flags.
- Existing cache invalidation (`documents:{type}`, `formconfig:{type}`)
  already covers create/update paths — no new invalidation needed.

### Frontend
- Admin `application-document-form.tsx`: two new Switches —
  「顯示於獎學金列表」and「需要學生上傳」.
- Scholarship-list card (`enhanced-student-portal.tsx`): both document
  boxes additionally filter on `doc.display_in_list`.
- `dynamic-application-form.tsx`: only render upload widgets for documents
  with `requires_upload`.
- `ScholarshipApplicationStep.tsx` (and the parallel validation copy in
  `enhanced-student-portal.tsx`): required-document validation filters on
  `is_required && is_active && requires_upload`.

## Feature B — per-scholarship 申請文件 note

Follow the `terms_document_url` precedent on `scholarship_types`:

- New columns: `application_document_note` (Text), `application_document_note_en` (Text).
- Admin edits the note in the scholarship management form-config area
  (`admin-scholarship-management-interface.tsx`), saved through the existing
  scholarship update endpoint.
- Student wizard: `selectedScholarship` already carries scholarship fields;
  render the locale-appropriate note directly under the「申請文件」header in
  step 3. Empty/unset note renders nothing (no default copy).

## Out of scope

- No changes to the dead inline form path in `enhanced-student-portal.tsx`
  beyond the shared list-card filters/validation helpers it exports.
- No changes to review flows or existing document upload storage.

## Testing

- Backend: CRUD roundtrip for both new flags; form-config response includes
  them; scholarship update accepts/returns the note fields.
- Frontend: unit tests for the filter logic (display_in_list ×
  requires_upload combinations); note rendering (shown when set, hidden when
  empty).
- Regenerate OpenAPI types (`npm run api:generate`).

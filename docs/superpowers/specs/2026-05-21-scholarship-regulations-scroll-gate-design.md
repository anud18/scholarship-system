# Scholarship Regulations Scroll-Gate Design

**Date**: 2026-05-21
**Status**: Approved

## Overview

Move the "scroll-to-bottom before agree" gate in the student application wizard from the hardcoded 8-item notice list onto the actual 獎學金要點 (scholarship regulations) PDF uploaded by an admin. The 8 hardcoded notices remain on the page as a static summary, but no longer drive the scroll-gate. Admins must upload the regulations as a PDF; non-PDF uploads are rejected. If no PDF has been uploaded, students cannot proceed past this wizard step.

---

## Motivation

Today the canonical "you must read this before applying" content lives in two disjoint places:

- A hardcoded list of 8 generic notice items inside `NoticeAgreementStep.tsx`, gated by a scroll-to-bottom check.
- An admin-uploaded 獎學金要點 PDF, surfaced only as an optional "open in dialog" button (no enforcement).

This means students can satisfy the agreement gate without ever opening the regulations that actually govern the scholarship. Moving the gate onto the PDF aligns enforcement with the authoritative source.

---

## Scope

**In scope**
- Frontend: replace the gated content in `NoticeAgreementStep.tsx`
- Frontend: new reusable `InlinePdfViewer` component (`react-pdf` based)
- Frontend: restrict 獎學金要點 admin upload (`regulations_url` slot) to PDF only
- Backend: server-side PDF validation on the `regulations_url` upload endpoint
- Build: add `react-pdf` dependency and configure its pdf.js worker

**Not in scope**
- 申請文件範例檔 (`sample_document_url`) behavior — continues to accept PDF/DOC/DOCX and open via the existing `FilePreviewDialog` button. No gating, no inline rendering.
- Any changes to the FilePreviewDialog itself (it stays as the iframe-based fallback for the sample document).
- Locale copy review beyond what's needed for the new states.

---

## Behavioral Changes

### Student-facing (`NoticeAgreementStep`)

New top-to-bottom layout inside the existing `<Card>`:

1. 重要提醒 amber `<Alert>` — unchanged copy, unchanged behavior.
2. 8-item notice summary box — same 8 items as today, but rendered **statically** (not inside a fixed-height scrollable div). No scroll, no gate.
3. 參考文件 row:
   - Inline indicator badge "獎學金要點 — 請於下方閱讀" (regulations now render inline below, not as a dialog button).
   - `[申請文件範例檔]` button — unchanged; opens `FilePreviewDialog` as today.
4. `InlinePdfViewer` rendering `regulations_url`. Fixed height (~500px), all PDF pages stacked inside one `overflow-y: auto` container. Scroll-to-bottom drives `hasReadNotice`.
5. "已詳閱獎學金要點" auto-checkbox — same logic as today's "已詳閱所有注意事項" (latches when bottom is reached, also auto-latches on mount if content fits without overflow).
6. Agree checkbox + Continue button — unchanged.

Locale copy updates (zh / en):
- `readNoticeText` → 「已詳閱獎學金要點」 / "I have read the scholarship regulations"
- `readNoticeHint` → 「請將下方獎學金要點滑到底端，閱讀完成後才能勾選同意」 / "Scroll the regulations document to the bottom to enable the agree checkbox"
- `readFirst` → 「請先滑到獎學金要點底部完成閱讀」 / "Please scroll to the bottom of the regulations first"
- `agreementText` → 「我已詳細閱讀並了解獎學金要點，同意遵守相關規定」 / "I have read and understand the scholarship regulations and agree to comply"

### Admin-facing (`SystemDocsPanel`)

The 獎學金要點 slot (`regulations_url`):
- `ACCEPTED` constant for this slot only becomes `".pdf"`.
- Drop-zone copy changes: 「僅接受 PDF · 上限 10 MB」.
- Existing badge / preview / replace UI is unchanged.

The 申請文件範例檔 slot (`sample_document_url`) is untouched and keeps `.pdf,.doc,.docx`.

---

## Component & API Surface

### New: `frontend/components/inline-pdf-viewer.tsx`

```ts
interface InlinePdfViewerProps {
  url: string;                          // proxy URL with token in query string
  height?: number;                      // viewer height in px (default 500)
  onReachedBottom?: () => void;         // fired once when scroll reaches bottom OR content fits without scrolling
  onLoadError?: (err: Error) => void;   // fired if pdf.js fails to load the doc
  locale?: "zh" | "en";                 // affects loading / error copy
}
```

Internals:
- Renders a single `<div ref={scrollRef} onScroll={...}>` with `overflow-y: auto`.
- Inside: `<Document file={url}>` → `<Page pageNumber={i} />` for `i in 1..numPages`, stacked vertically.
- Uses `pdfjs.GlobalWorkerOptions.workerSrc` set once at module load time via `frontend/lib/pdf-worker.ts`.
- Scroll-to-bottom check: `scrollHeight - scrollTop - clientHeight <= 8`, latched once.
- On `<Document onLoadSuccess>` and after the first render commit, if `scrollHeight <= clientHeight + 8`, fire `onReachedBottom` immediately.
- On `<Document onLoadError>`, fire `onLoadError` and render an internal error state with a "重新載入" button that re-mounts the `<Document>`.
- Loading state: `<Skeleton>` blocks inside the container (consistent with `FilePreviewDialog`'s existing skeleton).

### Updated: `NoticeAgreementStep.tsx`

- Drop the dialog button for 獎學金要點; keep the dialog button for 申請文件範例檔.
- Drop the existing `noticeScrollRef` / `handleNoticeScroll` / `hasReadNotice` mount-effect machinery; replace with `hasReadNotice` driven by `<InlinePdfViewer onReachedBottom={() => setHasReadNotice(true)} />`.
- The 8-item box becomes a plain `<div>` block (no `h-[400px]`, no `overflow-y-auto`, no `onScroll`).
- Empty/error state: when `publicDocs.regulations_url` is undefined or the viewer reports a load error, render an amber blocking `<Alert>` in place of the viewer (see "Error / Empty States" below) and never enable the agree checkbox.

### Updated: `SystemDocsPanel.tsx`

- Move from a single `ACCEPTED` module constant to a per-slot accepted-extensions property:
  ```ts
  const SLOTS: DocSlot[] = [
    { key: "regulations_url",      accepted: ".pdf",            ... },
    { key: "sample_document_url",  accepted: ".pdf,.doc,.docx", ... },
  ];
  ```
- `validateAndSet` consults `slot.accepted` instead of the global constant.
- Drop-zone helper copy uses `slot.accepted`.

### Updated: backend `system_settings.py`

The endpoint that handles the 獎學金要點 upload (the one wired to `apiClient.systemSettings.uploadRegulations`):
- Reject the upload with `HTTP 400` and message 「獎學金要點僅接受 PDF 檔案」 when either:
  - the filename extension (lowercased) is not `.pdf`, **or**
  - the request's `Content-Type` is not `application/pdf` (defense in depth — never trust client).
- The sample-document endpoint stays as-is.

---

## Data Flow

```
NoticeAgreementStep mount
  └─ GET /api/v1/system-settings/public-docs
       ├─ res.data.regulations_url is undefined / null
       │    └─ render blocking Alert, agree disabled, no viewer
       │
       └─ res.data.regulations_url present
            └─ build proxy URL:
               /api/v1/system-settings/file-proxy
                 ?key=regulations_url
                 &token=<localStorage auth_token>
                 &v=<basename(regulations_url)>           ← cache-buster
            └─ <InlinePdfViewer url={proxyUrl} ... />
                 └─ pdf.js loads PDF
                      ├─ onLoadSuccess: render all <Page> components stacked
                      │    └─ user scrolls → bottom reached → onReachedBottom
                      │         └─ NoticeAgreementStep: setHasReadNotice(true)
                      │              └─ "已詳閱獎學金要點" checkbox ticks
                      │                   └─ agree checkbox becomes enabled
                      │
                      └─ onLoadError
                           └─ render in-viewer error + "重新載入" button
                           └─ NoticeAgreementStep keeps hasReadNotice = false
```

The proxy URL pattern is identical to the one currently used by `FilePreviewDialog` for the same file, so the backend file-proxy, MinIO routing, and token-via-query-param auth are all unchanged.

---

## Error / Empty States

| State | Trigger | Display | Agree gate |
|---|---|---|---|
| **No regulations uploaded** | `publicDocs.regulations_url` is falsy after `getPublicDocs()` resolves | Amber `<Alert>` replacing the viewer: 「系統管理員尚未上傳獎學金要點，目前無法進行申請。請聯絡承辦單位。」 | Disabled, no way to enable |
| **PDF load failure** | `<Document onLoadError>` fires (network error, corrupt file, pdf.js worker failed to mount) | In-viewer red error state + 「重新載入」 button that re-triggers the document load | Disabled until reload succeeds and bottom is reached |
| **Admin uploads non-PDF for regulations** | File extension or MIME mismatch | Client rejects via `<input accept=".pdf">` and `validateAndSet` toast; server rejects with HTTP 400 message above | n/a — admin context |
| **Pre-existing DOC/DOCX in `regulations_url`** | Legacy data from before this change | Admin sees current file but the viewer treats it as unrenderable → falls through to "PDF load failure" branch for students. Admin must re-upload. | Disabled |

Per project policy ("NO BACKWARD COMPATIBILITY"), legacy non-PDF regulations are not auto-converted. Admins re-upload.

---

## Build & Dependencies

- **Add**: `react-pdf` (latest 9.x line). Pulls in `pdfjs-dist`.
- **Worker config**: create `frontend/lib/pdf-worker.ts`:
  ```ts
  import { pdfjs } from "react-pdf";
  pdfjs.GlobalWorkerOptions.workerSrc = `/_next/static/chunks/pdf.worker.min.mjs`;
  ```
  Import this module once from `InlinePdfViewer`. The exact worker path / copy step follows the `react-pdf` Next.js setup guide and is finalized during implementation; if a worker proxy URL doesn't pan out, fall back to `new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString()`.
- **Styling**: import `react-pdf`'s `TextLayer.css` and `AnnotationLayer.css` so selectable text and links render correctly. Imported alongside the worker module to keep `InlinePdfViewer` clean.
- No backend dependency changes. No Docker config changes.
- Bundle impact: +~80KB gz for `react-pdf` + lazy-loaded pdf.js worker (loaded only when a student visits the agreement step).

---

## Testing

### Frontend unit / component

- New tests for `InlinePdfViewer`:
  - Loads a fixture PDF, simulates a scroll event that reaches the bottom → `onReachedBottom` fires exactly once.
  - Loads a fixture PDF whose rendered height fits the container → `onReachedBottom` fires on mount-after-load, before any scroll.
  - `<Document onLoadError>` path → `onLoadError` fires, `onReachedBottom` never fires.
- New / updated tests for `NoticeAgreementStep`:
  - With `regulations_url` present + scroll-to-bottom simulated → agree checkbox becomes enabled.
  - With `regulations_url` absent → blocking alert visible, agree checkbox stays disabled regardless of any interaction.

### Backend

- `tests/api/test_system_settings.py` (or equivalent): upload a `.docx` to the regulations endpoint → expect 400 with the Chinese message. Upload a `.pdf` with matching MIME → expect 200. Upload a `.pdf` with mismatched MIME (e.g. `application/octet-stream`) → expect 400.

### E2E (Playwright)

- Update the existing student-application happy-path spec to scroll the new PDF viewer container instead of the 8-item list. Use the seeded admin to upload a small fixture PDF as `regulations_url` during test setup.
- New spec: with no `regulations_url` in `system_settings`, log in as a student, navigate to the agreement step, assert the blocking alert is visible and the Continue button stays disabled.

### Manual smoke (Docker dev env)

- Admin → System Docs → upload a 1-page PDF → log out → log in as student → reach agreement step → checkbox auto-latches on mount → agree → continue.
- Admin → System Docs → upload a 5-page PDF → student must scroll within the viewer to bottom → checkbox latches → agree → continue.
- Admin → delete the `regulations_url` row in DB / clear via UI → student sees blocking alert.
- Admin → attempt to upload a `.docx` to 獎學金要點 → rejected with the Chinese error toast (client) and the same on a curl bypass (server).

---

## Risks & Open Items

- **`react-pdf` worker setup in Next.js**: the worker path is environment-sensitive. The implementation plan should include a verification step (manual + Playwright smoke) that the worker loads in both dev (`docker compose up`) and a production-style build before declaring done.
- **CJK font rendering**: most NYCU regulations PDFs embed their own fonts; pdf.js renders them fine. If a PDF arrives without embedded fonts and depends on system fonts, glyphs may render as boxes. Out of scope to "fix" for arbitrary uploads — flagged here so it doesn't get rediscovered mid-implementation.
- **Bundle size**: +~80KB gz is acceptable but worth confirming against the existing budget after the change lands.
- **Performance on 20+ page PDFs**: Approach A (all pages stacked) was chosen on the assumption that real regulations are short (1–5 pages). If a real admin uploads a 30-page doc, first-render time may be noticeable. We accept this tradeoff per the brainstorm.

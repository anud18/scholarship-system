# Scholarship Regulations Scroll-Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the student-application "scroll to bottom before agree" gate from the hardcoded 8-item notice list onto the admin-uploaded 獎學金要點 PDF, rendered inline with `react-pdf`. Admins must upload as PDF; if none uploaded, students are blocked at the agreement step.

**Architecture:** Replace the gated scrollable content inside `NoticeAgreementStep.tsx` with a new reusable `InlinePdfViewer` component (`react-pdf` based). Tighten admin upload validation (client + server) so `regulations_url` accepts PDF only. The 8 hardcoded notice items remain as a static, non-gated summary. The 申請文件範例檔 button continues to use the existing `FilePreviewDialog`.

**Tech Stack:** Next.js 16 (frontend), React 18, TypeScript, `react-pdf` (new), FastAPI (backend), Jest (frontend tests), pytest (backend tests), Docker Compose dev env.

**Reference spec:** [`docs/superpowers/specs/2026-05-21-scholarship-regulations-scroll-gate-design.md`](../specs/2026-05-21-scholarship-regulations-scroll-gate-design.md)

---

## File Structure

**Files created:**
- `frontend/lib/pdf-worker.ts` — sets `pdfjs.GlobalWorkerOptions.workerSrc` exactly once
- `frontend/components/inline-pdf-viewer.tsx` — new reusable PDF viewer with scroll-to-bottom detection
- `frontend/components/__tests__/inline-pdf-viewer.test.tsx` — Jest tests for the new component
- `frontend/components/__tests__/notice-agreement-step.test.tsx` — Jest tests for the updated wizard step
- `backend/app/tests/test_system_settings_upload_doc.py` — pytest for PDF-only upload validation

**Files modified:**
- `frontend/package.json` — adds `react-pdf` dependency
- `frontend/components/student-wizard/steps/NoticeAgreementStep.tsx` — swap gated content, drop regulations dialog button, add empty/error states, update locale copy
- `frontend/components/admin/system-docs/SystemDocsPanel.tsx` — per-slot `accepted` extensions, restrict `regulations_url` slot to PDF
- `backend/app/api/v1/endpoints/system_settings.py` — add PDF-only guard in `upload_system_doc` when `doc_key == "regulations_url"`

---

## Tasks

### Task 1: Add react-pdf dependency and worker config

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/lib/pdf-worker.ts`

- [ ] **Step 1: Install `react-pdf`**

Run from project root:
```bash
docker compose -f docker-compose.dev.yml exec frontend npm install react-pdf@9
```

If the frontend container isn't running, start it first:
```bash
docker compose -f docker-compose.dev.yml up -d frontend
```

Expected: `package.json` shows `"react-pdf": "^9.x.x"` in `dependencies`. `package-lock.json` updated. `pdfjs-dist` appears as a transitive dep.

- [ ] **Step 2: Create the pdf.js worker config module**

Create `frontend/lib/pdf-worker.ts`:

```ts
// Configures the pdf.js worker for react-pdf. Imported once by InlinePdfViewer
// so the worker URL is set before any <Document> mounts.
import { pdfjs } from "react-pdf";

// Use the worker bundled with pdfjs-dist via a URL the browser can fetch.
// `new URL(..., import.meta.url)` is resolved by Next.js / Turbopack into a
// static asset URL at build time.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();
```

- [ ] **Step 3: Verify the worker module type-checks**

Run:
```bash
docker compose -f docker-compose.dev.yml exec frontend npm run type-check
```

Expected: PASS (no new TypeScript errors).

If `tsc` complains about `import.meta.url`, ensure `tsconfig.json` has `"module": "esnext"` or `"module": "nodenext"` (it should — Next.js defaults). If `tsc` complains about the `.mjs` import path, change the worker source to:

```ts
pdfjs.GlobalWorkerOptions.workerSrc =
  `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
```

…and re-run type-check.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/lib/pdf-worker.ts
git commit -m "feat(frontend): add react-pdf and configure pdf.js worker"
```

---

### Task 2: Create `InlinePdfViewer` component (failing test first)

**Files:**
- Create: `frontend/components/__tests__/inline-pdf-viewer.test.tsx`
- Create: `frontend/components/inline-pdf-viewer.tsx`

- [ ] **Step 1: Write failing tests for `InlinePdfViewer`**

Create `frontend/components/__tests__/inline-pdf-viewer.test.tsx`:

```tsx
import React from "react";
import { render, screen, act, fireEvent } from "@testing-library/react";
import { InlinePdfViewer } from "../inline-pdf-viewer";

// Mock react-pdf so we don't load real pdf.js in jsdom. We expose a
// `triggerLoadSuccess(numPages)` and `triggerLoadError(err)` helper via
// the mock so individual tests can drive the lifecycle.
jest.mock("react-pdf", () => {
  type Cb = (info: { numPages: number }) => void;
  type ErrCb = (err: Error) => void;
  const handlers: { success?: Cb; error?: ErrCb } = {};
  const Document = (props: {
    onLoadSuccess?: Cb;
    onLoadError?: ErrCb;
    children?: React.ReactNode;
  }) => {
    handlers.success = props.onLoadSuccess;
    handlers.error = props.onLoadError;
    return <div data-testid="pdf-document">{props.children}</div>;
  };
  const Page = ({ pageNumber }: { pageNumber: number }) => (
    <div data-testid={`pdf-page-${pageNumber}`} style={{ height: 800 }}>
      page {pageNumber}
    </div>
  );
  return {
    Document,
    Page,
    pdfjs: { GlobalWorkerOptions: { workerSrc: "" }, version: "x" },
    __setSuccess: (n: number) => handlers.success?.({ numPages: n }),
    __setError: (e: Error) => handlers.error?.(e),
  };
});

// Mock the worker side-effect import so it doesn't blow up jsdom.
jest.mock("@/lib/pdf-worker", () => ({}));

const reactPdf = jest.requireMock("react-pdf") as {
  __setSuccess: (n: number) => void;
  __setError: (e: Error) => void;
};

describe("InlinePdfViewer", () => {
  function setScrollMetrics(
    el: HTMLElement,
    { scrollHeight, clientHeight, scrollTop }: { scrollHeight: number; clientHeight: number; scrollTop: number }
  ) {
    Object.defineProperty(el, "scrollHeight", { configurable: true, value: scrollHeight });
    Object.defineProperty(el, "clientHeight", { configurable: true, value: clientHeight });
    Object.defineProperty(el, "scrollTop", { configurable: true, value: scrollTop });
  }

  it("renders one <Page> per numPages after onLoadSuccess", () => {
    render(<InlinePdfViewer url="/fake.pdf" />);
    act(() => reactPdf.__setSuccess(3));
    expect(screen.getByTestId("pdf-page-1")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-page-2")).toBeInTheDocument();
    expect(screen.getByTestId("pdf-page-3")).toBeInTheDocument();
  });

  it("fires onReachedBottom exactly once when the user scrolls to the bottom", () => {
    const onReached = jest.fn();
    const { container } = render(
      <InlinePdfViewer url="/fake.pdf" onReachedBottom={onReached} />
    );
    act(() => reactPdf.__setSuccess(2));

    const scroller = container.querySelector(
      "[data-testid='pdf-scroll-container']"
    ) as HTMLElement;
    expect(scroller).not.toBeNull();

    // Initial scroll, not yet at bottom.
    setScrollMetrics(scroller, { scrollHeight: 2000, clientHeight: 500, scrollTop: 100 });
    fireEvent.scroll(scroller);
    expect(onReached).not.toHaveBeenCalled();

    // Scroll to the bottom (within the 8px slack).
    setScrollMetrics(scroller, { scrollHeight: 2000, clientHeight: 500, scrollTop: 1495 });
    fireEvent.scroll(scroller);
    expect(onReached).toHaveBeenCalledTimes(1);

    // Bouncing back should NOT re-fire.
    setScrollMetrics(scroller, { scrollHeight: 2000, clientHeight: 500, scrollTop: 200 });
    fireEvent.scroll(scroller);
    expect(onReached).toHaveBeenCalledTimes(1);
  });

  it("fires onReachedBottom on mount-after-load when the document already fits the container", () => {
    const onReached = jest.fn();
    const { container } = render(
      <InlinePdfViewer url="/fake.pdf" onReachedBottom={onReached} />
    );

    const scroller = container.querySelector(
      "[data-testid='pdf-scroll-container']"
    ) as HTMLElement;
    setScrollMetrics(scroller, { scrollHeight: 400, clientHeight: 500, scrollTop: 0 });

    act(() => reactPdf.__setSuccess(1));

    expect(onReached).toHaveBeenCalledTimes(1);
  });

  it("fires onLoadError and never fires onReachedBottom when the document fails to load", () => {
    const onReached = jest.fn();
    const onErr = jest.fn();
    render(
      <InlinePdfViewer
        url="/broken.pdf"
        onReachedBottom={onReached}
        onLoadError={onErr}
      />
    );

    const err = new Error("boom");
    act(() => reactPdf.__setError(err));

    expect(onErr).toHaveBeenCalledWith(err);
    expect(onReached).not.toHaveBeenCalled();
    expect(screen.getByText(/重新載入|Reload/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to confirm they fail**

Run:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx jest components/__tests__/inline-pdf-viewer.test.tsx
```

Expected: FAIL with `Cannot find module '../inline-pdf-viewer'`.

- [ ] **Step 3: Implement `InlinePdfViewer`**

Create `frontend/components/inline-pdf-viewer.tsx`:

```tsx
"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page } from "react-pdf";
import { AlertCircle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

// Side-effect import: configures pdfjs.GlobalWorkerOptions.workerSrc.
import "@/lib/pdf-worker";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

interface InlinePdfViewerProps {
  url: string;
  height?: number;
  onReachedBottom?: () => void;
  onLoadError?: (err: Error) => void;
  locale?: "zh" | "en";
}

const SLACK_PX = 8;

export function InlinePdfViewer({
  url,
  height = 500,
  onReachedBottom,
  onLoadError,
  locale = "zh",
}: InlinePdfViewerProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [numPages, setNumPages] = useState<number | null>(null);
  const [loadError, setLoadError] = useState<Error | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  // Latch: fire onReachedBottom at most once per (url, reloadToken) instance.
  const latched = useRef(false);
  useEffect(() => {
    latched.current = false;
  }, [url, reloadToken]);

  const fireReached = useCallback(() => {
    if (latched.current) return;
    latched.current = true;
    onReachedBottom?.();
  }, [onReachedBottom]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight <= SLACK_PX) {
      fireReached();
    }
  }, [fireReached]);

  const handleLoadSuccess = useCallback(
    ({ numPages: n }: { numPages: number }) => {
      setNumPages(n);
      setLoadError(null);
      // After pages mount, if the document fits without overflowing the
      // container, treat it as already read. Schedule on the next frame so
      // layout has settled.
      requestAnimationFrame(() => {
        const el = scrollRef.current;
        if (!el) return;
        if (el.scrollHeight <= el.clientHeight + SLACK_PX) {
          fireReached();
        }
      });
    },
    [fireReached]
  );

  const handleLoadError = useCallback(
    (err: Error) => {
      setLoadError(err);
      onLoadError?.(err);
    },
    [onLoadError]
  );

  const labels =
    locale === "zh"
      ? { loading: "載入中…", error: "無法載入文件", reload: "重新載入" }
      : { loading: "Loading…", error: "Failed to load document", reload: "Reload" };

  return (
    <div
      ref={scrollRef}
      data-testid="pdf-scroll-container"
      onScroll={handleScroll}
      className="overflow-y-auto rounded-lg border bg-white"
      style={{ height }}
    >
      {loadError ? (
        <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
          <AlertCircle className="h-8 w-8 text-red-500" />
          <p className="text-sm font-medium text-red-700">{labels.error}</p>
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              setLoadError(null);
              setNumPages(null);
              setReloadToken((t) => t + 1);
            }}
          >
            <RotateCcw className="mr-1.5 h-4 w-4" />
            {labels.reload}
          </Button>
        </div>
      ) : (
        <Document
          // Key forces a remount on reload.
          key={`${url}#${reloadToken}`}
          file={url}
          loading={
            <div className="space-y-3 p-6">
              <Skeleton className="h-6 w-full" />
              <Skeleton className="h-6 w-[90%]" />
              <Skeleton className="h-6 w-[85%]" />
              <Skeleton className="h-6 w-[95%]" />
              <p className="pt-2 text-center text-xs text-muted-foreground">
                {labels.loading}
              </p>
            </div>
          }
          onLoadSuccess={handleLoadSuccess}
          onLoadError={handleLoadError}
        >
          {numPages !== null
            ? Array.from({ length: numPages }, (_, i) => (
                <Page
                  key={i + 1}
                  pageNumber={i + 1}
                  renderAnnotationLayer
                  renderTextLayer
                  className="mx-auto mb-2"
                />
              ))
            : null}
        </Document>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run tests to confirm they pass**

Run:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx jest components/__tests__/inline-pdf-viewer.test.tsx
```

Expected: PASS — all 4 tests green.

If the "fires onReachedBottom on mount-after-load when the document already fits" test fails because the `requestAnimationFrame` callback isn't flushed by jsdom, wrap the `act(() => reactPdf.__setSuccess(1))` block with a flush:

```tsx
// Replace the simple act() call in that test with:
await act(async () => {
  reactPdf.__setSuccess(1);
  await new Promise((resolve) => requestAnimationFrame(() => resolve(undefined)));
});
```

And re-run.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/inline-pdf-viewer.tsx frontend/components/__tests__/inline-pdf-viewer.test.tsx
git commit -m "feat(frontend): add InlinePdfViewer with scroll-to-bottom gating"
```

---

### Task 3: Rewrite `NoticeAgreementStep` to use `InlinePdfViewer`

**Files:**
- Create: `frontend/components/__tests__/notice-agreement-step.test.tsx`
- Modify: `frontend/components/student-wizard/steps/NoticeAgreementStep.tsx`

- [ ] **Step 1: Write failing tests for the rewritten step**

Create `frontend/components/__tests__/notice-agreement-step.test.tsx`:

```tsx
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { NoticeAgreementStep } from "../student-wizard/steps/NoticeAgreementStep";

// Mock the API client used inside the step.
jest.mock("@/lib/api", () => ({
  api: {
    systemSettings: {
      getPublicDocs: jest.fn(),
    },
  },
}));

// Mock the inline viewer so tests can drive `onReachedBottom` directly.
jest.mock("@/components/inline-pdf-viewer", () => ({
  InlinePdfViewer: (props: {
    url: string;
    onReachedBottom?: () => void;
  }) => (
    <div data-testid="inline-pdf-viewer" data-url={props.url}>
      <button
        type="button"
        data-testid="simulate-reached-bottom"
        onClick={() => props.onReachedBottom?.()}
      >
        simulate scroll bottom
      </button>
    </div>
  ),
}));

// Mock FilePreviewDialog (used for the sample-document button).
jest.mock("@/components/file-preview-dialog", () => ({
  FilePreviewDialog: () => null,
}));

const { api } = jest.requireMock("@/lib/api") as {
  api: { systemSettings: { getPublicDocs: jest.Mock } };
};

function flushPromises() {
  return new Promise<void>((resolve) => setTimeout(resolve, 0));
}

describe("NoticeAgreementStep", () => {
  const noop = () => undefined;

  beforeEach(() => {
    jest.clearAllMocks();
    Object.defineProperty(window, "localStorage", {
      value: {
        getItem: jest.fn(() => "test-token"),
      },
      configurable: true,
    });
  });

  it("blocks the agree checkbox and shows an alert when no regulations are uploaded", async () => {
    api.systemSettings.getPublicDocs.mockResolvedValue({
      success: true,
      data: {},
    });

    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={noop}
        onNext={noop}
        locale="zh"
      />
    );
    await flushPromises();

    expect(
      screen.getByText(/系統管理員尚未上傳獎學金要點/)
    ).toBeInTheDocument();
    expect(screen.queryByTestId("inline-pdf-viewer")).not.toBeInTheDocument();

    const agreeCheckbox = screen.getByRole("checkbox", {
      name: /同意遵守相關規定/,
    });
    expect(agreeCheckbox).toBeDisabled();
  });

  it("renders the InlinePdfViewer and enables the agree checkbox after scroll-to-bottom", async () => {
    api.systemSettings.getPublicDocs.mockResolvedValue({
      success: true,
      data: {
        regulations_url: "system-docs/regulations_url_20260520_120000.pdf",
        regulations_url_filename: "獎學金要點.pdf",
      },
    });

    const onAgree = jest.fn();
    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={onAgree}
        onNext={noop}
        locale="zh"
      />
    );
    await flushPromises();

    const viewer = screen.getByTestId("inline-pdf-viewer");
    expect(viewer.getAttribute("data-url")).toMatch(
      /\/api\/v1\/system-settings\/file-proxy\?key=regulations_url/
    );

    // Agree starts disabled (hasReadNotice = false).
    const agreeCheckbox = screen.getByRole("checkbox", {
      name: /同意遵守相關規定/,
    });
    expect(agreeCheckbox).toBeDisabled();

    // Simulate scroll-to-bottom from the inline viewer.
    fireEvent.click(screen.getByTestId("simulate-reached-bottom"));

    expect(agreeCheckbox).not.toBeDisabled();
  });

  it("keeps the 8 hardcoded notice items visible as a static summary", async () => {
    api.systemSettings.getPublicDocs.mockResolvedValue({
      success: true,
      data: { regulations_url: "system-docs/x.pdf" },
    });
    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={noop}
        onNext={noop}
        locale="zh"
      />
    );
    await flushPromises();

    expect(screen.getByText("申請資格")).toBeInTheDocument();
    expect(screen.getByText("申請期限")).toBeInTheDocument();
    expect(screen.getByText("獎金撥款")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
docker compose -f docker-compose.dev.yml exec frontend npx jest components/__tests__/notice-agreement-step.test.tsx
```

Expected: FAIL — assertions about the new alert text and the InlinePdfViewer don't match the current implementation (which still renders the 8-item scroll container and dialog button).

- [ ] **Step 3: Rewrite `NoticeAgreementStep.tsx`**

Open `frontend/components/student-wizard/steps/NoticeAgreementStep.tsx` and replace the full file contents with:

```tsx
"use client";

import React, { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertCircle,
  CheckCircle,
  FileText,
  AlertTriangle,
  ChevronRight,
} from "lucide-react";
import { api } from "@/lib/api";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import { InlinePdfViewer } from "@/components/inline-pdf-viewer";

interface NoticeAgreementStepProps {
  agreedToTerms: boolean;
  onAgree: (agreed: boolean) => void;
  onNext: () => void;
  locale: "zh" | "en";
}

export function NoticeAgreementStep({
  agreedToTerms,
  onAgree,
  onNext,
  locale,
}: NoticeAgreementStepProps) {
  const [hasReadNotice, setHasReadNotice] = useState(false);

  const [publicDocs, setPublicDocs] = useState<{
    regulations_url?: string;
    sample_document_url?: string;
    regulations_url_filename?: string;
    sample_document_url_filename?: string;
  }>({});
  const [docsLoaded, setDocsLoaded] = useState(false);
  const [previewFile, setPreviewFile] = useState<{
    url: string;
    filename: string;
    type: string;
  } | null>(null);
  const [showPreview, setShowPreview] = useState(false);

  useEffect(() => {
    api.systemSettings.getPublicDocs().then((res) => {
      if (res.success && res.data) setPublicDocs(res.data);
      setDocsLoaded(true);
    });
  }, []);

  const handleOpenSampleDoc = (label: string) => {
    const token = localStorage.getItem("auth_token") || "";
    const objectName = publicDocs.sample_document_url;
    const originalName = publicDocs.sample_document_url_filename;
    const cacheBuster = encodeURIComponent(objectName?.split("/").pop() || "");
    const url = `/api/v1/system-settings/file-proxy?key=sample_document_url&token=${encodeURIComponent(
      token
    )}&v=${cacheBuster}`;
    const filename = originalName || label;
    const lower = (originalName || objectName || "").toLowerCase();
    let type = "application/pdf";
    if (lower.endsWith(".doc")) type = "application/msword";
    else if (lower.endsWith(".docx"))
      type =
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
    else if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) type = "image/jpeg";
    else if (lower.endsWith(".png")) type = "image/png";
    setPreviewFile({ url, filename, type });
    setShowPreview(true);
  };

  const regulationsViewerUrl = (() => {
    const objectName = publicDocs.regulations_url;
    if (!objectName) return null;
    const token =
      typeof window !== "undefined"
        ? localStorage.getItem("auth_token") || ""
        : "";
    const cacheBuster = encodeURIComponent(objectName.split("/").pop() || "");
    return `/api/v1/system-settings/file-proxy?key=regulations_url&token=${encodeURIComponent(
      token
    )}&v=${cacheBuster}`;
  })();

  const notices = {
    zh: {
      title: "獎學金申請注意事項",
      subtitle:
        "請詳細閱讀以下內容，並滑完下方的「獎學金要點」後勾選同意方可繼續申請",
      items: [
        { title: "申請資格", content: "申請人必須為本校在學學生，且符合各獎學金規定的申請條件。請確認您的學籍狀態與申請資格。" },
        { title: "申請期限", content: "各獎學金有不同的申請期限，逾期申請恕不受理。請注意各獎學金的開放申請日期與截止日期。" },
        { title: "文件準備", content: "請備妥所需文件，包括但不限於成績單、在學證明、指導教授推薦函等。所有文件必須為清晰可辨識的電子檔案（PDF、JPG、JPEG 或 PNG 格式）。" },
        { title: "資料正確性", content: "申請人應確保所填寫資料及上傳文件之正確性與真實性。如有虛偽不實，將取消申請資格並依校規處理。" },
        { title: "個人資料使用", content: "您的個人資料將僅用於獎學金申請審核及後續相關作業，本校將依個人資料保護法規定妥善保管。" },
        { title: "審核流程", content: "申請送出後將經過系所初審、院級複審及行政單位核定等程序。審核期間請隨時注意系統通知。" },
        { title: "獎金撥款", content: "獲獎學生請確認銀行帳戶資料正確無誤，獎學金將於核定後撥款至指定帳戶。" },
        { title: "申請撤回", content: "申請送出後如需撤回，請於審核開始前聯繫承辦單位。審核程序啟動後將無法撤回申請。" },
      ],
      importantNotice: "重要提醒",
      importantContent:
        "請務必詳細閱讀各獎學金的申請條款與相關規定。每位學生每學期限申請一項獎學金，請謹慎選擇。",
      agreementText: "我已詳細閱讀並了解獎學金要點，同意遵守相關規定",
      readNoticeText: "已詳閱獎學金要點",
      readNoticeHint:
        "請將下方獎學金要點滑到底端，閱讀完成後才能勾選同意",
      readNoticeDone: "已閱讀完成",
      nextButton: "同意並繼續",
      readFirst: "請先滑到獎學金要點底部完成閱讀",
      sampleDocumentLabel: "申請文件範例檔",
      sampleDocumentRow: "需要參考申請文件格式？",
      sampleDocumentNotProvided: "尚未提供",
      regulationsHeader: "獎學金要點",
      regulationsMissing:
        "系統管理員尚未上傳獎學金要點，目前無法進行申請。請聯絡承辦單位。",
    },
    en: {
      title: "Scholarship Application Notice",
      subtitle:
        "Read the following carefully. Scroll the Scholarship Regulations below to the bottom before agreeing to continue.",
      items: [
        { title: "Eligibility", content: "Applicants must be currently enrolled students and meet the specific requirements of each scholarship. Please verify your enrollment status and eligibility." },
        { title: "Application Deadline", content: "Each scholarship has different application deadlines. Late applications will not be accepted. Please note the opening and closing dates for each scholarship." },
        { title: "Document Preparation", content: "Please prepare all required documents, including but not limited to transcripts, enrollment certificates, and advisor recommendation letters. All documents must be clear electronic files (PDF, JPG, JPEG, or PNG format)." },
        { title: "Data Accuracy", content: "Applicants must ensure the accuracy and authenticity of all information and uploaded documents. False information will result in disqualification and disciplinary action according to university regulations." },
        { title: "Personal Data Usage", content: "Your personal data will be used solely for scholarship application review and related procedures. The university will safeguard your data according to Personal Data Protection Act." },
        { title: "Review Process", content: "After submission, applications will go through department preliminary review, college review, and administrative approval. Please monitor system notifications during the review period." },
        { title: "Award Distribution", content: "Award recipients should ensure their bank account information is correct. Scholarships will be disbursed to the designated account after approval." },
        { title: "Application Withdrawal", content: "If you need to withdraw your application after submission, please contact the administrative office before the review begins. Withdrawal is not possible once the review process has started." },
      ],
      importantNotice: "Important Notice",
      importantContent:
        "Please read the terms and conditions of each scholarship carefully. Each student may only apply for one scholarship per semester. Choose wisely.",
      agreementText:
        "I have read and understand the scholarship regulations and agree to comply",
      readNoticeText: "I have read the scholarship regulations",
      readNoticeHint:
        "Scroll the regulations document to the bottom to enable the agree checkbox",
      readNoticeDone: "Reading complete",
      nextButton: "Agree and Continue",
      readFirst: "Please scroll to the bottom of the regulations first",
      sampleDocumentLabel: "Sample Application Documents",
      sampleDocumentRow: "Need to see the application document format?",
      sampleDocumentNotProvided: "Not available",
      regulationsHeader: "Scholarship Regulations",
      regulationsMissing:
        "The system administrator has not uploaded the scholarship regulations. Applications cannot proceed. Please contact the administrative office.",
    },
  };

  const t = notices[locale];

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <div className="p-3 bg-nycu-blue-100 rounded-lg">
              <FileText className="h-6 w-6 text-nycu-blue-600" />
            </div>
            <div>
              <CardTitle className="text-2xl">{t.title}</CardTitle>
              <CardDescription className="mt-1">{t.subtitle}</CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Important Notice Alert */}
          <Alert className="border-amber-200 bg-amber-50">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            <AlertDescription>
              <div className="font-semibold text-amber-900 mb-1">
                {t.importantNotice}
              </div>
              <div className="text-sm text-amber-800">{t.importantContent}</div>
            </AlertDescription>
          </Alert>

          {/* 8-item static summary (no scroll, no gate) */}
          <Card className="border-2">
            <div className="p-6">
              <div className="space-y-4">
                {t.items.map((item, index) => (
                  <div
                    key={index}
                    className="pb-4 border-b last:border-b-0 last:pb-0"
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-nycu-blue-100 text-nycu-blue-700 flex items-center justify-center font-semibold text-sm">
                        {index + 1}
                      </div>
                      <div className="flex-1">
                        <h4 className="font-semibold text-nycu-navy-800 mb-2">
                          {item.title}
                        </h4>
                        <p className="text-sm text-gray-700 leading-relaxed">
                          {item.content}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </Card>

          {/* Reference row: sample document button (regulations are rendered
              inline below, so they no longer need a button here). */}
          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200 flex items-center justify-between gap-3">
            <p className="text-sm text-blue-900">{t.sampleDocumentRow}</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleOpenSampleDoc(t.sampleDocumentLabel)}
              disabled={!publicDocs.sample_document_url}
              className="flex items-center gap-2"
            >
              <FileText className="h-4 w-4" />
              {t.sampleDocumentLabel}
              {!publicDocs.sample_document_url && (
                <span className="text-xs text-gray-400 ml-1">
                  ({t.sampleDocumentNotProvided})
                </span>
              )}
            </Button>
          </div>

          {/* Inline regulations viewer (the gated content) */}
          <div>
            <h3 className="font-semibold text-nycu-navy-800 mb-2">
              {t.regulationsHeader}
            </h3>
            {!docsLoaded ? (
              <div className="h-[500px] rounded-lg border bg-gray-50" />
            ) : regulationsViewerUrl ? (
              <>
                <InlinePdfViewer
                  url={regulationsViewerUrl}
                  height={500}
                  locale={locale}
                  onReachedBottom={() => setHasReadNotice(true)}
                />
                {!hasReadNotice && (
                  <p className="text-xs text-amber-700 mt-2 flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" />
                    {t.readNoticeHint}
                  </p>
                )}
              </>
            ) : (
              <Alert className="border-amber-300 bg-amber-50">
                <AlertCircle className="h-5 w-5 text-amber-700" />
                <AlertDescription className="text-amber-900">
                  {t.regulationsMissing}
                </AlertDescription>
              </Alert>
            )}
          </div>

          {/* Read confirmation — auto-checked when viewer reports bottom reached */}
          <div
            className={`flex items-center space-x-2 p-4 rounded-lg transition-colors ${
              hasReadNotice
                ? "bg-emerald-50 border border-emerald-200"
                : "bg-gray-50"
            }`}
          >
            <Checkbox id="read-notice" checked={hasReadNotice} disabled />
            <Label
              htmlFor="read-notice"
              className="text-sm font-medium leading-none cursor-default"
            >
              {hasReadNotice ? t.readNoticeDone : t.readNoticeText}
            </Label>
          </div>

          {/* Agreement checkbox */}
          <div
            className={`p-6 rounded-lg border-2 transition-all ${
              hasReadNotice
                ? "bg-white border-nycu-blue-200"
                : "bg-gray-50 border-gray-200 opacity-60"
            }`}
          >
            <div className="flex items-start space-x-3">
              <Checkbox
                id="agree-terms"
                checked={agreedToTerms}
                onCheckedChange={(checked) => onAgree(checked as boolean)}
                disabled={!hasReadNotice}
                className="mt-1"
              />
              <div className="flex-1">
                <Label
                  htmlFor="agree-terms"
                  className={`text-base font-semibold leading-relaxed ${
                    hasReadNotice
                      ? "cursor-pointer text-nycu-navy-800"
                      : "cursor-not-allowed text-gray-500"
                  }`}
                >
                  {t.agreementText}
                </Label>
                {!hasReadNotice && (
                  <p className="text-sm text-amber-600 mt-2 flex items-center gap-2">
                    <AlertCircle className="h-4 w-4" />
                    {t.readFirst}
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex justify-end pt-4">
            <Button
              onClick={onNext}
              disabled={!agreedToTerms}
              size="lg"
              className="nycu-gradient text-white px-8"
            >
              {agreedToTerms && <CheckCircle className="h-5 w-5 mr-2" />}
              {t.nextButton}
              <ChevronRight className="h-5 w-5 ml-2" />
            </Button>
          </div>
        </CardContent>
      </Card>

      <FilePreviewDialog
        isOpen={showPreview}
        onClose={() => setShowPreview(false)}
        file={previewFile}
        locale={locale}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
docker compose -f docker-compose.dev.yml exec frontend npx jest components/__tests__/notice-agreement-step.test.tsx
```

Expected: PASS — all 3 tests green.

- [ ] **Step 5: Run type-check and the full Jest suite for the affected modules**

```bash
docker compose -f docker-compose.dev.yml exec frontend npm run type-check
docker compose -f docker-compose.dev.yml exec frontend npx jest components/__tests__/inline-pdf-viewer.test.tsx components/__tests__/notice-agreement-step.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/student-wizard/steps/NoticeAgreementStep.tsx frontend/components/__tests__/notice-agreement-step.test.tsx
git commit -m "feat(frontend): gate agree checkbox on inline regulations PDF scroll"
```

---

### Task 4: Restrict the admin regulations slot to PDF only

**Files:**
- Modify: `frontend/components/admin/system-docs/SystemDocsPanel.tsx`

- [ ] **Step 1: Move `ACCEPTED` to a per-slot field**

Open `frontend/components/admin/system-docs/SystemDocsPanel.tsx`.

Replace the existing `DocSlot` interface and the global `ACCEPTED` constant with a per-slot `accepted` field.

Find:

```tsx
interface DocSlot {
  key: DocKey;
  title: string;
  subtitle: string;
  Icon: React.ComponentType<{ className?: string }>;
  accent: {
    ring: string;
    tile: string;
    iconColor: string;
    pillBg: string;
    dropHover: string;
    dropActive: string;
  };
}
```

Replace with:

```tsx
interface DocSlot {
  key: DocKey;
  title: string;
  subtitle: string;
  accepted: string;        // comma-separated extension list
  acceptedLabel: string;   // human-readable, shown in the drop zone hint
  Icon: React.ComponentType<{ className?: string }>;
  accent: {
    ring: string;
    tile: string;
    iconColor: string;
    pillBg: string;
    dropHover: string;
    dropActive: string;
  };
}
```

Find the `SLOTS` array and add the new fields. After the change it should be:

```tsx
const SLOTS: DocSlot[] = [
  {
    key: "regulations_url",
    title: "獎學金要點",
    subtitle: "提供學生、教授與學院審核時參閱的法規文件",
    accepted: ".pdf",
    acceptedLabel: "PDF",
    Icon: BookOpen,
    accent: {
      ring: "ring-nycu-blue-200",
      tile: "bg-nycu-blue-50",
      iconColor: "text-nycu-blue-600",
      pillBg: "bg-nycu-blue-100 text-nycu-blue-700",
      dropHover: "hover:border-nycu-blue-400 hover:bg-nycu-blue-50/40",
      dropActive:
        "border-nycu-blue-500 bg-nycu-blue-50 ring-4 ring-nycu-blue-100",
    },
  },
  {
    key: "sample_document_url",
    title: "申請文件範例檔",
    subtitle: "提供學生填寫申請文件時的參考範例",
    accepted: ".pdf,.doc,.docx",
    acceptedLabel: "PDF · DOC · DOCX",
    Icon: FileArchive,
    accent: {
      ring: "ring-amber-200",
      tile: "bg-amber-50",
      iconColor: "text-amber-600",
      pillBg: "bg-amber-100 text-amber-700",
      dropHover: "hover:border-amber-400 hover:bg-amber-50/40",
      dropActive: "border-amber-500 bg-amber-50 ring-4 ring-amber-100",
    },
  },
];
```

Delete the global `const ACCEPTED = ".pdf,.doc,.docx";` line.

- [ ] **Step 2: Update `validateAndSet` to use the slot's accepted list**

Find the current `validateAndSet`:

```tsx
const validateAndSet = (key: DocKey, file: File | null) => {
  if (!file) return;
  const ext = "." + (file.name.toLowerCase().split(".").pop() || "");
  if (!ACCEPTED.split(",").includes(ext)) {
    toast.error("僅接受 PDF / DOC / DOCX");
    return;
  }
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    toast.error(`檔案大小超過 ${MAX_SIZE_MB} MB`);
    return;
  }
  setPendingFiles((p) => ({ ...p, [key]: file }));
};
```

Replace with:

```tsx
const validateAndSet = (key: DocKey, file: File | null) => {
  if (!file) return;
  const slot = SLOTS.find((s) => s.key === key);
  if (!slot) return;
  const allowed = slot.accepted.split(",").map((s) => s.trim());
  const ext = "." + (file.name.toLowerCase().split(".").pop() || "");
  if (!allowed.includes(ext)) {
    toast.error(`僅接受 ${slot.acceptedLabel}`);
    return;
  }
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    toast.error(`檔案大小超過 ${MAX_SIZE_MB} MB`);
    return;
  }
  setPendingFiles((p) => ({ ...p, [key]: file }));
};
```

- [ ] **Step 3: Pass the per-slot `accepted` to the `<input>` and copy**

Find this `<input>` inside the drop-zone label:

```tsx
<input
  ref={inputRefs[slot.key]}
  type="file"
  accept={ACCEPTED}
  onChange={(e) =>
    validateAndSet(slot.key, e.target.files?.[0] || null)
  }
  className="sr-only"
/>
```

Replace with:

```tsx
<input
  ref={inputRefs[slot.key]}
  type="file"
  accept={slot.accepted}
  onChange={(e) =>
    validateAndSet(slot.key, e.target.files?.[0] || null)
  }
  className="sr-only"
/>
```

Find this copy line:

```tsx
<p className="text-xs text-gray-500 mt-1.5">
  支援 PDF · DOC · DOCX · 上限 {MAX_SIZE_MB} MB
</p>
```

Replace with:

```tsx
<p className="text-xs text-gray-500 mt-1.5">
  支援 {slot.acceptedLabel} · 上限 {MAX_SIZE_MB} MB
</p>
```

- [ ] **Step 4: Manually verify in the dev environment**

Start dev env if not already running:
```bash
docker compose -f docker-compose.dev.yml up -d
```

Open the admin System Docs page in a browser:
- Log in as `admin@nycu.edu.tw` (password `admin123` in dev).
- Navigate to System Settings → System Docs.

Verify:
- The 獎學金要點 slot's drop-zone hint reads "支援 PDF · 上限 10 MB".
- The 申請文件範例檔 slot's drop-zone hint reads "支援 PDF · DOC · DOCX · 上限 10 MB".
- Try selecting a `.docx` file for the 獎學金要點 slot → toast shows "僅接受 PDF".
- The `<input>` element on the 獎學金要點 slot has `accept=".pdf"` (DevTools).

- [ ] **Step 5: Type-check**

```bash
docker compose -f docker-compose.dev.yml exec frontend npm run type-check
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/admin/system-docs/SystemDocsPanel.tsx
git commit -m "feat(frontend): restrict 獎學金要點 admin upload to PDF only"
```

---

### Task 5: Backend — reject non-PDF for `regulations_url` upload (failing test first)

**Files:**
- Create: `backend/app/tests/test_system_settings_upload_doc.py`
- Modify: `backend/app/api/v1/endpoints/system_settings.py`

- [ ] **Step 1: Write failing pytest cases**

Create `backend/app/tests/test_system_settings_upload_doc.py`:

```python
"""
Tests for admin upload validation in
backend/app/api/v1/endpoints/system_settings.py::upload_system_doc.

Pins the policy that regulations_url accepts ONLY .pdf
(rejects .docx, rejects mismatched MIME), while sample_document_url
continues to accept .pdf / .doc / .docx.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole


@pytest.fixture
async def admin_user(db: AsyncSession) -> User:
    admin = User(
        email="docupload_admin@university.edu",
        username="docupload_admin",
        full_name="Doc Upload Admin",
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


@pytest.fixture
def fake_minio():
    """Patch minio_service so the test never touches MinIO."""
    with patch(
        "app.services.minio_service.minio_service"
    ) as mock_service:
        mock_service.default_bucket = "test-bucket"
        mock_service.client = MagicMock()
        mock_service.client.put_object = MagicMock()
        mock_service.client.remove_object = MagicMock()
        yield mock_service


async def _post_upload(
    client: AsyncClient,
    admin: User,
    doc_key: str,
    filename: str,
    content_type: str,
    body: bytes = b"%PDF-1.4 minimal",
):
    files = {"file": (filename, BytesIO(body), content_type)}
    # NOTE: how the test client authenticates as `admin` depends on this
    # repo's existing conftest. Most tests in app/tests use a
    # `authenticated_client(admin)` helper or set a header — match whichever
    # the existing endpoint tests use (e.g. test_scholarship_configuration_endpoints.py).
    return await client.post(
        f"/api/v1/system-settings/upload/{doc_key}",
        files=files,
        headers={"X-Test-User-Id": str(admin.id)},
    )


class TestRegulationsUploadValidation:
    async def test_rejects_docx_for_regulations_url(
        self, client: AsyncClient, admin_user: User, fake_minio
    ):
        res = await _post_upload(
            client,
            admin_user,
            "regulations_url",
            filename="rules.docx",
            content_type=(
                "application/vnd.openxmlformats-"
                "officedocument.wordprocessingml.document"
            ),
        )
        assert res.status_code == 400
        assert "PDF" in res.text
        fake_minio.client.put_object.assert_not_called()

    async def test_rejects_pdf_extension_with_mismatched_mime(
        self, client: AsyncClient, admin_user: User, fake_minio
    ):
        res = await _post_upload(
            client,
            admin_user,
            "regulations_url",
            filename="rules.pdf",
            content_type="application/octet-stream",
        )
        assert res.status_code == 400
        fake_minio.client.put_object.assert_not_called()

    async def test_accepts_pdf_with_pdf_mime(
        self, client: AsyncClient, admin_user: User, fake_minio
    ):
        res = await _post_upload(
            client,
            admin_user,
            "regulations_url",
            filename="rules.pdf",
            content_type="application/pdf",
        )
        assert res.status_code == 200
        fake_minio.client.put_object.assert_called_once()


class TestSampleDocumentUploadStillAcceptsDocx:
    async def test_accepts_docx_for_sample_document_url(
        self, client: AsyncClient, admin_user: User, fake_minio
    ):
        res = await _post_upload(
            client,
            admin_user,
            "sample_document_url",
            filename="sample.docx",
            content_type=(
                "application/vnd.openxmlformats-"
                "officedocument.wordprocessingml.document"
            ),
        )
        assert res.status_code == 200
        fake_minio.client.put_object.assert_called_once()
```

NOTE: the `X-Test-User-Id`/auth header in `_post_upload` is a placeholder. Before running the test, open `backend/app/tests/test_scholarship_configuration_endpoints.py` and copy the exact pattern used there for issuing authenticated admin requests (likely a fixture-based `authenticated_admin_client` or a token-injection helper) — replace the header in `_post_upload` accordingly. If a more idiomatic helper already exists in the repo's `app/tests/conftest.py`, prefer that.

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_system_settings_upload_doc.py -v
```

Expected:
- `test_rejects_docx_for_regulations_url`: FAIL (currently returns 200 because backend accepts .docx for both slots)
- `test_rejects_pdf_extension_with_mismatched_mime`: FAIL (same reason — no MIME check)
- `test_accepts_pdf_with_pdf_mime`: PASS (already accepted today)
- `test_accepts_docx_for_sample_document_url`: PASS (already accepted today)

- [ ] **Step 3: Add the PDF-only guard to `upload_system_doc`**

Open `backend/app/api/v1/endpoints/system_settings.py`. Find the `upload_system_doc` function. Right after this block:

```python
if doc_key not in _ALLOWED_DOC_KEYS:
    raise HTTPException(status_code=400, detail=f"Invalid doc_key. Allowed: {_ALLOWED_DOC_KEYS}")

allowed_extensions = [".pdf", ".doc", ".docx"]
```

Replace `allowed_extensions = [".pdf", ".doc", ".docx"]` with:

```python
# regulations_url is gated on the student-facing side by an inline PDF
# viewer (react-pdf), which can only render PDF. We enforce PDF-only on
# both the extension AND the request's Content-Type to prevent uploaders
# from disguising a non-PDF as application/pdf or vice versa.
if doc_key == "regulations_url":
    allowed_extensions = [".pdf"]
    if (file.content_type or "").lower() != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="獎學金要點僅接受 PDF 檔案",
        )
else:
    allowed_extensions = [".pdf", ".doc", ".docx"]
```

Make sure the rest of the function (the existing `validate_upload_file(...)` call, MinIO upload, upsert, return) is unchanged.

- [ ] **Step 4: Re-run the failing tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_system_settings_upload_doc.py -v
```

Expected: ALL PASS.

If `test_rejects_docx_for_regulations_url` returns 400 but the detail message doesn't contain "PDF" exactly, the assertion `assert "PDF" in res.text` should still pass because the message is "獎學金要點僅接受 PDF 檔案". If it doesn't, the response body may be JSON-wrapped — adjust to `assert "PDF" in res.json().get("detail", "")`.

- [ ] **Step 5: Run the broader backend test suite to confirm no regressions**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/ -x -q --ignore=app/tests/test_pre_commit_schema_check_analyzer.py
```

Expected: PASS (no new failures attributable to this change).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/endpoints/system_settings.py backend/app/tests/test_system_settings_upload_doc.py
git commit -m "feat(backend): enforce PDF-only upload for regulations_url"
```

---

### Task 6: Manual end-to-end smoke test in dev env

**Files:**
- (no code changes; verification only)

- [ ] **Step 1: Ensure clean dev env**

```bash
docker compose -f docker-compose.dev.yml up -d
docker compose -f docker-compose.dev.yml logs -f backend frontend
# In another terminal, continue with verification.
```

- [ ] **Step 2: Smoke A — fresh upload, short PDF auto-latches on mount**

1. Log in as `admin@nycu.edu.tw` (password `admin123`).
2. Open System Settings → System Docs.
3. If a 獎學金要點 file already exists, click 替換. Upload a 1-page PDF (any short academic regulations PDF; create one from a Word doc if needed via `Print → Save as PDF`).
4. Log out, log in as a student (e.g. `stuphd001` per the project's seeded users).
5. Start a scholarship application. On the first wizard step (`NoticeAgreementStep`):
   - The 8 hardcoded items render as a non-scrollable summary.
   - The 申請文件範例檔 button is visible (disabled if no sample uploaded yet).
   - The inline PDF viewer renders the regulations.
   - The "已詳閱獎學金要點" checkbox is **already checked** (because the 1-page PDF fits without overflow).
   - The agree checkbox is enabled.
6. Tick agree → Continue → wizard advances to the next step.

- [ ] **Step 3: Smoke B — long PDF requires scroll**

1. As admin, replace the regulations file with a 5+ page PDF.
2. As a student, reload the agreement step.
3. Verify:
   - The "已詳閱獎學金要點" checkbox is **unchecked**.
   - The agree checkbox is **disabled**.
   - The amber hint "請將下方獎學金要點滑到底端…" is visible.
4. Scroll inside the PDF viewer to the bottom.
5. Verify the read-notice checkbox ticks, the agree checkbox enables, and the hint disappears.

- [ ] **Step 4: Smoke C — admin cannot upload .docx for regulations**

1. As admin, in System Docs, try to drag/drop or select a `.docx` file into the 獎學金要點 slot.
2. Verify a toast appears: "僅接受 PDF".
3. Confirm `<input type="file">` on this slot has `accept=".pdf"` only (DevTools).

- [ ] **Step 5: Smoke D — no regulations uploaded → student is blocked**

1. As admin, clear the `regulations_url` row. Easiest path is to truncate via psql:
   ```bash
   docker compose -f docker-compose.dev.yml exec postgres psql -U scholarship_user -d scholarship -c \
     "DELETE FROM system_settings WHERE key IN ('regulations_url', 'regulations_url_filename');"
   ```
2. Also clear the MinIO object (or leave it — the DB row is what controls the UI).
3. As a student, reload the agreement step.
4. Verify:
   - No PDF viewer is rendered.
   - The amber alert "系統管理員尚未上傳獎學金要點，目前無法進行申請。請聯絡承辦單位。" is visible.
   - The agree checkbox stays disabled regardless of any interaction.
5. Re-upload a PDF as admin → reload → student can apply again.

- [ ] **Step 6: Capture screenshots for the PR**

For each scenario A–D, capture a screenshot using the bundled Playwright CLI (per the project's `playwright-test-and-debug` skill) or simply browser DevTools, and stash them under a temporary path you'll attach to the PR. Suggested filenames:
- `agree-step-shortpdf-autolatch.png`
- `agree-step-longpdf-must-scroll.png`
- `admin-rejects-docx.png`
- `agree-step-no-regulations-blocked.png`

- [ ] **Step 7: Re-seed the system after testing**

Re-upload a sensible default regulations PDF as admin so the dev environment is not left in a broken state for future testers.

---

### Task 7: Final review pass and PR

**Files:**
- (no code changes; quality gate)

- [ ] **Step 1: Run the full frontend test suite**

```bash
docker compose -f docker-compose.dev.yml exec frontend npm run test -- --watchAll=false
```

Expected: PASS. Pay attention to any pre-existing tests that touch `NoticeAgreementStep` or `SystemDocsPanel` — if any break because they assumed the old 8-item scroll container or the global `ACCEPTED` constant, update them to match the new behavior. Show the updated assertions in the diff (do not silently delete coverage).

- [ ] **Step 2: Run the full backend test suite**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/ -x -q
```

Expected: PASS.

- [ ] **Step 3: Regenerate OpenAPI types if any backend schema changed**

In this plan, the only backend change is server-side validation logic inside the existing `upload_system_doc` endpoint. No schema or path changes. Skip the `api:generate` step unless `git diff backend/app/api/v1/openapi.json` (or the live OpenAPI doc) shows differences. If it does:

```bash
docker compose -f docker-compose.dev.yml up -d backend
cd frontend && npm run api:generate && git add lib/api/generated/schema.d.ts
```

- [ ] **Step 4: Check for orphaned references to removed behavior**

```bash
grep -rn "ArrowDown" frontend/components/student-wizard/steps/NoticeAgreementStep.tsx || echo "ok: ArrowDown import removed"
grep -rn "noticeScrollRef" frontend/ || echo "ok: noticeScrollRef removed"
grep -rn "handleNoticeScroll" frontend/ || echo "ok: handleNoticeScroll removed"
grep -rn "handleOpenDoc" frontend/components/student-wizard/steps/NoticeAgreementStep.tsx || echo "ok: handleOpenDoc (regulations dialog opener) removed"
grep -rn "const ACCEPTED" frontend/components/admin/system-docs/SystemDocsPanel.tsx || echo "ok: global ACCEPTED removed"
```

Each line should print "ok: …". If a grep finds something, it's leftover from the rewrite — delete it.

- [ ] **Step 5: Commit any cleanups and open the PR**

If you made follow-up cleanups:
```bash
git add -A
git commit -m "chore: drop leftover refs from regulations scroll-gate refactor"
```

Then open the PR:
```bash
git push -u origin <your-branch>
gh pr create --title "feat: gate scholarship application agreement on regulations PDF scroll" --body "$(cat <<'EOF'
## Summary
- Replace the hardcoded 8-item scroll-gate in `NoticeAgreementStep` with an inline `react-pdf` viewer over the admin-uploaded 獎學金要點 PDF.
- Tighten the 獎學金要點 admin upload (client + server) to PDF only.
- Block the agreement step if no PDF is uploaded.
- Keep the 8 notice items as a static summary; the 申請文件範例檔 button still opens the existing `FilePreviewDialog`.

## Test plan
- [x] `frontend/components/__tests__/inline-pdf-viewer.test.tsx` (4 cases)
- [x] `frontend/components/__tests__/notice-agreement-step.test.tsx` (3 cases)
- [x] `backend/app/tests/test_system_settings_upload_doc.py` (4 cases)
- [x] Manual smoke A–D (see plan), screenshots attached
- [x] Full Jest + pytest suites pass

## Design
See `docs/superpowers/specs/2026-05-21-scholarship-regulations-scroll-gate-design.md`.
EOF
)"
```

---

## Self-Review

**Spec coverage:**
- "Inline `react-pdf` viewer in wizard step" → Task 2 (component), Task 3 (integration). ✓
- "8 hardcoded notice items remain as a static summary" → Task 3 Step 3 (8-item block rendered statically). ✓
- "申請文件範例檔 stays as dialog opener" → Task 3 Step 3 (`handleOpenSampleDoc` retained). ✓
- "Restrict admin upload of regulations to PDF" → Task 4 (client), Task 5 (server). ✓
- "Server-side MIME + extension check" → Task 5 Step 3 enforces both. ✓
- "Block step entirely when no PDF uploaded" → Task 3 Step 3 (`regulationsViewerUrl === null` branch), Task 6 Smoke D. ✓
- "Error state with reload button" → Task 2 Step 3 (`loadError` branch with 重新載入). ✓
- "Auto-latch when content fits without scrolling" → Task 2 Step 3 (`requestAnimationFrame` check in `handleLoadSuccess`). ✓
- "Locale copy updates" → Task 3 Step 3 (zh/en in `notices`). ✓
- "Bundle size / worker setup" → Task 1 covers worker config; bundle is observed as side effect, no enforced budget step (spec flagged this as "worth confirming" not "must enforce"). ✓
- "Pre-existing DOC/DOCX in `regulations_url`" → handled via the same load-error path in Task 2 Step 3; admin must re-upload. ✓ (Plan does not auto-migrate; matches the spec's "no backward compatibility" stance.)

**Placeholder scan:**
- The pytest auth header `X-Test-User-Id` is flagged as a placeholder with explicit instructions to align with the existing repo pattern. This is acceptable per the plan's intent (the test harness pattern varies between repos and the executor is told exactly where to look — `test_scholarship_configuration_endpoints.py` and `app/tests/conftest.py`). No other placeholders.

**Type consistency:**
- `InlinePdfViewerProps`: `url`, `height`, `onReachedBottom`, `onLoadError`, `locale` are consistent between Task 2 (definition) and Task 3 (consumer).
- `regulationsViewerUrl` in Task 3 produces `string | null`, matching the `string` typing of `InlinePdfViewer.url` via the `regulationsViewerUrl ? <InlinePdfViewer url={regulationsViewerUrl} /> : <Alert />` ternary.
- `DocSlot.accepted` / `acceptedLabel` are introduced in Task 4 and used consistently across the `<input>`, `validateAndSet`, and copy line.
- Backend endpoint path `/api/v1/system-settings/upload/{doc_key}` used in Task 5 tests matches the existing route definition.

No issues found that require fixing inline.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-21-scholarship-regulations-scroll-gate.md`. Two execution options:

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach?

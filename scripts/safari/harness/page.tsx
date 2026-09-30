"use client";

// CI-only harness (copied into frontend/app/safari-harness/ by
// .github/workflows/safari-pdf-preview.yml, never shipped): mounts the REAL
// FilePreviewDialog for the two ways a PDF reaches it — a just-picked local
// file (a blob: URL) and a saved file (a same-origin proxy URL) — plus a bare
// blob: iframe as a control (#1434).

import { useState } from "react";
import { FilePreviewDialog } from "@/components/file-preview-dialog";

type Mode = "control" | "local" | "remote";

// The route handler the workflow adds under /api/v1/preview/, so the response
// is framable exactly like the real proxy.
const REMOTE_URL = "/api/v1/preview/sample";

export default function SafariHarness() {
  const [mode, setMode] = useState<Mode | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  const open = async (next: Mode) => {
    if (next !== "remote") {
      // Same shape as FileUpload: a fresh File and its blob: URL.
      const blob = await (await fetch("/sample.pdf")).blob();
      const file = new File([blob], "local.pdf", { type: "application/pdf" });
      setBlobUrl(URL.createObjectURL(file));
    }
    setMode(next);
  };
  const close = () => setMode(null);

  const previewFile =
    mode === "local" && blobUrl
      ? { url: blobUrl, filename: "local.pdf", type: "application/pdf" }
      : mode === "remote"
        ? { url: REMOTE_URL, filename: "remote.pdf", type: "application/pdf" }
        : null;

  return (
    <main style={{ padding: 16 }}>
      <button id="open-control" onClick={() => open("control")}>
        open control{" "}
      </button>
      <button id="open-local" onClick={() => open("local")}>
        open local{" "}
      </button>
      <button id="open-remote" onClick={() => open("remote")}>
        open remote
      </button>
      {mode === "control" && blobUrl && (
        <iframe
          data-variant="control"
          src={blobUrl}
          title="control"
          style={{ width: 800, height: 420, display: "block", marginTop: 16 }}
        />
      )}
      <FilePreviewDialog
        isOpen={mode === "local" || mode === "remote"}
        onClose={close}
        file={previewFile}
        locale="zh"
      />
    </main>
  );
}

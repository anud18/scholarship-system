"use client";

// CI-only harness (copied into frontend/app/safari-harness/ by
// .github/workflows/safari-pdf-preview.yml, never shipped): mounts the REAL
// FilePreviewDialog, so real Safari exercises the same Radix Dialog + iframe
// + skeleton code path as the student wizard (issue #1434).

import { useState } from "react";
import { FilePreviewDialog } from "@/components/file-preview-dialog";

type PreviewFile = { url: string; filename: string; type: string };

export default function SafariHarness() {
  const [file, setFile] = useState<PreviewFile | null>(null);
  const [isOpen, setIsOpen] = useState(false);

  const openLocal = async () => {
    // Same shape as FileUpload: a freshly created blob: URL for a picked file.
    const blob = await (await fetch("/sample.pdf")).blob();
    const pdf = new File([blob], "local.pdf", { type: "application/pdf" });
    setFile({
      url: URL.createObjectURL(pdf),
      filename: "local.pdf",
      type: "application/pdf",
    });
    setIsOpen(true);
  };

  const openRemote = () => {
    // Same shape as a saved draft: a same-origin proxy URL the dialog fetches.
    setFile({ url: "/sample.pdf", filename: "remote.pdf", type: "application/pdf" });
    setIsOpen(true);
  };

  return (
    <main style={{ padding: 16 }}>
      <button id="open-local" onClick={openLocal}>
        open local
      </button>{" "}
      <button id="open-remote" onClick={openRemote}>
        open remote
      </button>
      <FilePreviewDialog
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        file={file}
        locale="zh"
      />
    </main>
  );
}

"use client";

// CI-only harness (copied into frontend/app/safari-harness/ by
// .github/workflows/safari-pdf-preview.yml, never shipped): mounts the REAL
// FilePreviewDialog plus single-ingredient variants of it, so real Safari can
// show which part of the dialog blanks a framed PDF (issue #1434).

import { useEffect, useState } from "react";
import { FilePreviewDialog } from "@/components/file-preview-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type Variant = "inline" | "plain" | "no-transform" | "opacity" | "swap" | "real";

// Radix centres DialogContent with translate(-50%, -50%) and animates it with
// zoom/slide transforms; this centres the same box with margins instead.
const NO_TRANSFORM_STYLE = {
  transform: "none",
  animation: "none",
  left: "50%",
  marginLeft: "-448px",
  top: "5vh",
} as const;

function RawDialog({
  variant,
  url,
  onClose,
}: {
  variant: Variant;
  url: string;
  onClose: () => void;
}) {
  const [src, setSrc] = useState(variant === "swap" ? "about:blank" : url);
  const [isVisible, setIsVisible] = useState(variant !== "opacity");

  useEffect(() => {
    if (variant === "swap") setSrc(url);
    if (variant !== "opacity") return;
    const timer = setTimeout(() => setIsVisible(true), 800);
    return () => clearTimeout(timer);
  }, [variant, url]);

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent
        className="max-w-4xl max-h-[90vh] overflow-hidden"
        style={variant === "no-transform" ? NO_TRANSFORM_STYLE : undefined}
      >
        <DialogHeader>
          <DialogTitle>{variant}</DialogTitle>
          <DialogDescription>variant</DialogDescription>
        </DialogHeader>
        <div className="flex-1 overflow-hidden relative">
          <iframe
            data-variant={variant}
            src={src}
            title={variant}
            className={`w-full h-[70vh] border rounded transition-opacity duration-300 ${
              isVisible ? "opacity-100" : "opacity-0"
            }`}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function SafariHarness() {
  const [active, setActive] = useState<Variant | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  const open = async (variant: Variant) => {
    // Same shape as FileUpload: a fresh blob: URL for a just-picked file.
    const blob = await (await fetch("/sample.pdf")).blob();
    const pdf = new File([blob], "local.pdf", { type: "application/pdf" });
    setBlobUrl(URL.createObjectURL(pdf));
    setActive(variant);
  };
  const close = () => setActive(null);

  const variants: Variant[] = ["inline", "plain", "no-transform", "opacity", "swap", "real"];

  return (
    <main style={{ padding: 16 }}>
      {variants.map(variant => (
        <button key={variant} id={`open-${variant}`} onClick={() => open(variant)}>
          open {variant}{" "}
        </button>
      ))}
      {active === "inline" && blobUrl && (
        <iframe
          data-variant="inline"
          src={blobUrl}
          title="inline"
          style={{ width: 800, height: 420, display: "block", marginTop: 16 }}
        />
      )}
      {active && active !== "inline" && active !== "real" && blobUrl && (
        <RawDialog key={blobUrl} variant={active} url={blobUrl} onClose={close} />
      )}
      <FilePreviewDialog
        isOpen={active === "real"}
        onClose={close}
        file={
          blobUrl
            ? { url: blobUrl, filename: "local.pdf", type: "application/pdf" }
            : null
        }
        locale="zh"
      />
    </main>
  );
}

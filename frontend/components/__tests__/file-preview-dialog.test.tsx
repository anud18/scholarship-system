/**
 * Regression test for the PDF-preview "stuck loading" bug.
 *
 * `FilePreviewDialog` renders PDFs in an <iframe> and hides it behind a
 * skeleton until `isLoading` clears. `isLoading` was only ever cleared by the
 * iframe's onLoad/onError — but Chrome's built-in PDF viewer frequently never
 * fires the iframe load event, so a PDF preview stayed on a permanent skeleton
 * (opacity-0 iframe) even though the proxy returned the file. The fix adds a
 * fallback timer; this test pins that the iframe becomes visible after it
 * elapses WITHOUT any onLoad firing.
 */
import React from "react";
import { render, screen, act } from "@testing-library/react";
import { FilePreviewDialog } from "../file-preview-dialog";

describe("FilePreviewDialog PDF loading fallback", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
  });

  const pdfFile = {
    url: "/api/v1/preview?fileId=16&type=pdf&applicationId=87&token=t",
    filename: "test-preview.pdf",
    type: "application/pdf",
  };

  it("clears the loading skeleton via the fallback timer even if the iframe onLoad never fires", () => {
    render(
      <FilePreviewDialog isOpen onClose={() => {}} file={pdfFile} locale="zh-TW" />
    );

    // The iframe exists but starts hidden (opacity-0) behind the skeleton —
    // and we deliberately never dispatch its onLoad event.
    const iframe = screen.getByTitle("test-preview.pdf") as HTMLIFrameElement;
    expect(iframe.className).toContain("opacity-0");

    // Fallback timer (1500ms) elapses → loading clears → iframe is revealed.
    act(() => {
      jest.advanceTimersByTime(1600);
    });

    expect(iframe.className).toContain("opacity-100");
    expect(iframe.getAttribute("src")).toContain("/api/v1/preview");
  });
});

/**
 * FilePreviewDialog loading behaviour.
 *
 * - A remote file is probed with fetch() so HTTP errors (401 expired token, 404
 *   deleted file) surface as a visible message instead of a blank pane.
 * - A remote PDF is then framed by its own same-origin proxy URL — NEVER by a
 *   blob: URL: Safari applies the page's inherited `frame-ancestors 'none'` to
 *   a blob: frame and paints it blank (#1434).
 * - A just-picked local PDF (blob: URL) cannot be fetched (CSP connect-src) or
 *   framed, so it is drawn by pdf.js from the File itself.
 * - Chrome's PDF viewer never firing the iframe load event still cannot leave
 *   the skeleton covering an opacity-0 iframe forever (fallback timer).
 */
import React from "react";
import { render, screen, act, waitFor } from "@testing-library/react";
import { FilePreviewDialog } from "../file-preview-dialog";

jest.mock("@/components/inline-pdf-viewer", () => ({
  InlinePdfViewer: (props: { url: string; blob?: Blob; hideActions?: boolean }) => (
    <div
      data-testid="inline-pdf-viewer"
      data-url={props.url}
      data-has-blob={String(props.blob instanceof Blob)}
      data-hide-actions={String(!!props.hideActions)}
    />
  ),
}));

const pdfFile = {
  url: "/api/v1/preview?fileId=16&type=pdf&applicationId=87&token=t",
  filename: "test-preview.pdf",
  type: "application/pdf",
};

function mockFetch(response: Partial<Response>) {
  const fetchMock = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
    body: { cancel: jest.fn().mockResolvedValue(undefined) },
    blob: async () => new Blob(["%PDF-1.4"], { type: "application/pdf" }),
    ...response,
  });
  global.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

describe("FilePreviewDialog", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    jest.useFakeTimers();
    URL.createObjectURL = jest.fn(() => "blob:mock-preview");
    URL.revokeObjectURL = jest.fn();
  });

  afterEach(() => {
    jest.runOnlyPendingTimers();
    jest.useRealTimers();
    global.fetch = originalFetch;
  });

  it("probes a remote PDF, then frames the proxy URL itself — not a blob: — and clears the skeleton via the fallback timer even if onLoad never fires", async () => {
    const fetchMock = mockFetch({});

    render(
      <FilePreviewDialog isOpen onClose={() => {}} file={pdfFile} locale="zh" />
    );

    expect(fetchMock).toHaveBeenCalledWith(pdfFile.url, {
      credentials: "same-origin",
    });

    const iframe = screen.getByTitle("test-preview.pdf") as HTMLIFrameElement;
    await waitFor(() => expect(iframe.getAttribute("src")).toBe(pdfFile.url));
    // A blob: frame renders blank in Safari (#1434): never wrap a PDF in one.
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    // We deliberately never fire the iframe's onLoad; only the fallback
    // timer can reveal it.
    act(() => {
      jest.advanceTimersByTime(1600);
    });

    expect(iframe.className).toContain("opacity-100");
    expect(iframe.getAttribute("data-source-url")).toBe(pdfFile.url);
  });

  it("shows an error message instead of a blank pane when the proxy answers with an HTTP error", async () => {
    mockFetch({ ok: false, status: 401 });

    render(
      <FilePreviewDialog isOpen onClose={() => {}} file={pdfFile} locale="zh" />
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("無法載入文件");
    expect(screen.queryByTitle("test-preview.pdf")).toBeNull();
  });

  it("renders a remote image from the fetched blob", async () => {
    mockFetch({});
    const imageFile = {
      url: "/api/v1/preview?fileId=17&type=image&token=t",
      filename: "passbook.png",
      type: "image",
    };

    render(
      <FilePreviewDialog
        isOpen
        onClose={() => {}}
        file={imageFile}
        locale="zh"
      />
    );

    const img = await screen.findByAltText("passbook.png");
    expect(img.getAttribute("src")).toBe("blob:mock-preview");
  });

  it("draws a just-picked local PDF with pdf.js from its Blob — no fetch (CSP connect-src has no blob:), no iframe, no revoke", async () => {
    const fetchMock = mockFetch({});
    const localFile = {
      url: "blob:http://localhost:3000/just-selected",
      filename: "just-selected.pdf",
      type: "application/pdf",
      blob: new Blob(["%PDF-1.4"], { type: "application/pdf" }),
    };

    const { unmount } = render(
      <FilePreviewDialog
        isOpen
        onClose={() => {}}
        file={localFile}
        locale="zh"
      />
    );

    const viewer = await screen.findByTestId("inline-pdf-viewer");
    expect(viewer.getAttribute("data-url")).toBe(localFile.url);
    expect(viewer.getAttribute("data-has-blob")).toBe("true");
    // The dialog's own footer already offers 下載 / 在新視窗開啟.
    expect(viewer.getAttribute("data-hide-actions")).toBe("true");
    expect(screen.queryByTitle("just-selected.pdf")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).toBeNull();

    // FileUpload owns the object URL and revokes it on ITS unmount.
    unmount();
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  });

  it("reports an error for a local PDF that arrives without its Blob rather than framing the blob: URL", async () => {
    const fetchMock = mockFetch({});

    render(
      <FilePreviewDialog
        isOpen
        onClose={() => {}}
        file={{
          url: "blob:http://localhost:3000/no-blob",
          filename: "no-blob.pdf",
          type: "application/pdf",
        }}
        locale="zh"
      />
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("無法載入文件");
    expect(screen.queryByTitle("no-blob.pdf")).toBeNull();
    expect(screen.queryByTestId("inline-pdf-viewer")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("renders a caller-owned blob: image URL directly — no fetch, no revoke", async () => {
    const fetchMock = mockFetch({});
    const localImage = {
      url: "blob:http://localhost:3000/just-selected-image",
      filename: "just-selected.png",
      type: "image",
    };

    const { unmount } = render(
      <FilePreviewDialog
        isOpen
        onClose={() => {}}
        file={localImage}
        locale="zh"
      />
    );

    const img = await screen.findByAltText("just-selected.png");
    expect(img.getAttribute("src")).toBe(localImage.url);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(URL.createObjectURL).not.toHaveBeenCalled();

    unmount();
    expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  });

  it("opens the source URL in a new window with noopener", () => {
    mockFetch({});
    const openSpy = jest.spyOn(window, "open").mockImplementation(() => null);

    render(
      <FilePreviewDialog isOpen onClose={() => {}} file={pdfFile} locale="zh" />
    );

    screen.getAllByRole("button", { name: /在新視窗開啟/ })[0].click();

    expect(openSpy).toHaveBeenCalledWith(
      pdfFile.url,
      "_blank",
      "noopener,noreferrer"
    );
    openSpy.mockRestore();
  });
});

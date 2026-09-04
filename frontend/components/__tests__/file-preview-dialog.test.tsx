/**
 * FilePreviewDialog loading behaviour.
 *
 * The dialog fetches the proxy URL itself and renders a blob: URL, so that
 * (a) HTTP errors (401 expired token, 404 deleted file) surface as a visible
 *     message instead of a blank pane, and
 * (b) Chrome's PDF viewer never firing the iframe load event still cannot
 *     leave the skeleton covering an opacity-0 iframe forever (fallback timer).
 */
import React from "react";
import { render, screen, act, waitFor } from "@testing-library/react";
import { FilePreviewDialog } from "../file-preview-dialog";

const pdfFile = {
  url: "/api/v1/preview?fileId=16&type=pdf&applicationId=87&token=t",
  filename: "test-preview.pdf",
  type: "application/pdf",
};

function mockFetch(response: Partial<Response>) {
  const fetchMock = jest.fn().mockResolvedValue({
    ok: true,
    status: 200,
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

  it("fetches the file, renders the blob, and clears the skeleton via the fallback timer even if onLoad never fires", async () => {
    const fetchMock = mockFetch({});

    render(
      <FilePreviewDialog isOpen onClose={() => {}} file={pdfFile} locale="zh" />
    );

    expect(fetchMock).toHaveBeenCalledWith(pdfFile.url, {
      credentials: "same-origin",
    });

    const iframe = screen.getByTitle("test-preview.pdf") as HTMLIFrameElement;
    await waitFor(() =>
      expect(iframe.getAttribute("src")).toBe("blob:mock-preview")
    );
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

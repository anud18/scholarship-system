import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { NoticeAgreementStep } from "../student-wizard/steps/NoticeAgreementStep";

jest.mock("../../lib/api", () => {
  const fn = jest.fn();
  return {
    __esModule: true,
    default: { systemSettings: { getPublicDocs: fn } },
    api: { systemSettings: { getPublicDocs: fn } },
  };
});

const mockGetPublicDocs = (
  jest.requireMock("../../lib/api") as { api: { systemSettings: { getPublicDocs: jest.Mock } } }
).api.systemSettings.getPublicDocs;

jest.mock("../inline-pdf-viewer", () => ({
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

jest.mock("../file-preview-dialog", () => ({
  FilePreviewDialog: () => null,
}));

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
    mockGetPublicDocs.mockResolvedValue({
      success: true,
      data: {},
    });

    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={noop}
        onNext={noop}
        locale="zh"
      />,
    );

    await waitFor(() =>
      expect(
        screen.getByText(/系統管理員尚未上傳獎學金要點/),
      ).toBeInTheDocument(),
    );
    // Loud failure if the mock isn't wired — otherwise this test would pass
    // for the wrong reason (real fetch returns {data: []} from the setup
    // file's global mock, which also has no `regulations_url`).
    expect(mockGetPublicDocs).toHaveBeenCalled();
    expect(screen.queryByTestId("inline-pdf-viewer")).not.toBeInTheDocument();

    const agreeCheckbox = screen.getByRole("checkbox", {
      name: /同意遵守相關規定/,
    });
    expect(agreeCheckbox).toBeDisabled();
  });

  it("opens regulations in a dialog and enables agree after scroll-to-bottom", async () => {
    mockGetPublicDocs.mockResolvedValue({
      success: true,
      data: {
        regulations_url: "system-docs/regulations_url_20260520_120000.pdf",
        regulations_url_filename: "獎學金要點.pdf",
      },
    });

    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={noop}
        onNext={noop}
        locale="zh"
      />,
    );

    // Trigger button should appear once docs are loaded.
    const openBtn = await screen.findByRole("button", {
      name: /閱讀獎學金要點/,
    });
    expect(mockGetPublicDocs).toHaveBeenCalled();

    // Viewer not mounted before button click (dialog closed).
    expect(screen.queryByTestId("inline-pdf-viewer")).not.toBeInTheDocument();

    const agreeCheckbox = screen.getByRole("checkbox", {
      name: /同意遵守相關規定/,
    });
    expect(agreeCheckbox).toBeDisabled();

    // Open dialog → viewer mounts inside.
    fireEvent.click(openBtn);
    const viewer = await screen.findByTestId("inline-pdf-viewer");
    expect(viewer.getAttribute("data-url")).toMatch(
      /\/api\/v1\/system-settings\/file-proxy\?key=regulations_url/,
    );

    // Simulate scroll-to-bottom inside the dialog viewer.
    fireEvent.click(screen.getByTestId("simulate-reached-bottom"));

    // Agree checkbox unlocks (latched state survives dialog close).
    await waitFor(() => expect(agreeCheckbox).not.toBeDisabled());
  });

  it("latched state survives dialog close + reopen", async () => {
    mockGetPublicDocs.mockResolvedValue({
      success: true,
      data: { regulations_url: "system-docs/x.pdf" },
    });

    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={noop}
        onNext={noop}
        locale="zh"
      />,
    );

    const openBtn = await screen.findByRole("button", {
      name: /閱讀獎學金要點/,
    });
    const agreeCheckbox = screen.getByRole("checkbox", {
      name: /同意遵守相關規定/,
    });

    // Open → scroll bottom → close dialog.
    fireEvent.click(openBtn);
    await screen.findByTestId("inline-pdf-viewer");
    fireEvent.click(screen.getByTestId("simulate-reached-bottom"));
    await waitFor(() => expect(agreeCheckbox).not.toBeDisabled());

    // Close via the dialog's close control (the small "關閉" button is
    // inside DialogContent's footer).
    fireEvent.click(screen.getByRole("button", { name: /^關閉$/ }));

    // Viewer unmounts (Radix removes DialogContent from DOM on close).
    await waitFor(() =>
      expect(screen.queryByTestId("inline-pdf-viewer")).not.toBeInTheDocument(),
    );

    // Agree must STILL be unlocked — the latch lives on the parent.
    expect(agreeCheckbox).not.toBeDisabled();

    // Reopening must not lock it back.
    fireEvent.click(openBtn);
    await screen.findByTestId("inline-pdf-viewer");
    expect(agreeCheckbox).not.toBeDisabled();
  });

  it("keeps the 8 hardcoded notice items visible as a static summary", async () => {
    mockGetPublicDocs.mockResolvedValue({
      success: true,
      data: { regulations_url: "system-docs/x.pdf" },
    });
    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={noop}
        onNext={noop}
        locale="zh"
      />,
    );

    await waitFor(() =>
      expect(screen.getByText("申請資格")).toBeInTheDocument(),
    );
    expect(mockGetPublicDocs).toHaveBeenCalled();
    expect(screen.getByText("申請期限")).toBeInTheDocument();
    expect(screen.getByText("獎金撥款")).toBeInTheDocument();
  });
});

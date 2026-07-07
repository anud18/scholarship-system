import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { NoticeAgreementStep } from "../student-wizard/steps/NoticeAgreementStep";

jest.mock("../../lib/api", () => {
  const getPublicDocs = jest.fn();
  const list = jest.fn();
  const noticesGet = jest.fn();
  return {
    __esModule: true,
    default: {
      systemSettings: {
        getPublicDocs,
        supplementaryDocs: { list },
        applicationNotices: { get: noticesGet },
      },
    },
    api: {
      systemSettings: {
        getPublicDocs,
        supplementaryDocs: { list },
        applicationNotices: { get: noticesGet },
      },
    },
  };
});

const apiMock = jest.requireMock("../../lib/api") as {
  api: {
    systemSettings: {
      getPublicDocs: jest.Mock;
      supplementaryDocs: { list: jest.Mock };
      applicationNotices: { get: jest.Mock };
    };
  };
};

const mockGetPublicDocs = apiMock.api.systemSettings.getPublicDocs;
const mockSuppList = apiMock.api.systemSettings.supplementaryDocs.list;
const mockNoticesGet = apiMock.api.systemSettings.applicationNotices.get;

const SAMPLE_NOTICES = {
  zh: {
    items: [
      { title: "申請資格", content: "申請資格說明內容" },
      { title: "申請期限", content: "申請期限說明內容" },
      { title: "獎金撥款", content: "獎金撥款說明內容" },
    ],
    important_notice: "請務必詳細閱讀各項獎學金要點與相關規定。",
  },
  en: {
    items: [
      { title: "Eligibility", content: "Eligibility details" },
      { title: "Deadline", content: "Deadline details" },
      { title: "Distribution", content: "Distribution details" },
    ],
    important_notice: "Please read the regulations carefully.",
  },
};

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
    mockSuppList.mockResolvedValue({ success: true, message: "OK", data: [] });
    mockNoticesGet.mockResolvedValue({
      success: true,
      message: "OK",
      data: SAMPLE_NOTICES,
    });
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
      /\/api\/v1\/preview\/system-docs\?key=regulations_url/,
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

  it("renders the admin-managed notice items fetched from the API", async () => {
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
    expect(mockNoticesGet).toHaveBeenCalled();
    expect(screen.getByText("申請期限")).toBeInTheDocument();
    expect(screen.getByText("獎金撥款")).toBeInTheDocument();
    expect(screen.getByText("申請資格說明內容")).toBeInTheDocument();
    expect(
      screen.getByText(/請務必詳細閱讀各項獎學金要點/),
    ).toBeInTheDocument();
  });

  it("shows an error message (not stale content) when notices fail to load", async () => {
    mockGetPublicDocs.mockResolvedValue({
      success: true,
      data: { regulations_url: "system-docs/x.pdf" },
    });
    mockNoticesGet.mockRejectedValue(new Error("network down"));

    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={noop}
        onNext={noop}
        locale="zh"
      />,
    );

    await waitFor(() =>
      expect(screen.getByText(/無法載入注意事項/)).toBeInTheDocument(),
    );
    expect(screen.queryByText("申請資格")).not.toBeInTheDocument();
  });
});

describe("NoticeAgreementStep — 參考文件 list", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSuppList.mockResolvedValue({ success: true, message: "OK", data: [] });
    mockNoticesGet.mockResolvedValue({
      success: true,
      message: "OK",
      data: SAMPLE_NOTICES,
    });
    Object.defineProperty(window, "localStorage", {
      value: { getItem: jest.fn(() => "test-token") },
      configurable: true,
    });
  });

  it("hides the 參考文件 section when sample doc and supp docs are both empty", async () => {
    mockGetPublicDocs.mockResolvedValue({
      success: true,
      message: "OK",
      data: { regulations_url: "system-docs/x.pdf" },
    });
    mockSuppList.mockResolvedValue({ success: true, message: "OK", data: [] });

    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={() => {}}
        onNext={() => {}}
        locale="zh"
      />
    );

    await waitFor(() => expect(mockGetPublicDocs).toHaveBeenCalled());
    expect(screen.queryByText("參考文件")).not.toBeInTheDocument();
  });

  it("shows supplementary docs alongside the fixed sample doc row", async () => {
    mockGetPublicDocs.mockResolvedValue({
      success: true,
      message: "OK",
      data: {
        regulations_url: "system-docs/r.pdf",
        sample_document_url: "system-docs/s.pdf",
        sample_document_url_filename: "sample.pdf",
      },
    });
    mockSuppList.mockResolvedValue({
      success: true,
      message: "OK",
      data: [
        {
          id: 1,
          title: "FAQ",
          object_name: "system-docs/supp_a.pdf",
          original_filename: "faq.pdf",
          content_type: "application/pdf",
          file_size: 10,
          sort_order: 0,
          created_at: "2026-05-27T00:00:00Z",
          updated_at: "2026-05-27T00:00:00Z",
        },
      ],
    });

    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={() => {}}
        onNext={() => {}}
        locale="zh"
      />
    );

    expect(await screen.findByText("參考文件")).toBeInTheDocument();
    expect(screen.getByText("申請文件範例檔")).toBeInTheDocument();
    expect(screen.getByText("FAQ")).toBeInTheDocument();
  });

  it("renders only supplementary docs when sample doc is missing", async () => {
    mockGetPublicDocs.mockResolvedValue({
      success: true,
      message: "OK",
      data: { regulations_url: "system-docs/r.pdf" },
    });
    mockSuppList.mockResolvedValue({
      success: true,
      message: "OK",
      data: [
        {
          id: 9,
          title: "範本",
          object_name: "system-docs/supp_x.pdf",
          original_filename: "x.pdf",
          content_type: "application/pdf",
          file_size: 1,
          sort_order: 0,
          created_at: "2026-05-27T00:00:00Z",
          updated_at: "2026-05-27T00:00:00Z",
        },
      ],
    });

    render(
      <NoticeAgreementStep
        agreedToTerms={false}
        onAgree={() => {}}
        onNext={() => {}}
        locale="zh"
      />
    );

    expect(await screen.findByText("參考文件")).toBeInTheDocument();
    expect(screen.queryByText("申請文件範例檔")).not.toBeInTheDocument();
    expect(screen.getByText("範本")).toBeInTheDocument();
  });
});

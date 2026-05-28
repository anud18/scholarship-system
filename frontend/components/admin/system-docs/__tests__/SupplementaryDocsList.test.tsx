import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SupplementaryDocsList } from "../SupplementaryDocsList";

jest.mock("../../../../lib/api", () => {
  const list = jest.fn();
  const upload = jest.fn();
  const updateTitle = jest.fn();
  const del = jest.fn();
  const reorder = jest.fn();
  return {
    __esModule: true,
    default: {
      systemSettings: {
        supplementaryDocs: {
          list,
          upload,
          updateTitle,
          delete: del,
          reorder,
        },
      },
    },
  };
});

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

const apiMock = jest.requireMock("../../../../lib/api") as {
  default: {
    systemSettings: {
      supplementaryDocs: {
        list: jest.Mock;
        upload: jest.Mock;
        updateTitle: jest.Mock;
        delete: jest.Mock;
        reorder: jest.Mock;
      };
    };
  };
};

const fakeDocs = [
  {
    id: 1,
    title: "FAQ",
    object_name: "system-docs/supp_a.pdf",
    original_filename: "faq.pdf",
    content_type: "application/pdf",
    file_size: 100,
    sort_order: 0,
    created_at: "2026-05-27T00:00:00Z",
    updated_at: "2026-05-27T00:00:00Z",
  },
  {
    id: 2,
    title: "範本",
    object_name: "system-docs/supp_b.pdf",
    original_filename: "sample.pdf",
    content_type: "application/pdf",
    file_size: 200,
    sort_order: 1,
    created_at: "2026-05-27T00:00:00Z",
    updated_at: "2026-05-27T00:00:00Z",
  },
];

beforeEach(() => {
  Object.values(apiMock.default.systemSettings.supplementaryDocs).forEach((fn) =>
    fn.mockReset()
  );
});

describe("SupplementaryDocsList", () => {
  it("renders rows from API", async () => {
    apiMock.default.systemSettings.supplementaryDocs.list.mockResolvedValue({
      success: true,
      message: "OK",
      data: fakeDocs,
    });

    render(<SupplementaryDocsList />);

    expect(await screen.findByText("FAQ")).toBeInTheDocument();
    expect(screen.getByText("範本")).toBeInTheDocument();
  });

  it("shows empty state when list is empty", async () => {
    apiMock.default.systemSettings.supplementaryDocs.list.mockResolvedValue({
      success: true,
      message: "OK",
      data: [],
    });

    render(<SupplementaryDocsList />);

    expect(
      await screen.findByText(/目前尚無補充參考文件/)
    ).toBeInTheDocument();
  });

  it("calls delete API after confirm", async () => {
    apiMock.default.systemSettings.supplementaryDocs.list.mockResolvedValue({
      success: true,
      message: "OK",
      data: fakeDocs,
    });
    apiMock.default.systemSettings.supplementaryDocs.delete.mockResolvedValue({
      success: true,
      message: "OK",
      data: { deleted: true },
    });

    render(<SupplementaryDocsList />);

    await screen.findByText("FAQ");
    const deleteBtns = screen.getAllByRole("button", { name: "刪除" });
    fireEvent.click(deleteBtns[0]);

    const confirmBtn = await screen.findByRole("button", { name: "刪除" });
    fireEvent.click(confirmBtn);

    await waitFor(() =>
      expect(
        apiMock.default.systemSettings.supplementaryDocs.delete
      ).toHaveBeenCalledWith(1)
    );
  });

  it("calls updateTitle on save edit", async () => {
    apiMock.default.systemSettings.supplementaryDocs.list.mockResolvedValue({
      success: true,
      message: "OK",
      data: fakeDocs,
    });
    apiMock.default.systemSettings.supplementaryDocs.updateTitle.mockResolvedValue({
      success: true,
      message: "OK",
      data: { ...fakeDocs[0], title: "FAQ v2" },
    });

    render(<SupplementaryDocsList />);

    await screen.findByText("FAQ");
    const editBtns = screen.getAllByRole("button", { name: "編輯標題" });
    fireEvent.click(editBtns[0]);

    const input = await screen.findByDisplayValue("FAQ");
    fireEvent.change(input, { target: { value: "FAQ v2" } });
    fireEvent.click(screen.getByRole("button", { name: "儲存" }));

    await waitFor(() =>
      expect(
        apiMock.default.systemSettings.supplementaryDocs.updateTitle
      ).toHaveBeenCalledWith(1, "FAQ v2")
    );
  });
});

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { FooterLinksPanel } from "../FooterLinksPanel";

jest.mock("../../../../lib/api", () => {
  const list = jest.fn();
  const create = jest.fn();
  const upload = jest.fn();
  const update = jest.fn();
  const del = jest.fn();
  const reorder = jest.fn();
  return {
    __esModule: true,
    default: {
      footerLinks: { list, create, upload, update, delete: del, reorder },
    },
  };
});

jest.mock("sonner", () => ({
  toast: { success: jest.fn(), error: jest.fn() },
}));

const apiMock = jest.requireMock("../../../../lib/api") as {
  default: {
    footerLinks: {
      list: jest.Mock;
      create: jest.Mock;
      upload: jest.Mock;
      update: jest.Mock;
      delete: jest.Mock;
      reorder: jest.Mock;
    };
  };
};

const api = apiMock.default.footerLinks;
const { toast } = jest.requireMock("sonner") as {
  toast: { success: jest.Mock; error: jest.Mock };
};

function makeLink(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    title_zh: "陽明交大首頁",
    title_en: "NYCU Homepage",
    link_type: "url",
    section: "related",
    url: "https://www.nycu.edu.tw",
    object_name: null,
    original_filename: null,
    content_type: null,
    file_size: null,
    sort_order: 0,
    is_active: true,
    created_at: "2026-07-29T00:00:00Z",
    updated_at: "2026-07-29T00:00:00Z",
    ...overrides,
  };
}

beforeEach(() => {
  Object.values(api).forEach((fn) => (fn as jest.Mock).mockReset());
  toast.success.mockReset();
  toast.error.mockReset();
});

test("requests inactive links so admins can manage hidden entries", async () => {
  api.list.mockResolvedValue({ success: true, message: "OK", data: [] });

  render(<FooterLinksPanel section="related" />);

  await waitFor(() => expect(api.list).toHaveBeenCalledWith(true, "related"));
  expect(await screen.findByText(/目前尚無相關連結/)).toBeInTheDocument();
});

test("the policy panel lists its own section and uses policy copy", async () => {
  api.list.mockResolvedValue({ success: true, message: "OK", data: [] });

  render(<FooterLinksPanel section="policy" />);

  await waitFor(() => expect(api.list).toHaveBeenCalledWith(true, "policy"));
  expect(await screen.findByText(/目前尚無政策連結/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "政策連結" })).toBeInTheDocument();
});

test("shows a 已隱藏 badge for inactive links", async () => {
  api.list.mockResolvedValue({
    success: true,
    message: "OK",
    data: [makeLink({ is_active: false })],
  });

  render(<FooterLinksPanel section="related" />);

  expect(await screen.findByText("已隱藏")).toBeInTheDocument();
});

test("toggling visibility patches is_active", async () => {
  api.list.mockResolvedValue({
    success: true,
    message: "OK",
    data: [makeLink()],
  });
  api.update.mockResolvedValue({
    success: true,
    message: "OK",
    data: makeLink({ is_active: false }),
  });

  render(<FooterLinksPanel section="related" />);

  fireEvent.click(await screen.findByLabelText("隱藏"));

  await waitFor(() =>
    expect(api.update).toHaveBeenCalledWith(1, { is_active: false })
  );
});

test("rejects a non-http URL before hitting the API", async () => {
  api.list.mockResolvedValue({
    success: true,
    message: "OK",
    data: [makeLink()],
  });

  render(<FooterLinksPanel section="related" />);

  fireEvent.click(await screen.findByLabelText("編輯"));

  const urlInput = await screen.findByLabelText("網址");
  fireEvent.change(urlInput, {
    target: { value: "javascript:alert(1)" },
  });
  fireEvent.click(screen.getByText("儲存"));

  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith(
      "網址必須以 http:// 或 https:// 開頭"
    )
  );
  expect(api.update).not.toHaveBeenCalled();
});

test("file links expose a preview action and no URL field when edited", async () => {
  api.list.mockResolvedValue({
    success: true,
    message: "OK",
    data: [
      makeLink({
        id: 4,
        title_zh: "操作手冊",
        link_type: "file",
        url: null,
        object_name: "footer-links/link_x.pdf",
        original_filename: "manual.pdf",
      }),
    ],
  });

  render(<FooterLinksPanel section="related" />);

  expect(await screen.findByLabelText("預覽")).toBeInTheDocument();

  fireEvent.click(screen.getByLabelText("編輯"));

  expect(await screen.findByText(/檔案內容無法直接替換/)).toBeInTheDocument();
  expect(screen.queryByLabelText("網址")).toBeNull();
});

test("deleting a link removes the row and calls the API", async () => {
  api.list.mockResolvedValue({
    success: true,
    message: "OK",
    data: [makeLink()],
  });
  api.delete.mockResolvedValue({
    success: true,
    message: "OK",
    data: { deleted: true },
  });

  render(<FooterLinksPanel section="related" />);

  fireEvent.click(await screen.findByLabelText("刪除"));
  fireEvent.click(await screen.findByText("刪除", { selector: "button" }));

  await waitFor(() => expect(api.delete).toHaveBeenCalledWith(1));
});

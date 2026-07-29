import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import { Footer } from "../footer";
import { FOOTER_LINKS_CHANGED_EVENT } from "../../lib/api/modules/footer-links";

jest.mock("../../lib/api", () => {
  const list = jest.fn();
  return {
    __esModule: true,
    default: { footerLinks: { list } },
  };
});

const apiMock = jest.requireMock("../../lib/api") as {
  default: { footerLinks: { list: jest.Mock } };
};

const listMock = apiMock.default.footerLinks.list;

function makeLink(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    title_zh: "陽明交大首頁",
    title_en: "NYCU Homepage",
    link_type: "url",
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
  listMock.mockReset();
  localStorage.setItem("auth_token", "test-token");
});

test("renders admin-managed links returned by the API", async () => {
  listMock.mockResolvedValue({
    success: true,
    message: "OK",
    data: [makeLink(), makeLink({ id: 2, title_zh: "教務處", url: "https://aa.nycu.edu.tw/" })],
  });

  render(<Footer locale="zh" />);

  const link = await screen.findByRole("link", { name: "陽明交大首頁" });
  expect(link).toHaveAttribute("href", "https://www.nycu.edu.tw");
  expect(await screen.findByRole("link", { name: "教務處" })).toBeInTheDocument();
});

test("file links point at the streaming proxy, not a raw object name", async () => {
  listMock.mockResolvedValue({
    success: true,
    message: "OK",
    data: [
      makeLink({
        id: 7,
        title_zh: "獎學金申請指南",
        link_type: "file",
        url: null,
        object_name: "footer-links/link_abc.pdf",
        original_filename: "guide.pdf",
      }),
    ],
  });

  render(<Footer locale="zh" />);

  const link = await screen.findByRole("link", { name: "獎學金申請指南" });
  const href = link.getAttribute("href") || "";
  expect(href).toContain("/api/v1/preview/footer-links?id=7");
  expect(href).not.toContain("footer-links/link_abc.pdf");
});

test("English locale falls back to the Chinese title when title_en is unset", async () => {
  listMock.mockResolvedValue({
    success: true,
    message: "OK",
    data: [makeLink({ title_zh: "校務系統", title_en: null })],
  });

  render(<Footer locale="en" />);

  expect(
    await screen.findByRole("link", { name: "校務系統" })
  ).toBeInTheDocument();
});

test("a failed links fetch leaves the rest of the footer intact", async () => {
  listMock.mockRejectedValue(new Error("boom"));

  render(<Footer locale="zh" />);

  // The static footer content still renders...
  expect(await screen.findByText("國立陽明交通大學")).toBeInTheDocument();
  // ...but the 相關連結 section is hidden rather than shown empty, so the
  // heading and its chevron never sit over an empty box.
  await waitFor(() => expect(screen.queryByText("相關連結")).toBeNull());
  expect(screen.queryByRole("link", { name: "陽明交大首頁" })).toBeNull();
});

test("the 相關連結 section is hidden when every link is hidden", async () => {
  listMock.mockResolvedValue({ success: true, message: "OK", data: [] });

  render(<Footer locale="zh" />);

  expect(await screen.findByText("國立陽明交通大學")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText("相關連結")).toBeNull());
});

test("refetches when the admin panel reports a change", async () => {
  listMock.mockResolvedValueOnce({
    success: true,
    message: "OK",
    data: [makeLink({ title_zh: "舊連結" })],
  });

  render(<Footer locale="zh" />);
  expect(await screen.findByRole("link", { name: "舊連結" })).toBeInTheDocument();

  listMock.mockResolvedValueOnce({
    success: true,
    message: "OK",
    data: [makeLink({ id: 9, title_zh: "新連結" })],
  });
  await act(async () => {
    window.dispatchEvent(new CustomEvent(FOOTER_LINKS_CHANGED_EVENT));
  });

  expect(await screen.findByRole("link", { name: "新連結" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "舊連結" })).toBeNull();
});

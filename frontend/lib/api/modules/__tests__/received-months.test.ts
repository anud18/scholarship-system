/**
 * Tests for `frontend/lib/api/modules/received-months.ts`.
 *
 * Covers the raw-fetch paths: multipart preview, confirm/cancel, and the
 * template download's blob + RFC 5987 filename handling.
 */

import { createReceivedMonthsApi } from "../received-months";
import { typedClient } from "../../typed-client";

const TEMPLATE_URL = "/api/v1/admin/received-months/template";

beforeEach(() => {
  jest.spyOn(typedClient, "getToken").mockReturnValue("tok-123");
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe("preview", () => {
  it("POSTs multipart with the file and scholarship_type_id, plus Bearer", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, message: "ok", data: { import_id: 7 } }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    const file = new File(["xlsx"], "nstc.xlsx");
    const result = await createReceivedMonthsApi().preview(2, file);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/admin/received-months/preview");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ Authorization: "Bearer tok-123" });

    const body = init.body as FormData;
    expect(body.get("file")).toBe(file);
    expect(body.get("scholarship_type_id")).toBe("2");
    expect(result.data?.import_id).toBe(7);
  });

  it("surfaces the backend message on a non-OK response", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 400,
      clone: () => ({ json: async () => ({ message: "找不到表頭列" }) }),
      json: async () => ({ message: "找不到表頭列" }),
    }) as unknown as typeof fetch;

    const result = await createReceivedMonthsApi().preview(2, new File([""], "x.xlsx"));

    expect(result.success).toBe(false);
    expect(result.message).toBe("找不到表頭列");
  });

  it("falls back to the HTTP status when the error body is unparseable", async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 502,
      clone: () => ({
        json: async () => {
          throw new Error("not json");
        },
      }),
      json: async () => {
        throw new Error("not json");
      },
    }) as unknown as typeof fetch;

    const result = await createReceivedMonthsApi().preview(2, new File([""], "x.xlsx"));

    expect(result.success).toBe(false);
    expect(result.message).toBe("匯入失敗 (HTTP 502)");
  });

  it("omits Authorization when there is no token", async () => {
    jest.spyOn(typedClient, "getToken").mockReturnValue(null as never);
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, message: "ok", data: {} }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    await createReceivedMonthsApi().preview(2, new File([""], "x.xlsx"));

    expect(fetchMock.mock.calls[0][1].headers).toEqual({});
  });
});

describe("confirm / cancel", () => {
  it.each([
    ["confirm", "/api/v1/admin/received-months/7/confirm"],
    ["cancel", "/api/v1/admin/received-months/7/cancel"],
  ])("%s POSTs to the id-templated path", async (method, expectedUrl) => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, message: "ok", data: {} }),
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    const api = createReceivedMonthsApi() as unknown as Record<
      string,
      (id: number) => Promise<unknown>
    >;
    await api[method](7);

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(expectedUrl);
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ Authorization: "Bearer tok-123" });
  });
});

describe("downloadTemplate", () => {
  function mockDom() {
    const link = { href: "", download: "", click: jest.fn() } as unknown as HTMLAnchorElement;
    jest.spyOn(document, "createElement").mockReturnValue(link);
    jest.spyOn(document.body, "appendChild").mockImplementation((n) => n);
    jest.spyOn(document.body, "removeChild").mockImplementation((n) => n);
    window.URL.createObjectURL = jest.fn(() => "blob:fake");
    window.URL.revokeObjectURL = jest.fn();
    return link;
  }

  it("decodes the RFC 5987 Chinese filename from Content-Disposition", async () => {
    const link = mockDom();
    const encoded = encodeURIComponent("獲獎生已領月份統計表_範例.xlsx");
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(["xlsx"]),
      headers: {
        get: () => `attachment; filename*=UTF-8''${encoded}`,
      },
    }) as unknown as typeof fetch;

    await createReceivedMonthsApi().downloadTemplate();

    expect(link.download).toBe("獲獎生已領月份統計表_範例.xlsx");
    expect(link.click).toHaveBeenCalled();
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith("blob:fake");
  });

  it("falls back to a default filename when the header is absent", async () => {
    const link = mockDom();
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(["xlsx"]),
      headers: { get: () => null },
    }) as unknown as typeof fetch;

    await createReceivedMonthsApi().downloadTemplate();

    expect(link.download).toBe("received-months-template.xlsx");
  });

  it("throws with the status when the download fails", async () => {
    mockDom();
    global.fetch = jest.fn().mockResolvedValue({
      ok: false,
      status: 403,
      clone: () => ({ json: async () => ({ detail: "Forbidden" }) }),
    }) as unknown as typeof fetch;

    await expect(createReceivedMonthsApi().downloadTemplate()).rejects.toThrow(
      "下載範例失敗 (403: Forbidden)",
    );
  });

  it("requests the template with the Bearer token", async () => {
    mockDom();
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(["xlsx"]),
      headers: { get: () => null },
    });
    global.fetch = fetchMock as unknown as typeof fetch;

    await createReceivedMonthsApi().downloadTemplate();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(TEMPLATE_URL);
    expect(init.method).toBe("GET");
    expect(init.headers).toEqual({ Authorization: "Bearer tok-123" });
  });
});

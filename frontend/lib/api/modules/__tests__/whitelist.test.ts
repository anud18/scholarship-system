/**
 * Tests for `frontend/lib/api/modules/whitelist.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives the admin
 * scholarship-whitelist UI (toggle, batch add/remove, Excel
 * import/export, template download).
 *
 * Wave 6a125 pins URL paths + batch body shapes + Excel
 * download blob handling.
 *
 * SECURITY-relevant: whitelist controls who can apply for
 * restricted scholarships. Drift in the batch-add body shape
 * would silently allow / block the wrong students.
 *
 * 12 cases.
 */

import { createWhitelistApi } from "../whitelist";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
      PATCH: jest.fn(),
      DELETE: jest.fn(),
    },
    getToken: jest.fn(() => "test-token"),
  },
}));

// Need to mock form-data-helpers too because importWhitelistExcel
// pre-processes the file before passing to typedClient.
jest.mock("../../form-data-helpers", () => ({
  createFileUploadFormData: jest.fn((data) => data),
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
  PATCH: jest.Mock;
  DELETE: jest.Mock;
};

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createWhitelistApi", () => {
  // ─── toggle ────────────────────────────────────────────────────────

  it("toggleScholarshipWhitelist PATCHes /scholarships/{id}/whitelist", async () => {
    // Pin: PATCH (state toggle); path templates scholarshipId
    // as "id"; body has {enabled}.
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({ success: true }));
    const api = createWhitelistApi();
    await api.toggleScholarshipWhitelist(5, true);
    expect(mockedRaw.PATCH).toHaveBeenCalledWith(
      "/api/v1/scholarships/{id}/whitelist",
      { params: { path: { id: 5 } }, body: { enabled: true } }
    );
  });

  it("toggleScholarshipWhitelist body uses enabled=false to disable", async () => {
    mockedRaw.PATCH.mockResolvedValueOnce(_ok({ success: true }));
    const api = createWhitelistApi();
    await api.toggleScholarshipWhitelist(5, false);
    expect(mockedRaw.PATCH.mock.calls[0][1].body.enabled).toBe(false);
  });

  // ─── getConfigurationWhitelist ─────────────────────────────────────

  it("getConfigurationWhitelist GETs /scholarship-configurations/{id}/whitelist", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createWhitelistApi();
    await api.getConfigurationWhitelist(7, { page: 1, size: 50, search: "wang" });
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/scholarship-configurations/{id}/whitelist",
      {
        params: {
          path: { id: 7 },
          query: { page: 1, size: 50, search: "wang" },
        },
      }
    );
  });

  it("getConfigurationWhitelist omits query when no params", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createWhitelistApi();
    await api.getConfigurationWhitelist(7);
    const opts = mockedRaw.GET.mock.calls[0][1];
    expect(opts.params).toEqual({ path: { id: 7 } });
  });

  // ─── batchAddWhitelist ─────────────────────────────────────────────

  it("batchAddWhitelist POSTs /whitelist/batch with students array", async () => {
    // SECURITY: body shape pinned — backend expects students
    // array with {nycu_id, sub_type} per element. Drift silently
    // allows/blocks the wrong students.
    mockedRaw.POST.mockResolvedValueOnce(
      _ok({ success_count: 2, failed_items: [] })
    );
    const api = createWhitelistApi();
    await api.batchAddWhitelist(7, {
      students: [
        { nycu_id: "310460031", sub_type: "nstc" },
        { nycu_id: "310460032", sub_type: "moe" },
      ],
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/scholarship-configurations/{id}/whitelist/batch",
      {
        params: { path: { id: 7 } },
        body: {
          students: [
            { nycu_id: "310460031", sub_type: "nstc" },
            { nycu_id: "310460032", sub_type: "moe" },
          ],
        },
      }
    );
  });

  // ─── batchRemoveWhitelist ──────────────────────────────────────────

  it("batchRemoveWhitelist DELETEs /whitelist/batch with body", async () => {
    // Pin: DELETE with body — unusual but documented contract.
    // Backend uses request body to identify which entries to
    // remove (nycu_ids array + optional sub_type filter).
    mockedRaw.DELETE.mockResolvedValueOnce(
      _ok({ success_count: 2, failed_items: [] })
    );
    const api = createWhitelistApi();
    await api.batchRemoveWhitelist(7, {
      nycu_ids: ["310460031", "310460032"],
      sub_type: "nstc",
    });
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/scholarship-configurations/{id}/whitelist/batch",
      {
        params: { path: { id: 7 } },
        body: { nycu_ids: ["310460031", "310460032"], sub_type: "nstc" },
      }
    );
  });

  it("batchRemoveWhitelist body sub_type is optional", async () => {
    // Pin: sub_type optional — omitting removes the student from
    // ALL sub_types within the configuration. Pin so a refactor
    // making it required doesn't silently force admin to specify.
    mockedRaw.DELETE.mockResolvedValueOnce(_ok({}));
    const api = createWhitelistApi();
    await api.batchRemoveWhitelist(7, { nycu_ids: ["310460031"] });
    const body = mockedRaw.DELETE.mock.calls[0][1].body;
    expect(body.sub_type).toBeUndefined();
    expect(body.nycu_ids).toEqual(["310460031"]);
  });

  // ─── importWhitelistExcel ──────────────────────────────────────────

  it("importWhitelistExcel POSTs /whitelist/import with FormData", async () => {
    // Pin: FormData path — uses createFileUploadFormData helper.
    mockedRaw.POST.mockResolvedValueOnce(_ok({ success_count: 1, failed_items: [] }));
    const api = createWhitelistApi();
    const fakeFile = new File(["test"], "test.xlsx");
    await api.importWhitelistExcel(7, fakeFile);
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/scholarship-configurations/{id}/whitelist/import",
      expect.objectContaining({
        params: { path: { id: 7 } },
      })
    );
  });

  // ─── exportWhitelistExcel (raw fetch, returns Blob) ────────────────

  it("exportWhitelistExcel uses raw fetch + Bearer token", async () => {
    // Pin: bypass typedClient because we need Blob response.
    // Bearer token attached when typedClient.getToken() returns
    // a value.
    const fakeBlob = new Blob(["xlsx"]);
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      blob: jest.fn().mockResolvedValue(fakeBlob),
    });
    global.fetch = fetchMock as any;

    const api = createWhitelistApi();
    const result = await api.exportWhitelistExcel(7);
    expect(result).toBe(fakeBlob);
    const url = fetchMock.mock.calls[0][0];
    expect(url).toContain(
      "/api/v1/scholarship-configurations/7/whitelist/export"
    );
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe(
      "Bearer test-token"
    );
  });

  it("exportWhitelistExcel throws on non-OK with backend detail message", async () => {
    // Pin: non-OK → throws with backend's error detail (or fallback
    // 匯出白名單失敗 i18n message). Admin UI surfaces this.
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      json: jest.fn().mockResolvedValue({ detail: "white-only access" }),
    });
    global.fetch = fetchMock as any;

    const api = createWhitelistApi();
    await expect(api.exportWhitelistExcel(7)).rejects.toThrow(
      "white-only access"
    );
  });

  it("exportWhitelistExcel falls back to zh-TW message when no detail", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      json: jest.fn().mockResolvedValue({}),
    });
    global.fetch = fetchMock as any;

    const api = createWhitelistApi();
    await expect(api.exportWhitelistExcel(7)).rejects.toThrow(
      "匯出白名單失敗"
    );
  });

  // ─── downloadTemplate ──────────────────────────────────────────────

  it("downloadTemplate GETs /whitelist/template + returns Blob", async () => {
    const fakeBlob = new Blob(["template"]);
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      blob: jest.fn().mockResolvedValue(fakeBlob),
    });
    global.fetch = fetchMock as any;

    const api = createWhitelistApi();
    const result = await api.downloadTemplate(7);
    expect(result).toBe(fakeBlob);
    expect(fetchMock.mock.calls[0][0]).toContain(
      "/api/v1/scholarship-configurations/7/whitelist/template"
    );
  });

  it("downloadTemplate throws zh-TW fallback when no detail", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: false,
      json: jest.fn().mockResolvedValue({}),
    });
    global.fetch = fetchMock as any;

    const api = createWhitelistApi();
    await expect(api.downloadTemplate(7)).rejects.toThrow("下載範本失敗");
  });
});

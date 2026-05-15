/**
 * Tests for `frontend/lib/api/modules/reference-data.ts`.
 *
 * Module had ZERO dedicated test coverage. Provides static
 * reference data (academies / departments / degrees / etc.)
 * used by dropdown UIs across the system. The `/all` endpoint
 * is heavily-cached and used by almost every form page.
 *
 * Wave 6a122 pins URL paths + scholarship-periods query keys.
 *
 * 8 cases.
 */

import { createReferenceDataApi } from "../reference-data";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
    },
  },
}));

const mockedRaw = typedClient.raw as unknown as { GET: jest.Mock };

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createReferenceDataApi", () => {
  it("getAcademies GETs /reference-data/academies", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createReferenceDataApi();
    await api.getAcademies();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/reference-data/academies"
    );
  });

  it("getDepartments GETs /reference-data/departments", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createReferenceDataApi();
    await api.getDepartments();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/reference-data/departments"
    );
  });

  it("getAll GETs /reference-data/all (bundled endpoint)", async () => {
    // Pin: dedicated bundled endpoint — pin so a refactor
    // splitting it into multiple GETs would impact every form
    // page that depends on the single-request batch.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createReferenceDataApi();
    await api.getAll();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/reference-data/all"
    );
  });

  it("getScholarshipPeriods GETs /reference-data/scholarship-periods", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createReferenceDataApi();
    await api.getScholarshipPeriods();
    expect(mockedRaw.GET.mock.calls[0][0]).toBe(
      "/api/v1/reference-data/scholarship-periods"
    );
  });

  it("getScholarshipPeriods omits all query params when no args", async () => {
    // Pin: 3 filters all undefined when not supplied.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createReferenceDataApi();
    await api.getScholarshipPeriods();
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.scholarship_id).toBeUndefined();
    expect(query.scholarship_code).toBeUndefined();
    expect(query.application_cycle).toBeUndefined();
  });

  it("getScholarshipPeriods forwards scholarship_id filter", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createReferenceDataApi();
    await api.getScholarshipPeriods({ scholarship_id: 7 });
    expect(mockedRaw.GET.mock.calls[0][1].params.query.scholarship_id).toBe(7);
  });

  it("getScholarshipPeriods forwards all 3 filters together", async () => {
    // Pin: 3-way combined filter (scholarship_id + scholarship_code
    // + application_cycle). Pin all keys SNAKE_CASE because
    // backend Pydantic validates exact names.
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createReferenceDataApi();
    await api.getScholarshipPeriods({
      scholarship_id: 1,
      scholarship_code: "phd_general",
      application_cycle: "semester",
    });
    const query = mockedRaw.GET.mock.calls[0][1].params.query;
    expect(query.scholarship_id).toBe(1);
    expect(query.scholarship_code).toBe("phd_general");
    expect(query.application_cycle).toBe("semester");
  });

  it("all endpoints share /api/v1/reference-data base", async () => {
    // Pin: all 4 endpoints under the same versioned base.
    // Pin so refactor moving any one to /api/v1/admin/* or
    // similar would require explicit migration.
    mockedRaw.GET.mockResolvedValue(_ok([]));
    const api = createReferenceDataApi();
    await api.getAcademies();
    await api.getDepartments();
    await api.getAll();
    await api.getScholarshipPeriods();
    for (const call of mockedRaw.GET.mock.calls) {
      expect(call[0]).toMatch(/^\/api\/v1\/reference-data/);
    }
  });
});

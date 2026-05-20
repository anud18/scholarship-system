/**
 * Tests for `frontend/lib/api/modules/user-profiles.ts`.
 *
 * Module had ZERO dedicated test coverage. Drives:
 *  - Student-facing profile editing (self-service /me)
 *  - Admin profile management (admin.* sub-namespace)
 *
 * Wave 6a132 pins URL paths + the SECURITY-relevant /me vs
 * /admin/{user_id} scope distinction + dual bank-document
 * upload paths (base64 query vs FormData body).
 *
 * 14 cases.
 */

import { createUserProfilesApi } from "../user-profiles";
import { typedClient } from "../../typed-client";

jest.mock("../../typed-client", () => ({
  typedClient: {
    raw: {
      GET: jest.fn(),
      POST: jest.fn(),
      PUT: jest.fn(),
      DELETE: jest.fn(),
    },
  },
}));

jest.mock("../../form-data-helpers", () => ({
  createFileUploadFormData: jest.fn((data) => ({ __formData: data })),
}));

const mockedRaw = typedClient.raw as unknown as {
  GET: jest.Mock;
  POST: jest.Mock;
  PUT: jest.Mock;
  DELETE: jest.Mock;
};

function _ok<T = any>(data: T) {
  return { data: { success: true, message: "", data }, response: { ok: true, status: 200 } };
}

beforeEach(() => {
  jest.clearAllMocks();
});

describe("createUserProfilesApi (self-service /me)", () => {
  it("getMyProfile GETs /user-profiles/me", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createUserProfilesApi();
    await api.getMyProfile();
    expect(mockedRaw.GET).toHaveBeenCalledWith("/api/v1/user-profiles/me");
  });

  it("createProfile POSTs /me with body", async () => {
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createUserProfilesApi();
    await api.createProfile({ phone: "0900000000" });
    expect(mockedRaw.POST).toHaveBeenCalledWith("/api/v1/user-profiles/me", {
      body: { phone: "0900000000" },
    });
  });

  it("updateProfile PUTs /me with body", async () => {
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createUserProfilesApi();
    await api.updateProfile({ phone: "0911111111" });
    expect(mockedRaw.PUT).toHaveBeenCalledWith("/api/v1/user-profiles/me", {
      body: { phone: "0911111111" },
    });
  });

  // ─── Bank info / Advisor info (separate sub-routes) ────────────────

  it("updateBankInfo PUTs /me/bank-info with change_reason", async () => {
    // Pin: dedicated /bank-info sub-route — bank changes have
    // audit-log implications, separate from regular profile
    // update. body includes change_reason for audit trail.
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createUserProfilesApi();
    await api.updateBankInfo({
      account_number: "12345-67890",
      change_reason: "switched banks",
    });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/user-profiles/me/bank-info",
      { body: { account_number: "12345-67890", change_reason: "switched banks" } }
    );
  });

  it("updateAdvisorInfo PUTs /me/advisor-info", async () => {
    // Pin: dedicated /advisor-info sub-route — separate from
    // bank-info because advisor changes don't need OCR verify.
    mockedRaw.PUT.mockResolvedValueOnce(_ok({}));
    const api = createUserProfilesApi();
    await api.updateAdvisorInfo({
      advisor_name: "李教授",
      advisor_email: "li@nycu.edu.tw",
      change_reason: "new advisor",
    });
    expect(mockedRaw.PUT).toHaveBeenCalledWith(
      "/api/v1/user-profiles/me/advisor-info",
      {
        body: {
          advisor_name: "李教授",
          advisor_email: "li@nycu.edu.tw",
          change_reason: "new advisor",
        },
      }
    );
  });

  // ─── Bank document upload (dual paths) ─────────────────────────────

  it("uploadBankDocument (base64) sends data via QUERY string", async () => {
    // Pin: legacy base64 path uses QUERY string (photo_data,
    // filename, content_type). Pin so refactor to body doesn't
    // break the backend handler that expects query.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createUserProfilesApi();
    await api.uploadBankDocument(
      "data:image/png;base64,XXX",
      "passbook.png",
      "image/png"
    );
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/user-profiles/me/bank-document",
      {
        params: {
          query: {
            photo_data: "data:image/png;base64,XXX",
            filename: "passbook.png",
            content_type: "image/png",
          },
        },
      }
    );
  });

  it("uploadBankDocumentFile uses FormData on /file sub-route", async () => {
    // Pin: newer file-upload path uses /file sub-route +
    // FormData body. Distinct from the base64 path.
    mockedRaw.POST.mockResolvedValueOnce(_ok({}));
    const api = createUserProfilesApi();
    await api.uploadBankDocumentFile(new File(["x"], "passbook.png"));
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/user-profiles/me/bank-document/file",
      expect.objectContaining({ body: expect.anything() })
    );
  });

  it("deleteBankDocument DELETEs /me/bank-document", async () => {
    mockedRaw.DELETE.mockResolvedValueOnce(_ok({}));
    const api = createUserProfilesApi();
    await api.deleteBankDocument();
    expect(mockedRaw.DELETE).toHaveBeenCalledWith(
      "/api/v1/user-profiles/me/bank-document"
    );
  });

  // ─── History / delete ─────────────────────────────────────────────

  it("getHistory GETs /me/history", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createUserProfilesApi();
    await api.getHistory();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/user-profiles/me/history"
    );
  });

  it("deleteProfile DELETEs /me (full profile removal)", async () => {
    // Pin: full profile DELETE — pin so refactor merging it
    // with deleteBankDocument doesn't accidentally remove the
    // wrong scope.
    mockedRaw.DELETE.mockResolvedValueOnce(_ok({}));
    const api = createUserProfilesApi();
    await api.deleteProfile();
    expect(mockedRaw.DELETE).toHaveBeenCalledWith("/api/v1/user-profiles/me");
  });
});

describe("createUserProfilesApi (admin sub-namespace)", () => {
  it("admin.getIncompleteProfiles GETs /admin/incomplete", async () => {
    // Pin: admin scope. Pin /admin/ prefix so refactor moving
    // it under /me doesn't break the auth boundary.
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createUserProfilesApi();
    await api.admin.getIncompleteProfiles();
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/user-profiles/admin/incomplete"
    );
  });

  it("admin.getUserProfile GETs /admin/{user_id} with snake_case key", async () => {
    // Pin: user_id snake_case in path template (NOT userId).
    mockedRaw.GET.mockResolvedValueOnce(_ok({}));
    const api = createUserProfilesApi();
    await api.admin.getUserProfile(42);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/user-profiles/admin/{user_id}",
      { params: { path: { user_id: 42 } } }
    );
  });

  it("admin.getUserHistory GETs /admin/{user_id}/history", async () => {
    mockedRaw.GET.mockResolvedValueOnce(_ok([]));
    const api = createUserProfilesApi();
    await api.admin.getUserHistory(42);
    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/user-profiles/admin/{user_id}/history",
      { params: { path: { user_id: 42 } } }
    );
  });

  // ─── Admin namespace is read-only ──────────────────────────────────

  it("admin sub-namespace exposes only read methods", async () => {
    // Pin: admin can VIEW user profiles but only the user can
    // EDIT their own (or via dedicated admin endpoints not yet
    // implemented). Pin so refactor adding admin.update or
    // admin.delete requires explicit audit/auth review.
    const api = createUserProfilesApi();
    expect(api.admin.getIncompleteProfiles).toBeDefined();
    expect(api.admin.getUserProfile).toBeDefined();
    expect(api.admin.getUserHistory).toBeDefined();
    expect((api.admin as any).updateProfile).toBeUndefined();
    expect((api.admin as any).deleteProfile).toBeUndefined();
  });
});

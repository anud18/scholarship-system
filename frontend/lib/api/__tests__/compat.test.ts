/**
 * Tests for `lib/api/compat.ts`.
 *
 * The compatibility layer between `openapi-fetch` responses and the
 * standard `ApiResponse<T>` format used app-wide. Every endpoint call
 * routes through `toApiResponse` for normalization.
 *
 * Regression risks:
 * - FastAPI validation array → not stringified → UI shows "[object
 *   Object], [object Object]" instead of helpful errors
 * - error.detail as object → not safeStringify'd → same UX issue
 * - Backend ApiResponse pass-through breaks → frontend sees wrong shape
 *
 * 14 cases covering 4 helpers.
 */
import {
  toApiResponse,
  extractErrorMessage,
  isSuccessResponse,
  isErrorResponse,
} from "../compat";

// Helper to build a minimal openapi-fetch-shaped response.
function makeResponse(opts: { data?: any; error?: any; status?: number; ok?: boolean }) {
  return {
    data: opts.data,
    error: opts.error,
    response: {
      ok: opts.ok ?? (opts.status ? opts.status >= 200 && opts.status < 300 : true),
      status: opts.status ?? 200,
    } as Response,
  };
}

// ─── toApiResponse: error paths ──────────────────────────────────────

describe("toApiResponse: error normalization", () => {
  it("strings: error.detail as string → uses as message", () => {
    const r = toApiResponse(makeResponse({ error: { detail: "Not found" }, status: 404, ok: false }));
    expect(r.success).toBe(false);
    expect(r.message).toBe("Not found");
    expect(r.data).toBeUndefined();
  });

  it("FastAPI array validation errors → joined with comma", () => {
    /** FastAPI's standard 422 shape:
     *   { detail: [{loc: ['body', 'gpa'], msg: 'must be >= 0'}, ...] }
     * Must format as 'body.gpa: must be >= 0, ...' — pin so users see
     * actionable validation messages. */
    const r = toApiResponse(
      makeResponse({
        error: {
          detail: [
            { loc: ["body", "gpa"], msg: "value must be ≥ 0" },
            { loc: ["body", "ranking"], msg: "value must be ≤ 100" },
          ],
        },
        status: 422,
        ok: false,
      }),
    );
    expect(r.message).toContain("body.gpa: value must be ≥ 0");
    expect(r.message).toContain("body.ranking: value must be ≤ 100");
    expect(r.message).toContain(", "); // joined with comma-space
  });

  it("error.detail as object → safeStringify (not '[object Object]')", () => {
    /** SECURITY-ADJACENT: never leak '[object Object]' to UI. */
    const r = toApiResponse(makeResponse({ error: { detail: { code: 42, msg: "bad" } }, status: 500, ok: false }));
    expect(r.message).not.toContain("[object Object]");
  });

  it("error.message fallback when detail is absent", () => {
    const r = toApiResponse(makeResponse({ error: { message: "Server down" }, status: 500, ok: false }));
    expect(r.message).toBe("Server down");
  });

  it("falls back to 'Request failed with status N' when no detail/message", () => {
    /** Last resort — include status code for debugging. Pin format
     * so logs / Sentry breadcrumbs can parse it. */
    const r = toApiResponse(makeResponse({ error: {}, status: 503, ok: false }));
    expect(r.message).toBe("Request failed with status 503");
  });
});

// ─── toApiResponse: success paths ───────────────────────────────────

describe("toApiResponse: success normalization", () => {
  it("backend ApiResponse format passes through unchanged", () => {
    /** Backend already returns {success, message, data} — don't re-wrap. */
    const r = toApiResponse(
      makeResponse({
        data: { success: true, message: "ok", data: { id: 42 } },
      }),
    );
    expect(r.success).toBe(true);
    expect(r.message).toBe("ok");
    expect(r.data).toEqual({ id: 42 });
  });

  it("raw data wraps in ApiResponse with 'Request completed successfully'", () => {
    /** Old endpoints that return raw lists/objects (not wrapped) — must
     * still produce a valid ApiResponse so frontend code paths are
     * uniform. */
    const r = toApiResponse(makeResponse({ data: [1, 2, 3] }));
    expect(r.success).toBe(true);
    expect(r.message).toBe("Request completed successfully");
    expect(r.data).toEqual([1, 2, 3]);
  });

  it("non-string message in backend response is safeStringify'd", () => {
    /** Defensive: if backend accidentally returns message: {nested},
     * still coerce to string (don't ship object to UI message slot). */
    const r = toApiResponse(
      makeResponse({
        data: { success: true, message: { code: 1 }, data: null },
      }),
    );
    expect(typeof r.message).toBe("string");
  });
});

// ─── extractErrorMessage ────────────────────────────────────────────

describe("extractErrorMessage", () => {
  it("returns detail string when present", () => {
    expect(
      extractErrorMessage(makeResponse({ error: { detail: "bad" }, status: 400, ok: false })),
    ).toBe("bad");
  });

  it("joins FastAPI validation array", () => {
    expect(
      extractErrorMessage(
        makeResponse({
          error: { detail: [{ loc: ["body", "x"], msg: "missing" }] },
          status: 422,
          ok: false,
        }),
      ),
    ).toContain("body.x: missing");
  });

  it("falls back to status code when no error fields", () => {
    expect(
      extractErrorMessage(makeResponse({ error: {}, status: 500, ok: false })),
    ).toBe("Request failed with status 500");
  });

  it("returns 'Unknown error occurred' for OK response with no error", () => {
    /** A response with no error and ok=true but called via this function
     * (shouldn't happen but pin behavior). */
    expect(extractErrorMessage(makeResponse({ data: { x: 1 }, status: 200 }))).toBe("Unknown error occurred");
  });
});

// ─── Type guards ─────────────────────────────────────────────────────

describe("isSuccessResponse / isErrorResponse", () => {
  it("isSuccessResponse: true when data present, no error, ok=true", () => {
    expect(isSuccessResponse(makeResponse({ data: { x: 1 }, status: 200 }))).toBe(true);
  });

  it("isSuccessResponse: false when error present", () => {
    expect(isSuccessResponse(makeResponse({ error: { detail: "x" }, status: 400, ok: false }))).toBe(false);
  });

  it("isErrorResponse: true when error present OR response not ok", () => {
    expect(isErrorResponse(makeResponse({ error: { detail: "x" }, status: 400, ok: false }))).toBe(true);
    // No error obj but ok=false → still an error.
    expect(isErrorResponse(makeResponse({ status: 500, ok: false }))).toBe(true);
  });

  it("isErrorResponse: false when data present and response ok", () => {
    expect(isErrorResponse(makeResponse({ data: { x: 1 }, status: 200 }))).toBe(false);
  });
});

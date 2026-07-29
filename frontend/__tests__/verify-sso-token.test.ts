/**
 * Issue #1223 A — the SSO callback must not trust a URL-supplied token.
 *
 * These tests pin the two properties that matter:
 *   1. the token is verified SERVER-side (a forged/unsigned JWT is rejected, no
 *      matter how convincing its payload); and
 *   2. a rejected token is distinguished from an unreachable server — conflating
 *      them is what turned the Sept 2025 attempt at this fix (f7301728) into a
 *      login outage, and it is why that fix was reverted to the vulnerable
 *      client-side decode.
 */

import {
  SsoTokenRejectedError,
  SsoVerificationUnavailableError,
  verifySsoToken,
} from "@/lib/auth/verify-sso-token";

/** A syntactically perfect but completely forged admin token. */
function forgedAdminToken(): string {
  const payload = Buffer.from(
    JSON.stringify({ sub: "1", nycu_id: "victim", role: "super_admin" })
  ).toString("base64url");
  return `eyJhbGciOiJIUzI1NiJ9.${payload}.not-a-real-signature`;
}

const originalFetch = global.fetch;

function mockFetch(impl: jest.Mock) {
  global.fetch = impl as unknown as typeof fetch;
  return impl;
}

afterEach(() => {
  global.fetch = originalFetch;
  jest.restoreAllMocks();
});

describe("verifySsoToken", () => {
  it("returns the SERVER's user, not the token's claims", async () => {
    // The token claims super_admin; the server says student. The server wins.
    mockFetch(
      jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          success: true,
          data: { id: "42", nycu_id: "real_student", role: "student" },
        }),
      })
    );

    const user = await verifySsoToken(forgedAdminToken());

    expect(user.role).toBe("student");
    expect(user.nycu_id).toBe("real_student");
    expect(user.id).toBe("42");
  });

  it("sends the token as an explicit Bearer header to a RELATIVE url", async () => {
    const fetchMock = mockFetch(
      jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ success: true, data: { id: "1", role: "student" } }),
      })
    );

    await verifySsoToken("tok-123");

    const [url, init] = fetchMock.mock.calls[0];
    // Relative: next.config.mjs rewrites /api/* to the backend in dev AND prod.
    // The 2025 revert built an absolute cross-origin dev URL — do not regress.
    expect(url).toBe("/api/v1/auth/me");
    expect(url.startsWith("http")).toBe(false);
    expect(init.headers.Authorization).toBe("Bearer tok-123");
  });

  it.each([401, 403])("rejects the token on HTTP %i (the actual attack path)", async (status) => {
    mockFetch(jest.fn().mockResolvedValue({ ok: false, status, json: async () => ({}) }));

    await expect(verifySsoToken(forgedAdminToken())).rejects.toBeInstanceOf(SsoTokenRejectedError);
  });

  it.each([500, 502, 503, 429])(
    "treats HTTP %i as UNAVAILABLE, not as a bad token",
    async (status) => {
      mockFetch(jest.fn().mockResolvedValue({ ok: false, status, json: async () => ({}) }));

      // Must NOT be SsoTokenRejectedError — a valid login would be thrown away.
      await expect(verifySsoToken("valid-token")).rejects.toBeInstanceOf(
        SsoVerificationUnavailableError
      );
    }
  );

  it("treats a network failure as UNAVAILABLE, not as a bad token", async () => {
    mockFetch(jest.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(verifySsoToken("valid-token")).rejects.toBeInstanceOf(
      SsoVerificationUnavailableError
    );
  });

  it("never fabricates a user when the envelope is missing data", async () => {
    // Project rule: no fallback/mock data on failure — raise instead.
    mockFetch(
      jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ success: true }),
      })
    );

    await expect(verifySsoToken("tok")).rejects.toBeInstanceOf(SsoVerificationUnavailableError);
  });

  it("rejects an unsuccessful envelope even on HTTP 200", async () => {
    mockFetch(
      jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ success: false, message: "nope" }),
      })
    );

    await expect(verifySsoToken("tok")).rejects.toBeInstanceOf(SsoVerificationUnavailableError);
  });

  it("treats a malformed (non-JSON) body as UNAVAILABLE", async () => {
    mockFetch(
      jest.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError("Unexpected token <");
        },
      })
    );

    await expect(verifySsoToken("tok")).rejects.toBeInstanceOf(SsoVerificationUnavailableError);
  });
});

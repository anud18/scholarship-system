/**
 * Tests for `lib/utils/jwt.ts:decodeJWT` + `isJWTExpired`.
 *
 * These helpers decode SSO tokens client-side to drive the role-based
 * routing in the auth layer. Wrong decoding → users get the wrong
 * role landing page, or unauthenticated users slip past client-side
 * route guards (note: server still verifies tokens).
 *
 * Security note: this is CLIENT-side decode only — it doesn't verify
 * signatures. The server's `verify_token` (already tested) is the
 * actual auth gate. These tests pin the client-side UX behavior.
 *
 * 12 cases.
 */
import { decodeJWT, isJWTExpired } from "../jwt";

/** Helper to construct a minimal JWT (header.payload.signature).
 * No real signing — just base64url encoding of a JSON payload. */
function makeJWT(payload: Record<string, unknown>): string {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  const body = btoa(JSON.stringify(payload))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `${header}.${body}.fakesignature`;
}

describe("decodeJWT", () => {
  it("decodes a well-formed token with all required fields", () => {
    const token = makeJWT({
      sub: "42",
      nycu_id: "S12345",
      role: "student",
      exp: 9999999999,
    });
    const payload = decodeJWT(token);
    expect(payload.sub).toBe("42");
    expect(payload.nycu_id).toBe("S12345");
    expect(payload.role).toBe("student");
    expect(payload.exp).toBe(9999999999);
  });

  it("throws on token with wrong number of parts", () => {
    /** JWT must be header.payload.signature — 2 dots, 3 parts. */
    expect(() => decodeJWT("only-one-part")).toThrow(/3 parts/);
    expect(() => decodeJWT("two.parts")).toThrow(/3 parts/);
    expect(() => decodeJWT("a.b.c.d")).toThrow(/3 parts/);
  });

  it("throws when payload is missing sub field", () => {
    /** Required field check — sub is the user-id claim, indispensable
     * for client-side routing. */
    const token = makeJWT({ nycu_id: "S1", role: "student" });
    expect(() => decodeJWT(token)).toThrow(/missing required fields/);
  });

  it("throws when payload is missing nycu_id field", () => {
    const token = makeJWT({ sub: "42", role: "student" });
    expect(() => decodeJWT(token)).toThrow(/missing required fields/);
  });

  it("throws when payload is missing role field", () => {
    const token = makeJWT({ sub: "42", nycu_id: "S1" });
    expect(() => decodeJWT(token)).toThrow(/missing required fields/);
  });

  it("handles base64url-encoded payload (+/ → -_)", () => {
    /** JWT spec uses base64url (with - and _ instead of + and /).
     * The decoder must convert back. Pin so a refactor doesn't drop
     * the replace() chain and start rejecting valid tokens. */
    // Construct an ASCII payload that's likely to produce + or / in
    // standard base64 (high-bit-set bytes → +/= are common). Using
    // 0xff-heavy content forces the encoder into +/ territory.
    const token = makeJWT({
      sub: "42",
      nycu_id: "S12345",
      role: "admin",
      extra: "????>>>", // produces + or / in standard base64
    });
    const payload = decodeJWT(token);
    expect(payload.extra).toBe("????>>>");
  });

  it("preserves unknown payload fields", () => {
    /** The interface allows [key: string]: any — pin that custom claims
     * survive. */
    const token = makeJWT({
      sub: "42",
      nycu_id: "S1",
      role: "professor",
      department: "EE",
      tenure_track: true,
    });
    const payload = decodeJWT(token);
    expect(payload.department).toBe("EE");
    expect(payload.tenure_track).toBe(true);
  });
});

describe("isJWTExpired", () => {
  it("returns true for token with exp in the past", () => {
    /** Past exp → expired. Pin the Date.now() vs exp*1000 unit conversion
     * (JWT exp is seconds, JS Date.now() is ms). */
    const pastExpSec = Math.floor(Date.now() / 1000) - 3600; // 1 hour ago
    const token = makeJWT({ sub: "42", nycu_id: "S1", role: "student", exp: pastExpSec });
    expect(isJWTExpired(token)).toBe(true);
  });

  it("returns false for token with exp in the future", () => {
    const futureExpSec = Math.floor(Date.now() / 1000) + 3600; // 1 hour from now
    const token = makeJWT({ sub: "42", nycu_id: "S1", role: "student", exp: futureExpSec });
    expect(isJWTExpired(token)).toBe(false);
  });

  it("returns false for token with no exp claim", () => {
    /** No exp → treated as non-expiring (matches the doc comment).
     * Server-side gates will still reject malformed tokens. */
    const token = makeJWT({ sub: "42", nycu_id: "S1", role: "student" });
    expect(isJWTExpired(token)).toBe(false);
  });

  it("returns true for malformed token (defensive)", () => {
    /** Can't decode → treat as expired. This is the safe default —
     * forces re-auth rather than silently allowing a possibly-bad
     * token through. */
    expect(isJWTExpired("not.a.jwt")).toBe(true);
    expect(isJWTExpired("")).toBe(true);
  });

  it("accepts pre-decoded payload object", () => {
    /** Function signature accepts string OR JWTPayload — pin both
     * paths so callers can pass either form. */
    const payload = {
      sub: "42",
      nycu_id: "S1",
      role: "student",
      exp: Math.floor(Date.now() / 1000) + 3600,
    };
    expect(isJWTExpired(payload)).toBe(false);

    const expiredPayload = { ...payload, exp: Math.floor(Date.now() / 1000) - 3600 };
    expect(isJWTExpired(expiredPayload)).toBe(true);
  });
});

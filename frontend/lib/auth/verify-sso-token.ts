/**
 * Server-authoritative verification of an SSO callback token (issue #1223 A).
 *
 * THE BUG THIS FIXES: the Portal SSO callback used to read `?token=` straight
 * out of the URL, base64-decode the JWT payload **client-side** (no signature
 * check) and install that as the session, commented "we trust the token since it
 * came from our backend". Nothing made that true. An attacker who got a victim
 * to open a crafted callback URL could:
 *   - log the victim into the ATTACKER's account (login-CSRF), then harvest
 *     whatever the victim went on to do; or
 *   - hand over a completely forged, unsigned token and pick the victim's
 *     client-side identity and role at will.
 *
 * The fix: never believe the URL. Ask the backend who the token belongs to, with
 * the token in an explicit Authorization header, and use the answer.
 *
 * WHY THE RELATIVE URL MATTERS. This exact approach was implemented and then
 * reverted in Sept 2025 (f7301728, "eliminate potential API request failures
 * that were preventing authentication"). That version built an ABSOLUTE dev URL
 * — `${protocol}//${hostname}:8000/api/v1/auth/me` — a cross-origin request, and
 * read `userData.data` from a response shape that was not yet standardised.
 * Today `next.config.mjs` rewrites `/api/:path*` to the backend in BOTH dev and
 * prod, so the relative path below is same-origin everywhere, and `/auth/me`
 * returns the project-standard `{success, message, data}` envelope. Keep this
 * path relative — making it absolute is what broke it last time.
 */

import type { User } from "@/lib/api";

/** The backend refused the token: forged, expired, or revoked. Reject the login. */
export class SsoTokenRejectedError extends Error {
  constructor(message = "SSO token rejected by server") {
    super(message);
    this.name = "SsoTokenRejectedError";
  }
}

/**
 * The backend could not be reached or failed. The token may be perfectly valid —
 * this must surface as "try again", NOT as a rejected login, or a transient blip
 * becomes a login outage (the failure mode that caused the 2025 revert).
 */
export class SsoVerificationUnavailableError extends Error {
  constructor(message = "Could not reach the server to verify the login") {
    super(message);
    this.name = "SsoVerificationUnavailableError";
  }
}

/**
 * Resolve the authoritative `User` for `token`, or throw.
 *
 * Never returns fabricated/placeholder data — per the project's no-fallback
 * rule, a failure raises rather than inventing a user.
 */
export async function verifySsoToken(token: string): Promise<User> {
  let response: Response;
  try {
    response = await fetch("/api/v1/auth/me", {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      // The token travels in the header; no ambient cookie session is involved.
      credentials: "omit",
      cache: "no-store",
    });
  } catch (err) {
    throw new SsoVerificationUnavailableError(`Network error verifying SSO token: ${String(err)}`);
  }

  // 401/403 is the ONLY signal that the token itself is bad — this is the
  // attack path from #1223 and the one case that must hard-reject.
  if (response.status === 401 || response.status === 403) {
    throw new SsoTokenRejectedError(`Server rejected SSO token (HTTP ${response.status})`);
  }

  // Anything else (5xx, 429, gateway errors) is about the SERVER, not the token.
  if (!response.ok) {
    throw new SsoVerificationUnavailableError(`Verification endpoint returned HTTP ${response.status}`);
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch (err) {
    throw new SsoVerificationUnavailableError(`Malformed verification response: ${String(err)}`);
  }

  const envelope = body as { success?: boolean; data?: User } | null;
  if (!envelope?.success || !envelope.data) {
    throw new SsoVerificationUnavailableError("Verification response missing user data");
  }

  return envelope.data;
}

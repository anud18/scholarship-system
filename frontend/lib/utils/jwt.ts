/**
 * JWT Utility Module
 * Provides secure JWT decoding functionality for SSO authentication
 */

export interface JWTPayload {
  sub: string;
  nycu_id: string;
  role: string;
  exp?: number;
  iat?: number;
  [key: string]: any;
}

/**
 * Decodes a JWT token and returns the payload
 * @param token - The JWT token string
 * @returns Parsed JWT payload
 * @throws Error if token is invalid or cannot be decoded
 */
export function decodeJWT(token: string): JWTPayload {
  try {
    // Split JWT into parts
    const parts = token.split(".");
    if (parts.length !== 3) {
      throw new Error("Invalid JWT format: must have 3 parts");
    }

    // Extract and decode payload (second part)
    const base64Url = parts[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");

    // Decode base64 to UTF-8 string
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map(function (c) {
          return "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2);
        })
        .join("")
    );

    // Parse JSON payload
    const payload: JWTPayload = JSON.parse(jsonPayload);

    // Validate required fields
    if (!payload.sub || !payload.nycu_id || !payload.role) {
      throw new Error("JWT payload missing required fields (sub, nycu_id, role)");
    }

    return payload;
  } catch (error) {
    if (error instanceof Error) {
      throw new Error(`Failed to decode JWT: ${error.message}`);
    }
    throw new Error("Failed to decode JWT: Unknown error");
  }
}

/**
 * Checks if a JWT token is expired
 * @param token - The JWT token string or decoded payload
 * @returns true if token is expired, false otherwise
 */
export function isJWTExpired(token: string | JWTPayload): boolean {
  try {
    const payload = typeof token === "string" ? decodeJWT(token) : token;

    if (!payload.exp) {
      // No expiration time set, consider as not expired
      return false;
    }

    // JWT exp is in seconds, Date.now() is in milliseconds
    const expirationTime = payload.exp * 1000;
    return Date.now() >= expirationTime;
  } catch {
    // If we can't decode the token, consider it expired
    return true;
  }
}

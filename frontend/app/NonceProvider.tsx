import { headers } from "next/headers";
import type React from "react";

/**
 * getNonce - Server-side function to retrieve CSP nonce from middleware
 *
 * Reads the nonce from middleware-injected headers.
 * Must be called from a Server Component.
 *
 * @returns The nonce string or undefined if not available
 */
export async function getNonce(): Promise<string | undefined> {
  const headersList = await headers();
  return headersList.get("x-nonce") || undefined;
}

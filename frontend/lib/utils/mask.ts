/**
 * Masking helpers for personally identifiable information shown in the UI.
 */

/**
 * Mask a national ID number (身分證字號) for display.
 * Keeps the first character and the last three characters,
 * replacing everything in between with asterisks.
 *
 * Example: "A123456789" -> "A******789"
 */
export function maskIdNumber(idNumber?: string | null): string {
  if (!idNumber) return "";
  const value = idNumber.trim();
  if (value.length <= 4) {
    return value.charAt(0) + "*".repeat(Math.max(value.length - 1, 0));
  }
  return value.charAt(0) + "*".repeat(value.length - 4) + value.slice(-3);
}

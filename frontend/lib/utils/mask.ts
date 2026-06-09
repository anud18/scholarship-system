/**
 * Masking helpers for personally identifiable information shown in the UI.
 */

/**
 * Mask a national ID number (身分證字號) for display.
 * Keeps the first character and the last three characters,
 * replacing everything in between with asterisks.
 *
 * Values of four characters or fewer are too short to keep the last
 * three characters without exposing almost the whole value, so only
 * the first character is kept and the rest is masked.
 *
 * Examples: "A123456789" -> "A******789", "ABCD" -> "A***", "" -> ""
 */
export function maskIdNumber(idNumber?: string | null): string {
  if (!idNumber) return "";
  const value = idNumber.trim();
  if (value.length <= 4) {
    return value.charAt(0) + "*".repeat(Math.max(value.length - 1, 0));
  }
  return value.charAt(0) + "*".repeat(value.length - 4) + value.slice(-3);
}

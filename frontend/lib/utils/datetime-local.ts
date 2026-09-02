import { logger } from "@/lib/utils/logger";

/**
 * Helpers for `<input type="datetime-local">`.
 *
 * The input works in the browser's local wall-clock time and carries no
 * timezone. Its value must therefore be converted to an absolute instant
 * (UTC ISO-8601) before it is sent to the API, and an API value must be
 * converted back to local wall-clock time when it is loaded into the input.
 * Sending the raw input value made the backend store it as UTC, shifting
 * every deadline by the viewer's UTC offset (+8h in Taiwan).
 */

const pad2 = (value: number) => String(value).padStart(2, "0");

/**
 * Format an API datetime string as a `datetime-local` value
 * (`YYYY-MM-DDTHH:mm`) in the browser's local time. Empty or invalid → "".
 */
export function formatDateTimeLocal(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    logger.warn("Invalid date string:", value);
    return "";
  }
  const datePart = `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
  const timePart = `${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  return `${datePart}T${timePart}`;
}

/**
 * Convert a `datetime-local` value (browser-local wall clock) to a UTC
 * ISO-8601 instant for the API. Empty → null (clears the field).
 * Values that already carry an offset keep their meaning, so the
 * conversion is idempotent.
 */
export function dateTimeLocalToIso(
  value: string | null | undefined
): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    throw new Error(`無效的日期時間：${value}`);
  }
  return date.toISOString();
}

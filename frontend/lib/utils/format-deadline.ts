import { format } from "date-fns";

/** Display format for configured deadlines: date plus the minute it closes. */
export const DEADLINE_FORMAT = "yyyy/MM/dd HH:mm";

/**
 * Format a configured deadline (API ISO string or Date) as
 * `yyyy/MM/dd HH:mm` in the viewer's local time, so students, professors
 * and colleges can see the exact minute a period closes — not just the day.
 * Empty or invalid input → null, letting the caller decide what to render.
 */
export function formatDeadline(
  value: string | Date | null | undefined
): string | null {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return format(date, DEADLINE_FORMAT);
}

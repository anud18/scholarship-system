/**
 * Deadlines are institution wall-clock time. Rendering them in Asia/Taipei
 * (not the browser's zone) keeps every viewer — and the backend's
 * "已過…截止時間" messages, which use to_taipei_str — on the same minute.
 */
const DEADLINE_TIME_ZONE = "Asia/Taipei";

const deadlineFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: DEADLINE_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/**
 * Format a configured deadline (API ISO string or Date) as
 * `yyyy/MM/dd HH:mm` in Taipei time, so students, professors and colleges
 * can see the exact minute a period closes — not just the day.
 * Empty or invalid input → null, letting the caller decide what to render.
 */
export function formatDeadline(
  value: string | Date | null | undefined
): string | null {
  if (!value) return null;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  const parts = Object.fromEntries(
    deadlineFormatter.formatToParts(date).map(part => [part.type, part.value])
  );
  return `${parts.year}/${parts.month}/${parts.day} ${parts.hour}:${parts.minute}`;
}

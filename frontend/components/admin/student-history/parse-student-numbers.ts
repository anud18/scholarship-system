/**
 * Multi-學號 input parsing for the student history lookup.
 *
 * Accepts comma / 頓號 / semicolon / whitespace (incl. newline) separators,
 * trims, dedupes preserving order, and splits into valid / invalid tokens.
 * Mirrors the backend rules: `^[A-Za-z0-9]{4,15}$`, max 50 per batch.
 */

export const STUDENT_NUMBER_REGEX = /^[A-Za-z0-9]{4,15}$/;
export const MAX_BATCH_SIZE = 50;

export interface ParsedStudentNumbers {
  valid: string[];
  invalid: string[];
}

export function parseStudentNumbers(input: string): ParsedStudentNumbers {
  const tokens = input
    .split(/[\s,，、;；]+/)
    .map((token) => token.trim())
    .filter(Boolean);
  const deduped = [...new Set(tokens)];
  return {
    valid: deduped.filter((token) => STUDENT_NUMBER_REGEX.test(token)),
    invalid: deduped.filter((token) => !STUDENT_NUMBER_REGEX.test(token)),
  };
}

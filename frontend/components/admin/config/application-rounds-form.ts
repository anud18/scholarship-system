import type { ApplicationRound } from "@/lib/api/types";
import type { components } from "@/lib/api/generated/schema";
import {
  dateTimeLocalToIso,
  formatDateTimeLocal,
} from "@/lib/utils/datetime-local";

export type ApplicationRoundInput = components["schemas"]["ApplicationRoundInput"];

/** Editable state of one later round; dates are `datetime-local` values. */
export interface RoundDraft {
  round_number: number;
  application_start_date: string;
  application_end_date: string;
  open_sub_types: string[];
  professor_review_start: string;
  professor_review_end: string;
  college_review_start: string;
  college_review_end: string;
}

const DEFAULT_ROUND_DAYS = 14;
// A new round gets its own review windows from its application start, so it never
// falls back to the configuration's general windows (usually closed with round 1).
const DEFAULT_PROFESSOR_REVIEW_DAYS_AFTER_END = 14;
const DEFAULT_COLLEGE_REVIEW_DAYS_AFTER_END = 30;
const DAY_MS = 24 * 60 * 60 * 1000;
export const FIRST_EXTRA_ROUND = 2;

export function toRoundDrafts(rounds: ApplicationRound[]): RoundDraft[] {
  return [...rounds]
    .sort((a, b) => a.round_number - b.round_number)
    .map(round => ({
      round_number: round.round_number,
      application_start_date: formatDateTimeLocal(round.application_start_date),
      application_end_date: formatDateTimeLocal(round.application_end_date),
      open_sub_types: [...round.open_sub_types],
      professor_review_start: formatDateTimeLocal(round.professor_review_start),
      professor_review_end: formatDateTimeLocal(round.professor_review_end),
      college_review_start: formatDateTimeLocal(round.college_review_start),
      college_review_end: formatDateTimeLocal(round.college_review_end),
    }));
}

/**
 * A new round after the last one: it opens when the previous round (or the
 * first round) closes and runs two weeks, with every sub-type ticked.
 */
export function nextRoundDraft(
  drafts: RoundDraft[],
  firstRoundEnd: string | null,
  availableSubTypes: string[]
): RoundDraft {
  const previous = drafts[drafts.length - 1];
  const previousEnd = previous
    ? previous.application_end_date
    : formatDateTimeLocal(firstRoundEnd);
  const start = previousEnd ? new Date(previousEnd) : new Date();
  const end = new Date(start.getTime() + DEFAULT_ROUND_DAYS * DAY_MS);
  const daysAfterEnd = (days: number) =>
    formatDateTimeLocal(new Date(end.getTime() + days * DAY_MS).toISOString());
  const startLocal = formatDateTimeLocal(start.toISOString());
  return {
    round_number: previous ? previous.round_number + 1 : FIRST_EXTRA_ROUND,
    application_start_date: startLocal,
    application_end_date: formatDateTimeLocal(end.toISOString()),
    open_sub_types: [...availableSubTypes],
    professor_review_start: startLocal,
    professor_review_end: daysAfterEnd(DEFAULT_PROFESSOR_REVIEW_DAYS_AFTER_END),
    college_review_start: startLocal,
    college_review_end: daysAfterEnd(DEFAULT_COLLEGE_REVIEW_DAYS_AFTER_END),
  };
}

export function toggleSubType(draft: RoundDraft, code: string): RoundDraft {
  const open_sub_types = draft.open_sub_types.includes(code)
    ? draft.open_sub_types.filter(existing => existing !== code)
    : [...draft.open_sub_types, code];
  return { ...draft, open_sub_types };
}

/** Client-side checks before saving; the backend validates the same rules again. */
export function validateRoundDrafts(drafts: RoundDraft[]): string | null {
  for (const draft of drafts) {
    const label = `第 ${draft.round_number} 梯次`;
    if (!draft.application_start_date || !draft.application_end_date) {
      return `${label}需設定申請開始與截止時間`;
    }
    if (draft.open_sub_types.length === 0) {
      return `${label}至少需開放一個子類別`;
    }
    const pairs: Array<[string, string, string]> = [
      ["教授審查", draft.professor_review_start, draft.professor_review_end],
      ["學院審查", draft.college_review_start, draft.college_review_end],
    ];
    for (const [name, start, end] of pairs) {
      if (Boolean(start) !== Boolean(end)) {
        return `${label}的${name}期間需同時設定開始與結束時間`;
      }
    }
  }
  return null;
}

export function toRoundInputs(drafts: RoundDraft[]): ApplicationRoundInput[] {
  return drafts.map(draft => ({
    round_number: draft.round_number,
    application_start_date: dateTimeLocalToIso(draft.application_start_date) as string,
    application_end_date: dateTimeLocalToIso(draft.application_end_date) as string,
    open_sub_types: draft.open_sub_types,
    professor_review_start: dateTimeLocalToIso(draft.professor_review_start),
    professor_review_end: dateTimeLocalToIso(draft.professor_review_end),
    college_review_start: dateTimeLocalToIso(draft.college_review_start),
    college_review_end: dateTimeLocalToIso(draft.college_review_end),
  }));
}

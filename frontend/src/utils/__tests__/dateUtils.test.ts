/**
 * Tests for `frontend/src/utils/dateUtils.ts` ROC↔Western calendar
 * conversion helpers.
 *
 * These functions sit between the UI (which displays 民國年 e.g. "114")
 * and the API (which expects/returns Gregorian e.g. "2025"). A
 * silent bug here would either:
 *   - render the wrong year on every page using ROC display
 *   - send the wrong year to the backend on every API call
 *
 * Wave 6a97 covered the backend twins (taiwan_to_western_year etc.);
 * this is the frontend mirror. The pinned offset (+/- 1911) must
 * stay identical across both ends or every cross-layer test would
 * fail.
 *
 * 23 cases.
 */

import {
  fromROCYear,
  toROCYear,
  formatSemesterROC,
  formatSemesterROCText,
  generateAvailableSemesters,
  getCurrentSemesterROC,
  parseROCSemesterToWestern,
  isROCFormat,
} from "../dateUtils";

// ─── toROCYear / fromROCYear ─────────────────────────────────────────

describe("toROCYear / fromROCYear", () => {
  it("converts 2025 to 114 (current academic year)", () => {
    // Pin: matches backend taiwan_to_western_year(114) == 2025
    expect(toROCYear(2025)).toBe(114);
  });

  it("converts 1912 to 1 (ROC founding year)", () => {
    expect(toROCYear(1912)).toBe(1);
  });

  it("converts 114 to 2025 (reverse)", () => {
    expect(fromROCYear(114)).toBe(2025);
  });

  it("roundtrip is identity", () => {
    // Pin: any year passed through both converters returns itself.
    [1, 100, 114, 200].forEach((year) => {
      expect(toROCYear(fromROCYear(year))).toBe(year);
    });
  });
});

// ─── formatSemesterROC ───────────────────────────────────────────────

describe("formatSemesterROC", () => {
  it('converts "2025-1" to "114-1"', () => {
    expect(formatSemesterROC("2025-1")).toBe("114-1");
  });

  it('converts "2025-2" to "114-2"', () => {
    expect(formatSemesterROC("2025-2")).toBe("114-2");
  });

  it("returns input unchanged when no hyphen", () => {
    // Pin: malformed input returns AS-IS — function doesn't throw.
    // Caller must handle invalid input separately; pinned so a
    // defensive empty-string return doesn't get added.
    expect(formatSemesterROC("invalid")).toBe("invalid");
  });

  it("returns input unchanged when only year part", () => {
    // Pin: "2025-" has empty term → returns input unchanged.
    expect(formatSemesterROC("2025-")).toBe("2025-");
  });
});

// ─── formatSemesterROCText ──────────────────────────────────────────

describe("formatSemesterROCText", () => {
  it('formats "2025-1" as "民國114年第1學期"', () => {
    // Pin: the Chinese-text display format used in the admin and
    // student dropdowns.
    expect(formatSemesterROCText("2025-1")).toBe("民國114年第1學期");
  });

  it('formats "2025-2" as "民國114年第2學期"', () => {
    expect(formatSemesterROCText("2025-2")).toBe("民國114年第2學期");
  });

  it("falls through to generic term text for non-1/2 terms", () => {
    // Pin: term "3" → "第3學期" (generic fallback). NYCU usually
    // uses 1/2 but the function accepts any term integer.
    expect(formatSemesterROCText("2025-3")).toBe("民國114年第3學期");
  });

  it("returns input unchanged when malformed", () => {
    expect(formatSemesterROCText("oops")).toBe("oops");
  });
});

// ─── generateAvailableSemesters ─────────────────────────────────────

describe("generateAvailableSemesters", () => {
  it("returns sorted ROC semesters newest first", () => {
    // Pin: yearsBack=3, currentYear=2025 → 6 entries from years
    // 2025/2024/2023, sorted year-desc then term-desc.
    const out = generateAvailableSemesters(2025, 3);
    expect(out).toEqual([
      "114-2", "114-1",
      "113-2", "113-1",
      "112-2", "112-1",
    ]);
  });

  it("yearsBack=1 returns only current year's two semesters", () => {
    expect(generateAvailableSemesters(2025, 1)).toEqual(["114-2", "114-1"]);
  });

  it("yearsBack=0 returns empty array", () => {
    // Pin: zero years back → empty. Useful for "no historical
    // data" cases.
    expect(generateAvailableSemesters(2025, 0)).toEqual([]);
  });
});

// ─── getCurrentSemesterROC ──────────────────────────────────────────

describe("getCurrentSemesterROC", () => {
  // Lock Date.now() across tests
  afterEach(() => {
    jest.useRealTimers();
  });

  it("returns 1st semester in September", () => {
    // Pin: Sep–Jan = 1st semester (NYCU academic calendar). Sep
    // is the month most students start, so the dropdown should
    // default to 1st.
    jest.useFakeTimers().setSystemTime(new Date(2025, 8, 15)); // 0-indexed → September
    expect(getCurrentSemesterROC()).toBe("114-1");
  });

  it("returns 1st semester in January (still part of fall term)", () => {
    // Pin: January is technically the end of fall semester (per
    // the comment "Sep-Jan = 1st semester").
    jest.useFakeTimers().setSystemTime(new Date(2025, 0, 15));
    expect(getCurrentSemesterROC()).toBe("114-1");
  });

  it("returns 2nd semester in March", () => {
    // Pin: Feb–Aug = 2nd semester.
    jest.useFakeTimers().setSystemTime(new Date(2025, 2, 15));
    expect(getCurrentSemesterROC()).toBe("114-2");
  });

  it("returns 2nd semester in August (still part of spring term)", () => {
    // Pin: August is end of spring semester before the new
    // academic year starts in September.
    jest.useFakeTimers().setSystemTime(new Date(2025, 7, 15));
    expect(getCurrentSemesterROC()).toBe("114-2");
  });
});

// ─── parseROCSemesterToWestern ──────────────────────────────────────

describe("parseROCSemesterToWestern", () => {
  it('converts "114-1" to "2025-1"', () => {
    // Pin: reverse of formatSemesterROC — used when submitting
    // ROC-displayed value back to the API.
    expect(parseROCSemesterToWestern("114-1")).toBe("2025-1");
  });

  it('converts "114-2" to "2025-2"', () => {
    expect(parseROCSemesterToWestern("114-2")).toBe("2025-2");
  });

  it("returns input unchanged when malformed", () => {
    expect(parseROCSemesterToWestern("oops")).toBe("oops");
  });
});

// ─── isROCFormat ────────────────────────────────────────────────────

describe("isROCFormat", () => {
  it('"114-1" is ROC format (< 200)', () => {
    // Pin: ROC years are typically < 200 (current ~114). Western
    // years are >= 1912.
    expect(isROCFormat("114-1")).toBe(true);
  });

  it('"2025-1" is NOT ROC format (>= 200)', () => {
    expect(isROCFormat("2025-1")).toBe(false);
  });

  it("returns false for empty input", () => {
    // Pin: defensive — empty string → false (not crash).
    expect(isROCFormat("")).toBe(false);
  });

  it('"199-1" is still ROC format (boundary at 200)', () => {
    // Pin: 199 is below the 200 threshold. The threshold gives
    // us until ROC year 199 (= Western 2110) before the heuristic
    // breaks; pinned so a refactor moving the threshold doesn't
    // silently misclassify near-future dates.
    expect(isROCFormat("199-1")).toBe(true);
  });
});

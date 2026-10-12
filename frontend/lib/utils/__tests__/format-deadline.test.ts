import { formatDeadline } from "@/lib/utils/format-deadline";

describe("formatDeadline", () => {
  // Built from local wall-clock parts so the assertions hold in any TZ.
  const localDeadline = new Date(2026, 9, 31, 23, 59, 59);

  it("shows the date and the closing minute for a Date", () => {
    expect(formatDeadline(localDeadline)).toBe("2026/10/31 23:59");
  });

  it("converts an API UTC ISO string to local wall-clock time", () => {
    expect(formatDeadline(localDeadline.toISOString())).toBe(
      "2026/10/31 23:59"
    );
  });

  it("pads single-digit months, days, hours and minutes", () => {
    expect(formatDeadline(new Date(2026, 0, 5, 9, 5))).toBe("2026/01/05 09:05");
  });

  it.each([null, undefined, "", "not-a-date"])(
    "returns null for missing or invalid input (%p)",
    value => {
      expect(formatDeadline(value)).toBeNull();
    }
  );
});

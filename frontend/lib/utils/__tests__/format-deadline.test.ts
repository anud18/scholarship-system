import { formatDeadline } from "@/lib/utils/format-deadline";

describe("formatDeadline", () => {
  it("renders an API UTC instant in Taipei time to the minute", () => {
    // 15:59:59Z is 23:59 in Taipei (UTC+8), whatever the browser zone.
    expect(formatDeadline("2026-10-31T15:59:59Z")).toBe("2026/10/31 23:59");
  });

  it("rolls the date over when the Taipei offset crosses midnight", () => {
    expect(formatDeadline("2026-10-31T16:00:00+00:00")).toBe(
      "2026/11/01 00:00"
    );
  });

  it("accepts a Date and pads single-digit parts", () => {
    expect(formatDeadline(new Date("2026-01-05T01:05:00Z"))).toBe(
      "2026/01/05 09:05"
    );
  });

  it.each([null, undefined, "", "not-a-date"])(
    "returns null for missing or invalid input (%p)",
    value => {
      expect(formatDeadline(value)).toBeNull();
    }
  );
});

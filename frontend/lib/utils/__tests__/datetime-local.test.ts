import {
  dateTimeLocalToIso,
  formatDateTimeLocal,
} from "@/lib/utils/datetime-local";

const MS_PER_MINUTE = 60_000;

describe("dateTimeLocalToIso", () => {
  it("returns null for empty input so the API clears the field", () => {
    expect(dateTimeLocalToIso("")).toBeNull();
    expect(dateTimeLocalToIso(null)).toBeNull();
    expect(dateTimeLocalToIso(undefined)).toBeNull();
  });

  it("treats the picker value as local wall-clock time and emits a UTC instant", () => {
    const local = "2026-08-24T06:15";
    const iso = dateTimeLocalToIso(local);

    // The wall-clock time shifted by this machine's UTC offset.
    const offsetMinutes = new Date(local).getTimezoneOffset();
    const expectedMs =
      Date.UTC(2026, 7, 24, 6, 15) + offsetMinutes * MS_PER_MINUTE;

    expect(iso).toMatch(/Z$/);
    expect(new Date(iso as string).getTime()).toBe(expectedMs);
  });

  it("is idempotent for values that already carry an offset", () => {
    const iso = "2026-08-23T22:15:00.000Z";
    expect(dateTimeLocalToIso(iso)).toBe(iso);
  });

  it("rejects unparsable input instead of silently clearing the field", () => {
    expect(() => dateTimeLocalToIso("not-a-date")).toThrow("無效的日期時間");
  });
});

describe("formatDateTimeLocal", () => {
  it("returns an empty string for empty or invalid input", () => {
    expect(formatDateTimeLocal("")).toBe("");
    expect(formatDateTimeLocal(null)).toBe("");
    expect(formatDateTimeLocal(undefined)).toBe("");
    expect(formatDateTimeLocal("garbage")).toBe("");
  });

  it("round-trips a picker value through the API representation unchanged", () => {
    const local = "2026-08-24T06:15";
    expect(formatDateTimeLocal(dateTimeLocalToIso(local))).toBe(local);
  });

  it("renders an offset-bearing API value in local wall-clock time", () => {
    const iso = "2026-08-23T22:15:00+00:00";
    const expected = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    const expectedDate = `${expected.getFullYear()}-${pad(expected.getMonth() + 1)}-${pad(expected.getDate())}`;
    const expectedTime = `${pad(expected.getHours())}:${pad(expected.getMinutes())}`;
    expect(formatDateTimeLocal(iso)).toBe(`${expectedDate}T${expectedTime}`);
  });
});

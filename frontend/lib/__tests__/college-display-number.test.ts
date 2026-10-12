import {
  COLLEGE_DISPLAY_NUMBERS,
  formatCollegeName,
  sortByCollegeDisplayNumber,
} from "../college-display-number";

describe("college-display-number", () => {
  it("numbers 1..19, with only legacy code 8 aliasing A", () => {
    const { "8": legacy, ...rest } = COLLEGE_DISPLAY_NUMBERS;
    expect(legacy).toBe(COLLEGE_DISPLAY_NUMBERS.A);
    const numbers = Object.values(rest).sort((a, b) => a - b);
    expect(numbers).toEqual(Array.from({ length: 19 }, (_, i) => i + 1));
  });

  it("ignores prototype keys and nullish codes", () => {
    expect(formatCollegeName("constructor", "x")).toBe("x");
    expect(formatCollegeName(null, "x")).toBe("x");
    expect(formatCollegeName(undefined, "x")).toBe("x");
  });

  it("prefixes numbered colleges with 'N. '", () => {
    expect(formatCollegeName("C", "資訊學院")).toBe("6. 資訊學院");
    expect(formatCollegeName("2", "牙醫學院")).toBe("13. 牙醫學院");
  });

  it("leaves colleges outside the 對照表 unchanged", () => {
    expect(formatCollegeName("Y", "電資學院")).toBe("電資學院");
  });

  it("sorts by number without mutating, unnumbered last in original order", () => {
    const input = [
      { code: "Y", name: "電資學院" },
      { code: "C", name: "資訊學院" },
      { code: "J", name: "博雅書苑" },
      { code: "A", name: "人社院" },
    ];
    const sorted = sortByCollegeDisplayNumber(input);
    expect(sorted.map((c) => c.code)).toEqual(["A", "C", "Y", "J"]);
    expect(input.map((c) => c.code)).toEqual(["Y", "C", "J", "A"]);
  });
});

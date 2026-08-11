import { parseStudentNumbers } from "../parse-student-numbers";

describe("parseStudentNumbers", () => {
  it("parses a single student number", () => {
    expect(parseStudentNumbers(" 310460031 ")).toEqual({
      valid: ["310460031"],
      invalid: [],
    });
  });

  it("splits on commas, 頓號, semicolons and whitespace", () => {
    expect(
      parseStudentNumbers("S001,S002，S003、S004;S005；S006 S007\nS008"),
    ).toEqual({
      valid: ["S001", "S002", "S003", "S004", "S005", "S006", "S007", "S008"],
      invalid: [],
    });
  });

  it("dedupes preserving first-seen order", () => {
    expect(parseStudentNumbers("S002, S001, S002")).toEqual({
      valid: ["S002", "S001"],
      invalid: [],
    });
  });

  it("separates invalid tokens", () => {
    expect(parseStudentNumbers("S001, bad@@chars, ab")).toEqual({
      valid: ["S001"],
      invalid: ["bad@@chars", "ab"],
    });
  });

  it("returns empty lists for blank input", () => {
    expect(parseStudentNumbers("  \n ,, ")).toEqual({ valid: [], invalid: [] });
  });
});

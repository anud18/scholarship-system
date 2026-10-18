import {
  nextRoundDraft,
  toggleSubType,
  toRoundDrafts,
  toRoundInputs,
  validateRoundDrafts,
  type RoundDraft,
} from "../application-rounds-form";

const draft = (overrides: Partial<RoundDraft> = {}): RoundDraft => ({
  round_number: 2,
  application_start_date: "2026-11-01T09:00",
  application_end_date: "2026-11-15T17:00",
  open_sub_types: ["nstc"],
  professor_review_start: "",
  professor_review_end: "",
  college_review_start: "",
  college_review_end: "",
  ...overrides,
});

describe("application-rounds-form", () => {
  it("turns API rounds into sorted drafts", () => {
    const drafts = toRoundDrafts([
      {
        round_number: 3,
        application_start_date: "2026-12-01T01:00:00Z",
        application_end_date: "2026-12-10T01:00:00Z",
        open_sub_types: ["moe_1w"],
      },
      {
        round_number: 2,
        application_start_date: "2026-11-01T01:00:00Z",
        application_end_date: "2026-11-10T01:00:00Z",
        open_sub_types: ["nstc"],
        college_review_start: null,
      },
    ]);
    expect(drafts.map(d => d.round_number)).toEqual([2, 3]);
    expect(drafts[0].college_review_start).toBe("");
    expect(drafts[0].application_start_date).toMatch(/^2026-11-0\dT\d\d:\d\d$/);
  });

  it("numbers a new round after the last and starts it when the previous one ends", () => {
    const first = nextRoundDraft([], "2026-10-31T16:00:00Z", ["nstc", "moe_1w"]);
    expect(first.round_number).toBe(2);
    expect(first.open_sub_types).toEqual(["nstc", "moe_1w"]);
    expect(new Date(first.application_start_date).toISOString()).toBe("2026-10-31T16:00:00.000Z");

    const second = nextRoundDraft([first], null, ["nstc"]);
    expect(second.round_number).toBe(3);
    expect(second.application_start_date).toBe(first.application_end_date);
  });

  it("toggles sub-types without mutating the draft", () => {
    const original = draft();
    const added = toggleSubType(original, "moe_1w");
    expect(added.open_sub_types).toEqual(["nstc", "moe_1w"]);
    expect(original.open_sub_types).toEqual(["nstc"]);
    expect(toggleSubType(added, "nstc").open_sub_types).toEqual(["moe_1w"]);
  });

  it("validates required fields and review pairs", () => {
    expect(validateRoundDrafts([draft()])).toBeNull();
    expect(validateRoundDrafts([draft({ application_end_date: "" })])).toContain("申請開始與截止時間");
    expect(validateRoundDrafts([draft({ open_sub_types: [] })])).toContain("至少需開放一個子類別");
    expect(validateRoundDrafts([draft({ college_review_start: "2026-11-16T09:00" })])).toContain(
      "學院審查期間需同時設定"
    );
  });

  it("serializes drafts as UTC instants, blank review windows as null", () => {
    const [input] = toRoundInputs([draft({ professor_review_start: "2026-11-16T09:00", professor_review_end: "2026-11-20T17:00" })]);
    expect(input.round_number).toBe(2);
    expect(input.application_start_date).toBe(new Date("2026-11-01T09:00").toISOString());
    expect(input.professor_review_end).toBe(new Date("2026-11-20T17:00").toISOString());
    expect(input.college_review_start).toBeNull();
    expect(input.open_sub_types).toEqual(["nstc"]);
  });
});

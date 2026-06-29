import {
  parseQuotaSheet,
  type KnownCollege,
  type KnownSubType,
} from "@/lib/quota/parse-quota-sheet";

const COLLEGES: KnownCollege[] = [
  { code: "C", name: "資訊" },
  { code: "E", name: "電機", nameEn: "ECE" },
];
const SUBTYPES: KnownSubType[] = [
  { code: "nstc", label: "國科會" },
  { code: "moe_1w", label: "教育部1萬" },
];
const sheet = (...rows: unknown[][]) => rows;

describe("parseQuotaSheet", () => {
  it("parses a valid matrix by college code and sub_type code", () => {
    const { quotas, errors, warnings } = parseQuotaSheet(
      sheet(["", "C", "E"], ["nstc", 5, 4], ["moe_1w", 3, 2]),
      COLLEGES, SUBTYPES, {},
    );
    expect(errors).toEqual([]);
    expect(warnings).toEqual([]);
    expect(quotas).toEqual({ nstc: { C: 5, E: 4 }, moe_1w: { C: 3, E: 2 } });
  });

  it("treats blank cells and absent columns/rows as 0", () => {
    const { quotas, errors } = parseQuotaSheet(
      sheet(["", "C"], ["nstc", ""]),
      COLLEGES, SUBTYPES, {},
    );
    expect(errors).toEqual([]);
    expect(quotas).toEqual({ nstc: { C: 0, E: 0 }, moe_1w: { C: 0, E: 0 } });
  });

  it("matches headers and rows by name/label as well as code", () => {
    const { quotas } = parseQuotaSheet(
      sheet(["", "資訊", "ECE"], ["國科會", 7, 8]),
      COLLEGES, SUBTYPES, {},
    );
    expect(quotas.nstc).toEqual({ C: 7, E: 8 });
  });

  it("errors on an unknown college column", () => {
    const { errors } = parseQuotaSheet(sheet(["", "ZZ"], ["nstc", 1]), COLLEGES, SUBTYPES, {});
    expect(errors.some(e => e.kind === "college")).toBe(true);
  });

  it("errors on an unknown sub_type row", () => {
    const { errors } = parseQuotaSheet(sheet(["", "C"], ["ghost", 1]), COLLEGES, SUBTYPES, {});
    expect(errors.some(e => e.kind === "subType")).toBe(true);
  });

  it("errors on negative, fractional, non-numeric, and >1000 cells", () => {
    const { errors } = parseQuotaSheet(
      sheet(["", "C", "E"], ["nstc", -1, 2.5], ["moe_1w", "x", 1001]),
      COLLEGES, SUBTYPES, {},
    );
    expect(errors.filter(e => e.kind === "cell")).toHaveLength(4);
  });

  it("errors on duplicate college columns and sub_type rows", () => {
    const { errors } = parseQuotaSheet(
      sheet(["", "C", "C"], ["nstc", 1, 2], ["nstc", 3, 4]),
      COLLEGES, SUBTYPES, {},
    );
    expect(errors.some(e => e.kind === "duplicate")).toBe(true);
  });

  it("warns when an import zeroes a cell that currently has a quota", () => {
    const { warnings } = parseQuotaSheet(
      sheet(["", "C", "E"], ["nstc", 0, 4]),
      COLLEGES, SUBTYPES, { nstc: { C: 5, E: 4 } },
    );
    expect(warnings.some(w => w.kind === "zeroed")).toBe(true);
  });
});

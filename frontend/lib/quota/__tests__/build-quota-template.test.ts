import { buildQuotaMatrixRows } from "@/lib/quota/build-quota-template";
import {
  parseQuotaSheet,
  type KnownCollege,
  type KnownSubType,
} from "@/lib/quota/parse-quota-sheet";

const COLLEGES: KnownCollege[] = [{ code: "C", name: "資訊" }, { code: "E", name: "電機" }];
const SUBTYPES: KnownSubType[] = [{ code: "nstc" }, { code: "moe_1w" }];

describe("buildQuotaMatrixRows", () => {
  it("round-trips: build → parse reproduces the full matrix", () => {
    const quotas = { nstc: { C: 5, E: 4 }, moe_1w: { C: 3, E: 0 } };
    const rows = buildQuotaMatrixRows(quotas, COLLEGES, SUBTYPES);
    const { quotas: parsed, errors } = parseQuotaSheet(rows, COLLEGES, SUBTYPES, {});
    expect(errors).toEqual([]);
    expect(parsed).toEqual(quotas);
  });

  it("emits a header row of college names and pre-fills 0 for missing cells", () => {
    const rows = buildQuotaMatrixRows({ nstc: { C: 9 } }, COLLEGES, SUBTYPES);
    expect(rows[0].slice(1)).toEqual(["資訊", "電機"]);
    expect(rows[1]).toEqual(["nstc", 9, 0]);
    expect(rows[2]).toEqual(["moe_1w", 0, 0]);
  });
});

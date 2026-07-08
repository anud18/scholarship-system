/**
 * E2E spec: the phd moe_1w sub-type card label reads
 * 「教育部博士生獎學金 (指導教授配合款每月 $5000 元)」.
 *
 * Why this exists: the student wizard (ScholarshipApplicationStep) renders
 * the 選擇申請項目 cards verbatim from `eligible_sub_types[].label`, which the
 * backend reads from scholarship_sub_type_configs.name. The label was renamed
 * from the stale 「指導教授配合款一萬」 wording, and because the seed only
 * INSERTs when the row is missing, deployed DBs kept the old name until
 * migration update_moe_1w_label_001 rewrote it in place. This spec pins both
 * layers so the wording can't silently regress:
 *
 *   (a) DB   — scholarship_sub_type_configs.name for (phd, moe_1w) is the
 *              new wording (the migration/seed actually landed), and
 *   (b) API  — GET /api/v1/scholarships/eligible as stuphd001 (本國籍,
 *              三年級 → eligible for moe_1w) returns that exact label in
 *              eligible_sub_types, which is the string the wizard card shows.
 *
 * Pinned invariants:
 * - The zh label is exactly 教育部博士生獎學金 (指導教授配合款每月 $5000 元).
 * - Neither the stale 「一萬」 nor the interim 「每月五千」 wording survives
 *   anywhere in the phd sub-type labels served to students.
 */
import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";
import { apiAs } from "../helpers/api";
import { pool } from "../helpers/db";
import { attachRunState, newRunState, pushTrace, type RunState } from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";

const STUDENT_ID = "stuphd001";
const SCHOLARSHIP_CODE = "phd";
const SUB_TYPE = "moe_1w";
const EXPECTED_LABEL = "教育部博士生獎學金 (指導教授配合款每月 $5000 元)";
const STALE_WORDINGS = ["指導教授配合款一萬", "指導教授配合款每月五千"];

interface EligibleSubType {
  value: string | null;
  label: string;
  label_en: string;
  is_default?: boolean;
}

interface EligibleScholarship {
  code: string;
  eligible_sub_types: EligibleSubType[];
}

test.describe("phd moe_1w sub-type label wording", () => {
  let runState: RunState;

  test.beforeEach(() => {
    runState = newRunState();
  });

  test.afterEach(async ({}, testInfo) => {
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test("@nightly DB + /scholarships/eligible serve 每月 $5000 元 label for moe_1w", async ({
    browser,
  }) => {
    // (a) DB layer — the source of truth the wizard label is built from.
    // (scholarship_type_id, sub_type_code) has no unique constraint, so pin
    // exactly ONE active row — a duplicate would make the backend's
    // translation lookup (last-write-wins) nondeterministic.
    const { rows } = await pool.query<{ name: string }>(
      `SELECT sstc.name
         FROM scholarship_sub_type_configs sstc
         JOIN scholarship_types st ON st.id = sstc.scholarship_type_id
        WHERE st.code = $1 AND sstc.sub_type_code = $2 AND sstc.is_active = TRUE`,
      [SCHOLARSHIP_CODE, SUB_TYPE],
    );
    expect(
      rows.length,
      `expected exactly one ACTIVE scholarship_sub_type_configs row for (${SCHOLARSHIP_CODE}, ${SUB_TYPE}), got ${rows.length} — seed/migration missing or duplicated`,
    ).toBe(1);
    expect(
      rows[0].name,
      "scholarship_sub_type_configs.name must carry the 每月 $5000 元 wording (migration update_moe_1w_label_001)",
    ).toBe(EXPECTED_LABEL);

    // (b) API layer — the exact payload ScholarshipApplicationStep renders as
    // the 選擇申請項目 card text (subType.label, verbatim).
    const studentLogin = await loginAs(browser, STUDENT_ID);
    pushTrace(runState, studentLogin.traceId);

    const eligibleRes = await apiAs<{
      success: boolean;
      data: EligibleScholarship[];
    }>(studentLogin.token, "GET", "/scholarships/eligible");
    pushTrace(runState, eligibleRes.traceId);
    expect(
      eligibleRes.ok,
      `GET /scholarships/eligible failed: HTTP ${eligibleRes.status} body=${JSON.stringify(
        eligibleRes.body,
      )}`,
    ).toBe(true);
    expect(
      eligibleRes.body?.success,
      `ApiResponse.success must be true: body=${JSON.stringify(eligibleRes.body)}`,
    ).toBe(true);
    expect(
      Array.isArray(eligibleRes.body.data),
      `ApiResponse.data must be a scholarship array: body=${JSON.stringify(eligibleRes.body)}`,
    ).toBe(true);

    const phd = eligibleRes.body.data.find((s) => s.code === SCHOLARSHIP_CODE);
    expect(phd, `phd scholarship missing from /scholarships/eligible for ${STUDENT_ID}`).toBeTruthy();

    const moe1w = phd!.eligible_sub_types.find((st) => st.value === SUB_TYPE);
    expect(
      moe1w,
      `moe_1w missing from eligible_sub_types — ${STUDENT_ID} (本國籍/三年級) should qualify; got ${JSON.stringify(
        phd!.eligible_sub_types,
      )}`,
    ).toBeTruthy();
    expect(moe1w!.label, "the wizard card text (subType.label)").toBe(EXPECTED_LABEL);

    // No phd sub-type label may still carry the stale wordings.
    for (const subType of phd!.eligible_sub_types) {
      for (const stale of STALE_WORDINGS) {
        expect(
          subType.label.includes(stale),
          `stale wording 「${stale}」 leaked back into sub-type ${subType.value}: ${subType.label}`,
        ).toBe(false);
      }
    }

    await studentLogin.context.close();
  });
});

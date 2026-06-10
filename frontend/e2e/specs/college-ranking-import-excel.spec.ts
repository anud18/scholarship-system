/**
 * E2E spec: college imports ranking data from Excel (JSON body endpoint).
 *
 * Tests POST /college-review/rankings/{ranking_id}/import-excel.
 * This is a pure API spec — the endpoint takes a JSON body (not multipart
 * file upload), so no browser file-dialog interaction is needed.
 *
 * Actor mapping (all from seed + mock SIS API):
 *   csphd0001  → student, std_academyno="C", std_stdcode="csphd0001"
 *   cs_college → college reviewer, college_code="C"
 *   "C" == "C" → application appears in cs_college's ranking
 *
 * Flow:
 *   beforeAll:
 *     1. csphd0001 submits phd/nstc application
 *     2. cs_college creates ranking (force_new=true) — auto-includes the app
 *   Test 1: GET ranking → items array has csphd0001, college_rejected=false
 *   Test 2: POST import-excel [rank=1] → updated_count=1, rejected_count=0
 *   Test 3: POST import-excel [rank="N"] → updated_count=1, rejected_count=1
 *   Test 4: GET ranking after "N" import → college_rejected=true
 *   afterAll: SQL cleanup (ranking items → ranking → application)
 *
 * Issue #76 AC: college import-excel spec.
 */
import { test, expect } from "@playwright/test";
import { apiAs } from "../helpers/api";
import { deleteApplicationCascade, getActiveConfig, pool } from "../helpers/db";
import {
  attachRunState,
  newRunState,
  pushTrace,
  type RunState,
} from "../helpers/runState";
import { captureDiagnostics } from "../helpers/diagnose";
import { BACKEND_URL } from "../helpers/env";

const STUDENT_NYCU_ID = "csphd0001";
const STUDENT_STD_CODE = "csphd0001"; // std_stdcode returned by mock SIS API
const STUDENT_NAME = "王博士研究生"; // std_cname returned by mock SIS API
const COLLEGE_NYCU_ID = "cs_college";
const SCHOLARSHIP_CODE = "phd";
const SUB_TYPE = "nstc";

test.describe.configure({ mode: "serial" });

async function getApiToken(nycuId: string): Promise<string> {
  const r = await fetch(`${BACKEND_URL}/api/v1/auth/mock-sso/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nycu_id: nycuId }),
  });
  const body = (await r.json()) as {
    success?: boolean;
    data?: { access_token?: string };
    message?: string;
  };
  if (!r.ok || !body.data?.access_token) {
    throw new Error(
      `login failed for ${nycuId}: HTTP ${r.status} ${body.message ?? ""}`,
    );
  }
  return body.data.access_token;
}

test.describe("College ranking import-excel @nightly", () => {
  let runState: RunState;
  let rankingId: number | undefined;
  let fixtureAppId: string | undefined;
  let fixtureAppDbId: number | undefined;
  let collegeToken: string;

  test.beforeAll(async () => {
    const config = await getActiveConfig(SCHOLARSHIP_CODE);

    // Pre-clean leftover csphd0001 phd applications to avoid unique conflicts.
    const { rows: existing } = await pool.query<{ app_id: string }>(
      `SELECT a.app_id FROM applications a
       JOIN users u ON u.id = a.user_id
       JOIN scholarship_types st ON st.id = a.scholarship_type_id
       WHERE u.nycu_id = $1 AND st.code = $2`,
      [STUDENT_NYCU_ID, SCHOLARSHIP_CODE],
    );
    for (const { app_id } of existing) {
      await deleteApplicationCascade(app_id).catch(() => undefined);
    }

    // Pre-clean any unfinalized nstc rankings so force_new=true always
    // creates a fresh row (avoids stale-state interference from prior runs).
    await pool
      .query(
        `DELETE FROM college_ranking_items
           WHERE ranking_id IN (
             SELECT id FROM college_rankings
              WHERE scholarship_type_id = $1
                AND sub_type_code = $2
                AND is_finalized = false
           )`,
        [config.scholarship_type_id, SUB_TYPE],
      )
      .catch(() => undefined);
    await pool
      .query(
        `DELETE FROM college_rankings
           WHERE scholarship_type_id = $1
             AND sub_type_code = $2
             AND is_finalized = false`,
        [config.scholarship_type_id, SUB_TYPE],
      )
      .catch(() => undefined);

    const studentToken = await getApiToken(STUDENT_NYCU_ID);
    collegeToken = await getApiToken(COLLEGE_NYCU_ID);

    // 1. csphd0001 submits phd/nstc application.
    const createRes = await apiAs<{
      success: boolean;
      data: { id: number; app_id: string };
    }>(studentToken, "POST", "/applications?is_draft=false", {
      scholarship_type: SCHOLARSHIP_CODE,
      configuration_id: config.id,
      scholarship_subtype_list: [SUB_TYPE],
      sub_type_preferences: [SUB_TYPE],
      form_data: { fields: {}, documents: [] },
      agree_terms: true,
    });
    if (!createRes.ok || !createRes.body.success) {
      throw new Error(
        `import-excel beforeAll: create application failed HTTP ${createRes.status} body=${JSON.stringify(createRes.body)}`,
      );
    }
    fixtureAppDbId = createRes.body.data.id;
    fixtureAppId = createRes.body.data.app_id;

    // 2. cs_college creates ranking (force_new=true → always a fresh row).
    // The service auto-includes csphd0001's submitted application because
    // std_academyno="C" matches cs_college.college_code="C" and
    // ApplicationStatus.submitted is in the valid_ranking_statuses list.
    const rankRes = await apiAs<{
      success: boolean;
      data: { id: number };
    }>(collegeToken, "POST", "/college-review/rankings", {
      scholarship_type_id: config.scholarship_type_id,
      sub_type_code: SUB_TYPE,
      academic_year: config.academic_year,
      semester: config.semester,
      force_new: true,
    });
    if (!rankRes.ok || !rankRes.body.success) {
      throw new Error(
        `import-excel beforeAll: create ranking failed HTTP ${rankRes.status} body=${JSON.stringify(rankRes.body)}`,
      );
    }
    rankingId = rankRes.body.data.id;
  });

  test.beforeEach(() => {
    runState = newRunState();
    if (fixtureAppId) runState.appId = fixtureAppId;
  });

  test.afterEach(async ({}, testInfo) => {
    await captureDiagnostics(testInfo, runState);
    await attachRunState(testInfo, runState);
  });

  test.afterAll(async () => {
    if (rankingId !== undefined) {
      await pool
        .query("DELETE FROM college_ranking_items WHERE ranking_id = $1", [
          rankingId,
        ])
        .catch(() => undefined);
      await pool
        .query("DELETE FROM college_rankings WHERE id = $1", [rankingId])
        .catch(() => undefined);
    }
    if (fixtureAppId) {
      await deleteApplicationCascade(fixtureAppId).catch(() => undefined);
    }
  });

  test(
    "@nightly GET ranking → items include csphd0001, college_rejected=false",
    async () => {
      const res = await apiAs<{
        success: boolean;
        data: {
          items: Array<{
            rank_position: number;
            student_id: string;
            status: string;
            college_rejected: boolean;
            application: { id: number };
          }>;
        };
      }>(collegeToken, "GET", `/college-review/rankings/${rankingId}`);
      pushTrace(runState, res.traceId);

      expect(
        res.ok,
        `GET ranking failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
      ).toBe(true);
      expect(res.body.success).toBe(true);

      const items = res.body.data.items ?? [];
      expect(
        items.length,
        `expected at least 1 item in ranking ${rankingId}, got ${items.length}`,
      ).toBeGreaterThan(0);

      const found = items.find(
        (item) => item.application.id === fixtureAppDbId,
      );
      expect(
        found,
        `csphd0001 app (db_id=${fixtureAppDbId}) not in ranking items. ` +
          `application ids: [${items.map((i) => i.application.id).join(", ")}]`,
      ).toBeDefined();
      expect(found!.student_id).toBe(STUDENT_STD_CODE);
      // Freshly created item has no college rejection.
      expect(found!.college_rejected).toBe(false);
    },
  );

  test(
    "@nightly POST import-excel [rank=1] → updated_count=1, rejected_count=0",
    async () => {
      const res = await apiAs<{
        success: boolean;
        data: {
          ranking_id: number;
          updated_count: number;
          rejected_count: number;
          total_imported: number;
        };
      }>(
        collegeToken,
        "POST",
        `/college-review/rankings/${rankingId}/import-excel`,
        [
          {
            student_id: STUDENT_STD_CODE,
            student_name: STUDENT_NAME,
            rank_position: 1,
          },
        ],
      );
      pushTrace(runState, res.traceId);

      expect(
        res.ok,
        `import-excel failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
      ).toBe(true);
      expect(res.body.success).toBe(true);
      expect(res.body.data.ranking_id).toBe(rankingId);
      expect(res.body.data.updated_count).toBe(1);
      expect(res.body.data.rejected_count).toBe(0);
      expect(res.body.data.total_imported).toBe(1);
    },
  );

  test(
    "@nightly POST import-excel [rank='N'] → updated_count=1, rejected_count=1",
    async () => {
      const res = await apiAs<{
        success: boolean;
        data: {
          ranking_id: number;
          updated_count: number;
          rejected_count: number;
          total_imported: number;
        };
      }>(
        collegeToken,
        "POST",
        `/college-review/rankings/${rankingId}/import-excel`,
        [
          {
            student_id: STUDENT_STD_CODE,
            student_name: STUDENT_NAME,
            rank_position: "N",
          },
        ],
      );
      pushTrace(runState, res.traceId);

      expect(
        res.ok,
        `import-excel (N) failed: HTTP ${res.status} body=${JSON.stringify(res.body)}`,
      ).toBe(true);
      expect(res.body.success).toBe(true);
      expect(res.body.data.updated_count).toBe(1);
      expect(res.body.data.rejected_count).toBe(1);
    },
  );

  test(
    "@nightly GET ranking after N import → csphd0001 college_rejected=true",
    async () => {
      const res = await apiAs<{
        success: boolean;
        data: {
          items: Array<{
            student_id: string;
            college_rejected: boolean;
            status: string;
            application: { id: number };
          }>;
        };
      }>(collegeToken, "GET", `/college-review/rankings/${rankingId}`);
      pushTrace(runState, res.traceId);

      expect(res.ok, `GET ranking failed HTTP ${res.status}`).toBe(true);
      expect(res.body.success).toBe(true);

      const items = res.body.data.items ?? [];
      const found = items.find(
        (item) => item.application.id === fixtureAppDbId,
      );
      expect(found, "csphd0001 item not found post-N-import").toBeDefined();
      // After importing with "N", the item should be flagged as college_rejected.
      expect(found!.college_rejected).toBe(true);
      // Status remains "ranked" — "N" only sets the college_rejected flag.
      expect(found!.status).toBe("ranked");
    },
  );
});

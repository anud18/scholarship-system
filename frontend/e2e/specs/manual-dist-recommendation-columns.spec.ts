/**
 * Scenario: 教授推薦 / 學院推薦 recommendation columns on the admin manual
 * distribution grid (管理員手動分發).
 *
 * The feature adds two columns between 申請類別 and the 核配 checkbox group:
 *
 *   教授推薦 — per-sub-type verdict chips built from professor review items
 *     ("國科會: 推薦" emerald / "教育部: 不推薦" red, reviewer comment in the
 *     title attr); an amber "審核中" chip when the config requires a professor
 *     recommendation but no professor review exists yet; "—" when there is no
 *     professor step at all.
 *   學院推薦 — ALWAYS leads with the ranking verdict chip: "排名: 推薦" (emerald)
 *     normally, "排名: 不推薦" (red) when the ranking item has college_rejected
 *     (the 排序 cell then shows a red "N") — followed by any per-sub-type
 *     college-role review chips.
 *
 * Admin-role reviews are excluded from BOTH columns — the grid IS the admin
 * decision surface.
 *
 * This spec seeds four ranked applications (all college C, scholarship phd /
 * config 5 / 114 全年) plus one finalized college ranking directly via SQL,
 * logs in as admin, opens the manual-distribution grid, asserts the chips, and
 * saves labeled screenshot evidence. It only READS the grid — no allocate /
 * finalize is triggered, so it leaves distribution state untouched.
 */
import { test, expect, type Locator, type Page } from "@playwright/test";
import { authContext } from "../helpers/auth";
import { FRONTEND_URL } from "../helpers/env";
import { pool } from "../helpers/db";
import * as fs from "fs";
import * as path from "path";

const SCHOLARSHIP_TYPE_ID = 2;
const CONFIG_ID = 5;
const ACADEMIC_YEAR = 114;
const COLLEGE_CODE = "C";
const RANKING_NAME = "E2E-REC-DISPLAY"; // idempotency tag for our seeded ranking
const APP_PREFIX = "APP-114-0-9"; // our app_ids: APP-114-0-9000x

const PROFESSOR_ID = 12; // cs_professor
const COLLEGE_REVIEWER_ID = 13; // cs_college (college_code C)
const ADMIN_ID = 1; // admin — must NOT appear in either column

const EVIDENCE_DIR = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
  "docs",
  "staging-tests",
  "2026-07-22",
  "01-manual-dist-recommendation"
);

interface SeedStudent {
  appId: string;
  userId: number;
  nycuId: string;
  name: string;
  rank: number;
  renewal: boolean;
  collegeRejected: boolean;
}

const STUDENTS: SeedStudent[] = [
  // App1 — professor partial_approve (nstc approve, moe_1w reject) + college approve(nstc)
  {
    appId: "APP-114-0-90001",
    userId: 14,
    nycuId: "csphd0001",
    name: "王博士研究生",
    rank: 1,
    renewal: false,
    collegeRejected: false,
  },
  // App2 — NO reviews → 教授推薦 = 審核中
  {
    appId: "APP-114-0-90002",
    userId: 15,
    nycuId: "csphd0002",
    name: "陳AI博士",
    rank: 2,
    renewal: false,
    collegeRejected: false,
  },
  // App3 — professor approve(nstc, moe_1w); college_rejected → red N + 排名: 不推薦
  {
    appId: "APP-114-0-90003",
    userId: 16,
    nycuId: "csphd0003",
    name: "林機器學習博士",
    rank: 3,
    renewal: false,
    collegeRejected: true,
  },
  // App4 — renewal; ONLY an admin reject review → excluded → 教授推薦 = 審核中
  {
    appId: "APP-114-0-90004",
    userId: 6,
    nycuId: "stuphd001",
    name: "王博士",
    rank: 4,
    renewal: true,
    collegeRejected: false,
  },
];

const ADMIN_ONLY_COMMENT = "admin 審查不應顯示";
const PROF_MOE_REJECT_COMMENT = "名額有限，僅推薦國科會";

test.describe.configure({ mode: "serial" });

async function purgeSeed(): Promise<void> {
  const { rows } = await pool.query<{ id: number }>(
    "SELECT id FROM applications WHERE app_id LIKE $1",
    [`${APP_PREFIX}%`]
  );
  const ids = rows.map(r => r.id);
  if (ids.length > 0) {
    await pool.query(
      `DELETE FROM application_review_items
         WHERE review_id IN (SELECT id FROM application_reviews WHERE application_id = ANY($1))`,
      [ids]
    );
    await pool.query("DELETE FROM application_reviews WHERE application_id = ANY($1)", [ids]);
    await pool.query("DELETE FROM college_ranking_items WHERE application_id = ANY($1)", [ids]);
  }
  await pool.query(
    "DELETE FROM college_ranking_items WHERE ranking_id IN (SELECT id FROM college_rankings WHERE ranking_name = $1)",
    [RANKING_NAME]
  );
  await pool.query("DELETE FROM college_rankings WHERE ranking_name = $1", [RANKING_NAME]);
  if (ids.length > 0) {
    await pool.query("DELETE FROM applications WHERE id = ANY($1)", [ids]);
  }
}

async function insertReview(
  applicationId: number,
  reviewerId: number,
  recommendation: string,
  items: Array<{ sub_type_code: string; recommendation: string; comments: string | null }>
): Promise<void> {
  const { rows } = await pool.query<{ id: number }>(
    `INSERT INTO application_reviews (application_id, reviewer_id, recommendation, reviewed_at, created_at)
       VALUES ($1, $2, $3, now(), now()) RETURNING id`,
    [applicationId, reviewerId, recommendation]
  );
  const reviewId = rows[0].id;
  for (const item of items) {
    await pool.query(
      `INSERT INTO application_review_items (review_id, sub_type_code, recommendation, comments)
         VALUES ($1, $2, $3, $4)`,
      [reviewId, item.sub_type_code, item.recommendation, item.comments]
    );
  }
}

async function seed(): Promise<void> {
  await purgeSeed();

  // 1. Applications
  for (const s of STUDENTS) {
    const studentData = {
      std_academyno: COLLEGE_CODE,
      std_stdcode: s.nycuId,
      std_cname: s.name,
      trm_academyname: "資訊學院",
      trm_depname: "資訊工程學系",
      trm_termcount: "3",
      std_nation: "中華民國",
    };
    await pool.query(
      `INSERT INTO applications
         (app_id, user_id, scholarship_type_id, scholarship_configuration_id,
          scholarship_subtype_list, sub_type_selection_mode, sub_scholarship_type,
          is_renewal, renewal_year, status, review_stage, academic_year, semester,
          student_data, agree_terms, created_at, updated_at)
       VALUES ($1, $2, $3, $4,
          $5::json, 'multiple', 'nstc',
          $6, $7, 'submitted', 'college_ranked', $8, NULL,
          $9::json, true, now(), now())`,
      [
        s.appId,
        s.userId,
        SCHOLARSHIP_TYPE_ID,
        CONFIG_ID,
        JSON.stringify(["nstc", "moe_1w"]),
        s.renewal,
        s.renewal ? ACADEMIC_YEAR : null,
        ACADEMIC_YEAR,
        JSON.stringify(studentData),
      ]
    );
  }

  const { rows: appRows } = await pool.query<{ id: number; app_id: string }>(
    "SELECT id, app_id FROM applications WHERE app_id = ANY($1)",
    [STUDENTS.map(s => s.appId)]
  );
  const appDbId: Record<string, number> = {};
  for (const r of appRows) appDbId[r.app_id] = r.id;

  // 2. One finalized college ranking (college C, phd, 114, yearly)
  const { rows: rk } = await pool.query<{ id: number }>(
    `INSERT INTO college_rankings
       (scholarship_type_id, sub_type_code, academic_year, semester, college_code,
        ranking_name, total_applications, total_quota, is_finalized, ranking_status,
        finalized_at, finalized_by, created_by, created_at, updated_at)
     VALUES ($1, 'default', $2, NULL, $3, $4, $5, 5, true, 'finalized',
        now(), $6, $6, now(), now())
     RETURNING id`,
    [SCHOLARSHIP_TYPE_ID, ACADEMIC_YEAR, COLLEGE_CODE, RANKING_NAME, STUDENTS.length, COLLEGE_REVIEWER_ID]
  );
  const rankingId = rk[0].id;

  // 3. Ranking items (rank 1-4; App3 college_rejected)
  for (const s of STUDENTS) {
    await pool.query(
      `INSERT INTO college_ranking_items
         (ranking_id, application_id, rank_position, college_rejected, is_supplementary,
          status, created_at, updated_at)
       VALUES ($1, $2, $3, $4, false, 'ranked', now(), now())`,
      [rankingId, appDbId[s.appId], s.rank, s.collegeRejected]
    );
  }

  // 4. Reviews
  // App1: professor partial_approve (nstc approve / moe_1w reject) + college approve(nstc)
  await insertReview(appDbId["APP-114-0-90001"], PROFESSOR_ID, "partial_approve", [
    { sub_type_code: "nstc", recommendation: "approve", comments: null },
    { sub_type_code: "moe_1w", recommendation: "reject", comments: PROF_MOE_REJECT_COMMENT },
  ]);
  await insertReview(appDbId["APP-114-0-90001"], COLLEGE_REVIEWER_ID, "approve", [
    { sub_type_code: "nstc", recommendation: "approve", comments: "學院同意" },
  ]);
  // App2: (no reviews)
  // App3: professor approve both sub-types
  await insertReview(appDbId["APP-114-0-90003"], PROFESSOR_ID, "approve", [
    { sub_type_code: "nstc", recommendation: "approve", comments: null },
    { sub_type_code: "moe_1w", recommendation: "approve", comments: null },
  ]);
  // App4: ADMIN reject only — MUST NOT appear in either column
  await insertReview(appDbId["APP-114-0-90004"], ADMIN_ID, "reject", [
    { sub_type_code: "nstc", recommendation: "reject", comments: ADMIN_ONLY_COMMENT },
  ]);
}

/** Locate the data <tr> whose 學號 cell holds the given nycu_id (unique per row). */
function rowFor(page: Page, nycuId: string): Locator {
  return page.locator("tbody tr").filter({ hasText: nycuId });
}

/** 教授推薦 is the 3rd column (index 2); 學院推薦 is the 4th (index 3). */
function profCell(row: Locator): Locator {
  return row.locator("td").nth(2);
}
function collegeCell(row: Locator): Locator {
  return row.locator("td").nth(3);
}

test.describe("Admin manual distribution — 教授推薦 / 學院推薦 columns", () => {
  test.beforeAll(async () => {
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    await seed();
  });

  test.afterAll(async () => {
    await purgeSeed();
  });

  test("recommendation chips render per role, admin reviews hidden, college_rejected shows red N", async ({
    browser,
  }) => {
    const context = await browser.newContext({
      baseURL: FRONTEND_URL,
      viewport: { width: 1920, height: 2200 },
      deviceScaleFactor: 2,
      locale: "zh-TW",
    });
    await authContext(context, "admin");
    const page = await context.newPage();

    try {
      // First navigation compiles the page — be generous.
      await page.goto("/", { waitUntil: "networkidle", timeout: 90_000 });

      // Admin top-level tab → 獎學金分發
      await page.getByRole("tab", { name: "獎學金分發" }).first().click({ timeout: 60_000 });
      // Scholarship-type tab (博士生獎學金) — may already be active.
      try {
        await page.getByRole("tab", { name: /博士生獎學金/ }).first().click({ timeout: 8_000 });
      } catch {
        /* already selected */
      }
      await page.getByRole("heading", { name: /手動分發/ }).first().waitFor({ timeout: 60_000 });

      // Native <select>s — pick 114 學年度 + 全年 so the grid loads.
      const yearSel = page
        .locator("select")
        .filter({ has: page.locator("option", { hasText: "選擇學年度" }) })
        .first();
      const semSel = page
        .locator("select")
        .filter({ has: page.locator("option", { hasText: "選擇學期" }) })
        .first();
      await yearSel.selectOption({ label: "114 學年度" });
      await semSel.selectOption({ label: "全年" });

      // Grid ready when the seeded rows render (學號 is unique per row).
      await expect(rowFor(page, "csphd0001")).toBeVisible({ timeout: 60_000 });
      await expect(rowFor(page, "stuphd001")).toBeVisible({ timeout: 30_000 });
      await page.waitForTimeout(500);
      await page.evaluate(() => window.scrollTo(0, 0));

      // ---- Evidence screenshots (captured before assertions so they persist) ----
      // The panel renders two tables (quota matrix, then the student grid) — pick
      // the grid by the recommendation header it uniquely contains.
      const gridTable = page
        .locator("table")
        .filter({ hasText: "教授推薦" })
        .first();
      await gridTable.screenshot({ path: path.join(EVIDENCE_DIR, "01-grid-overview.png") });

      const rankHeader = page.getByRole("columnheader", { name: "排序" }).first();
      const collegeHeader = page.getByRole("columnheader", { name: "學院推薦" }).first();
      const rankBox = await rankHeader.boundingBox();
      const collegeBox = await collegeHeader.boundingBox();
      const app4Box = await rowFor(page, "stuphd001").boundingBox();
      if (rankBox && collegeBox && app4Box) {
        const x = Math.max(0, rankBox.x - 4);
        const y = Math.max(0, rankBox.y - 4);
        const width = collegeBox.x + collegeBox.width - x + 6;
        const height = app4Box.y + app4Box.height - y + 6;
        await page.screenshot({
          path: path.join(EVIDENCE_DIR, "02-professor-college-columns.png"),
          clip: { x, y, width, height },
        });
      }

      const row3Box = await rowFor(page, "csphd0003").boundingBox();
      if (rankBox && collegeBox && row3Box) {
        const x = Math.max(0, rankBox.x - 4);
        const width = collegeBox.x + collegeBox.width - x + 6;
        await page.screenshot({
          path: path.join(EVIDENCE_DIR, "03-college-rejected-row.png"),
          clip: { x, y: row3Box.y - 6, width, height: row3Box.height + 12 },
        });
      }

      // ---------------------------- Assertions ----------------------------

      // Group 1 — headers exist
      await expect(page.getByRole("columnheader", { name: "教授推薦" })).toBeVisible();
      await expect(page.getByRole("columnheader", { name: "學院推薦" })).toBeVisible();

      // Group 2 — App1 (csphd0001)
      const row1 = rowFor(page, "csphd0001");
      const prof1 = profCell(row1);
      await expect(prof1).toContainText("國科會: 推薦");
      await expect(prof1).toContainText("教育部: 不推薦");
      // reviewer comment surfaced in the moe_1w reject chip's title attr
      const rejectChip = prof1.locator(`[title="${PROF_MOE_REJECT_COMMENT}"]`);
      await expect(rejectChip).toHaveText("教育部: 不推薦");
      const college1 = collegeCell(row1);
      // ranking verdict chip (approve) — located by its title, then the college review chip
      await expect(college1.locator('[title="已列入學院確認排名"]')).toContainText("排名: 推薦");
      await expect(college1).toContainText("國科會: 推薦");

      // Group 3 — App2 (csphd0002): no reviews
      const row2 = rowFor(page, "csphd0002");
      await expect(profCell(row2).locator('[title="教授尚未完成推薦審核"]')).toHaveText("審核中");
      await expect(collegeCell(row2).locator('[title="已列入學院確認排名"]')).toContainText(
        "排名: 推薦"
      );

      // Group 4 — App3 (csphd0003): college_rejected
      const row3 = rowFor(page, "csphd0003");
      const rankCell3 = row3.locator("td").first();
      await expect(rankCell3.locator("span.text-red-600")).toHaveText("N");
      const college3 = collegeCell(row3);
      await expect(
        college3.locator('[title="學院於確認排名將此生標記為 N（不推薦）"]')
      ).toContainText("排名: 不推薦");
      // no approve ranking chip on a rejected row
      await expect(college3.locator('[title="已列入學院確認排名"]')).toHaveCount(0);
      const prof3 = profCell(row3);
      await expect(prof3).toContainText("國科會: 推薦");
      await expect(prof3).toContainText("教育部: 推薦");

      // Group 5 — App4 (stuphd001, renewal): admin review excluded
      const row4 = rowFor(page, "stuphd001");
      await expect(profCell(row4).locator('[title="教授尚未完成推薦審核"]')).toHaveText("審核中");
      // admin comment must appear NOWHERE on the page
      await expect(page.getByText(ADMIN_ONLY_COMMENT)).toHaveCount(0);
      await expect(page.locator(`[title="${ADMIN_ONLY_COMMENT}"]`)).toHaveCount(0);
      // no reject chip in either column for app4
      await expect(profCell(row4)).not.toContainText("不推薦");
      await expect(collegeCell(row4)).not.toContainText("不推薦");
    } finally {
      await context.close();
    }
  });
});

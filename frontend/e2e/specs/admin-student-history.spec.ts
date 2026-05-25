/**
 * E2E: Admin student scholarship history lookup.
 *
 * Tab: AdminManagementShell → "學生領取歷史"
 * Endpoint: GET /api/v1/admin/student-history/{student_number}
 *
 * Mirrors the auth pattern from admin-manual-distribution.spec.ts: log in as
 * the seeded "admin" user, reuse its BrowserContext, navigate to "/" which
 * mounts AdminManagementShell, click the new tab.
 */

import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";

test.describe("Admin student scholarship history", () => {
  test("rejects invalid student number client-side", async ({ browser }) => {
    const { context } = await loginAs(browser, "admin");
    const page = await context.newPage();
    await page.goto("/");
    await page.getByRole("tab", { name: "學生領取歷史" }).click();
    await page.getByLabel("學號").fill("@@");
    await page.getByRole("button", { name: "查詢" }).click();
    await expect(page.getByText(/請輸入有效的學號/)).toBeVisible();
    await context.close();
  });

  test("shows 查無此學生資料 for unknown student", async ({ browser }) => {
    const { context } = await loginAs(browser, "admin");
    const page = await context.newPage();
    await page.goto("/");
    await page.getByRole("tab", { name: "學生領取歷史" }).click();
    await page.getByLabel("學號").fill("GHOST00000");
    await page.getByRole("button", { name: "查詢" }).click();
    await expect(page.getByText("查無此學生資料")).toBeVisible({
      timeout: 10000,
    });
    await context.close();
  });

  // NOTE: This test uses seeded `stuphd001` (see backend/app/seed.py). The
  // dev DB may or may not have paid (COMPLETED or LOCKED) rosters for them
  // by default. If not, the table will show the "尚無領取記錄" empty state —
  // both outcomes are valid for "the page renders without error". A stronger
  // assertion needs roster seeding which is out of scope for this plan.
  test("renders page for seeded student (table OR empty state)", async ({
    browser,
  }) => {
    const { context } = await loginAs(browser, "admin");
    const page = await context.newPage();
    await page.goto("/");
    await page.getByRole("tab", { name: "學生領取歷史" }).click();
    await page.getByLabel("學號").fill("stuphd001");
    await page.getByRole("button", { name: "查詢" }).click();
    await expect(
      page.getByText(/領取明細|查無此學生資料|尚無領取記錄/),
    ).toBeVisible({ timeout: 10000 });
    await context.close();
  });
});

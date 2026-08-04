/**
 * E2E: student scholarship history access for college and student roles.
 *
 * - College: top-level "領獎紀錄查詢" tab renders StudentHistoryPanel in the
 *   college variant (no admin-only 匯入已領月份數 button); backend scopes
 *   lookups to the user's own college (college_code, seeded "C").
 * - Student: 我的申請 tab shows the 已領獎學金總月數 card fed by
 *   GET /student-history/me/months (0 個月 is a valid state on a fresh seed).
 */

import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";

test.describe("College student history lookup", () => {
  test("college tab renders panel without admin import action", async ({
    browser,
  }) => {
    const { context } = await loginAs(browser, "cs_college");
    const page = await context.newPage();
    await page.goto("/");
    await page.getByRole("tab", { name: "領獎紀錄查詢" }).click();
    await expect(page.getByLabel("學號")).toBeVisible();
    await expect(page.getByText("僅能查詢本學院學生的領獎紀錄。")).toBeVisible();
    await expect(
      page.getByRole("button", { name: "匯入已領月份數" }),
    ).toHaveCount(0);
    await context.close();
  });

  test("college multi-student query shows one result block per 學號", async ({
    browser,
  }) => {
    const { context } = await loginAs(browser, "cs_college");
    const page = await context.newPage();
    await page.goto("/");
    await page.getByRole("tab", { name: "領獎紀錄查詢" }).click();
    // Unknown 學號s keep the assertion seed-independent: each yields its own
    // per-student "查無此學生資料" block from the batch endpoint.
    await page.getByLabel("學號").fill("GHOST00001, GHOST00002");
    await page.getByRole("button", { name: "查詢" }).click();
    await expect(page.getByText("查無此學生資料")).toHaveCount(2, {
      timeout: 15000,
    });
    await context.close();
  });
});

test.describe("Student total received months", () => {
  test("我的申請 tab shows the 總月數 card", async ({ browser }) => {
    const { context } = await loginAs(browser, "stuphd001");
    const page = await context.newPage();
    await page.goto("/");
    await page.getByRole("tab", { name: "我的申請" }).click();
    const card = page.getByTestId("total-received-months-card");
    await expect(card).toBeVisible({ timeout: 15000 });
    await expect(card).toContainText("已領獎學金總月數");
    await expect(card).toContainText("個月");
    await context.close();
  });
});

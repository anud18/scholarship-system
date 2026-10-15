/**
 * E2E: the top-level tab the admin clicked survives the /auth/me refresh.
 *
 * use-auth restores the user from localStorage first, then refreshes it from
 * GET /api/v1/auth/me and swaps in a new user object. app/page.tsx used to
 * reset the active tab to the role default whenever that object changed, so a
 * click landing before the refresh was silently undone — the nightly
 * admin-student-history spec failed this way ~1 run in 3 (#1467).
 *
 * The race is made deterministic by holding the /auth/me response until after
 * the tab click, then releasing it.
 */

import { test, expect } from "@playwright/test";
import { MODE, ROLE } from "../helpers/tags";
import { loginAs } from "../helpers/auth";

test.describe("管理員分頁不因個人資料刷新而重設 | Admin tab survives /auth/me refresh", { tag: [MODE.browser, ROLE.admin] }, () => {
  test("系統管理 stays selected after the delayed /auth/me response lands", async ({
    browser,
  }) => {
    const { context } = await loginAs(browser, "admin");
    const page = await context.newPage();

    let releaseAuthMe: () => void = () => {};
    const authMeReleased = new Promise<void>(resolve => {
      releaseAuthMe = resolve;
    });
    let authMeServed: () => void = () => {};
    const authMeDone = new Promise<void>(resolve => {
      authMeServed = resolve;
    });
    await page.route("**/api/v1/auth/me", async route => {
      await authMeReleased;
      const response = await route.fetch();
      // Return a profile that differs from the localStorage copy so use-auth
      // always takes the setUser branch (it skips identical profiles).
      const body = await response.json();
      await route.fulfill({
        response,
        json: { ...body, data: { ...body.data, full_name: "系統管理員（已刷新）" } },
      });
      authMeServed();
    });

    await page.goto("/");
    const adminTab = page.getByRole("tab", { name: "系統管理" });
    await adminTab.click();
    await expect(adminTab).toHaveAttribute("aria-selected", "true");

    releaseAuthMe();
    await authMeDone;
    // Let React commit the refreshed user before asserting.
    await expect(page.getByText("系統管理員（已刷新）").first()).toBeVisible();

    await expect(adminTab).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tab", { name: "學生領獎紀錄查詢" })).toBeVisible();
    await context.close();
  });
});

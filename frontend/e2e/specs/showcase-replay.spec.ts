/**
 * E2E "showcase" flow — the always-recorded walkthrough.
 *
 * Why this file exists:
 *   The published nightly report (https://anud18.github.io/scholarship-system)
 *   keeps video + trace only `retain-on-failure` (see playwright.config.ts) to
 *   stay small. But the nightly suite almost always passes, so a green report
 *   has NO watchable recording at all. This one spec opts INTO video + trace on
 *   EVERY run so the report always contains at least one Cursor-agent-style
 *   replay (the interactive Trace viewer) plus a video of a real happy path.
 *
 * It MUST use the built-in `page` fixture (a runner-owned context): video is a
 * creation-time `recordVideo` option the runner only applies to its own
 * fixtures, so a manually-created `browser.newContext()` (helpers/auth.loginAs)
 * records trace but never video. We inject auth onto the fixture context via
 * `authContext` instead.
 *
 * Flow: admin → 系統管理 → 學生領取歷史 → query seeded stuphd001 → result renders.
 * Kept assertion-light on purpose: the value is the recording, and it must stay
 * green every night.
 */

import { test, expect } from "@playwright/test";
import { authContext } from "../helpers/auth";

// Record video + an interactive trace on EVERY run, not just on failure.
test.use({ video: "on", trace: "on" });

test("showcase: admin looks up a student's scholarship history", async ({
  page,
}) => {
  await authContext(page.context(), "admin");
  await page.goto("/");

  // AdminManagementShell renders inside the top-level "系統管理" tab.
  await page.getByRole("tab", { name: "系統管理" }).click();
  await page.getByRole("tab", { name: "學生領取歷史" }).click();

  await page.getByLabel("學號").fill("stuphd001");
  await page.getByRole("button", { name: "查詢" }).click();

  // Either a result table or an empty / not-found state is a valid render — the
  // point is the page responded without error (see admin-student-history.spec).
  await expect(
    page.getByText(/領取明細|查無此學生資料|尚無領取記錄/).first()
  ).toBeVisible({ timeout: 10000 });
});

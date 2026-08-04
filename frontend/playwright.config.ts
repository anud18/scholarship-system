import { defineConfig, devices } from "@playwright/test";
import { FRONTEND_URL } from "./e2e/helpers/env";

export default defineConfig({
  testDir: "./e2e/specs",
  timeout: 60_000,
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [
    ["list"],
    ["html", { open: "never" }],
    ["./e2e/reporters/diagnostic-reporter.ts"],
  ],
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  use: {
    baseURL: FRONTEND_URL,
    trace: "retain-on-failure",
    video: "retain-on-failure",
    // "on": capture a screenshot at the end of EVERY test (pass or fail) so the
    // GitHub Pages e2e report always shows screenshots, not only on failures.
    screenshot: "on",
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});

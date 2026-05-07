---
name: nycu-sso-login
description: Use this skill whenever the user needs an authenticated session against the NYCU scholarship staging site (`ss.test.nycu.edu.tw`) or its SSO portal (`portal.test.nycu.edu.tw`) — logging in, getting a Playwright `storageState`, opening an authed browser context, running browser/E2E/automation scripts, screenshotting or clicking through the dashboard, reproducing portal SSO bugs, verifying login still works, or switching among student/teacher/staff/學院 test accounts (IDs like `414551001`, `A00001`, `E00001`). Treat any task that implicitly needs an authed session against this staging host — even phrased casually as "poke at an endpoint", "verify login", "spin up a session as <id>", or "screenshot the dashboard" — as a trigger; users rarely say "SSO" out loud. Do NOT use for production (`ss.nycu.edu.tw`), localhost/docker dev stacks, frontend code fixes that don't run a browser, VPN troubleshooting, unrelated NYCU systems, or non-NYCU SSO logins.
---

# NYCU SSO login & session reuse (staging environment)

This skill captures a working Playwright SSO flow for the NYCU scholarship system **staging** environment. Despite the `ss.test.nycu.edu.tw` URL, this is the staging deployment, not a throwaway test box — credentials and behavior should be treated accordingly. The login form is a SPA — selectors are brittle if you guess them, so use the bundled scripts.

## When to use

- User wants an authenticated session for `https://ss.test.nycu.edu.tw/`
- User wants to switch between test accounts (student / teacher / staff) to verify role-specific behavior
- User wants to write a new Playwright test that needs to start from a logged-in state
- User asks to take a screenshot, scrape, or click through the dashboard

## Prerequisites

1. **VPN tunnel must be up.** Both `ss.test.nycu.edu.tw` and `portal.test.nycu.edu.tw` are only reachable through the user's WireGuard tunnel `peer2`. Before doing anything, check reachability:

   ```bash
   curl -sI --max-time 5 https://ss.test.nycu.edu.tw/ >/dev/null && echo OK || echo UNREACHABLE
   ```

   If unreachable, tell the user to bring the tunnel up themselves (it needs `sudo`):

   ```
   sudo env "PATH=$PATH" wg-quick up peer2
   ```

   Do **not** run that `sudo` command yourself — ask the user to run it with `! <command>` in their shell, or to start it manually. Re-check reachability before proceeding.

2. **Playwright + Node available.** This skill assumes `playwright` is installed (globally is fine — `npm install -g playwright`) and that the Chromium browser binary has been downloaded (`playwright install`).

3. **Password file.** Test-account password lives at `${NYCU_DIR:-/tmp/pw-test}/.password` (chmod 600). If it's missing, ask the user for the password and create the file with restrictive permissions:

   ```bash
   umask 077 && mkdir -p /tmp/pw-test && printf '<password>' > /tmp/pw-test/.password && chmod 600 /tmp/pw-test/.password
   ```

   The password is shared across all test accounts in this environment.

## How to use

### Log in as a specific account

```bash
NODE_PATH=$(npm root -g) node scripts/login.js <username> [--headed]
```

`<username>` is one of the test-account IDs (e.g. `414551001` for a student, `A00001` for a teacher, `E00001` for staff). On success, this writes:

- `${NYCU_DIR:-/tmp/pw-test}/auth-<username>.json` — Playwright `storageState` for headless reuse
- `${NYCU_DIR:-/tmp/pw-test}/dashboard-<username>.png` — post-login screenshot

`--headed` shows the browser window — useful when something is broken and you want to watch.

### Reuse a saved session in a new test

The simplest pattern (also bundled as `scripts/with-session.js`):

```js
const { chromium } = require('playwright');
const browser = await chromium.launch();
const ctx = await browser.newContext({
  ignoreHTTPSErrors: true,
  storageState: '/tmp/pw-test/auth-414551001.json',
});
const page = await ctx.newPage();
await page.goto('https://ss.test.nycu.edu.tw/');
// ...you are logged in as 414551001
```

To smoke-test a saved session quickly:

```bash
NODE_PATH=$(npm root -g) node scripts/with-session.js <username> [url]
```

### When the session expires

Sessions expire after some hours. If `with-session.js` reports `SESSION: EXPIRED` or the dashboard shows the login button again, just rerun `login.js <username>` to refresh the storage state.

## Test accounts (test environment only)

Shared password lives in the password file (see Prerequisites). Don't hard-code, log, or commit it.

- **Students (28):** `114550034`, `114550036`, `413510025`, `313551007`, `414111001`, `414708008`, `413708006`, `413708007`, `414551001`–`414551005`, `413551001`–`413551005`, `412551001`–`412551005`, `414551005`–`414551009`
- **Teachers (5):** `A00001`–`A00005` (`A00001`–`A00002` may also be used as staff per local convention)
- **Staff (3):** `E00001`, `E00004`, `E00005`

**Confirmed working today** with the default password: `414551001` (student, role=學生), `A00001` (role=學院). Other accounts may be provisioned later or have different passwords — if a login fails with "credentials rejected", try the next ID in the range rather than retrying the same one (it's not the script).

When the user asks for "a student" / "a teacher" / "a staff" without specifying an ID, default to a confirmed-working one (`414551001` / `A00001` / try `E00001` first then `E00004`) and tell them which you picked so they can override.

## Configurable paths (env vars)

These let the same scripts work outside the default `/tmp/pw-test` location without editing code:

| Env var | Default | Purpose |
| --- | --- | --- |
| `NYCU_DIR` | `/tmp/pw-test` | Directory for password file, storage states, screenshots |
| `NYCU_PASSWORD_FILE` | `$NYCU_DIR/.password` | Password file path |
| `NYCU_APP_URL` | `https://ss.test.nycu.edu.tw/` | App entrypoint (override for staging/prod) |

## Safety rules

These exist because credentials in this environment open more than the scholarship app — NYCU SSO unlocks mail, portal, and other school systems. Treat them like real production secrets.

- **Never echo the password** to stdout, logs, screenshots, error messages, or commit messages. Read from the password file; don't pass it on the command line.
- **Never commit** the password file, storage state files, or anything under `/tmp/pw-test/` to git. Add to `.gitignore` if the user moves them into the repo.
- **Never paste the password into chat** — if the user does, do not echo it back. Save it to the password file silently and confirm only that "password saved".
- **Don't run `sudo` for the VPN yourself** — ask the user.
- **Don't attempt to use these credentials** against any host other than `*.nycu.edu.tw`.

## Selectors reference (for debugging if the portal UI changes)

These are the selectors that work today. If login starts failing with a "could not locate field" error, inspect the live page and update `scripts/login.js`:

- App login button: `getByText('使用 NYCU Portal 登入')`
- Portal username field: `input[placeholder*="帳號"]` (SPA — must wait for visibility, ~1–3s after navigation)
- Portal password field: `input[type="password"]`
- Portal submit button: `button:has-text("同意以及登入")` (falls back to `button:has-text("登入")`)
- Optional OAuth authorize step: `button:has-text("授權")` / `button:has-text("Authorize")` (rarely shown for already-authorized scopes)

If a `login-failed-<username>.png` screenshot appears in `$NYCU_DIR`, open it — usually shows the exact portal screen the script got stuck on.

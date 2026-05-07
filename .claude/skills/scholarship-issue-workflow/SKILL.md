---
name: scholarship-issue-workflow
description: |
  Full workflow for picking up a GitHub issue in the NYCU scholarship-system, implementing the fix, and validating it end-to-end on both localhost and ss.test.nycu.edu.tw staging. Use this skill whenever the user says "work on issue #N", "pick up an issue", "fix issue", "implement this feature", or otherwise wants to take a GitHub issue from open → fixed → verified. Also invoke it when the user asks to validate a recent fix on staging, or to post a verification screenshot to an issue.

  Key protection: always grep to confirm a file is actually imported before editing it — the most expensive mistake in this codebase is spending time on a dead/unused component while the real rendering path goes elsewhere.
---

# Scholarship Issue Workflow

Lifecycle: read issue → check imports → before screenshot → implement → test locally → commit → deploy → verify on staging → post before/after to issue.

## Execution style — no asking, just proceed

The user's strong preference: **don't ask clarifying questions, don't pause for confirmation between phases**. Default to the recommended path at every fork without asking:

- **New branch from `origin/main`** for every issue (`fix/issue-<N>-<slug>`) — never reuse the current branch unless its name already matches.
- **Always open a PR** after pushing — even before staging verification, so CI starts running.
- **Pause only at the merge boundary** — do not auto-merge. Stop after Phase 5 / PR creation and wait for the user to merge manually. They will say "merged" or "continue" before you run Phase 6+ (CI watch / staging verify / close-the-loop).
- **Never push to `main` directly.**
- **No mid-flow `AskUserQuestion` for routine choices** (commit message wording, whether to open a PR, branch strategy). Reserve questions for genuinely ambiguous cases (the bug has multiple plausible fixes; the spec is contradictory).

---

## Phase 1 — Issue Intake

```bash
gh issue view <N> --json number,title,body,labels,assignees,comments
```

Extract:
- **Acceptance criterion** — what does "done" look like, not just the symptom
- **Affected layer** — frontend / backend / both
- **User roles** involved (student / professor / college / admin / staff)
- **File hints** in the issue body or comments

### General rule: verify imports before editing any file

For any file you plan to edit, confirm it is actually reachable at runtime:

```bash
# Is this component imported anywhere?
grep -rn "ComponentName\|filename-without-ext" frontend/ --include="*.tsx" --include="*.ts"

# Is this endpoint registered in a router?
grep -rn "router\|include_router" backend/app/api/ --include="*.py"
```

A file can exist, export a symbol, and be completely ignored at runtime. If grep finds zero import sites outside the file itself, it is dead code — find the real entry point instead.

**Admin panel chain** (confirmed live):
```
frontend/app/page.tsx
  → AdminManagementShell.tsx  (dynamic imports per tab)
      → history/HistoryPanel.tsx      (歷史申請 tab)
      → ... other tab components
```
`frontend/components/admin-management-interface.tsx` exports `AdminManagementInterface` but is **never imported anywhere** — do not edit it.

### Every plan must include a staging validation section

Even when the task is planning only, your output must include a section like:

```
## Staging Validation (ss.test.nycu.edu.tw)
- Requires WireGuard peer2 VPN (ask user: `sudo wg-quick up peer2`)
- Login account: E00001 (staff/admin), 414551001 (student), A00001 (professor)
- Flow to verify: <specific navigation steps>
- Assertion: <what to check on staging to confirm the fix>
```

This ensures staging validation is never forgotten when the fix gets implemented.

---

## Phase 2 — Before Evidence

Before writing a single line of code, capture the current broken state on staging. Once the fix is deployed it's gone forever.

**For UI bugs:** take a Playwright screenshot (steps below).

**For backend-only bugs (5xx, error logs, missing API field):** screenshots don't apply. The "before evidence" is one of:
- Error log entries from `ss.test/monitoring` (Grafana/Loki) — copy the trace_ids and timestamps into the issue body so you can prove the same condition is gone after the fix
- Raw `curl` of the failing endpoint capturing HTTP status + body + response headers
- A monitoring screenshot is fine if the user wants something visual, but logs/curl output are the load-bearing evidence

Skip the Playwright spec entirely for backend-only flows — proceed straight to Phase 3 once the failure is reproducibly captured in the issue.

**1. VPN check first:**
```bash
curl -sI --max-time 5 https://ss.test.nycu.edu.tw/ >/dev/null && echo OK || echo UNREACHABLE
```
If unreachable, ask the user to bring the tunnel up — do NOT run sudo yourself:
```
sudo env "PATH=$PATH" wg-quick up peer2
```

**2. Ensure session is valid** (use nycu-sso-login skill if missing/expired):
```bash
ls /tmp/pw-test/auth-E00001.json || node scripts/login.js E00001
```

**3. Write a quick before-spec** (`e2e/staging/issue<N>-before.spec.ts`, delete after closing):
```typescript
import { test } from '@playwright/test';
test('issue #<N>: before state', async ({ page }) => {
  // ⚠️  AdminManagementShell is on / (homepage tab), NOT a separate /admin route
  await page.goto('https://ss.test.nycu.edu.tw/');
  await page.click('button:has-text("系統管理")');
  await page.click('button:has-text("歷史申請")');  // adjust for affected tab
  await page.waitForLoadState('networkidle');

  // Scroll thead into viewport — without this the screenshot shows only the nav bar
  await page.evaluate(() => {
    const t = document.querySelector('thead');
    if (t) { t.scrollIntoView({ behavior: 'instant', block: 'start' }); window.scrollBy(0, -60); }
  });
  await page.waitForTimeout(400);
  await page.screenshot({ path: '/tmp/issue<N>-before.png' });
});
```

```bash
cd frontend
npx playwright test e2e/staging/issue<N>-before.spec.ts \
  --config playwright.staging.config.ts --reporter=list
```

If `playwright.staging.config.ts` doesn't exist yet, create it:
```typescript
import { defineConfig } from '@playwright/test';
export default defineConfig({
  use: {
    baseURL: 'https://ss.test.nycu.edu.tw',
    storageState: '/tmp/pw-test/auth-E00001.json',
    ignoreHTTPSErrors: true,
    viewport: { width: 1920, height: 1080 },
    screenshot: 'on',
    trace: 'on',
  },
  timeout: 60000,
});
```

---

## Phase 3 — Implement

### Branch
```bash
git checkout -b fix/issue-<N>-short-description
```

### Rules (from CLAUDE.md)
- Never return fallback/mock data on DB failure — throw directly
- All API endpoints return `{"success": bool, "message": str, "data": any}`
- Enums: Python lowercase, TypeScript UPPERCASE names / lowercase values, Postgres lowercase
- After touching backend schemas: `cd frontend && npm run api:generate`

### Lint after editing
```bash
# Backend
docker compose -f docker-compose.dev.yml exec backend python -m black <files>
# Frontend
docker compose -f docker-compose.dev.yml exec frontend npm run lint
```

`flake8` is often not installed in the dev image (`No module named flake8`) — `black` alone is enough; don't block on flake8.

**`exec` failing with "current working directory is outside of container mount namespace root"?** The backend container drifted unhealthy. Restart it and retry:
```bash
docker compose -f docker-compose.dev.yml restart backend && sleep 8
docker compose -f docker-compose.dev.yml exec backend python -m black <files>
```

---

## Phase 4 — Local E2E Validation

Use the `playwright-test-and-debug` skill for localhost:

```bash
.claude/skills/playwright-test-and-debug/scripts/check-stack.sh
TOKEN=$(scripts/login-mock-sso.sh admin | jq -r .data.access_token)
STORAGE=$(scripts/build-storage-state.sh admin)
```

Drive the actual user flow — not just a page screenshot. Check:
- Golden path works as expected
- At least one negative case still fails correctly
- No console errors: `docker compose -f docker-compose.dev.yml logs frontend --since 2m | grep -i error`

---

## Phase 5 — Commit & Push

```bash
git add <specific files — never -A blindly>
git commit -m "$(cat <<'EOF'
fix(#<N>): short description of what changed

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin <branch>
```

Never push directly to `main`. If the branch already exists upstream, keep it.

---

## Phase 6 — Wait for CI + Deploy

A push to `main` fires **multiple workflows in parallel** — at minimum:
- `Main CI/CD Pipeline` (tests, lint, security)
- `Deployment Pipeline` (build images + deploy-staging)
- `Security`, `API Types Check`, `CodeQL Advanced`

Both Main CI/CD and Deployment must be green before staging actually has the new image. Use a polling loop, not just `gh run watch <single-id>` — that only watches one workflow:

```bash
# Wait for all main-branch runs at the merge SHA to settle
SHA=$(git rev-parse origin/main)
until ! gh run list --branch main --limit 8 --json status,headSha \
       --jq ".[] | select(.headSha==\"$SHA\" and .status!=\"completed\")" \
       | grep -q .; do
  sleep 30
done
gh run list --branch main --limit 8 --json name,conclusion,headSha \
  --jq ".[] | select(.headSha==\"$SHA\") | \"\(.name): \(.conclusion)\""
```

Typical wall-clock: ~9–10 min. The Deployment Pipeline:
1. `build-images` — Docker + GHA BuildKit cache (`scope=frontend`/`backend`)
2. `deploy-staging` — self-hosted runner pulls new image and restarts containers

**If deploy is stuck:** check runner logs for `fatal: no submodule mapping found in .gitmodules` — this means `.claude/worktrees/*` were accidentally committed as gitlinks. Fix: `git rm --cached .claude/worktrees/<name>` and commit.

---

## Phase 7 — Staging Validation + After Screenshot

### VPN check
```bash
curl -sI --max-time 5 https://ss.test.nycu.edu.tw/ >/dev/null && echo OK || echo UNREACHABLE
```
Session may have expired during the deploy wait — re-login if needed:
```bash
node scripts/login.js E00001
```

### Pick the right account for the path you're testing

A common verification mistake: testing a permission-denied path with an admin/super_admin account, which **bypasses** most permission checks (`_check_academic_year_permission` and `_check_scholarship_permission` both `return True` for `is_admin() or is_super_admin()`). The denial path never executes and you "verify" nothing.

To exercise a permission denial:
- Use a `學院` (college) account like **A00001** — not E00001 (staff/admin)
- For role-gate denials (`require_college` etc.), use a student or professor account

### Match a "User N" in error logs to a test account

When a staging error references "User 77 not authorized for ...", you can identify which test account that is by decoding the JWT `sub` field from the saved storageState:

```bash
cat /tmp/pw-test/auth-A00001.json | python3 -c "
import json, sys, base64
d = json.load(sys.stdin)
for o in d.get('origins', []):
    for kv in o.get('localStorage', []):
        if kv['name'] == 'auth_token':
            payload = kv['value'].split('.')[1]
            payload += '=' * (-len(payload) % 4)
            print(json.loads(base64.urlsafe_b64decode(payload)))
            break"
```

The `sub` field is the user's DB id. Match it against the error log to reproduce the **exact same request** the user hit, which is the strongest possible verification.

### Write the verify spec (`e2e/staging/issue<N>-verify.spec.ts`)
```typescript
import { test, expect } from '@playwright/test';
test('issue #<N>: <description>', async ({ page }) => {
  // ⚠️  Homepage (/), not /admin — admin panel is a tab on the main page
  await page.goto('https://ss.test.nycu.edu.tw/');
  await page.click('button:has-text("系統管理")');
  await page.click('button:has-text("歷史申請")');
  await page.waitForLoadState('networkidle');

  // Replace with your actual assertion
  const headers = await page.$$eval('thead th', els => els.map(el => el.textContent?.trim()));
  expect(headers).toContain('國籍/身分');

  // Scroll thead to top so the screenshot shows headers AND data rows
  await page.evaluate(() => {
    const t = document.querySelector('thead');
    if (t) { t.scrollIntoView({ behavior: 'instant', block: 'start' }); window.scrollBy(0, -60); }
  });
  await page.waitForTimeout(400);
  await page.screenshot({ path: '/tmp/issue<N>-after.png' });
});
```

```bash
cd frontend
npx playwright test e2e/staging/issue<N>-verify.spec.ts \
  --config playwright.staging.config.ts --reporter=list
```

Fallback if CLI is blocked: `NODE_PATH=$(npm root -g) node /tmp/verify-staging.js`

If staging looks wrong despite green CI, check:
- Did `COPY . .` hit cache in the build logs? (means wrong commit was baked in)
- Is the component actually used by this route? (re-run import grep from Phase 1)

---

## Phase 8 — Close the Loop

**Auto-close note:** if your PR body contains `Fixes #N` / `Closes #N`, a squash-merge auto-closes the issue. The close-the-loop comment should still post (it adds verification evidence) — check before re-running `gh issue close`, you'll get an "already closed" warning otherwise.

### Backend bugs: comment with a before/after table

For backend-only bugs there are no UI screenshots. Post a markdown table comparing the failing request before vs. after, including: HTTP status, body, and a one-line backend log signature (`ERROR Unhandled exception ...` → `WARNING Permission denied ...`). Cite the original failing trace_ids and the new clean trace_id from your verification. This is what convinces the reviewer the fix worked, not a screenshot.

### UI bugs: before + after screenshots

GitHub CLI can't upload binary images directly — commit to repo and reference via raw URL.

**1. Commit both screenshots:**
```bash
cp /tmp/issue<N>-before.png docs/screenshots/issue<N>-before.png
cp /tmp/issue<N>-after.png  docs/screenshots/issue<N>-after.png
git add docs/screenshots/issue<N>-{before,after}.png
git commit -m "docs(#<N>): add before/after screenshots"
git push
```

**2. Raw URLs:**
```
https://raw.githubusercontent.com/anud18/scholarship-system/<branch>/docs/screenshots/issue<N>-before.png
https://raw.githubusercontent.com/anud18/scholarship-system/<branch>/docs/screenshots/issue<N>-after.png
```

**3. Post comment:**
```bash
gh issue comment <N> --body "$(cat <<'EOF'
## Fix verified on ss.test.nycu.edu.tw ✅

### Before
![before](<before-raw-url>)

### After
![after](<after-raw-url>)

**Changed:** <one-line summary>
**Evidence:** <headers / API field / data rows confirming the fix>
EOF
)"
```

To update an existing comment instead:
```bash
gh api --method PATCH /repos/anud18/scholarship-system/issues/comments/<comment-id> \
  --field body="<updated body with both images>"
```

### Done criteria
- [ ] Before screenshot captured on staging (Phase 2) before any code changes
- [ ] Fix works on localhost (golden path + 1 negative case)
- [ ] CI pipeline green, image deployed to staging
- [ ] After screenshot confirms the fix on staging
- [ ] Issue comment has **both** before + after screenshots
- [ ] No regressions in adjacent flows

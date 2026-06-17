---
name: playwright-test-and-debug
description: Drive browser-based actions against the scholarship-system localhost dev env (http://localhost:3000), AND when something diverges from the codebase's spec, walk an integrated diagnose-and-fix loop — tail backend logs, query Postgres, classify the gap, and patch the responsible layer. Use this skill whenever the user asks to drive a quick local browser test, screenshot a page, log in as a seeded user (admin / cs_professor / cs_college / stuphd001 / stuunder1 / etc.) and click through a flow, debug why a localhost endpoint is returning 5xx or behaving unexpectedly, dump application/review/whitelist DB state, OR — most importantly — verify a recent code change end-to-end ("I just finished feature X / fixed bug Y, smoke-test that it works"). Treat any post-change verification request, any "make sure my localhost change works" prompt, any "the e2e test in frontend/e2e failed — figure out why" debugging request, and any "log in as <seeded user> and check the dashboard" exploratory request as a trigger. Includes a ready-made multi-college ranking→distribution→roster end-to-end driver (`scripts/verify-multi-college-distribution.js`) for the #1029/#1034 college-pipeline regression. Do NOT use for staging (use `nycu-sso-login` for `ss.test.nycu.edu.tw`), and do NOT use for setting up a new `@playwright/test` runner from scratch (that's a project-config task, not session tooling).
---

# Playwright local test & debug (scholarship-system dev env)

This skill encodes both halves of a real Claude Code testing session for the scholarship-system localhost dev env: (1) how to drive the browser — the **Webwright loop** (code-as-action, screenshot-per-step, self-verify) for multi-step flows, and the quick one-shot scripts for simple checks — and (2) the diagnose-and-fix loop to actually close the gap when something doesn't behave as the codebase says it should. Without it, sessions re-derive both from scratch and tend to use them in isolation — drive a click, see a 500, and stop at "report failure".

The dev env (`docker compose -f docker-compose.dev.yml`) has full mock-SSO so logging in as any seeded user is a single POST — no Portal SSO dance, no rate limits.

## When to use vs not

| User intent | Use this skill? | Why |
|---|---|---|
| "log in as admin on localhost and screenshot the dashboard" | Yes | mock-SSO + screenshot |
| "drive a click through the review queue and verify the API got hit" | Yes | with-session + dump-app-state |
| "this localhost endpoint returns 500 — debug it" | Yes | tail-logs + db-query loop |
| "the e2e test in `frontend/e2e/...` failed — figure out why" | Yes | same diagnose loop applies |
| **"I just finished feature X / fix Y — verify it works end-to-end"** | **Yes — primary use case** | drives the relevant flow + cross-validates UI/API/DB; runs diagnose loop on divergence |
| "log in to NYCU staging" | No — use `nycu-sso-login` | different env, different login flow |
| "set up `@playwright/test` in `frontend/`" | No | runner setup is one-time project-config, not per-session |

## Prerequisites (one command)

```bash
.claude/skills/playwright-test-and-debug/scripts/check-install.sh && \
.claude/skills/playwright-test-and-debug/scripts/check-stack.sh
```

`check-install.sh` verifies Playwright + browser cache. `check-stack.sh` checks backend / frontend / postgres independently and prints per-service fix commands (so you can bring up only what's missing — e.g. `docker compose -f docker-compose.dev.yml up -d frontend` if only frontend is down). After running `up -d`, use the bundled poller instead of manual `sleep`:

```bash
.claude/skills/playwright-test-and-debug/scripts/wait-for-stack.sh   # polls every 2s, default 90s timeout
```

## Drive the browser — core patterns

**Pick the approach by task shape:**

| Task | Approach |
|---|---|
| One-shot: screenshot a page, log in once and look, a single UI/API check | The **quick one-shot scripts** below — fastest path, no ceremony |
| **Multi-step flow or end-to-end change verification** (the default) | The **Webwright loop** — plan → instrumented run → screenshot-per-step → harsh self-verify |

### Default for multi-step flows — the Webwright loop

For any flow with more than one meaningful step (click through a queue, submit→review cascade, post-change end-to-end verification), drive the browser the **Webwright way** rather than ad-hoc one-off clicks. Follow the **`webwright`** skill's contract, with two localhost adaptations: **seed the context with a logged-in storage state** (don't launch fresh), and **use the bundled Node scripts** — adopt the *discipline*, not webwright's Python venv.

1. **Plan.** Write `plan.md` with a numbered checklist of critical points — each independently verifiable from a screenshot AND/OR a log/DB line.
2. **Bootstrap auth.** `STORAGE=$(scripts/build-storage-state.sh <user>)` → a logged-in `/tmp/auth-<user>.json` for the seeded user (sets both `auth_token` and the user blob `useAuth` needs).
3. **Drive one step at a time** with Node Playwright (`NODE_PATH=$(npm root -g) node ...`), launching the context with `storageState: "$STORAGE"` so every step stays logged in. Keep the whole workspace under `/tmp` (matching this skill's /tmp convention — e.g. `/tmp/ptd-<task>/final_runs/run_<id>/`, `<id>` one higher than any existing run folder), so generated runs never touch the repo. Save a uniquely-named screenshot per critical point + an action-log line per constraint-relevant step. `scripts/with-session.js` already loads storage state and screenshots — extend it, or write an instrumented script in the run folder.
4. **Cross-validate** each step against backend logs (`scripts/tail-logs.sh`) and Postgres (`scripts/db-query.sh`). This is the localhost upgrade over webwright's visual-only self-verify: you have stronger evidence than screenshots, so use it.
5. **Self-verify** harshly against `plan.md` — tick a critical point only with concrete cited evidence (screenshot + log/DB row). On any failure, walk the diagnose-and-fix loop below, fix the responsible layer, and re-run in `final_runs/run_<id+1>/`.

The one-shot scripts below remain the right tool for simple single-step checks — don't spin up a `plan.md` and a run folder to screenshot one page.

### Quick one-shot scripts (fast path)

### Quick screenshot of any URL
```bash
NODE_PATH=$(npm root -g) node scripts/screenshot.js http://localhost:3000 /tmp/home.png
```
Then use the **Read** tool on `/tmp/home.png` — it renders inline.

### Log in as a seeded user (mock-SSO)
```bash
scripts/login-mock-sso.sh admin              # returns { success, message, data: { access_token, user, ... } }
TOKEN=$(scripts/login-mock-sso.sh admin | jq -r .data.access_token)
```

The token is a JWT. Use it with `curl -H "Authorization: Bearer $TOKEN" ...` for direct API calls — no browser needed.

Available seeded users (from `backend/app/seed.py`):
- **Students**: `stuunder1` (undergrad), `stuphd001` (PhD), `stumaster`, `studirect`, `stuchina1`, `stuleave1`
- **Professor**: `professor`, `cs_professor`
- **College reviewer**: `college`, `cs_college`
- **Admin**: `admin`
- **Super admin**: `super_admin`

If unsure which exist, use the helper:
```bash
scripts/list-users.sh         # tabular DB query, grouped by role
scripts/list-users.sh --api   # via mock-SSO /users endpoint (formatted with jq)
```

### Open a logged-in browser (UI-driven session)

The frontend's `useAuth` hook (`frontend/hooks/use-auth.tsx:39-45`) requires **BOTH** `auth_token` AND a user blob (under `user` or `dev_user`) in localStorage — injecting only the token fails silently and the page falls back to the dev login picker. Use the bundled helper to build the storage state correctly:

```bash
STORAGE=$(scripts/build-storage-state.sh admin)         # writes /tmp/auth-admin.json, prints the path
NODE_PATH=$(npm root -g) node scripts/with-session.js "$STORAGE" http://localhost:3000
```

The output prints title, URL, status code, and the first 400 chars of body — usually enough to know if the dashboard loaded. A screenshot is saved to `/tmp/session-<timestamp>.png` for visual confirmation.

**Verification cue**: the body should contain the role label (`管理員` / `學生` / `教授` / `學院`) and nav items like `儀表板` / `審核管理` / `獎學金分發`. If you see `Development Login` / `Select a user to simulate login` instead, the auth check failed — usually because storage state was built without the user blob.

### Codegen a new flow (when you actually need to record clicks)
```bash
playwright codegen --save-storage=/tmp/auth-admin.json http://localhost:3000
```
**Always launch via `run_in_background: true`** since codegen blocks until the user closes the window. Tell the user explicitly: "log in / click through, then close the window when done".

## The diagnose-and-fix loop — the heart of the skill

When a browser action fails (5xx, unexpected page, missing element) OR an API call returns something inconsistent with the codebase's documented behavior, **walk this loop in order, before reporting back to the user:**

```
[1] capture context
    - note trace ID(s) from response headers (X-Trace-ID)
    - note the timestamp
    - note the affected entity ID (app_id, user_id, config_id, etc.)

[2] tail backend logs filtered by trace ID or keyword
    scripts/tail-logs.sh 10m "<trace_id_or_keyword_or_ERROR>"

[3] inspect DB state for the affected entity
    scripts/dump-app-state.sh APP-114-0-00033          # for application issues
    scripts/db-query.sh "SELECT * FROM users WHERE nycu_id='stuphd001';"
    scripts/db-query.sh "SELECT id, whitelist_student_ids FROM scholarship_configurations WHERE id=4;"

[4] classify the gap (table below)

[5] patch the responsible layer; re-run the action; verify
```

### Classification table

Match the symptom to one row, then fix in the indicated layer:

| Symptom | Class | Where to fix |
|---|---|---|
| Backend log shows 5xx, exception, missing column, enum mismatch | **Codebase bug** | `backend/app/services/{application,review,college_review,eligibility}_service.py` first; then API endpoint in `backend/app/api/v1/endpoints/` |
| Seeded user / scholarship missing or in wrong starting state at test start | **Seed data drift** | `backend/app/seed.py` and `backend/app/db/seed_scholarship_configs.py` |
| Direct API call returns correct data but UI doesn't render it | **Frontend bug** | relevant `frontend/app/.../page.tsx` or `frontend/components/...` |
| Backend behavior is documented + intentional, action assumed otherwise | **Wrong assumption** | revise the action / script — never silence the check |

### Anti-patterns

- **Don't** discover a 500 in logs and then re-run the same action hoping it works. If logs say there's a bug, fix it (or escalate to the user with the exact line + proposed patch). Don't loop.
- **Don't** silence an assertion to make a test pass. If the spec says X and the code does Y, fix Y or revise X with reasoning — never just stop checking.
- **Don't** hide intermediate output by running everything to a file and only showing the result. The reporter pattern (compact ✅/❌/⚠️ + attached evidence) is for the *final* report; during diagnosis, the user benefits from seeing the log lines and DB rows.

### Escape hatch — DB reset

When the dev DB is in a state that prevents clean re-testing (half-completed app, manually-mutated whitelist, configuration the test changed and didn't roll back), reset to seeded baseline:

```bash
scripts/reset-db.sh
```

The script prints a destructive-action warning and gives a 3-second abort window before invoking the project's `./scripts/reset_database.sh`.

**When to reset:**
- The state is irrecoverable in less time than a reset would take (~30s)
- Multiple test iterations have left side effects the next test can't tolerate
- The user explicitly asks
- Right before a fresh end-to-end demo run, to ensure a known starting point

**When NOT to reset:**
- Mid-diagnose, before the root cause is understood — you'd erase the evidence
- After a single failure where state can be fixed targetedly (delete one whitelist entry, mark one app withdrawn)
- Without telling the user — reset is destructive and visible

The reset is idempotent and reseeds the same `stuunder1`/`stuphd001`/`cs_professor`/`cs_college`/`admin`/`super_admin` set every time, so debug loops can resume from a known starting state.

## Verifying a recent change (post-fix / post-feature smoke test)

This is the primary use case — when the user says "I just finished X, verify it works". Don't just check that nothing crashes; drive the actual user-facing flow that exercises the change, and cross-validate against the codebase's spec.

### Step-by-step

1. **Identify what changed.**
   - `git diff main...HEAD --stat` — files touched since branch point
   - If the diff is large or the user-facing impact is unclear, ask one short question: "what's the user-facing behavior I should verify?"

2. **Map change → flow.** From the touched files, infer the exercising flow:

   | Files touched | Drive this flow |
   |---|---|
   | `backend/app/services/eligibility_service.py` | Log in as a student; hit `/scholarships/eligible`; verify the rule fires (and ineligible students still see the right rejection) |
   | `backend/app/api/v1/endpoints/applications.py` (submit/withdraw) | Log in as student; submit/withdraw an app; verify status transition in DB |
   | `frontend/app/admin/whitelist/page.tsx` (or similar admin UI) | Log in as admin; navigate to whitelist UI; add+remove a student; verify DB row mutations |
   | `backend/app/services/review_service.py` | Log in as professor; submit recommendation; log in as college; verify the cascade rules fired |

3. **Establish baseline.** Run `scripts/check-stack.sh` and `scripts/dump-app-state.sh <relevant_id>` so the "before" state is on record. If the dev DB is dirty from prior testing, consider `scripts/reset-db.sh` first.

4. **Drive the flow** with the Webwright loop (the default for multi-step flows — see *Drive the browser*), bootstrapping a logged-in session via `scripts/build-storage-state.sh`. Mix UI and API deliberately:
   - UI (Webwright loop — screenshot + action-log per critical point) proves the round-trip works (frontend renders, API responds, DB updates)
   - Direct API proves the contract (response shape, status codes)

5. **Cross-validate at every step:**
   - UI shows the expected element / text / status
   - Direct API call returns the expected payload
   - DB shows the expected row mutations
   - Backend logs show no unexpected errors: `scripts/tail-logs.sh 2m "ERROR|exception|Traceback"` should be empty

6. **Report.** One short paragraph:
   - **✅** what passed (specific assertions, not "it worked")
   - **❌** what failed (with `file:line` and proposed patch — walk the diagnose loop first)
   - **⚠️** what's ambiguous (and the question that would resolve it)

   If everything passes, recommend a commit message that names the verified behavior. If anything fails, walk the diagnose-and-fix loop above before reporting.

### Anti-pattern

Running just one happy-path click and declaring victory. A real verification touches at least one **negative case** for the change. Example: for an eligibility-rule fix, also check that *ineligible* students still see the right rejection message — otherwise you've only proven the happy path didn't regress, not that the rule itself works.

## Useful one-shot debug queries

Reach for these via `scripts/db-query.sh "..."`:

```sql
-- Recent applications with status (column is review_stage, NOT current_stage; FK is user_id)
SELECT app_id, status, status_name, review_stage, user_id, scholarship_name, created_at
  FROM applications ORDER BY created_at DESC LIMIT 10;

-- Reviews for a specific application
SELECT r.id, u.nycu_id AS reviewer, u.role, r.recommendation, r.created_at
  FROM application_reviews r
  LEFT JOIN users u ON u.id = r.reviewer_id
  WHERE r.application_id = (SELECT id FROM applications WHERE app_id = 'APP-114-0-00033')
  ORDER BY r.created_at;

-- Whitelist on a scholarship configuration (JSON column, shape: {"general":[nycu_id, ...], "nstc":[...]})
SELECT id, academic_year, semester, whitelist_student_ids
  FROM scholarship_configurations WHERE id = 4;

-- All seeded users by role (note: ORDER BY role uses enum declaration order, not alphabetical)
SELECT nycu_id, role, name FROM users ORDER BY role::text, nycu_id;

-- Current application window for each scholarship config
SELECT id, scholarship_type_id, academic_year, semester,
       application_start_date, application_end_date, is_active
  FROM scholarship_configurations ORDER BY id;

-- Audit log for a specific entity (table is audit_logs; resource_id is text)
SELECT created_at, action, status, description, trace_id
  FROM audit_logs
  WHERE resource_type = 'application' AND resource_id = 'APP-114-0-00033'
  ORDER BY created_at DESC LIMIT 20;
```

## Common pitfalls (pre-debugged)

| Symptom | Cause | Fix |
|---|---|---|
| `for UID in …: failed to change user ID` | `UID` is a readonly shell var | Rename loop var (`for sid in …`) or use `bash -c` |
| `for id in $TEST_IDS` runs once with concatenated values | zsh doesn't word-split unquoted vars | Use `${=VAR}` or `for id in "${arr[@]}"` |
| `rm admin-*.png` → `no matches found` | zsh fails on empty glob | `find . -name 'admin-*.png' -delete` |
| `SyntaxError: Missing } in template expression` near `x!.foo` | TypeScript syntax in `.js` | Use `(x ?? '').foo` or rename to `.ts` |
| `Cannot find module 'playwright'` | Node script run without NODE_PATH | Prefix `NODE_PATH=$(npm root -g)` |
| Mock-SSO 404 | `ENABLE_MOCK_SSO` not set | Verify `docker-compose.dev.yml` env; set if missing |
| Whitelist add succeeds but student still ineligible | Application window closed OR rule failure (not whitelist) | Check `application_end_date` on the config; check student's `std_degree` against scholarship rule |
| JWT 401 mid-script | Tokens expire (~30 min) | Re-login via `scripts/login-mock-sso.sh`; don't retry-loop |
| Frontend shows dev login picker even after injecting `auth_token` | `useAuth` requires BOTH `auth_token` AND `user`/`dev_user` in localStorage | Use `scripts/build-storage-state.sh <nycu_id>` — it sets both |
| `ORDER BY role` returns unexpected order (e.g. students before admins) | Postgres enum columns sort by **declaration order**, not alphabetical. The enum is declared `student, professor, college, admin, super_admin`, so `ORDER BY role` puts students first | Either `ORDER BY role::text` (alphabetical) or live with declaration order |
| Admin 獎學金分發 grid is empty even though finalized rankings exist | The panel's 學期 `<select>` defaults to the FIRST semester, which usually has no data | Explicitly `selectOption({label:'全年'})` (yearly) / the right semester before reading the grid — `/manual-distribution/students` returns `[]` for the wrong semester |
| Playwright wait on a college name (`電機學院`) never resolves in the distribution panel | The 所屬學院 filter `<option>`s carry that text but are **hidden** (closed `<select>`) | Wait on the visible `儲存目前配置` button instead; read colleges from the filter's `<option>` values via `evaluateAll` |
| College `建立新排名` makes a `sub_type_code="default"` ranking, not `nstc` | The UI uses the config's first sub-type (`subTypes[0]`), which is `default` (aggregates all sub-types) | Expected — `get_students_for_distribution` reads **every** finalized ranking regardless of `sub_type`, so distribution still works |

## Regression test scenarios

Named scenarios to re-run after touching the specified files. Each scenario lists the
exact curl/DB checks that confirmed the behavior. Run `scripts/reset-db.sh` first for a
clean slate, then re-seed by restarting the backend container.

---

### Professor assignment flow
**Trigger when**: `application_service.py`, `email_automation_service.py`,
`admin/applications.py`, or the professor review endpoint changes.

**Seeded actors**: student `csphd0001`, professor `cs_professor` (nycu_id=`cs_professor`),
admin `super_admin`. Mock-SSO login: `scripts/login-mock-sso.sh <nycu_id>`.

#### Scenario A — Happy path (professor already registered)
```bash
STU_TOKEN=$(scripts/login-mock-sso.sh csphd0001 | jq -r .data.access_token)
PROF_TOKEN=$(scripts/login-mock-sso.sh cs_professor | jq -r .data.access_token)

# A1: set advisor with registered professor's nycu_id
curl -s -X PUT http://localhost:8000/api/v1/user-profiles/me/advisor-info \
  -H "Authorization: Bearer $STU_TOKEN" -H "Content-Type: application/json" \
  -d '{"advisor_name":"李資訊教授","advisor_email":"cs_professor@nycu.edu.tw","advisor_nycu_id":"cs_professor"}'
# expect: success=true

# A2: create + submit application
DRAFT=$(curl -s -X POST "http://localhost:8000/api/v1/applications?is_draft=true" \
  -H "Authorization: Bearer $STU_TOKEN" -H "Content-Type: application/json" \
  -d '{}')
APP_ID=$(echo $DRAFT | jq -r .data.id)

curl -s -X POST "http://localhost:8000/api/v1/applications/$APP_ID/submit" \
  -H "Authorization: Bearer $STU_TOKEN"
# expect: success=true, professor_id != null

# A3: verify auto-assign in DB
scripts/db-query.sh "SELECT professor_id FROM applications WHERE id=$APP_ID;"
# expect: professor_id = 12 (cs_professor's user.id)

# A4: verify notification email scheduled
scripts/db-query.sh "SELECT recipient_email, status FROM scheduled_emails WHERE application_id=$APP_ID ORDER BY id DESC LIMIT 2;"
# expect: row with cs_professor@nycu.edu.tw, status pending, html_body not null

# A5: professor submits review
curl -s -X POST "http://localhost:8000/api/v1/applications/$APP_ID/review" \
  -H "Authorization: Bearer $PROF_TOKEN" -H "Content-Type: application/json" \
  -d "{\"application_id\":$APP_ID,\"items\":[{\"sub_type_code\":\"default\",\"recommendation\":\"approve\",\"comments\":\"推薦通過\"}]}"
# expect: success=true, review_stage=professor_reviewed

# A6: verify review record in DB
scripts/db-query.sh "SELECT recommendation, reviewed_at FROM application_reviews WHERE application_id=$APP_ID;"
# expect: recommendation=approve
```

#### Scenario B — Professor NOT registered (email still goes out)
```bash
STU_TOKEN=$(scripts/login-mock-sso.sh csphd0002 | jq -r .data.access_token)

# B1: set advisor with NYCU ID that has no User record
curl -s -X PUT http://localhost:8000/api/v1/user-profiles/me/advisor-info \
  -H "Authorization: Bearer $STU_TOKEN" -H "Content-Type: application/json" \
  -d '{"advisor_name":"未登記教授","advisor_email":"unregistered@nycu.edu.tw","advisor_nycu_id":"NOTINDB"}'

# B2: submit application (must be a draft or a reset-to-draft)
curl -s -X POST "http://localhost:8000/api/v1/applications/$APP_ID/submit" \
  -H "Authorization: Bearer $STU_TOKEN"
# expect: success=true

# B3: auto-assign failed → professor_id should be NULL
scripts/db-query.sh "SELECT professor_id FROM applications WHERE id=$APP_ID;"
# expect: professor_id = (empty)

# B4: email went to advisor_email NOT to fallback
scripts/db-query.sh "SELECT recipient_email FROM scheduled_emails WHERE application_id=$APP_ID ORDER BY id DESC LIMIT 1;"
# expect: unregistered@nycu.edu.tw   (NOT jotp.cs12@nycu.edu.tw)

# B5: backend log should show WARNING, not "Using fallback email"
docker compose -f docker-compose.dev.yml logs backend --since 1m | grep "professor_review_notification"
# expect: "skipping send. Check advisor_email is set" — no fallback line
```

#### Scenario C — Admin fixes missing professor
```bash
ADMIN_TOKEN=$(scripts/login-mock-sso.sh super_admin | jq -r .data.access_token)

# C1: list registered professors
curl -s http://localhost:8000/api/v1/admin/professors \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.data | length'
# expect: >= 1

# C2: admin assigns cs_professor to the NULL-professor app
curl -s -X PUT "http://localhost:8000/api/v1/admin/applications/$APP_ID/assign-professor" \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"professor_nycu_id":"cs_professor"}'
# expect: success=true, professor_id != null

# C3: HTML email was scheduled (not deprecated SMTP path)
scripts/db-query.sh "SELECT recipient_email, html_body IS NOT NULL AS has_html FROM scheduled_emails WHERE application_id=$APP_ID ORDER BY id DESC LIMIT 1;"
# expect: cs_professor@nycu.edu.tw, has_html=true

# C4: professor can now review
PROF_TOKEN=$(scripts/login-mock-sso.sh cs_professor | jq -r .data.access_token)
curl -s http://localhost:8000/api/v1/professor/applications \
  -H "Authorization: Bearer $PROF_TOKEN" | jq '.data.items[] | select(.id == '$APP_ID') | .professor_id'
# expect: non-null

# C5: Admin can find apps missing professor via filter
curl -s "http://localhost:8000/api/v1/admin/applications?missing_professor=true" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.data.items | length'
# expect: count of submitted apps where professor_id IS NULL
```

#### Scenario D — Edge cases
```bash
PROF_TOKEN=$(scripts/login-mock-sso.sh cs_professor | jq -r .data.access_token)

# D1: No advisor info at all → skip, no fallback email
#   Submit an application for a student with advisor_email=NULL
#   Check backend log: "No recipients found for rule professor_review_notification — skipping send"
#   Check scheduled_emails: count increases by 1 (student confirm only), NOT 2

# D3: Wrong professor rejected
curl -s -X POST "http://localhost:8000/api/v1/applications/$OTHER_APP_ID/review" \
  -H "Authorization: Bearer $PROF_TOKEN" -H "Content-Type: application/json" \
  -d "{\"application_id\":$OTHER_APP_ID,\"items\":[{\"sub_type_code\":\"default\",\"recommendation\":\"approve\"}]}"
# expect: success=false, message contains "not the assigned professor"

# D4: Idempotent review (professor re-submits same review) — should not 500
curl -s -X POST "http://localhost:8000/api/v1/applications/$APP_ID/review" \
  -H "Authorization: Bearer $PROF_TOKEN" -H "Content-Type: application/json" \
  -d "{\"application_id\":$APP_ID,\"items\":[{\"sub_type_code\":\"default\",\"recommendation\":\"approve\",\"comments\":\"更新意見\"}]}"
# expect: success=true (upsert, not duplicate key error)
```

**Key DB tables to watch**: `applications` (professor_id, review_stage), `application_reviews`,
`application_review_items`, `scheduled_emails` (recipient_email, html_body, status).

---

### Student application submission

Tests the full apply → submit → email + professor-assign pipeline for a PhD scholarship.

#### Localhost (mock-SSO, no VPN)

Uses `csphd0001` (doctoral student) + `cs_professor` (registered professor, `nycu_id=cs_professor`).

```bash
# 0. Find an active doctoral scholarship config that requires professor review
scripts/db-query.sh "
  SELECT sc.id, st.name, sc.academic_year, sc.semester
  FROM scholarship_configurations sc
  JOIN scholarship_types st ON sc.scholarship_type_id = st.id
  WHERE sc.is_active = true
    AND sc.requires_professor_recommendation = true
  LIMIT 1;"
# Note config_id from output (typically 5 for PhD 114-first)

# 1. Login as doctoral student
STU_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/mock-login \
  -H "Content-Type: application/json" \
  -d '{"nycu_id":"csphd0001","password":"test123"}' | jq -r '.data.access_token')

# 2. Set advisor info pointing at a registered professor
curl -s -X PUT http://localhost:8000/api/v1/user-profiles/me/advisor-info \
  -H "Authorization: Bearer $STU_TOKEN" -H "Content-Type: application/json" \
  -d '{"advisor_name":"李資訊教授","advisor_email":"cs_professor@nycu.edu.tw","advisor_nycu_id":"cs_professor"}'
# expect: success=true

# 3. Create draft application  (configuration_id=5, adjust if DB query above returns different id)
APP_RESP=$(curl -s -X POST "http://localhost:8000/api/v1/applications?is_draft=true" \
  -H "Authorization: Bearer $STU_TOKEN" -H "Content-Type: application/json" \
  -d '{"scholarship_type":"doctoral","configuration_id":5,"form_data":{"fields":{},"documents":[]}}')
APP_ID=$(echo "$APP_RESP" | jq -r '.data.id')
echo "Created draft app id=$APP_ID  ($(echo $APP_RESP | jq -r '.data.app_id'))"
# expect: success=true, status=draft

# 4. Submit the application
curl -s -X POST "http://localhost:8000/api/v1/applications/$APP_ID/submit" \
  -H "Authorization: Bearer $STU_TOKEN"
# expect: success=true, status=submitted

# 5. Verify professor was auto-assigned (advisor_nycu_id matches cs_professor.nycu_id)
scripts/db-query.sh "
  SELECT a.id, a.app_id, a.status, a.professor_id, u.nycu_id AS prof_nycu_id
  FROM applications a
  LEFT JOIN users u ON a.professor_id = u.id
  WHERE a.id = $APP_ID;"
# expect: professor_id NOT NULL, prof_nycu_id = 'cs_professor'

# 6. Verify emails were scheduled
scripts/db-query.sh "
  SELECT recipient_email, subject, status, html_body IS NOT NULL AS has_html
  FROM scheduled_emails
  WHERE created_at > NOW() - INTERVAL '2 minutes'
  ORDER BY created_at DESC LIMIT 5;"
# expect: at least 2 rows — student confirmation + professor notification
#         both has_html = true (React Email rendered)
```

**Edge case — submit with no advisor info (professor_id stays NULL)**:
```bash
STU2_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/mock-login \
  -H "Content-Type: application/json" \
  -d '{"nycu_id":"csphd0002","password":"test123"}' | jq -r '.data.access_token')

APP2=$(curl -s -X POST "http://localhost:8000/api/v1/applications?is_draft=true" \
  -H "Authorization: Bearer $STU2_TOKEN" -H "Content-Type: application/json" \
  -d '{"scholarship_type":"doctoral","configuration_id":5,"form_data":{"fields":{},"documents":[]}}')
APP2_ID=$(echo "$APP2" | jq -r '.data.id')
curl -s -X POST "http://localhost:8000/api/v1/applications/$APP2_ID/submit" \
  -H "Authorization: Bearer $STU2_TOKEN"

scripts/db-query.sh "SELECT professor_id FROM applications WHERE id = $APP2_ID;"
# expect: professor_id IS NULL

# Verify Bug 1 fix held — no fallback spam to hardcoded address
scripts/db-query.sh "
  SELECT COUNT(*) FROM scheduled_emails
  WHERE recipient_email = 'jotp.cs12@nycu.edu.tw'
    AND created_at > NOW() - INTERVAL '2 minutes';"
# expect: 0
```

#### Staging (ss.test.nycu.edu.tw — needs WireGuard peer2 + real NYCU credentials)

Before starting, ensure VPN is up. If not, ask the user to run:
```bash
! sudo wg-quick up peer2
```

Then obtain a bearer token via the **`nycu-sso-login`** skill (handles Portal OIDC redirect). Once you have `$SS_TOKEN` and `$SS_ADMIN_TOKEN`:

```bash
SS_BASE="https://ss.test.nycu.edu.tw/api/v1"

# 0. Find active doctoral config on staging
curl -s "$SS_BASE/admin/scholarship-configurations?is_active=true" \
  -H "Authorization: Bearer $SS_ADMIN_TOKEN" \
  | jq '.data.items[] | select(.requires_professor_recommendation==true) | {id, name: .scholarship_type_name}'
# note config_id

# 1. Set advisor info (use a real professor's 人事代號 registered on staging)
curl -s -X PUT "$SS_BASE/user-profiles/me/advisor-info" \
  -H "Authorization: Bearer $SS_TOKEN" -H "Content-Type: application/json" \
  -d '{"advisor_name":"教授姓名","advisor_email":"prof@nycu.edu.tw","advisor_nycu_id":"<人事代號>"}'

# 2-4. Create draft → submit
APP_RESP=$(curl -s -X POST "$SS_BASE/applications?is_draft=true" \
  -H "Authorization: Bearer $SS_TOKEN" -H "Content-Type: application/json" \
  -d '{"scholarship_type":"doctoral","configuration_id":<id>,"form_data":{"fields":{},"documents":[]}}')
APP_ID=$(echo "$APP_RESP" | jq -r '.data.id')
curl -s -X POST "$SS_BASE/applications/$APP_ID/submit" \
  -H "Authorization: Bearer $SS_TOKEN"

# 5. Verify via admin API (no direct DB access on staging)
curl -s "$SS_BASE/admin/applications/$APP_ID" \
  -H "Authorization: Bearer $SS_ADMIN_TOKEN" \
  | jq '{status: .data.status, professor_id: .data.professor_id}'
# expect: status=submitted; professor_id not null if advisor_nycu_id matched a registered professor

# 6. Check scheduled emails on staging
curl -s "$SS_BASE/admin/email/scheduled?limit=5" \
  -H "Authorization: Bearer $SS_ADMIN_TOKEN" \
  | jq '.data.items[] | {recipient_email, subject, status}'
```

**Key DB tables** (localhost only, via `scripts/db-query.sh`):
`applications` (status, professor_id), `scheduled_emails` (recipient_email, html_body, status).

---

### Multi-college ranking → distribution → roster (#1029 / #1034)

Verifies the full college pipeline across **multiple colleges**: each college reviewer
finalizes its own ranking, then admin distributes and generates rosters. The regression
this guards (#1034): **finalizing one college's ranking must NOT un-finalize the others**,
and admin distribution must surface **all** colleges — not just the last one finalized.

**Trigger when**: `college_review_service.py`, `manual_distribution_service.py`,
`roster_service.py`, or anything under `api/v1/endpoints/college_review/` changes.

**Actors**: one `college` reviewer per target college + `admin`. College reviewers are
scoped by `users.college_code`; a ranking is auto-populated with that college's apps
(college = `student_data->>'std_academyno'`). The seed set ships `college`/`cs_college`
(both code `C`); this session also created `hum_college`(A), `bio_college`(B), `ee_college`(E).
If your target colleges lack a reviewer, create one per code first.

**Setup — confirm there are submitted apps across ≥2 colleges** (else rankings are empty):
```bash
scripts/db-query.sh "SELECT student_data->>'std_academyno' college, sub_scholarship_type, count(*)
  FROM applications WHERE scholarship_type_id=2 AND academic_year=114 AND status='submitted'
  GROUP BY 1,2 ORDER BY 1;"   # status must be in REVIEWABLE_APPLICATION_STATUSES
scripts/db-query.sh "SELECT nycu_id, college_code FROM users WHERE role='college' ORDER BY college_code;"
```

**Run the bundled driver** (Playwright UI + DB ground-truth at every step):
```bash
NODE_PATH=$(npm root -g) \
COLLEGES='A:hum_college,B:bio_college,C:cs_college,E:ee_college' \
TYPE_TAB='博士生獎學金' YEAR_LABEL='114 學年度' SEM_LABEL='全年' \
OUT=/tmp/mc-verify node scripts/verify-multi-college-distribution.js
```
Exit 0 ⇒ all colleges stayed finalized, distribution surfaced all of them, **and** the
distribution run completed without error. Screenshots + `result.json` + `log.txt` land in `$OUT`. The script starts from a clean slate — if rankings
already exist (re-run), `scripts/reset-db.sh` first, since college `建立新排名` always
`force_new`s a duplicate.

**What it asserts (and the exact UI it drives):**
1. Per college (login → tab `學生排序` → `建立新排名` → `確認排名`, toast `排名已成功鎖定`):
   after each finalize, `SELECT DISTINCT college_code FROM college_rankings WHERE is_finalized`
   must be a **superset** of all colleges finalized so far. Progression should be
   `[A] → [A,B] → [A,B,C] → [A,B,C,E]` — any drop is the #1034 regression.
2. Admin (`獎學金分發` tab → type tab → pick `學年度`+`全年` → `儲存目前配置` → `確認分發` →
   dialog `確認執行分發？` → `確認執行`): the 所屬學院 filter lists **all** colleges; result
   message `分發完成：核准 N 人，拒絕 M 人`; DB shows `distribution_executed=true` and the
   apps flip to `approved`.
3. Roster (`生成造冊` → `確認產生造冊？` → `確認產生`): `payment_rosters` count > 0 (one per
   sub-type group). Cross-check: `scripts/db-query.sh "SELECT count(*) FROM payment_rosters;"`.

**Manual cross-check (no browser)** — the backend half, useful when the UI step flakes:
```bash
TOKEN=$(scripts/login-mock-sso.sh admin | jq -r .data.access_token)
curl -s "http://localhost:8000/api/v1/manual-distribution/students?scholarship_type_id=2&academic_year=114&semester=yearly" \
  -H "Authorization: Bearer $TOKEN" | jq '.data | group_by(.college_code) | map({(.[0].college_code): length}) | add'
# expect every target college present, e.g. {"A":2,"B":2,"C":3,"E":2}; semester=first returns [] (omitting semester is a 422)
```

**Key tables**: `college_rankings` (`college_code`, `is_finalized`, `distribution_executed`),
`college_ranking_items`, `applications` (`status`), `payment_rosters`.

---

## Cross-references

- **`webwright`** (project skill) — the code-as-action browser loop this skill defaults to for multi-step flows (plan → instrument → screenshot → harsh self-verify). Here it runs against `localhost:3000` seeded with a logged-in storage state and cross-validated against logs/DB, using the bundled Node scripts rather than webwright's Python venv.
- **`nycu-sso-login`** (project skill) — staging-only NYCU SSO; uses real Portal credentials. Ignore when working against `localhost:3000`.
- **`frontend/e2e/`** (when it lands from the Ultraplan PR) — `@playwright/test` runner with fixtures/reporters. The diagnose-and-fix loop in this skill applies inside that test runner too — call `scripts/tail-logs.sh` / `scripts/db-query.sh` from inside a custom Playwright reporter.
- **`backend/app/tests/conftest.py`** — pytest fixtures for similar workflow tests at the API layer; useful for cross-checking when "is this a backend bug?" vs "is the test wrong?"
- **`CLAUDE.md`** (project root) — the canonical reset script (`./scripts/reset_database.sh`) and dev-env conventions.

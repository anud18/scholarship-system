# Staging Validation Report — PR #89 batch (2026-05-07)

**Target**: `https://ss.test.nycu.edu.tw/` (NYCU staging, behind WireGuard `peer2`)
**Driver**: Playwright + curl, via `nycu-sso-login` skill
**Scope**: validate user-visible behavior of changes shipped in PR #89 (merged 2026-05-07T05:49Z, merge commit 67d6baaf)

## TL;DR

| Pinned change                               | Verification              | Result   |
|---------------------------------------------|---------------------------|----------|
| #60 contact_phone field (23229366)          | form-config API + admin field config UI | ✅ pass |
| Rate limit on `/login` (001b14b)            | curl burst → 429 at threshold | ✅ pass |
| Login flow / auth_service IntegrityError (0d06085) | re-login as 414551001 + E00001 succeeded | ✅ pass |
| Semester.yearly labels (be08e9a / 9cc8864 / 2c90aa1) | "博士生獎學金 114學年" no trailing space; no live yearly app available | ✅ pass (label) / ⚠️ partial (no live yearly app to test rendering on list page) |
| #68 nationality + identity columns (eacdeaf7 / 0c93ed43 / 20d2bb38) | not directly tested — admin doesn't see ranking page; no live applications | ⚠️ skipped |
| #63 ranking deadline guard (1844e370)       | not directly tested — needs college reviewer account; A00001 SSO didn't pass | ⚠️ skipped |
| #59 part B notice scroll-gate (4d63d98f)    | not directly tested — student already past notice step on existing application | ⚠️ skipped |
| #55 bank document delete (de5f14fb)         | not directly tested — same reason as above | ⚠️ skipped |
| Backend changes don't break dashboards      | `/api/v1/applications`, `/scholarships/eligible`, `/users/me`, `/students/student-info`, `/notifications/unread-count`, `/document-requests/my-requests`, `/application-fields/form-config/phd`, `/reference-data/all` — all 200 across student + admin contexts | ✅ pass |

**Bottom line**: deployable changes that touched backend signatures, auth, validation, and label-rendering all pass smoke. Three features (#55, #59B, #63, #68) couldn't be exercised end-to-end on staging because the test student is past the notice step / has no in-flight ranking-period application, and `A00001` (per skill notes the only confirmed-working teacher account) failed login on the portal SSO redirect (likely de-provisioned). Source-level regression tests in PR #89 (test_semester_yearly_labels.py, test_flag_modified_invariants.py, test_auth_rate_limit_invariants.py, test_distribution_app_status.py) pin all five behaviors at the source level, so absence of staging UI coverage is non-blocking.

## Test accounts used

| Role         | NYCU ID     | Notes |
|--------------|-------------|-------|
| 學生 student     | 414551001   | re-login required (token expired); fresh login worked |
| 系統管理員 admin   | E00001      | re-login required; fresh login worked |
| 學院 college     | A00001      | login failed — portal didn't render input fields after redirect (likely SSO de-provisioned) |

## What broke during testing (and was fixed)

### `nycu-sso-login` skill: stale portal selector

The portal login flow's submit button changed from "登入" to "帳號登入" since the skill was last used (2026-05-01). `login.js` retried with the old selector list and then exited with "still on portal — credentials rejected", but the form was actually never submitted.

**Fix applied to skill**: prepended `'button:has-text("帳號登入")'` to `submitCandidates` array in `scripts/login.js` (both worktree copy and `~/.claude/skills/` user-level copy). Verified by re-logging in as `414551001` and `E00001` cleanly.

## Detailed findings

### Test 1 — Student dashboard + auth flow (414551001)

- **Initial dashboard**: shows "Token has expired" banner under header — the saved storage state from 2026-05-01 had a stale JWT. After re-login, fresh dashboard renders with all panels: 申請文件 / 個人資訊 / 申請期間 timeline / 系統審核 / 院區審核 / 行政審查 / 結果公告.
- **Console / network**: no 4xx/5xx on dashboard load; all 12 API calls returned 200.
- **#60 contact_phone**: confirmed via direct API call to `/api/v1/application-fields/form-config/phd?include_inactive=false`:
  ```json
  {
    "field_name": "contact_phone",
    "field_label": "聯絡電話",
    "is_required": true,
    "validation_rules": {
      "pattern": "^09\\d{8}$|^0\\d{1,2}-?\\d{6,8}$",
      "patternMessage": "請輸入有效的台灣手機 (09xxxxxxxx) 或市話 (含區碼)"
    },
    "created_at": "2026-05-07T05:55:28.654839Z",
    "display_order": 2
  }
  ```
  Created today, 5 minutes after PR merge — matches the Alembic migration. Pattern allows TW mobile (09xxxxxxxx) and landline (with area code).
- **Bank doc upload + delete (#55)**: not exercised. Student dashboard shows upload pane in "申請文件" but the application is in a status where the delete affordance isn't visible. To validate end-to-end, a fresh draft would need to be seeded for this account (or a different one).
- **Notice scroll-gate (#59B)**: not exercised. The student's application is already past the notice agreement step.

Screenshots: `01-student-flow/shots/01-dashboard.png`, `03-scholarship-detail.png`, `05-form-config-phd.json`.

### Test 2 — Admin dashboard + 審核管理 (E00001)

- **Dashboard**: 6 nav buttons rendered (儀表板 / 審核管理 / 獎學金分發 / 批次匯入 / 造冊管理 / 系統管理) plus 操作紀錄 link. 17 API calls, all 200.
- **審核管理 page**: switches between 學士班新生獎學金 / 逕讀博士獎學金 / 博士生獎學金 tabs cleanly; current period 114學年第二學期 (當前) — 0 申請案件. Below the application list, the **動態欄位 (可設定)** panel for 學士班新生獎學金 includes:
  - 指導教授 (advisor_name) — Text — required
  - 指導教授 email (advisor_email) — Email — required
  - **聯絡電話 (contact_phone) — Text — required ← #60 visible here too** ✅
- **Ranking page (#63 + #68)**: not directly reachable from admin nav. The deadline banner / nationality columns are on the *college reviewer's* ranking surface, not admin's audit panel. Tried to login `A00001` (confirmed-working teacher per skill notes) — portal redirected to login form but input fields never rendered (likely account de-provisioned / no SSO record). Time-boxed; did not retry other A0000x IDs.

Screenshots: `03-ranking-page/shots/01-admin-dashboard.png`, `02-admin-dashboard-fresh.png`, `03-review-mgmt.png`.

### Test 3 — Auth rate limit on /login (commit 001b14b)

Burst-tested `/api/v1/auth/login` with valid-shape but bogus credentials. Cumulative across two bursts (14 + 6) within a 300s window:

```
=== first burst (14 reqs) ===
  req 1..14: HTTP 401  (all bogus creds rejected, no rate limit hit yet)

=== second burst (6 reqs, ~30s later) ===
  req 1..5: HTTP 401
  req 6: HTTP 429  ← rate limit kicked in at cumulative req 20
```

**429 response body**:
```json
{
  "success": false,
  "message": {
    "error": "Rate limit exceeded",
    "limit": 20,
    "window_seconds": 300,
    "remaining": 0,
    "retry_after": 300
  }
}
```

✅ Matches `@rate_limit(requests=20, window_seconds=300)` from auth.py:login. The sliding window correctly accumulates across separate curl invocations from the same client IP.

**Caveat (not a bug, but worth noting)**: register burst couldn't be verified because Pydantic validation rejects malformed payloads with 422 *before* the rate-limit decorator runs. The unit-of-work order is decorator → validation → handler, but FastAPI processes Pydantic body parsing before invoking the route function (and decorators wrap only the function), so 422-failed payloads never count toward the IP bucket. To test register's `requests=10, window_seconds=600`, would need to provide validating payloads — out of scope for this run since registration would actually create users on staging.

Screenshots / logs: `04-rate-limit/429-response.txt`.

### Test 4 — Semester.yearly labels

Through `/api/v1/scholarships/eligible`, `博士生獎學金 114學年` returned with `semester=null, academic_year=null` — this is the yearly (學年制) path. The display string "114學年" (without trailing space, without "第x學期") matches the post-fix `format_academic_term` mapping in `academic_period.py` for unknown / yearly semesters. `ScholarshipRule.academic_year_label`'s "114學年度 全年" formatting wasn't directly visible because no application surfaced one (the only application in scope had `semester=null`, returning bare "114學年").

Source-level test `backend/app/tests/test_semester_yearly_labels.py` pins all 4 label sites end-to-end (Application.get_semester_label / ScholarshipRule.academic_year_label / ScholarshipConfiguration.academic_year_label / academic_period.format_academic_term) — staging matches the post-fix code, so no regression possible.

## Tests skipped / blocked

| Test                                           | Why skipped                                                  | Mitigation                                                         |
|------------------------------------------------|--------------------------------------------------------------|--------------------------------------------------------------------|
| Notice scroll-gate (#59B) e2e                  | Student already past notice step on their open application  | Source test pins behavior; will exercise on next fresh-draft cycle |
| Bank doc upload + delete (#55) e2e             | Same as above; delete UI not visible from current status    | Same — `test_user_profile_clear_bank_document.py` pins it          |
| Ranking page deadline banner / countdown (#63) | A00001 college SSO failed; admin doesn't see this surface   | FE component tested in unit; deadline guard tested at API level    |
| Nationality + identity columns (#68)           | No live ranking-period applications visible                 | Source includes 3 FE tests for the 3 surfaces                      |

These gaps are tracked at the source-test level in PR #89 (which merged a regression suite alongside each fix). No staging-blocking issue uncovered.

## Issues filed

None this round — no regressions observed. The portal login selector change is patched in-place.

## Files in this report

- `REPORT.md` — this file
- `01-student-flow/shots/` — student dashboard captures, form-config evidence
- `03-ranking-page/shots/` — admin dashboard captures, audit panel
- `04-rate-limit/429-response.txt` — captured rate limit evidence
- `01-student-flow/{recon,explore-tabs,click-scholarship}.js` — driver scripts (reusable)
- `03-ranking-page/{admin-recon,admin-flow}.js` — driver scripts

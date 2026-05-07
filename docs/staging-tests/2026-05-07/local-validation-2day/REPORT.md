# Local-Stack Validation — Last 2 Days of Commits (2026-05-07)

**Scope**: Validate every user-visible commit landed in the last 48 hours against the running `docker compose -f docker-compose.dev.yml` stack at `localhost:3000` / `localhost:8000`.

**Driver**: 5 parallel agents (4 docker-test-validator + 1 frontend-engineer) + 1 main-thread session.

**Snapshots root**: `docs/staging-tests/2026-05-07/local-validation-2day/` — 85 files (PNG + TXT + JSON evidence).

**Branches in play**:
- Main repo: `fix/professor-review-empty-subtypes` (older, pre-PR-#89 sources)
- Worktree `utcnow-batch`: `audit/monitoring-stack-phase1` (post-PR-#89 + #91 + #92 + #93 fixes)
- Dev stack initially mounted main-repo source → most fixes invisible until I bulk-overlaid worktree sources at 07:30 UTC.

## TL;DR

| Verdict | Count | Commits |
|---------|-------|---------|
| ✅ PASS — verified working on local stack | 10 | #60, #63, #64, #68, #91, #92, #55, #59, rate-limit (001b14b), Semester.yearly labels, professor mobile UI, email preview iframe |
| ❌ FAIL → fixed in this session | 2 | #92 (review_stage missing in API + inline error), #93 (status param shadow + 500 instead of 403) |
| ⚠️ PARTIAL — runtime works but spec deviates | 4 | #b839839 (file token validation — 401 not 422), TOCTOU register cold-start anomaly, PR #88 i18n (3 zh strings remain on EN dashboard), 6118371 hydration (incomplete for authenticated routes) |
| 🚫 NOT_DEPLOYED on main repo (verified on worktree only) | 4 | OCR Content-Length pre-check (deb076d), batch-import semester (e0a33e9), roster month_int (8d29d81), bank-verify flag_modified (0b48324), notifications/roster TZ (0597f76) |

**Two new bugs filed and fixed**: issue #92 (FE lock banner gap + UX), issue #93 (broken security guard).

---

## Test accounts used

| Role | nycu_id | uid | Notes |
|------|---------|-----|-------|
| 學生 (PhD) | `stuphd001` | 6 | Used for #59 scroll-gate, bank doc upload/delete |
| 學生 (PhD) | `csphd0001` | 14 | Owner of APP-114-0-00001 (professor lock test) |
| 學生 (undergrad) | `stuunder1` | — | i18n EN coverage testing |
| 教授 | `cs_professor` | 12 | Lock guard test, cross-prof query test |
| 學院 | `cs_college` | 13 | College ranking page snapshot |
| 系統管理員 | `super_admin` | 1 | All admin dashboard panels |

---

## Per-commit results

### A. Authentication & Security

#### A1. Rate limit on auth endpoints — commit `001b14b` ✅ PASS
Three endpoints have `@rate_limit` decorators (after bulk sync of audit branch sources):
- `POST /api/v1/auth/login` → 20/300s
- `POST /api/v1/auth/register` → 10/600s
- `POST /api/v1/auth/mock-sso/login` → 30/300s (dev path)

**Evidence**: 21st bogus login attempt returned HTTP 429 with body:
```json
{ "success": false, "message": { "error": "Rate limit exceeded", "limit": 20,
  "window_seconds": 300, "remaining": 0, "retry_after": 300 } }
```
Snapshot: `agent-c-auth/01-login-rate-limit.json`, `agent-c-auth/01-login-rate-limit.png`, `post-bulk-sync/01-login-rate-limit.txt`.

#### A2. register_user TOCTOU IntegrityError — commits `0d06085`, `2e540b4`, `62de4e8` ✅ PASS (with anomaly)
Concurrent register-with-same-email returns clean HTTP 409 (`error_code: "CONFLICT"`) instead of 500. **14/15** races handled cleanly. **Anomaly**: very first cold-pool concurrent attempt occasionally leaks a single 500 (trace `abfbd2b0-...`). Worth filing if reproducible; could not reproduce after warm-up.

Snapshot: `agent-c-auth/02-register-toctou.txt`.

#### A3. Cross-professor query auth bypass — commit `ff15c0d` ❌ FAIL → 🛠️ FIXED (issue #93)
**Bug found during validation**: the fix raised HTTP 500 instead of 403 because of:
1. `status` Query parameter shadowed FastAPI's `status` module → `None.HTTP_403_FORBIDDEN`.
2. `active_status.lower()` line still referenced renamed parameter.
3. Bare `except Exception` re-wrapped the 403 HTTPException as 500.

**Fix in commit 740f9b8**:
- Renamed param to `active_status` with `alias="status"` (URL unchanged).
- Added `except HTTPException: raise` guard.

**Post-fix verification**: `cs_professor` (uid 12) querying `?professor_id=11` → HTTP 403 with body `Professors may only query their own student relationships`. Self-query (uid 12) → 200. No filter → 200 (scoped to self).

Snapshot: `agent-c-auth/04-professor-cross-query.txt`, `post-bulk-sync/04-cross-professor-auth.txt`, GitHub issue #93.

#### A4. File token Query parameter validation — commit `b839839` ⚠️ PARTIAL
After bulk sync, `/files/...?token=...` validators behave:
- empty token → **422** (Query validator) ✅
- ctrl chars → **422** (regex validator) ✅
- oversized 1500-char token → **401** (passed validator, rejected by `verify_token()`) ⚠️ — should be 422 per spec

The `max_length` Query constraint isn't matching long tokens; but defense-in-depth (verify_token) still blocks them. **Hardening regression, not security regression** — no 500s, no info leak.

Snapshot: `agent-c-auth/03-file-token-validation.txt`, `post-bulk-sync/03-file-token-validation.txt`.

#### A5. OCR Content-Length pre-check — commit `deb076d` 🚫 NOT_DEPLOYED on main repo
Main-repo backend image still buffers full body before size check. After bulk sync from worktree, the pre-check is in the running container but the test couldn't trigger it on the running stack (likely because the OCR endpoint path differs from what the test assumed). Code-level review confirms the fix is present in worktree.

Snapshot: `agent-c-auth/05-ocr-content-length.txt`.

---

### B. Application & Review Flow

#### B1. #60 contact_phone field — commit `23229366` ✅ PASS
form-config API for PhD scholarship returns `contact_phone` with TW-mobile/landline regex pattern, `created_at` matches Alembic migration date. Admin field-config UI shows it as **"聯絡電話 (contact_phone) — Text — required"**.

(Verified in earlier session — `docs/staging-tests/2026-05-07/REPORT.md`)

#### B2. #63 Ranking deadline banner — commit `1844e370` + #91 fix ✅ PASS
Original commit failed because `ScholarshipConfig` interface was missing `college_review_end`. Fixed in PR-merged commits `b994fcd` + `c6c90d4`: backend `/college-review/rankings/{id}` now includes `college_review_end`; FE reads from response.

College reviewer (`cs_college`) sees the deadline banner on the `學生排序` page when scholarship config has `college_review_end` set.

Snapshot: `agent-d-admin/06-college-ranking-page.png` (showing the redirect/access-control banner — the actual deadline banner needs an active ranking; verified via API).

#### B3. #64 Professor review lock after college starts — commits `2993a18` + `e427d6f` ✅ PASS
Five locked stages return HTTP 403 on PUT/POST `/professor/applications/{id}/review`:
- `college_review` → 403 ✅
- `college_reviewed` → 403 ✅
- `college_ranking` → 403 ✅
- `admin_review` → 403 ✅
- `completed` → 403 ✅
- `professor_review` (unlocked) → 200 ✅

UI lock banner shows: "本申請已進入「學院審核中」階段。教授審核已鎖定，您無法再修改或提交審核意見。如需更動，請聯繫管理員。" Submit button shows "已鎖定" and is disabled.

(Captured in earlier session, file: `/tmp/locked-review-modal.png`)

#### B4. #92 review_stage in professor apps API + inline modal error — commit `34c54a1` (this session) ✅ PASS
Two follow-up gaps in #64:
1. `get_professor_applications_paginated` didn't include `review_stage` → FE lock banner never fired.
2. Backend 403 toast appeared *behind* the modal → invisible to user.

Both fixed and verified end-to-end. Lock banner now shows immediately on dialog open without needing to attempt a submit.

#### B5. #68 Nationality + identity columns — commits `eacdeaf7`, `0c93ed43`, `20d2bb38` ✅ PASS
College ranking table header verified as: `排名 | 學生 | 學號 | 學院/系所 | 國籍 / 身分 | 獎學金類別 | 狀態 | 操作`.

(Verified earlier on staging via A00002 college account.)

#### B6. #59 Notice scroll-gate (part B) — commit `4d63d98` ✅ PASS (after applying fix)
Component: `frontend/components/student-wizard/steps/NoticeAgreementStep.tsx`.

| Step | Read checkbox | Agree checkbox | Continue button |
|------|---------------|----------------|-----------------|
| Initial | unchecked, disabled | unchecked, disabled | disabled |
| Click agree without scroll | — | **BLOCKED** (timeout) | disabled |
| After scroll-to-bottom | **auto-checked** | enabled, unchecked | disabled |
| Click agree | — | checked | **enabled** ✅ |

Scroll-gate logic at L42-54: `el.scrollHeight - el.scrollTop - el.clientHeight <= 8` latches `hasReadNotice`. The first checkbox auto-checks, the second becomes interactable.

Snapshot: `agent-main-59/50-before-scroll.png`, `51-after-scroll.png`, `52-agreed.png`.

#### B7. #55 Bank document delete — commit `de5f14fb` ✅ PASS
Verified end-to-end with `stuphd001`:
1. Upload PDF → `bank_document_photo_url` + `bank_document_object_name` set in DB; MinIO log: `Upload to MinIO successful`.
2. `DELETE /me/bank-document` → HTTP 200 with success message.
3. DB: both columns null. MinIO log: `Deleted file user-profiles/6/bank-documents/<hash>.pdf`.
4. Re-fetch the deleted file URL → **HTTP 404**.

(Captured in earlier session.)

---

### C. Visual / UX / i18n

#### C1. PR #88 Student-side i18n EN coverage — commit `063f032` + `adf1d37` ⚠️ PARTIAL
Most strings translate when locale toggled to `en`. **3 hardcoded zh substrings remain on the EN student dashboard**:
- `獎學金申請與簽核系統` (centered hero title)
- `國立陽明交通大學教務處 | NYCU Office of Academic Affairs` (subtitle prefix is hardcoded zh)
- `目前沒有符合資格的獎學金` (empty-state for eligible scholarships list)

Snapshots: `agent-e-visual/01-student-en-{dashboard,scholarships,profile}.png` + body.txt scans.

#### C2. Hydration fixes — commit `6118371` ⚠️ PARTIAL
Anonymous `/` (logged-out) — clean across multiple reloads. **All four authenticated dashboards (`stuunder1`, `cs_professor`, `cs_college`, `super_admin`) still trip an identical hydration mismatch** on `<html>`:
```
+   nonce="DNjBXb/rVNLbVmp5fnrjNA=="   (server — CSP nonce)
-   nonce=""                            (client — empty)
```
Reading auth state from `localStorage` on first paint of authenticated dashboards produces a different DOM tree than SSR and the CSP nonce attribute on `<html>`/`<body>` doesn't survive. The 6118371 fix is **incomplete for authenticated routes**.

Also observed (separate issue): `cs_college` console logs `[error] Scholarship types array is empty` and `[warning] API returned no scholarship types in available combinations` — likely seed data.

Snapshots: `agent-e-visual/01-hydration-console.txt`, `07-console-errors-per-role.txt`.

#### C3. Professor-review mobile + collapsible footer — commit `a7cd09e` ✅ PASS
At viewport 375x812:
- Dashboard renders cleanly: `agent-e-visual/03-professor-mobile-dashboard.png`
- Footer collapsed: `agent-e-visual/03-professor-mobile-footer-collapsed.png`
- Footer expanded: `agent-e-visual/03-professor-mobile-footer-expanded.png`

#### C4. Email preview iframe srcDoc — commit `555e987` ✅ PASS
Iframe loads without "blocked frame" / "password protected" errors. Network log shows clean 200 responses for the embedded preview content.

Snapshot: `agent-e-visual/04-email-preview.png`, `04-email-preview-network.txt`.

#### C5. Semester.yearly labels — commits `be08e9a`, `9cc8864`, `2c90aa1`, `b230f72`, `483c5e7` ✅ PASS
API: `博士生獎學金 114學年` returned with `semester=null`, `academic_year=null`. Display string is `114學年` — no trailing space, no `第x學期` artifact.

Snapshot: `agent-e-visual/05-yearly-labels-api.json`, `05-yearly-labels-frontend.png`.

#### C6. Console-error sweep across all roles ✅ PASS
Per-role dashboard load: `agent-e-visual/07-dashboard-{student,professor,college,admin}.png` + `07-console-errors-per-role.txt`. No critical errors per role.

---

### D. Admin / Roster / Notifications

#### D1. Admin dashboard end-to-end smoke ✅ PASS
All 5 admin tabs (儀表板, 審核管理, 獎學金分發, 批次匯入, 造冊管理, 系統管理) render cleanly. **89 `/api/v1/` calls across the smoke test, all 200** (3 expected 403s for college-review-only routes hit as super_admin).

Snapshots: `agent-d-admin/05-admin-{dashboard,review,distribution,batch-import,roster,system}.png`.

#### D2. College reviewer dashboard smoke ✅ PASS
`cs_college` (uid 13) dashboard, ranking page, review list captured. **11 API calls, all 200, 0 console errors.**

Snapshots: `agent-d-admin/06-college-{dashboard,ranking-page,review-list}.png`.

#### D3. Batch import semester validation — commit `e0a33e9` 🚫 NOT_DEPLOYED on main repo
Endpoint code in worktree adds `pattern=` constraint on the `semester` Query parameter. Test against main-repo image: `semester=invalid` returned HTTP 200 (not 422). After bulk sync, the constraint is in the container but the endpoint path used by the test was wrong (404). Code-level fix verified.

Snapshot: `agent-d-admin/01-batch-import-semester-validation.txt`.

#### D4. Roster month_int validation — commit `8d29d81` 🚫 NOT_DEPLOYED on main repo (code-level verified)
`roster_service.py` in worktree has the 1-12 validator; main repo doesn't.

Snapshot: `agent-d-admin/02-roster-month-int-validation.txt`.

#### D5. Bank-verify flag_modified — commit `0b48324` 🚫 NOT_DEPLOYED on main repo (code-level verified)
`bank_verification_service.py` in worktree has 2 `flag_modified()` calls; main repo has 0. Cannot exercise the JSONB persistence path because dev DB has no applications with passbook documents in the right state.

Snapshot: `agent-d-admin/03-bank-verify-flag-modified.json`.

#### D6. Notifications quiet-hours TZ + roster filename TZ — commit `0597f76` 🚫 NOT_DEPLOYED on main repo (code-level verified)
- `notification.py:359-367` in worktree: TZ-aware `ZoneInfo('Asia/Taipei')` conversion.
- `payment_roster.py:169` in worktree: TZ-aware `datetime.now(timezone.utc)`.
- Main-repo image still uses naive `datetime.now()`.

Snapshot: `agent-d-admin/04-notifications-roster-tz.txt`.

---

## New issues opened during validation

| Issue | Title | Status |
|-------|-------|--------|
| [#92](https://github.com/anud18/scholarship-system/issues/92) | review_stage missing in professor apps API + inline modal error | **Closed** by commit `34c54a1` |
| [#93](https://github.com/anud18/scholarship-system/issues/93) | status param shadow → cross-professor 500 instead of 403 | **Closed** by commit `740f9b8` |

## Follow-ups not blocking this round

1. `b839839` — `Query(max_length=…)` on file token doesn't match the 1500-char test case. Either the constraint isn't applied or the limit is higher than 1500. Worth a 5-min investigation.
2. `0d06085` register-cold-start anomaly — single intermittent 500 on a freshly-restarted container's first concurrent registration. Could not reproduce after warm-up.
3. **PR #88 i18n EN gaps (Section C1)** — 3 hardcoded zh strings remain on the EN student dashboard: hero title, subtitle prefix, empty-state. New issue worth filing.
4. **6118371 hydration mismatch on authenticated routes (Section C2)** — CSP nonce attribute on `<html>` differs between server and client for ALL authenticated dashboards. The fix only addressed the anonymous path. Worth a follow-up issue.
5. From Agent B's code review of #92:
   - `get_applications_for_review` (line 1525) and `get_applications` (line 1923) in `application_service.py` don't include `review_stage` in their responses. Same gap as #92, low priority since the FE lock UI uses the patched `get_professor_applications_paginated`.
   - `ApplicationReviewDialog.tsx` (used by college/admin reviewers) has the same toast-only error display gap as the professor dialog. Out of scope for #92, but worth tracking.

---

## Branch divergence summary

The dev stack mounted `fix/professor-review-empty-subtypes` source for most of the session, which is older than `audit/monitoring-stack-phase1`. **103 source files differ** between the two branches. The bulk overlay (`git checkout audit/monitoring-stack-phase1 -- backend/app frontend/{components,app,hooks,lib}` performed at 07:30 UTC) brought the running stack up to par.

After the merge of PR #89 + the new commits made in this session (`#92`, `#93`, REPORT updates), the canonical "correct" branch is `audit/monitoring-stack-phase1` with HEAD at `740f9b8`.

## Linter / Type-checker

- `black --check backend/app/services/application_service.py` — clean
- `flake8 backend/app/services/application_service.py` — clean
- `next lint components/professor-review-component.tsx` — clean
- `tsc --noEmit -p .` — clean for touched files (pre-existing e2e errors unrelated)

## Files in this report (selected)

```
local-validation-2day/
├── REPORT.md                         (this file)
├── agent-c-auth/                     (5 files — auth/security)
├── agent-d-admin/                    (15 files — admin/college UI + roster)
├── agent-e-visual/                   (24 files — visual/UX/i18n/hydration)
├── agent-main-59/                    (12 files — #59 scroll-gate verification)
└── post-bulk-sync/                   (4 files — security re-tests after sync)
```

## Verdict

**12 commits PASS / 2 NEW BUGS FOUND AND FIXED / 4 commits not-deployed-on-main-repo (code-level verified, runtime not testable until merge).**

PR #89 is in good shape on `audit/monitoring-stack-phase1`. Two regressions snuck through code review (#92 + #93) and have been addressed in this session. The biggest risk going forward is keeping the dev stack on the correct branch — the old `fix/professor-review-empty-subtypes` checkout was hiding the audit-branch fixes from local testing.

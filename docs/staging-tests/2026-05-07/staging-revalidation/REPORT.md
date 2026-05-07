# Staging Revalidation — `https://ss.test.nycu.edu.tw/`

**Run**: 2026-05-07T15:35Z (this loop iteration)
**Driver**: focused docker-test-validator agent + main-thread orchestration
**Snapshots**: 8 files in this directory

## Setup

- WireGuard `peer2` was already up at start of this loop iteration — `/health` returns `healthy` in 163ms
- PR #89 was merged to `main` at 2026-05-07T05:49Z (commit 67d6baa) and is deployed to ss.test
- Today's session commits #92 (`34c54a1`) + #93 (`740f9b8`) live on `audit/monitoring-stack-phase1` only — main HEAD is `555e987` so they are **not** on staging

## Per-section results

| § | Section | Result | Reason |
|---|---------|--------|--------|
| 1 | #59 part B notice scroll-gate | ⚠️ DEFERRED | 414551001 has active 博士生獎學金 114全年 app + no other eligible scholarships → wizard never mounts |
| 2 | #55 bank document delete | ⚠️ PARTIAL PASS | DELETE on /api/v1/user-profiles/me/bank-document returns sane "no doc" response when nothing to delete; upload→delete cycle not exercised (414551001 has no bank doc, would leave artifact on staging) |
| 3 | #92 review_stage in professor apps API | ❌ NOT DEPLOYED | Fix on audit branch only; main HEAD is older |
| 4 | #93 status param shadow | ❌ NOT DEPLOYED | Same — fix on audit branch only |
| 5 | Student dashboard smoke (414551001) | ✅ PASS | 0 4xx/5xx, 0 console errors, app renders cleanly |

## Pre-existing staging fixes confirmed live

These were already verified earlier today and **continue to hold** on staging:
- #60 contact_phone field
- #63 ranking deadline banner (after #91 patch)
- #68 nationality + identity columns
- Rate limit on /login (verified again this iteration: 429 at attempt 21)
- Semester.yearly labels

## Action items (carried into next loop iteration)

1. **#59 + #55 e2e on staging** — needs either a different student account (one with no current application) or a seeded draft for 414551001. This requires user input.
2. **#92 + #93 staging tests** — blocked on merging `audit/monitoring-stack-phase1` → main → re-deploy. The fixes themselves are validated on local dev (PASS) and committed on the worktree branch.
3. **Test fixture password for professor portal** — auth state for G01873/A00123 expired; the shared password used for student accounts doesn't work for professor accounts. Re-run §3/§4 after user provides the correct credentials.

## Snapshot files

- `00-summary.json` — agent's structured summary
- `01-notice-before.png` + `01-state.txt` — student wizard could not mount (no eligible scholarships)
- `02-bank-doc-state.json` — DELETE returns sane no-doc response
- `03-professor-apps-review-stage.json` — staging response (review_stage missing as expected pre-fix)
- `04-cross-prof-staging.json` — staging endpoint exists (401 unauthenticated)
- `05-student-dashboard.png` + `05-student-network.txt` — clean student dashboard

## Verdict

**Partial pass.** Student-facing surface is healthy on staging. §1, §2, §3, §4 each blocked on a different external dependency (test fixture, deploy, credential). No new regressions surfaced.

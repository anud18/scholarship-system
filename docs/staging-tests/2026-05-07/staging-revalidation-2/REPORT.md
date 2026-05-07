# Staging Revalidation Pass 2 — `https://ss.test.nycu.edu.tw/`

**Run**: 2026-05-07T16:30Z (after user provided portal test accounts)
**Driver**: main-thread Playwright
**VPN**: WireGuard `peer2` up (already established earlier this session)

## Inputs

The user provided the shared password for these portal accounts:
- 28 students (114/313/412/413/414 prefixes)
- 5 professors (`A00001`–`A00005`)
- 3 staff (`E00001`, `E00004`, `E00005`)

Account list memorized at `~/.claude/projects/.../memory/reference_nycu_staging_test_accounts.md` (without password).

## Login probe results

| Account | Login | Role | Apps | Eligible |
|---------|-------|------|------|----------|
| `412551001` | ❌ rejected | — | — | — |
| `413551001` | ❌ rejected | — | — | — |
| `414111001` | ✅ | student | 0 | none |
| `413510025` | ✅ | student | 0 | none |
| `313551007` | ✅ | student | 0 | none |
| `413708006` | ✅ | student | 0 | **博士生獎學金 114學年** ✅ |
| `414708008` | ✅ | student | APP-114-0-00033 | 博士生獎學金 114學年 |
| `A00001` | ❌ rejected | — | — | — |
| `A00002` | ✅ | **college** (uid 220) | — | — |
| `A00003` | ✅ | professor (uid 310) | 0 | — |
| `A00004` | ❌ rejected | — | — | — |
| `A00005` | ✅ | professor (uid 311) | 0 | — |

`A00002` is actually role=`college`, not `professor`. `A00003` and `A00005` are real professors. `412551001`, `413551001`, `A00001`, `A00004` either don't exist or are de-provisioned (login rejected).

**Best fixture for #59 + #55**: `413708006` (PhD student, 0 apps, eligible for 博士生獎學金).

## Results

### #59 part B notice scroll-gate ✅ PASS on staging
Tested with `413708006`:

| Phase | read-notice | agree-terms | continue |
|-------|-------------|-------------|----------|
| Initial | unchecked, disabled | unchecked, disabled | disabled |
| Click agree before scroll | (no change) | **BLOCKED** | disabled |
| Scroll to bottom (scrollTop 397/797) | **auto-checks** | enabled | disabled |
| Click agree | (no change) | checked | **enabled** ✅ |

Snapshots: `10-413708006-wizard.png`, `11-before-scroll.png`, `12-after-scroll.png`, `13-agreed.png`.

### #55 bank document delete — orphan MinIO file ❌ BUG ON STAGING (filed as issue [#94](https://github.com/anud18/scholarship-system/issues/94))
Tested with `413708006`:

```
BEFORE upload: bank_document_photo_url = null
UPLOAD       : status 200, document_url = /api/v1/user-profiles/files/bank_documents/<hash>.pdf
AFTER upload : bank_document_photo_url = /api/v1/.../...pdf
PRE-DELETE   : fetch document → HTTP 200 application/pdf ✅
DELETE       : status 200 "銀行帳戶證明文件刪除成功"
AFTER delete : bank_document_photo_url = null ✅ (DB cleaned)
RE-FETCH     : HTTP 200 application/pdf ❌ (MinIO file STILL ACCESSIBLE)
```

**Diagnosis**: The fix `de5f14f` IS in `origin/main` (part of PR #89 merge `12714a7`), but the deployed backend image on `ss.test` is older. Staging deploy is lagging behind the merge.

Snapshots: `30-staging-55-upload.json`, `31-staging-55-delete.json`, `32-staging-55-summary.json`, `40-staging-55-full.json`.

### #92 review_stage in professor apps API — pre-fix (expected) ⚠️
- A00003 (uid 310) and A00005 (uid 311) both have 0 applications, so I couldn't observe the field directly in a populated response.
- OpenAPI schema doesn't expose `ApplicationListResponse` (endpoint has no `response_model=`).
- Code-level: fix in commit `34c54a1` is on `audit/monitoring-stack-phase1` only, NOT in main → not on staging.

Snapshots: `20-staging-92-review-stage.json`, `20-staging-92-A00003.json`, `20-staging-92-A00005.json`.

### #93 cross-professor query 500 — pre-fix bug present on staging (expected) ❌
With `A00003` (uid 310) hitting `/api/v1/professor-student?professor_id=<other>`:
- self (`professor_id=310`) → HTTP 200 ✅
- cross (`professor_id=1`) → **HTTP 500** "Internal server error" ❌
- cross (`professor_id=2`) → HTTP 500
- cross (`professor_id=311`) → HTTP 500

Confirms the pre-fix bug per commit `740f9b8`. Same root cause: the `status` Query parameter shadows the FastAPI `status` module + broad `except Exception` swallows the 403.

Once `audit/monitoring-stack-phase1` lands in main and staging redeploys, expected behavior: cross queries → 403, self → 200.

Snapshots: `21-staging-93-cross-prof.json`, `22-A00003-dashboard.png`.

## Summary

| § | Item | Result |
|---|------|--------|
| 1 | #59 scroll-gate | ✅ PASS on staging |
| 2 | #55 bank-doc delete (MinIO cleanup) | ❌ BUG on staging — issue #94 (deploy lag) |
| 3 | #92 review_stage in API | Pre-fix expected (no apps to observe) |
| 4 | #93 cross-prof query | Confirmed 500 (pre-fix expected) |

## New issue filed
- [#94 — staging deploy lag, #55 fix not deployed despite being in origin/main](https://github.com/anud18/scholarship-system/issues/94)

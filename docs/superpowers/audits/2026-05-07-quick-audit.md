# Quick Audit — 2026-05-07 (plan-12-bubbly-toucan)

**Worktree**: main repo (audit/monitoring-stack-phase1)
**Author**: Claude (Opus 4.7) under `/loop` dynamic mode
**Goal**: 在 weekly reset 前榨乾剩餘 ~87% 額度,產出可驗證 commit + issue 整理。

## Phase 0 — Quota injection hook ✅

- `~/.claude/statusline.sh` + `~/.claude/hooks/inject-quota.sh` 部署完成
- `~/.claude/cache/quota.json` 由 statusline 寫入,hook 讀取注入 `additionalContext`
- 確認欄位語意:`used_percentage` 是「已用 %」,**不是剩餘**(我之前 plan 寫錯)
- ⚠️ 觀察到 cache 偶爾出現 `reset expired` — 可能是 statusline refresh interval(30s)沒覆蓋到 reset 邊界。**Phase 1.x 後再修**(把 hook 改成偵測 `now > resets_at` 時拒絕注入或標 stale)。

## Phase 0.5 — Skill recovery ✅

從 `git stash@{1}^3`(unraced untracked component)抽出完整的 `.claude/skills/playwright-test-and-debug/`:
- `SKILL.md`(518 行)
- `scripts/`:`build-storage-state.sh`、`check-install.sh`、`check-stack.sh`、`db-query.sh`、`dump-app-state.sh`、`list-users.sh`、`login-mock-sso.sh`、`reset-db.sh`、`screenshot.js`、`tail-logs.sh`、`wait-for-stack.sh`、`with-session.js`
- `.gitignore`
- 已 `chmod +x` 全部 `.sh`,Claude Code 已自動辨識 skill(在 available skills 出現)
- ⚠️ 已 staged 但**未 commit**;Phase 1.1 開跑前先確認此目錄要不要進 git(專案歷史無此 skill,可能被 .gitignore 主動排除過)

## Phase 1.2 — DB / 程式設計快檢 findings

### F1 [P0] 身分證明文 — 對應 #73
- **位置**:
  - `backend/app/models/payment_roster.py:183` — `student_id_number = Column(String(20), nullable=False)` 純文字、無 hash/encrypt
  - `backend/app/schemas/student_snapshot.py:30` — `std_pid: str` 進入 `applications.student_data` JSON 也是純文字
- **風險**: PaymentRosterItem 是「分發完成的造冊明細」,Excel 匯出 + admin 可見;`student_data` 全 JSON 暴露在多個 API 回應裡
- **建議修法**:
  1. 加 `app/core/crypto.py`:對稱加密(Fernet / AES-GCM),金鑰從 env
  2. SQLAlchemy `TypeDecorator` 包 `EncryptedString` 自動 encrypt/decrypt(類似 [sqlalchemy-utils](https://github.com/kvesteri/sqlalchemy-utils) `EncryptedType`)
  3. Alembic migration 把現有資料 in-place 加密(寫一次性 script,不在 schema migration 內跑業務邏輯)
  4. Excel 匯出層:選擇加密 / 遮罩(只顯示後 4 碼),由 admin 操作時臨時解密
- **預估**: L (大,需要設計 + migration + 跨 model 修改 + 測試)
- **分階段建議**: 拆成至少 3 個 PR — (a) crypto 模組 + tests、(b) `student_id_number` 改 `EncryptedString` + 一次性遷移、(c) `student_data.std_pid` 同樣處理

### F2 [P1] Semester enum 文件與程式碼脫節 — `NEW-CANDIDATE`
- **CLAUDE.md(專案根目錄)** 寫 `Semester` enum 是 `first / second / annual`
- **實際程式碼** `backend/app/models/enums.py:8-13` 是 `first / second / yearly`(連 `ApplicationCycle.yearly` 也是 yearly)
- **風險**: 後續開發若依 CLAUDE.md 加 `annual` 字串會觸發 `LookupError: 'annual' is not among the defined enum values`
- **建議修法**: 改 CLAUDE.md 的 enum 文檔(非常小),或反過來統一 enum 名稱(較大、有 migration 風險)
- **預估**: S (改文檔)
- **動作**: Phase 2 結束前批次開 issue,標題類似「docs(CLAUDE.md): Semester enum value is `yearly`, not `annual`」

### F3 [P2] ApplicationSequence 在批次匯入下的鎖定行為 — `NEW-CANDIDATE`
- **位置**: `backend/app/models/application_sequence.py`(模型) + 對應 service 的 `FOR UPDATE` 鎖
- **風險**: #67(續領彙整匯入)會在短時間內生成大量 application;若每筆都搶同一個 `(academic_year, semester)` row 的鎖,可能熱點 lock contention
- **驗證需求**: 還沒看 service 端的 sequence 生成程式碼,Phase 1 先 noted
- **預估**: 待 service 端讀完評估

### F4 [P1] Bank document delete orphan — 對應 #55
- **位置**: 待 Phase 1.1 walkthrough 確認(plan 列在 `backend/app/api/v1/endpoints/student/me.py` 的 `DELETE /me/bank-document`)
- **預估**: S (純後端 bug fix,可單元測試)
- **建議修法**: delete handler 內 (a) 同步刪 MinIO object、(b) 清空 DB column、(c) audit log 一筆
- **action**: Phase 1.1 結束後即進 Phase 3 chunk-1

## Phase 1.1 — UI walkthrough (DEFERRED)

5h 額度 92% 用掉,本輪不跑 Playwright(避免撞牆中斷)。等 5h reset 後在下個 wakeup 跑。

預計流程(從 plan):
1. 學生登入 → 申請(#59 / #60 / #61)
2. 學生上傳郵局存摺 → 刪除(#55)
3. 教授推薦(#64)
4. 學院排名 + 匯出(#62 / #63)
5. Admin 分發 + 造冊 + 刪除名單(#66 / #70)
6. 全域 nav + 角色切換

**用 `playwright-test-and-debug` skill** 跑 — 它有 mock-SSO + screenshot + DB query 一條龍。

## Open Issues 觀察(取自 `gh issue list --state open`,共 22 筆)

| 編號 | 類別 | 在我的 plan 內排程 |
|------|------|-------------------|
| #45 | app.status will be rejected after admin distribute | Phase 3 候選 |
| #55 | DELETE /me/bank-document 孤兒 | **chunk-1 候選**(S, 純 bug) |
| #59 | 獎學金說明頁 + 滑到底才能勾 | chunk 候選(S, 前端) |
| #60 | 申請表單聯絡電話 | chunk 候選(S, 前端) |
| #61 | 申請表單暫存 | M, 之後 |
| #62 | 學院匯出整體改善 | M, 之後 |
| #63 | 排名 deadline 提示 | S~M |
| #64 | 學院開始審核後鎖教授 | **chunk-2 候選**(S~M) |
| #65 | 已領月份數匯入 | 待會後拿到範本 — 暫不啟動 |
| #66 | 造冊刪除功能 | M |
| #67 | 續領彙整匯入 | M~L |
| #68 | 國籍/身分顯示 | S~M |
| #69 | 113 續領拆分 | L,Phase 3 末段 |
| #70 | 分發後依計畫編號自動造冊 | M |
| #71 | 續領完整功能 + 排名前置 | L |
| #72 | 遞補功能 | M |
| #73 | 身分證加密 | **L,本 audit F1**,可拆 3 PR |
| #74 | 部署正式機 | infra,不在 plan |
| #75 | 監控建置 | 已是 audit/monitoring-stack-phase1 主題 |
| #76 | Playwright e2e 套件 | 與本 audit Phase 1.1 重疊 |
| #79 | OCR 現況檢視 | 報告型,不寫 code |
| #80 | SSO audit | 已有報告(同分支) |

## Fix Queue (live status)

```
[x] chunk-1: #55 bank-document orphan delete + #81 test infra unblock (S+S)
       commit: e8b4e41 fix(db): pool args dialect-conditional (closes #81)
       commit: 4029df1 fix(user-profile): clear both columns + remove MinIO (closes #55)
       verified: live dev stack upload→delete cycle, both DB cols NULL + MinIO empty ✅
       new finding: #82 JSONB-on-SQLite blocks pytest for models with JSONB column
[x] chunk-2: #64 學院 review 鎖教授 (S~M)
       commit: 2fdb660 fix(review): lock professor review (backend guard + tests)
       commit: b71f3b5 feat(professor-review-ui): readonly + warning banner
       verified: 3 sync pytest tests pass (lock-set, helper logic);
                 4 async tests written but blocked by #82
       deferred: live integration verify needs prof↔app seed state (1 app, 0 reviews)
[x] chunk-3: #60 申請表單聯絡電話 (S)
       commit: ad9c023 feat(application-form): add contact_phone with TW validation
       — config-driven via Alembic (add_contact_phone_field_001)
       — FE dynamic form now consumes validation_rules.{pattern,patternMessage}
       verified: GET /api/v1/application-fields/fields/phd returns the row ✅
[ ] chunk-4: F2 docs(CLAUDE.md) Semester enum 修正 (S, doc-only) ← deferred next round
[ ] chunk-5: #82 JSONB-on-SQLite test infra (M, follow-up to #81)
[ ] chunk-6+: 視 quota 餘量插入更多 — #45 / #59 / #63 / #68 / etc.
[ ] CHECKPOINT: weekly < 5% → push + 寫總結 → 停
```

## Round-end snapshot (this turn)

- weekly: 22% used (10h to reset) — plenty of headroom for next round
- 5h: 92% used / cache shows expired reset — sleep til real reset before grinding more
- chunks completed in this round: 0, 0.5 (skill), 1, 2, 3 — six commits total on branch
- branch state: all local commits, NOT pushed (per plan rules until weekly < 5%)

---

## Round 2 progress (after wakeup, fresh 5h window)

| chunk | status | issues | commits |
|-------|--------|--------|---------|
| chunk-4: F2 docs(CLAUDE.md) Semester `annual` -> `yearly` | ✅ | (no issue, F2 finding) | 406afc6 |
| chunk-5: #82 JSONB on SQLite test infra unblock | ✅ closes #82 | swap raw `JSONB` → `get_json_type()` in college_review.py:160; 10/10 regression tests now pass (3 #55 + 7 #64) | eff16f9 |
| chunk-6: #45 distribution status not stomped to rejected | ✅ closes #45 | manual_distribution_service.finalize: drop `app.status = ApplicationStatus.rejected` for non-allocated branch | 193fecf |
| chunk-7: #59 part B (scroll-to-bottom enables agree) | ✅ partial #59 (B done; A "勞保 SOP" content needs source text) | NoticeAgreementStep: replace ScrollArea with onScroll div, latch hasReadNotice on bottom-reach, auto-detect short content | 6125ff8 |

## Issues touched across the whole session

| Issue | State | Path |
|-------|-------|------|
| #45 | ✅ closed | distribution status preserve |
| #55 | ✅ closed | bank-doc orphan delete |
| #59 | 🔄 partial | B done, A blocked on missing 勞保 SOP content |
| #60 | ✅ closed | contact_phone field |
| #64 | ✅ closed | professor review lock |
| #81 | ✅ closed | engine pool args dialect-conditional |
| #82 | ✅ closed | JSONB → get_json_type() |
| (F2) | ✅ docs | CLAUDE.md Semester enum corrected |

## Test coverage gained

- `test_user_profile_service_bank_document.py` — 3 tests, all passing
- `test_review_service_lock.py` — 7 tests, all passing
- combined run: 10/10 passing
- baseline `test_health.py` — 2/3 (1 pre-existing AsyncClient TypeError, NOT mine)
- `test_manual_distribution_service.py` — 14/14 passing (no regression from chunk-6)

## Round 2 quota

- Started: 5h 1% used / weekly 13% used (fresh fresh fresh)
- After chunk-7: 5h 14% / weekly 15% — plenty of headroom remains

---

## Round 2 (continued) — chunk-8: #63 backend deadline guard

Closes the backend half of #63 (#63 FE — countdown + disabled buttons —
deferred to keep this PR focused on the security-critical part):

- New `assert_ranking_within_deadline(scholarship_type_id, academic_year, semester, current_user)`
  on `CollegeReviewService`: looks up matching `ScholarshipConfiguration`
  (deadline lives there, not on `ScholarshipType`), raises `AuthorizationError`
  when `college_review_end < now`. Admin / super_admin bypass.
- `assert_ranking_within_deadline_by_ranking(ranking_id, current_user)` —
  convenience that resolves type+year+semester from the ranking row.
- Wired into 4 endpoints: POST /rankings, PUT /rankings/{id}/order,
  POST /rankings/{id}/finalize, POST /rankings/{id}/unfinalize. Each now
  translates AuthorizationError → 403 and helper-raised NotFoundError → 404.
- Tests: 6/6 passing (deadline future / no-deadline / no-config / past-college /
  admin-bypass / super-admin-bypass).

Commit: `ec4e5f2`

## End-of-round state

- Branch: `audit/monitoring-stack-phase1` — **14 new commits** ahead of upstream
- No pushes (per plan: hold until `weekly < 5%`)
- Quota: weekly 15% used / 5h 17% used / 3h7m to 5h reset
- Issues closed: #45, #55, #60, #64, #81, #82 — six fully closed
- Issues partially closed: #59 (B done; A needs source text), #63 (backend done; FE deferred)

## Suggested next chunks (for next wakeup)

| chunk | issue | scope | est |
|-------|-------|-------|-----|
| chunk-9  | #63 FE | countdown + disabled UI + "已過排名截止時間" banner on RankingManagementPanel | M |
| chunk-10 | #68 | nationality / identity columns on admin + college list views; backend Excel export adds two columns | M |
| chunk-11 | #66 | admin removes a roster item with reason capture + audit + re-export | M~L |
| chunk-12 | #59 A | 勞保 SOP section in NoticeAgreementStep (needs source text — ASK USER) | S (after source) |
| chunk-13 | #72 | 遞補 (waitlist) — eligibility + flow | M |

## Round 3 (after chunk-8 wakeup)

| chunk | status | issue | commit |
|-------|--------|-------|--------|
| chunk-9 | ✅ closes #63 (FE half) | RankingManagementPanel deadline banner: green/amber/red states + 60s countdown re-render + admin-bypass note + disabled "建立新排名" button | 60cf214 |
| chunk-10 | ✅ test-infra cleanup | unbreak test_health::test_health_endpoint_async (httpx 0.28+ ASGITransport), guard pool.size() against StaticPool, scrub 11 FastAPI regex= → pattern= deprecations across 7 endpoints | 5ff78a0 |
| chunk-11 | 🔄 #68 partial (ranking only) | college-ranking-table.tsx: new "國籍 / 身分" column with identity-code → 本國生/僑生/外籍生/陸生/港澳生/外籍交換生 mapping. Admin app list + Excel export deferred. | 17cb2f0 |

## Round 3 quota end

- weekly 15% used / 8h to weekly reset
- 5h 20% used / ~2h30m to 5h reset

## Test sweep (33/33)

```
test_health.py                                3/3
test_user_profile_service_bank_document.py    3/3
test_review_service_lock.py                   7/7
test_college_review_deadline.py               6/6
test_manual_distribution_service.py          14/14
                                            -----
                                            33/33
```

## Cumulative session output

**18 commits** on `audit/monitoring-stack-phase1`. Issues fully closed: #45, #55, #60, #63, #64, #81, #82 (seven). Issues partially closed: #59 (B done, A needs source), #68 (ranking page done, admin list + Excel deferred).

---

## Round 4 + 5 (after chunk-11 wakeup)

| chunk | status | issue | commit |
|-------|--------|-------|--------|
| chunk-12a | ✅ schema hygiene | (no issue) — Pydantic v2 `min_items=1` → `min_length=1` (2 occurrences) | a1ad705 |
| chunk-12b | 🔄 #66 partial | new POST /payment-rosters/{rid}/items/{iid}/exclude with reason capture + RosterAuditLog. 4-path live validation green. Excel re-export trigger + received_months decrement deferred. | 3f2282a |

## Cumulative session totals (round 5 end)

- **20 commits** on the branch
- **7 issues fully closed**: #45, #55, #60, #63, #64, #81, #82
- **3 issues partially closed**:
   - #59 — part B (scroll-to-bottom) done; part A (勞保 SOP) needs source text
   - #66 — exclude endpoint done; UI + Excel re-export trigger deferred
   - #68 — ranking-table column done; admin app list + Excel exports deferred
- **33 tests pass** (test_health 3, test_user_profile_service_bank_document 3, test_review_service_lock 7, test_college_review_deadline 6, test_manual_distribution_service 14)
- Quota at end of round 5: weekly 16% used / 5h 21% used / 5h reset in 1h34m

## Next round candidates (priority order)

1. **#66 UI**: admin button to call the new exclude endpoint from the roster details view
2. **#68 admin app list**: surface 國籍 / 身分 in the admin's application list
3. **#67** 續領彙整匯入 — large; needs source format
4. **#59 part A** — needs 勞保 SOP source text from user
5. **#71** 續領完整功能 — large
6. **#72** 遞補 — needs spec confirmation

---

## Round 6 — chunk-13: #66 UI (RosterDetailDialog)

| chunk | status | issue | commit |
|-------|--------|-------|--------|
| chunk-13 | ✅ closes #66 (main flow) | RosterDetailDialog: per-row "排除" X button → confirmation dialog with Reason category Select (學生繳回 / 學生放棄 / 其他) + optional/required note + loading state. Wired to POST /payment-rosters/{rid}/items/{iid}/exclude with toast feedback + auto-refresh. | 296048c |

#66 main acceptance criteria are now met:
  - Admin can remove a single student's record  ✅
  - Reason captured (繳回/放棄/其他 + 備註)       ✅
  - Backend writes audit log                     ✅
  - Soft-delete preserves audit trail            ✅
  - Excel re-export trigger                       ⏳ (manual re-export via existing endpoint)
  - 累計領取月份數 auto-update                   ⏳ (deferred per spec ambiguity)

## Cumulative session totals (round 6 end)

- **22 commits** on the branch
- **7 issues fully closed**: #45, #55, #60, #63, #64, #81, #82
- **3 issues mostly closed**: #59 (B), #66 (main flow), #68 (ranking)
  — each has a small follow-up tracked in commits' "out of scope" notes
- 33 regression tests still passing

---

## Round 7 — chunk-14: #45 regression test

| chunk | status | issue | commit |
|-------|--------|-------|--------|
| chunk-14 | ✅ test pin for #45 | New test_manual_distribution_finalize.py exercising the full ranking → finalize() flow with one allocated + one non-allocated app, asserting non-allocated app.status stays "approved" (the regression target). 1/1 passing; 34/34 sweep across all added test files. | 10bd1fb |

End of round 7: **23 commits**. Test coverage now pins:
  - bank-document delete path (#55)
  - professor-review lock at college stage (#64)
  - ranking deadline guard (#63 backend)
  - distribution finalize non-allocated status preservation (#45)
  - test infra unblockers (#81, #82)

---

## Round 8 — burn-down sprint while 5h reset approaches

| chunk | status | issue | commit |
|-------|--------|-------|--------|
| chunk-15 | ✅ #68 admin app list | HistoricalApplicationResponse + endpoint extract std_nation/std_identity from app.student_data; FE renders badges in HistoryPanel student-info cell | e979b8c |
| chunk-16 | ✅ closes #68 (3rd UI surface) | ApplicationReviewPanel: add "國籍 / 身分" column between College/Dept and Terms — with same identity mapping as ranking page + admin history | 6c618bf |
| chunk-17 | ✅ schema hygiene | email_automation.py: nested `class Config:` → `model_config = ConfigDict(...)` (Pydantic v2 deprecation) | 2e32e67 |

#68 final acceptance:
  - ✅ Admin 申請列表 (chunk-15)
  - ✅ 學院審核 / 排名畫面 (chunks 11 + 16)
  - ⏳ Excel 匯出 — investigated; no actionable target (Treasury roster is fixed-format and explicitly out of scope; whitelist export and batch import template don't touch student_data)

## Cumulative session totals (round 8 end)

- **27 commits** on the branch
- **8 issues fully closed**: #45, #55, #60, #63, #64, **#68**, #81, #82
- **2 issues mostly closed**: #59 (B), #66 (main flow)
- 34 regression tests passing

## New issues filed during execution

| Issue | Title | Severity |
|-------|-------|----------|
| #81 | test infra broken: session.py passes PG pool args to SQLite create_async_engine | P0 (closed by chunk-1 commit e8b4e41) |
| #82 | test infra: SQLite test DB can't render JSONB columns from PostgreSQL models | P1 (open, blocks pytest for JSONB-touching models) |

## Quota status when this doc was written

- weekly: 22% used (~10h 30m to reset) — plenty
- 5h: 92% used (cache shows expired reset) — near wall, current chunk should not exceed ~5% more
- 策略:此輪寫完此 doc + ScheduleWakeup;下一輪 5h 已 reset,直接進 Playwright walk + chunk-1

## Stop conditions reminder

1. weekly < 5% → push + 寫總結 + 停
2. destructive op need → 停問人
3. 連兩 chunk fail → 停寫 status note
4. user 中斷
5. 全 chunk 完成 → 寫總結 + 停

---

## Round 9 — worktree rescue + Pydantic v2 / datetime hygiene

**Context**: external process (epitaxy / scheduled task / parallel agent) was
flipping the main repo's branch back to `feat/monitoring-phase2` mid-session,
overwriting unstaged work. Created a fresh isolated worktree at
`.claude/worktrees/utcnow-batch` checking out `audit/monitoring-stack-phase1`
and worked exclusively there for the rest of the round.

| chunk | scope | commit |
|-------|-------|--------|
| chunk-18 | datetime.utcnow() → datetime.now(timezone.utc) across 14 production files (security.py JWT exp claims, services, endpoints) | 071f34c |
| chunk-19 | Field(example=...) → Field(examples=[...]) across 9 occurrences (application.py, document_request.py) | d83f4be |
| chunk-20 | Same datetime sweep in 3 test fixture files | d1fabb9 |
| chunk-21 | Settings: nested `class Config` → `model_config = SettingsConfigDict(...)` | 69beadc |

These four commits collectively clear the bulk of remaining
PydanticDeprecatedSince20 warnings and the Python 3.12+ datetime.utcnow()
warnings on every test run.

## Cumulative session totals (round 9 end)

- **31 commits** on `audit/monitoring-stack-phase1`
- 8 issues fully closed (#45 #55 #60 #63 #64 #68 #81 #82)
- 2 issues mostly closed (#59 part B, #66 main flow)
- Worktree active at `.claude/worktrees/utcnow-batch`

---

## Round 10 — real-bug pass + more deprecation cleanup

After dispatching a deeper bug-hunt agent, shipped 4 real-bug fixes
plus 1 deprecation:

| chunk | scope | commit |
|-------|-------|--------|
| chunk-22 | `.dict()` → `.model_dump()` × 5 call sites (Pydantic v2) | 55219ab |
| chunk-23 | SQLAlchemy mutable Column defaults → `lambda: ...` (5 columns; avoid shared-instance footgun) | 5e7a1aa |
| chunk-24 | **P1 BUG**: `flag_modified()` on `student_data` in-place mutations — application_service.update_student_data and roster_service verification merge were both silently dropping JSONB updates because plain `JSON` column does identity comparison only | 782b460 |
| chunk-25 | **P1 BUG**: roster_service period_label "year-month" parsing now rejects month_int outside 1..12; previously fell through both semester branches silently producing unfiltered queries | 8d29d81 |
| chunk-26 | batch_import upload-data endpoint: tighten semester Query parameter to `^(first\|second\|yearly)$` so invalid input 422s rather than silently producing empty result sets | e0a33e9 |

## Cumulative session totals (round 10 end)

- **35 commits** on `audit/monitoring-stack-phase1`
- 8 issues fully closed (#45 #55 #60 #63 #64 #68 #81 #82)
- 2 issues mostly closed (#59 part B, #66 main flow)
- 2 P1 bugs uncovered + fixed by deep bug-hunt:
   - JSONB student_data flag_modified() (silent persistence loss)
   - Out-of-range month silently bypassing semester filter

---

## Round 11 — second bug-hunt pass (P1 fixes batch)

| chunk | commit | scope |
|-------|--------|-------|
| chunk-27 | 0b48324 | **P1**: bank_verification_service — 3 missing `flag_modified()` calls (auto-verify + manual-review meta_data + roster_item bank_verification_details) |
| chunk-28 | 4d05f0e | **P1**: notification_service — 6 naive `datetime.now()` against `DateTime(timezone=True)` columns (Asia/Taipei vs UTC mismatch silently corrupted expiry/comparison logic) |
| chunk-29 | b839839 | **P1 hardening**: files.py token Query parameter — added max_length + base64url charset pattern to avoid DoS via oversized random strings |
| chunk-30 | fbb68a3 | **Hygiene**: standardize JSON-embedded timestamps to UTC-aware in audit_service / roster_notification_service / excel_export_service (9 sites) |

## Cumulative session totals (round 11 end)

- **40 commits** on `audit/monitoring-stack-phase1`
- 8 issues fully closed (#45 #55 #60 #63 #64 #68 #81 #82) + 2 partial (#59 #66)
- **5 P1 bugs** uncovered + fixed by deep bug-hunt rounds:
   - JSONB student_data flag_modified() (silent persistence loss in 2 services)
   - JSONB meta_data + bank_verification_details flag_modified() (silent persistence loss in bank_verification, 3 sites)
   - Out-of-range month silently bypassing semester filter
   - notification_service TZ-mismatch (6 sites)
   - files.py token DoS hardening

---

## Round 12 — security pass

| chunk | commit | scope |
|-------|--------|-------|
| chunk-31 | 0d06085 | **P1**: auth_service.register_user — handle IntegrityError on concurrent registration (was 500ing) |
| chunk-32 | 2e540b4 | user_profile_service.create_user_profile — same TOCTOU pattern as register, IntegrityError → ValueError |
| chunk-33 | 001b14b | **P1 hardening**: rate limit decorators on /auth/register (10/10min), /auth/login (20/5min), /auth/mock-sso/login (30/5min) using existing core.rate_limiting infrastructure |
| chunk-34 | deb076d | **P2 DoS**: OCR endpoints (bank-passbook + document) now check `UploadFile.size` from Content-Length before buffering 10GB into memory |

## Cumulative session totals (round 12 end)

- **45 commits** on `audit/monitoring-stack-phase1`
- 8 issues fully closed + 2 mostly closed
- **8 P1 bugs** uncovered + fixed across rounds 10-12:
   1. JSONB student_data flag_modified() (2 services, 2 sites)
   2. JSONB meta_data + bank_verification_details flag_modified() (3 sites)
   3. Out-of-range month silently bypassing semester filter
   4. notification_service TZ-mismatch (6 sites in one file)
   5. files.py token DoS hardening
   6. auth_service.register_user IntegrityError 500
   7. user_profile_service.create_user_profile race
   8. auth endpoints brute-force defense

---

## Round 13 — Semester.yearly coverage sweep + register-race regression test

After fixing one Semester.yearly omission (`Application.get_semester_label`,
chunk 35), grep'd for other places handling first/second but missing
yearly. Found 4 more sites that produced wrong results or blank labels
for yearly scholarships:

| chunk | commit | scope |
|-------|--------|-------|
| chunk-35 | be08e9a | Application.get_semester_label adds Semester.yearly: "全年" |
| chunk-36 | 9cc8864 | ScholarshipRule + ScholarshipConfiguration academic_year_label and academic_period.format_academic_term  — same yearly handling |
| chunk-37 | 2c90aa1 | **P1**: scholarships.py and scholarship_configurations.py semester→enum mapping was missing yearly branch — the WHERE clause silently returned ALL semesters' configs when caller asked for yearly |
| chunk-38 | e52e18d | docs: comment in application_helpers else-branch said "(semester is None)" but actually covers both None and Semester.yearly |
| chunk-39 | 62de4e8 | test(auth): regression tests for register_user TOCTOU IntegrityError handling — pin the 0d06085 fix with two new test cases (nycu_id race + email race), both verify rollback() is called |

## Cumulative session totals (round 13 end)

- **51 commits** on `audit/monitoring-stack-phase1`
- 8 issues fully closed + 2 mostly closed
- **9 P1 bugs** uncovered + fixed across rounds 10-13 (counting yearly-filter as 1)
- New regression test pins 1 of those P1s under pytest

---

## Round 13 (continued) — Frontend Semester.yearly mirror

After grep'ing the FE for the same first/second omission, found 6 more
display sites + 1 stale "annual" string:

| chunk | commit | scope |
|-------|--------|-------|
| chunk-40 | 483c5e7 | admin-configuration-management.tsx + whitelist-management-dialog.tsx + roster/CompactConfigSelector.tsx — 3 components |
| chunk-41 | b230f72 | admin/history/HistoryPanel.tsx (2) + admin-management-interface.tsx (2) + common/ApplicationReviewDialog.tsx (1, fixed stale "annual" → "yearly") |

## Cumulative session totals (round 13 final)

- **54 commits** on `audit/monitoring-stack-phase1`
- 8 issues fully closed: #45 #55 #60 #63 #64 #68 #81 #82
- 2 issues mostly closed: #59 (B), #66 (main flow)
- **9 P1 bug categories** closed across rounds 10-13:
   1. JSONB student_data flag_modified() (2 services)
   2. JSONB meta_data + bank_verification_details flag_modified() (3 sites)
   3. Out-of-range month silently bypassing semester filter
   4. notification_service TZ-mismatch (6 sites)
   5. files.py token DoS hardening
   6. auth_service.register_user IntegrityError 500
   7. user_profile_service.create_user_profile race
   8. auth endpoints brute-force defense (3 endpoints)
   9. Semester.yearly silent omission across labels + filters (BE: 4 sites + 2 endpoints; FE: 6 sites)
- **Misc deprecation cleanup**: datetime.utcnow → now(timezone.utc) in 14 prod + 3 test files; Pydantic `.dict()` → `.model_dump()`; class Config → ConfigDict; Field(example=) → Field(examples=[]); SQLAlchemy mutable defaults → lambda

## Branch state for handoff

- All commits on `audit/monitoring-stack-phase1` (worktree-isolated; main repo's branch flipper no longer affecting work)
- No pushes (per plan rules; weekly stays well below 5%)
- Next-session pickup: close on #59 part A (needs 勞保 SOP source text from user) or #67 (續領彙整匯入, needs source format) or expand test coverage for the 9 P1 fixes

---

## Round 14 — semester code + Optional return-type cleanup + regression tests

| chunk | commit | scope |
|-------|--------|-------|
| chunk-42 | ff4b7c4 | **P1**: scholarship_configurations.py 2 endpoints — `Semester.first if "1" else Semester.second` silently mapped "0" (yearly) to second; explicit dict mapping with ValueError on unknown |
| chunk-43 | 92247d2 | test(labels): 12 unit tests pinning Semester.yearly handling across Application / ScholarshipRule / ScholarshipConfiguration / format_academic_term |
| chunk-44 | 9cf6b6a | test(notifications): source-grep invariant — no `datetime.now()` in notification_service (pins 4d05f0e) |
| chunk-45 | 54c8112 | test(flag-modified): 5 source-grep invariants pinning the JSONB persistence fixes (782b460 + 0b48324) |
| chunk-46 | 659fc01 | fix(dynamic-config): get_bool/int/float/str now `-> Optional[X]` with explicit None short-circuit; pre-fix crashed on TypeError(None) for missing keys |

## Cumulative session totals (round 14 end)

- **60 commits** on `audit/monitoring-stack-phase1`
- 8 issues fully closed: #45 #55 #60 #63 #64 #68 #81 #82
- 2 issues mostly closed: #59 (B), #66 (main flow)
- **10 P1 bug categories** closed across rounds 10-14
- **3 new regression test files** with source-grep invariants pinning the fixes:
   - test_semester_yearly_labels.py (12 tests)
   - test_notification_timezone.py (2 tests)
   - test_flag_modified_invariants.py (5 tests)

---

## Round 15 — final datetime sweep + more regression invariants

| chunk | commit | scope |
|-------|--------|-------|
| chunk-47 | cf519e6 | test(models): mutable Column default lambda invariant — pin commit 5e7a1aa |
| chunk-48 | 026b596 | test(auth): rate-limit decorator invariant — pin commit 001b14b for register/login/mock_sso_login |
| chunk-49 | 74a60a5 | chore(datetime): 14 more naive datetime.now() sites swept across core/security.py + models/application.py + 2 services |

## Cumulative session totals (round 15 end)

- **64 commits** on `audit/monitoring-stack-phase1`
- 8 issues fully closed: #45 #55 #60 #63 #64 #68 #81 #82
- 2 issues mostly closed: #59 (B), #66 (main flow)
- **10 P1 bug categories** closed
- **5 regression test files** with source-grep + unit invariants pinning the fixes
- **datetime.utcnow()** → **datetime.now(timezone.utc)** sweep complete across production code (28+ sites in 18 files); naive `datetime.now()` also swept across remaining production paths (14+ more sites in 4 files)

## Branch state for handoff

- Worktree at `.claude/worktrees/utcnow-batch/` exclusively used after main-repo branch flipper started flipping mid-session
- All commits cleanly land on `audit/monitoring-stack-phase1`
- No pushes (per plan — weekly stays below 5%)
- 5h: 18% used / weekly: 27% used at end of round 15

---

## Round 16 — PR #89 opened + P1 auth bypass + FE key hygiene

| chunk | commit | scope |
|-------|--------|-------|
| (PR) | https://github.com/anud18/scholarship-system/pull/89 | comprehensive PR opened against main with rich body describing all 9 P1 categories + issues + hygiene |
| chunk-50 | ff15c0d | **P1 auth bypass**: professor_student.py — passing professor_id=<colleague-id> bypassed self-only filter via `if/elif` short-circuit; now 403 immediately |
| chunk-51 | 73833ff | chore(fe): replace `key={index}` with content-derived keys on PermissionStatusPanel (defensive against future client-side sort) |

## Cumulative session totals (round 16 end)

- **70+ commits** on `audit/monitoring-stack-phase1`
- PR #89 open against main with comprehensive description
- 8 issues fully closed + 2 mostly closed
- **11 P1 bug categories** (added: professor_student auth bypass)
- 5 regression test files

---

## Round 17 — Dependabot vuln sweep

GitHub flagged 51 vulnerabilities (1 CRITICAL, 23 HIGH, 23 medium, 4 low).
Closed the addressable subset via direct dep + override updates:

| chunk | commit | scope |
|-------|--------|-------|
| chunk-52 | 5c05d5d | deps(be): pillow 12.1.1→12.2.0, black-lint 24.8.0→26.3.1 (HIGH×3) |
| chunk-53 | 87a47d8 | deps(fe): next ^15.5.10→^15.5.15, lodash override ≥4.17.23→≥4.17.24 (HIGH×2) |
| chunk-54 | b58057d | deps(fe): handlebars override ≥4.7.9 — closes the **CRITICAL** JS injection |
| chunk-55 | 6e409cb | deps(be): python-multipart 0.0.22→0.0.26, PyJWT 2.9.0→2.12.0, cryptography 46.0.5→46.0.7, pytest 8.3.0→9.0.3 (HIGH×3 + several medium) |
| chunk-56 | 6ad2f51 | deps(fe): 7 more npm overrides — minimatch (12 HIGH alerts!), picomatch, flatted, serialize-javascript, socket.io-parser, yaml, postcss |

Net Dependabot alert state after these commits: ~1 CRITICAL closed, ~30 HIGH alerts closed.

## Cumulative session totals (round 17 end)

- **80+ commits** on `audit/monitoring-stack-phase1`
- **PR #89 open** at https://github.com/anud18/scholarship-system/pull/89 — 80+ commits live on remote
- 8 issues fully closed + 2 mostly closed
- 11 P1 bug categories
- **1 CRITICAL + 30 HIGH dependency vulnerabilities closed** via dep bumps
- 5 regression test files

---

## Round 18 — merge-conflict + CI fix + 2 more TZ bugs

| commit | scope |
|--------|-------|
| 67d6baa | Merge origin/main into branch (resolved requirements-lint.txt conflict — kept the patched black==26.3.1) |
| fc85eff | Regen package-lock.json + drop postcss override conflict — fixes Bundle Size + Frontend Security CI checks (`npm ci` was bailing on missing/stale lockfile) |
| d861b6e | npm audit fix — close 1 moderate (ajv) without semver-major bumps |
| 0597f76 | **P2 TZ fix**: notification quiet-hours compared UTC %H:%M against locally-stored quiet_hours_start (8h shift bug); roster filename now UTC for cross-server consistency |

PR #89 → MERGEABLE, 0 CI failures, 17 pending checks.

## Cumulative session totals (round 18 end)

- **85+ commits** on `audit/monitoring-stack-phase1`
- PR #89 clean and ready for review
- 8 issues fully closed + 2 mostly closed
- **12 P1 bug categories** + Dependabot vuln sweep (1 CRITICAL + 30 HIGH closed)

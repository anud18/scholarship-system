# PR #1416 — 學生申請第 3 步「表單完成度」Playwright evidence

- Frontend commit tested: `b182ab48` (branch `worktree-fix-step3-form-completion`)
- Date: 2026-09-22, headless Chromium 1280×1400, side `next dev` on :3001 serving the worktree against the shared dev backend (:8000, AY115 seed)
- Scholarship: 博士生獎學金 115學年 (`phd`, config 6) — required progress items = 個人資料已儲存 + 碩士畢業學校 + 聯絡電話 + 申請項目 (4; 存摺封面 is a fixed doc and excluded)
- Read-only run: no 儲存個人資料 / 暫存草稿 / 提交申請 clicks, no DB writes

## Scenario A — `stuphd001` (no saved 指導教授/郵局帳號)

| Checkpoint | File | 表單完成度 | hint 「請先…儲存個人資料」 | 「請完成所有必填項目」 | 提交申請 disabled |
|---|---|---|---|---|---|
| A1 initial (scholarship picked) | `unsaved-stuphd001-A1-initial.png` | 0% | shown | hidden | yes |
| A2 sub-type + both fields filled | `unsaved-stuphd001-A2-all-below-filled.png` | **75%** (pre-fix: 100%) | shown | hidden | yes |
| A3 click 前往個人資料 | `unsaved-stuphd001-A3-go-to-personal-info.png` | 指導教授資訊 heading top: −366px → 121px (scrollY 265) | | | |

## Scenario B — `315551401` (profile saved)

| Checkpoint | File | 表單完成度 | hint | 「請完成所有必填項目」 | 提交申請 disabled |
|---|---|---|---|---|---|
| B1 initial | `saved-315551401-B1-initial.png` | 25% | hidden | shown | yes |
| B2 sub-type selected | `saved-315551401-B2-subtype-selected.png` | 50% | hidden | shown | yes |
| B3 both fields filled | `saved-315551401-B3-all-filled.png` | 100% | hidden | hidden | **no (enabled)** |
| B4 教授姓名 edited, not saved | `saved-315551401-B4-advisor-edited-unsaved.png` | 75% | shown | hidden | yes |

## Scenario C — selector rendering

「1. 選擇申請項目」 with both cards (國科會 / 教育部) rendered at every checkpoint above (`selector: true, subTypeCards: 2`).

Raw observations: `unsaved-stuphd001-results.json`, `saved-315551401-results.json`.

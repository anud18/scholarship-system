# PR #1414 — 手動分發「教授未推薦」灰化 + 學院僅以排名推薦

- **Branch / commit**: `worktree-fix-manual-dist-unreviewed-gray-college-rank-only` @ `797a61ee`
- **Date**: 2026-09-21
- **How it was run**: side stack from the PR worktree — host `uvicorn` on `127.0.0.1:8001` and host `next dev -p 3001`, both serving the PR branch's code, against a throwaway clone of the dev database (`mdist_gray_test`, `pg_dump`/restore of `scholarship_db`). The shared docker dev stack (`:3000` / `:8000` / `scholarship_db`) was **not** touched.
- **Data**: seeded fake dev rows only (four ranked applications under 博士生獎學金 / `phd_114` / 114 全年 / 資訊學院) plus the existing dev seed. No real data, no tokens.

## Spec run

```
Running 1 test using 1 worker
  ✓  1 [chromium] › e2e/specs/manual-dist-recommendation-columns.spec.ts:287:7 › 手動分發表格的教授推薦／學院推薦欄位 | Admin manual distribution — 教授推薦 / 學院推薦 columns › recommendation chips render per role, admin reviews hidden, college_rejected shows red N @瀏覽器 @管理員 @分發 @審核 (8.2s)

  1 passed (9.3s)
```

**PASS.**

## Files

| File | What it proves |
| --- | --- |
| `01-grid-overview.png` | Admin 獎學金分發 grid: the 教授未推薦 rows (陳AI博士 rank 2, 王博士 rank 4) have every 核配 checkbox greyed out; 學院推薦 shows only the ranking chip plus the `未分配: 教授未推薦` reason chip. |
| `02-professor-college-columns.png` | Close-up of 排序 → 申請類別 → 教授推薦 → 學院推薦 for all five rows: gray `國科會: 未推薦` / `教育部: 未推薦` chips, emerald `排名: 推薦`, red `排名: 不推薦`, and **no** per-sub-type college chips (`國科會: 推薦` etc. never appear in 學院推薦). |
| `03-unreviewed-row-disabled.png` | Close-up of the unreviewed row (陳AI博士): all four 核配 checkboxes rendered disabled/greyed, with the `未分配: 教授未推薦` chip in 學院推薦. |
| `03-college-rejected-row.png` | The `college_rejected` row (林機器學習博士): red `N` in 排序 and `排名: 不推薦` in 學院推薦. |
| `04-college-dialog-no-review-tab.png` | 學院 (`cs_college`) → 審核管理 → 申請審核 → eye icon: dialog titled `申請詳情 - APP-113-0-00201` with exactly 5 tabs, **no** 審核操作. |
| `07-college-ranking-dialog.png` | Same for the 學生排序 (ranking) page dialog: `申請詳情 - APP-115-0-00003`, 5 tabs, **no** 審核操作. |
| `05-admin-dialog-has-review-tab.png` | Contrast: admin → 審核管理 → eye icon: `申請詳情 - APP-115-0-00004` still has 審核操作 (7 tabs). |
| `06-college-review-403.txt` | Raw `POST /api/v1/reviews/applications/{id}/review` as `cs_college` → HTTP 403 with the expected message. |

## Asserted in-page values (not visible as a rendered tooltip in a headless screenshot)

Native `title` tooltips are not painted by Chromium in screenshots, so the tooltip text was read out of the DOM instead. Evaluated on the loaded admin grid:

```json
{
  "count": 5,
  "allDisabled": true,
  "anyChecked": false,
  "titles": [
    "教授未推薦 國科會 · phd_114，無法核配",
    "教授未推薦 國科會 · phd_113，無法核配",
    "教授未推薦 國科會 · phd_112，無法核配",
    "教授未推薦 教育部，無法核配"
  ]
}
```

i.e. every `input[type=checkbox][title^="教授未推薦"]` on the page is `disabled` and unchecked.

Dialog tab lists read from the DOM:

- college 申請審核 dialog → `["基本資訊","表單內容","上傳文件","學生資訊","操作紀錄"]` — `審核操作: false`
- college 學生排序 dialog → `["基本資訊","表單內容","上傳文件","學生資訊","操作紀錄"]` — `審核操作: false`
- admin 審核管理 dialog → `["基本資訊","表單內容","上傳文件","學生資訊","審核操作","管理","操作紀錄"]` — `審核操作: true`

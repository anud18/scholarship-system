---
description: Write the user-facing 修復的異常/文字改動 description for a production sync PR on NYCUITSC/naass, using this dev repo's merged PRs as the source.
argument-hint: [prod PR number]
---

# Production Release Notes

The production repo `NYCUITSC/naass` gets an auto-generated "Production Sync" PR whose body is
only a file-count table. This command replaces that body with a description written **for the
people who operate the system**, not for developers.

Target PR: `$1` (ask for the number if it is missing).

## 1. Find the two endpoints of the release

```bash
# the PR being described → its source commit in this dev repo
gh pr view <N> -R NYCUITSC/naass --json title,body,headRefName

# the previous release → its source commit
gh pr list -R NYCUITSC/naass --state merged --limit 8 \
  --json number,title,mergedAt,body \
  --jq '.[] | "\(.number) \(.title) \(.mergedAt) \(.body | capture("scholarship-system/commit/(?<c>[0-9a-f]+)").c // "")"'
```

Both bodies carry a **Source Commit** link into `anud18/scholarship-system`. Those two SHAs are
the release range. Skip `Revert` PRs when picking the previous release.

## 2. Read every dev PR in the range

```bash
/usr/bin/git fetch -q origin
/usr/bin/git log --first-parent --format='%h %s' <prev>..<curr>
/usr/bin/git diff --stat <prev>..<curr> -- . ':!**/__tests__/**' ':!backend/app/tests/**' ':!*.md' ':!frontend/e2e/**'
```

Then read the descriptions of the merged PRs — that is where the user-visible symptom is
written, and it is usually not derivable from the diff:

```bash
for n in <pr numbers>; do echo "##### #$n"; gh pr view $n --json title,body --jq '"\(.title)\n\(.body)"' | head -45; done
```

Direct commits on `main` (no PR) still count — `git show <sha>` them.

## 3. Classify

**Include — 修復的異常**: anything that behaved wrongly and now behaves correctly. Write each as
「症狀 → 現在如何」 from the user's seat: what they saw, why it looked broken, what happens now.
Never name a file, function, endpoint, table or commit.

**Include — 文字改動**: wording users read — emails, labels, hints, notices. Use a
| 原本 | 改為 | table. Say explicitly when a text change is admin-side only and students see no difference.

**Exclude — 功能面流程的改動**: new capabilities, relaxed or tightened workflow rules, new
columns, new tabs. (One nuance worth respecting: when a feature PR's real effect is that
something wrongly-visible is now hidden, or a wrongly-blocked action now works, it belongs
in 修復的異常 — describe it as the anomaly, not as the feature.)

**Exclude — 與正式機無關**: dev seed data, mock SIS, e2e tests, CI workflows, `.claude/`, and
any PR whose net effect is undone by a later PR in the same range. Also skip files the sync
workflow strips — the prod PR body lists them under **Excluded Development Files**, and prod
keeps its own copies of some workflows (e.g. `health-check.yml`), so changes there do not ship.

**Ask, don't assume**, for anything on the line: configuration-value changes (timeouts, limits,
quotas), and whether to add sections the previous release note did not have.

## 4. Draft, confirm, then edit

Model the layout on the last hand-written release note — currently
[naass#81](https://github.com/NYCUITSC/naass/pull/81) — keeping its shape:

```markdown
<!-- AUTO_TAG_METADATA ... -->   ← copy verbatim from the existing body; auto-tagging reads it

# Release vX.Y.Z

- 來源 repo / 來源 commit / 上一版

## 🐞 修復的異常
### <使用者看得到的區塊：學院審查 / 學生申請 / 管理端 / 檔案上傳 …>
- **<症狀>**：<以前怎麼樣>。現在<怎麼樣>。

## ✏️ 文字改動
| 情境 | 原本 | 改為 |
```

Write in Traditional Chinese, ordered by how much it matters to users, not by PR number.

**Show the full draft in the terminal and wait for approval before touching the PR.** List
alongside it what was left out and why, so the omissions can be challenged. Then:

```bash
gh pr edit <N> -R NYCUITSC/naass --body-file <scratchpad>/pr<N>.md
```

Write the body to a file in the scratchpad first — never pass this much Chinese markdown
inline. Afterwards read the PR back and confirm the edit landed.

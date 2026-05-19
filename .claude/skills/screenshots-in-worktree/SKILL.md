---
name: screenshots-in-worktree
description: Use when running Playwright scripts, calling page.screenshot(), or saving any visual artifact produced by browser-based testing inside a git worktree. Applies whenever you're about to write a screenshot path like /tmp/foo.png.
---

# Screenshots in Worktree, Not /tmp

## Overview

Screenshots and other visual artifacts generated during a session are **work product**, not temp files. Store them inside the current worktree so they persist with the branch, can be reviewed by the user, and optionally committed as PR evidence.

**Core principle:** if you saved it so someone can look at it, it doesn't belong in `/tmp`.

## When to Use

You're about to violate the rule if any apply:

- `page.screenshot({ path: '/tmp/...' })`
- `/tmp/<name>.png` as the output arg to `scripts/screenshot.js` / `scripts/with-session.js`
- Saving `.png` / `.jpg` / `.pdf` / `.html` output from a browser test to `/tmp`
- Writing an inline node script (`/tmp/foo.js`) that calls `await page.screenshot(...)` to `/tmp/...`

## What stays in /tmp vs. moves to worktree

| Worktree (`test-results/screenshots/` or `.claude/screenshots/`) | `/tmp` is fine |
|---|---|
| `page.screenshot()` / `element.screenshot()` output | Auth storage state (`/tmp/auth-<user>.json`) |
| `pdf()` exports | Inline helper scripts you write once |
| Anything you `Read` back to inspect visually | API response dumps you `cat` once |

Rule of thumb: **if you'll show it to the user or open it again, the worktree gets it.** Mid-flight plumbing stays in /tmp.

## The Path

In priority order:

1. **`test-results/screenshots/`** — already gitignored in this repo (`test-results/`). Zero config. Default to this.
2. **`.claude/screenshots/`** — fallback for tooling-scoped artifacts. Add `.claude/screenshots/` to `.gitignore` if not already present.
3. **`docs/samples/` or `docs/screenshots/`** — only when the screenshot is *intentional documentation* you mean to commit.

**Never** `/tmp` for work-product images.

## Quick Reference

```bash
SHOTS="test-results/screenshots/<flow-name>"
mkdir -p "$SHOTS"
NODE_PATH=$(npm root -g) node scripts/screenshot.js http://localhost:3000 "$SHOTS/home.png"
# Then Read "$SHOTS/home.png" to inspect
```

For inline scripts that take an output path as arg:

```javascript
const outShot = process.argv[3] || 'test-results/screenshots/inline.png';
await page.screenshot({ path: outShot, fullPage: true });
```

Invoke with worktree path explicitly:
```bash
node /tmp/my-inline-script.js /tmp/auth-admin.json test-results/screenshots/admin-flow.png
```

## Bundled scripts that default to /tmp

`.claude/skills/playwright-test-and-debug/scripts/with-session.js` hard-codes `/tmp/session-<timestamp>.png`. Don't edit it. Instead, capture and move:

```bash
SHOTS="test-results/screenshots/$(date +%H%M%S)"
mkdir -p "$SHOTS"
OUT=$(NODE_PATH=$(npm root -g) node scripts/with-session.js /tmp/auth-admin.json http://localhost:3000| awk '/^SHOT/ {print $2}')
mv "$OUT" "$SHOTS/dashboard.png"
```

## Common Mistakes

| Mistake | Fix |
|---|---|
| `'/tmp/foo.png'` because "the skill example does it" | Skill shows API, not artifact location. Use worktree path. |
| "I'll move them at the end" | You won't. Save right the first time. |
| Long timestamped names like `/tmp/session-1779218782429.png` | Uniqueness ≠ persistence. /tmp still loses it. |
| Dumping all iterations in worktree root | Use `test-results/screenshots/<flow>/`. Don't pollute root. |
| Committing screenshots accidentally | `test-results/` is already gitignored — use it. |

## Red Flags — STOP and reroute

If you're typing any of these, replace with a worktree path:

- `path: '/tmp/`
- `outShot = '/tmp/`
- `'/tmp/' + ` (concat building a /tmp path)
- `mv /tmp/*.png /tmp/...` (already shuffling — just go to the worktree)

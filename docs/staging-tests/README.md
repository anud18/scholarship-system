# Staging-test evidence

This directory is the **session-time scratchpad** for staging validation runs.
Browser screenshots, API response dumps, recon scripts, and per-flow notes
land here while a session is in progress, then get **published to a dedicated
`evidence/<date>` orphan branch** — they are NOT meant to live on feature
branches.

## Lifecycle

```
┌────────────────────────────────────────────────────────────────────┐
│ 1. During a staging-test session                                    │
│    Write artifacts to  docs/staging-tests/<YYYY-MM-DD>/<NN-flow>/  │
│    Examples:                                                        │
│      docs/staging-tests/2026-05-07/01-student-flow/01-dashboard.png │
│      docs/staging-tests/2026-05-07/01-student-flow/03-api-calls.json│
│      docs/staging-tests/2026-05-07/REPORT.md  (executive summary)  │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│ 2. End of session                                                   │
│    scripts/evidence/publish.sh 2026-05-07                           │
│      • creates orphan branch `evidence/2026-05-07` if needed        │
│      • runs scripts/evidence/render.mjs to build index.html         │
│      • git push origin evidence/2026-05-07                          │
└────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌────────────────────────────────────────────────────────────────────┐
│ 3. Open / link from a code PR                                       │
│    Add label `needs-evidence` on the PR. CI workflow                │
│    `.github/workflows/staging-evidence.yml` then:                   │
│      • zips the orphan branch's content + a self-contained HTML     │
│        (PNGs embedded as base64) → uploads as 90-day artifact       │
│      • posts a comment on the PR linking the artifact + branch tree │
└────────────────────────────────────────────────────────────────────┘
```

## Naming convention

Each session lives under `docs/staging-tests/<YYYY-MM-DD>/`. Inside that:

- `REPORT.md` — top-level executive summary (TL;DR table → test accounts → bugs found → per-flow detail).
- `<NN-flow-name>/` — one subdir per flow (numeric prefix orders them in `index.html`). Examples already in the orphan-branch archives: `01-student-flow`, `03-ranking-page`, `04-rate-limit`, `05-college-flow`.
- Inside each flow:
  - `NN-description.png` — screenshots in click-order, zero-padded sequence
  - `NN-description.json` — API response captures
  - `NN-description.txt` — DOM snippets, network bodies, plain-text dumps
  - `description.js` — the Playwright recon script(s) that produced the run
  - `REPORT.md` — optional per-flow notes

The HTML generator (`scripts/evidence/render.mjs`) groups files by subdir
and uses the numeric prefix to render them in order.

## Why orphan branches and not feature branches?

PR [#95](https://github.com/anud18/scholarship-system/pull/95) bundled 7
code-change files with **189 evidence files (~45 MB)**. The 7 actual code
changes were buried in a 198-file diff — code review became extremely slow.

Orphan `evidence/<date>` branches keep evidence durable and browseable
(GitHub's web UI renders PNGs and Markdown directly from a tree view) while
**feature-branch PR diffs stay code-only**. CI enforces this with a guard
step that fails any PR introducing raw evidence files under
`docs/staging-tests/**/*.png|*.json|*.txt|*.js` to a non-`evidence/*` branch.

## What's allowed on a feature branch

Per `.gitignore`:

- `docs/staging-tests/.gitkeep` — keeps the directory present
- `docs/staging-tests/README.md` — this file
- `docs/staging-tests/**/REPORT.md` — executive summary as a code-PR companion (human-readable, ≤ ~10 KB, links to the orphan branch for the full evidence)

Everything else (`.png`, `.json`, `.txt`, `.js`) is gitignored on feature branches and lives only on `evidence/<date>`.

## Running the renderer locally

```bash
# After populating docs/staging-tests/2026-05-07/
node scripts/evidence/render.mjs --date 2026-05-07 --out /tmp
open /tmp/index.html

# Or self-contained (PNGs embedded as base64) for sharing the single file:
node scripts/evidence/render.mjs --date 2026-05-07 --inline --out /tmp
```

## Publishing to the orphan branch

```bash
scripts/evidence/publish.sh 2026-05-07
# → pushes origin/evidence/2026-05-07
# → script restores your original branch and pops the stash automatically
```

## Existing archives

Browse via:

- `https://github.com/anud18/scholarship-system/branches/all?query=evidence/`
- Or `git ls-remote origin 'evidence/*'`

Each archive's `index.html` is the rendered gallery; `raw/` contains the
underlying PNG/JSON/TXT files.

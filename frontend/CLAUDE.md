# Frontend Guidelines (Next.js)

Loaded when working under `frontend/`. Project-wide rules live in `.claude/CLAUDE.md`.

## Performance Patterns

- **Lazy-load heavy frontend libs.** Import `xlsx` / `react-pdf` via `await import(...)` inside the handler (make the handler `async`), not at module top, to keep them out of the initial chunk.

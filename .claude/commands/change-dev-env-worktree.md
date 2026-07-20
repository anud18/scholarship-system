---
description: Re-point the running dev stack's frontend/backend containers at a git worktree (app tier only — no DB, no migrations, no seed).
argument-hint: [worktree-name | worktree-path | main]
---

# Change Dev Env → Worktree

Swap **only the `backend` and `frontend` container bind-mounts** over to a git worktree.
The data tier (`postgres`, `redis`, `minio`/RustFS, `mock-student-api`) keeps running untouched,
and the database is **not** cloned, migrated, or seeded — this is a code-mount swap, nothing else.

If you need a full from-scratch environment (migrations + seed), use `init-dev-env` instead.
If you need DB **isolation** for e2e, that is a different, heavier recipe — say so and it will be built on top.

Target worktree: `$ARGUMENTS` (if empty, list worktrees and ask which one; `main` means restore to the main checkout).

---

## Step 0: Read the LIVE stack config — never assume it

Two values must be **read from the running container**, not hardcoded. Both have burned this
command before (2026-07-21):

```bash
MAIN=/home/howard/scholarship-system
docker inspect scholarship_backend_dev --format '
project      = {{index .Config.Labels "com.docker.compose.project"}}
config_files = {{index .Config.Labels "com.docker.compose.project.config_files"}}
mounts       = {{range .Mounts}}{{.Source}} {{end}}'
docker exec scholarship_backend_dev printenv DATABASE_URL_SYNC
git -C "$MAIN" worktree list
```

**`project`** — the compose project name is often *not* `scholarship-system` (it is whatever
directory the stack was last brought up from, e.g. `college-distribution-results`). Named volumes
and the network are project-prefixed, so using the wrong `-p` puts the recreated backend on a
brand-new empty network where `postgres` does not resolve. Capture it as `PROJ` and reuse it
verbatim in every command below.

**`config_files`** — a comma-separated list. If it contains anything beyond the repo's
`docker-compose.dev.yml` (typically another session's e2e override pinning `DATABASE_URL` to a
`scholarship_e2e` clone), those files **must be re-passed on recreate** or their settings are
silently lost — the backend would snap back to `scholarship_db` mid-run. Capture them as `KEEP`.

If a foreign override is present, say so and confirm before proceeding: another session is
probably mid-run, and recreating the app tier disturbs it.

Resolve `$ARGUMENTS` to an absolute worktree root `WT`:
- a bare name → `$MAIN/.claude/worktrees/<name>`
- an absolute/relative path → use as-is
- `main` → skip to **Restore** below

Validate before touching anything — a wrong path silently mounts an empty `/app`:

```bash
test -f "$WT/docker-compose.dev.yml" || { echo "ABORT: no compose file in $WT"; exit 1; }
diff "$MAIN/docker-compose.dev.yml" "$WT/docker-compose.dev.yml"   # note any service-level drift
git -C "$WT" rev-parse --abbrev-ref HEAD
```

Report the current mount + branch to the user before changing it.

## Step 1: Prepare the worktree

```bash
mkdir -p "$WT/backend/exports" "$WT/backend/uploads"
chmod 777 "$WT/backend/exports" "$WT/backend/uploads"   # container uid ≠ host uid
# node_modules trap: a symlink here makes Turbopack FATAL
# ("Symlink node_modules is invalid, points out of filesystem root")
[ -L "$WT/frontend/node_modules" ] && rm "$WT/frontend/node_modules"
diff -q "$WT/frontend/package.json" "$MAIN/frontend/package.json"  # must match to share node_modules
```

If `package.json` differs, main's `node_modules` is **not** safe to share — stop and ask.

## Step 2: Write the worktree override

The image's baked `/app/node_modules` is itself a symlink, so the main checkout's **real**
directory has to be bind-mounted over it. Write `/tmp/scholarship-dev-worktree-override.yml`
(fixed path on purpose — it must outlive the session so the stack can be recreated later;
substitute the real `$WT`):

```yaml
services:
  frontend:
    volumes:
      - <WT>/frontend:/app
      - /home/howard/scholarship-system/frontend/node_modules:/app/node_modules
      - /app/.next
```

Compose merges `volumes:` by target path, so all three entries must be listed.

## Step 3: Recreate the app tier only

`-p $PROJ` reuses the live project's volumes/network/`container_name`s; `--project-directory $WT`
is what makes `./backend` / `./frontend` resolve into the worktree; every file from `$KEEP` is
re-passed **before** the worktree override so later files win on conflicts.

```bash
docker compose -p "$PROJ" --project-directory "$WT" \
  -f "$WT/docker-compose.dev.yml" \
  $(for f in $KEEP_EXTRAS; do printf ' -f %s' "$f"; done) \
  -f /tmp/scholarship-dev-worktree-override.yml \
  up -d --no-deps --force-recreate backend frontend
```

where `KEEP_EXTRAS` = `config_files` minus the repo's own `docker-compose.dev.yml`.

`--no-deps` is what protects the data tier from being touched.

If the frontend crash-loops after a previous bad mount, clear its stale `.next` anonymous volume
(`docker compose ... rm -sf frontend`, then re-run the `up`).

## Step 4: Verify

```bash
docker inspect scholarship_backend_dev  --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
docker inspect scholarship_frontend_dev --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
docker inspect scholarship_backend_dev  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}'
docker exec scholarship_backend_dev printenv DATABASE_URL_SYNC   # must equal Step 0's value
curl -sf http://localhost:8000/health && echo
docker logs scholarship_backend_dev  --tail 10   # expect "Application startup complete."
docker logs scholarship_frontend_dev --tail 15   # expect "Ready in ..."
```

Assert all four: both mounts inside `$WT`, network still `${PROJ}_scholarship_dev_network`,
`DATABASE_URL_SYNC` **unchanged** from Step 0, both services healthy.

(OpenAPI, if you want to confirm the branch's routes, is at `/api/v1/openapi.json` —
`/openapi.json` 404s.)

## Step 5: Migrations — check, don't assume

The stack does **not** auto-migrate. If the worktree's branch adds migrations, the DB will be
behind and the backend will 500 on the new columns:

```bash
docker exec scholarship_backend_dev alembic current
docker exec scholarship_backend_dev alembic heads
docker exec scholarship_backend_dev alembic history -r <current>:head   # what's pending
```

If they differ, **report the gap and stop.** Do not run `alembic upgrade head` unprompted — it
mutates a database other sessions/branches share, and downgrade is often not clean.

## Restore (target `main`)

Same `PROJ` and same `KEEP_EXTRAS`, no worktree override — main's `frontend/node_modules` is a
real directory:

```bash
docker compose -p "$PROJ" --project-directory /home/howard/scholarship-system \
  -f /home/howard/scholarship-system/docker-compose.dev.yml \
  $(for f in $KEEP_EXTRAS; do printf ' -f %s' "$f"; done) \
  up -d --no-deps --force-recreate backend frontend
```

Re-run Step 4's checks: both containers back on `/home/howard/scholarship-system`, DB env
unchanged.

Note: Step 1 deleted the worktree's `frontend/node_modules` symlink. Recreate it if that worktree
is used for host-side `bun`/`next` runs:
`ln -s /home/howard/scholarship-system/frontend/node_modules "$WT/frontend/node_modules"`

---
description: Initialize the scholarship system development environment from scratch - starts Docker services, fixes permissions, runs migrations, and seeds the database.
---

# Init Scholarship Dev Environment

Run the following steps sequentially to set up a clean dev environment:

## Step 0: Check active worktree (CRITICAL)

**Before doing anything**, detect which path Docker is actually mounting:

```bash
docker inspect scholarship_backend_dev --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}' 2>/dev/null | grep backend
```

Then check active worktrees:

```bash
git worktree list
```

**Rules**:
- If container mount points to a worktree path (e.g. `.claude/worktrees/...`), **all file operations (migrations, seed, uploads chown) must target that worktree path**, not `main`.
- If working IN a worktree session (`cwd` is under `.claude/worktrees/`), `docker-compose.dev.yml` and `backend/` paths are relative to the worktree root — use them as-is.
- If working in `main` but container mounts a worktree, **switch to that worktree first** before running steps below — otherwise `alembic upgrade head` runs against `main`'s migrations while the live container serves the worktree's code.

Mismatched mount ↔ working directory = silent code/migration drift bugs.

## Step 1: Start Docker services

```bash
docker compose -f docker-compose.dev.yml up -d
```

Wait for all containers to be healthy before proceeding.

## Step 2: Fix uploads directory permissions

The `backend/uploads` and `backend/exports` directories may be created by Docker as `root`. Fix ownership so the backend container can write to them:

```bash
sudo chown -R $(whoami):$(whoami) backend/uploads backend/exports
sudo chmod 777 backend/exports
```

## Step 3: Run database migrations

```bash
docker exec -u root scholarship_backend_dev alembic upgrade head
```

## Step 4: Seed the database

```bash
docker exec -u root scholarship_backend_dev python -m app.seed
```

## Step 5: Assign cs_college to PhD scholarship

```bash
docker compose -f docker-compose.dev.yml exec -T postgres \
  psql -U scholarship_user -d scholarship_db -c "
    INSERT INTO admin_scholarships (admin_id, scholarship_id, assigned_at)
    SELECT u.id, st.id, NOW()
      FROM users u, scholarship_types st
     WHERE u.nycu_id = 'cs_college' AND st.code = 'phd'
    ON CONFLICT ON CONSTRAINT uq_admin_scholarship DO NOTHING;
  "
```

## Step 6: Restart backend

After migrations and seeding, restart the backend to pick up the initialized database:

```bash
docker compose -f docker-compose.dev.yml restart backend
```

## Step 7: Verify

Check that the backend is running without errors:

```bash
docker compose -f docker-compose.dev.yml logs backend --tail 10
```

Confirm `Application startup complete.` appears in the output.

## Troubleshooting

### `up -d` fails with "Conflict. The container name ... is already in use"

The stack's `container_name`s are fixed, so only **one** project/worktree can own them at a
time. This means the stack is already running (possibly re-pointed at a different worktree).
Check first instead of assuming a fresh init is needed:

```bash
docker ps -a --filter "name=scholarship_" --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
```

If containers are already `Up`/`healthy`, skip Steps 1–6 — just verify the mount (Step 0) matches
where you want to work. Use the **change-dev-env-worktree** skill to re-point an already-running
stack's `backend`/`frontend` to a different worktree without touching the data tier.

### Frontend crash-loops: `TurbopackInternalError: Symlink node_modules is invalid, it points out of the filesystem root`

This is the worktree `node_modules` trap: the worktree's `frontend/node_modules` is a symlink to
the main checkout, and the image's baked `/app/node_modules` is *also* a symlink — Turbopack
can't resolve either from inside the container. It's not fixed by restarting; the `.next` cache
also needs clearing once it's crashed on the bad state. Use the **change-dev-env-worktree** skill,
which handles the real bind-mount override and clears the stale `.next` volume — do not just
`restart` the frontend container.

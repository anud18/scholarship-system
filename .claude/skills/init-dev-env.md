---
name: init-dev-env
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

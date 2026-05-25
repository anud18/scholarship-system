---
name: init-dev-env
description: Initialize the scholarship system development environment from scratch - starts Docker services, fixes permissions, runs migrations, and seeds the database.
---

# Init Scholarship Dev Environment

Run the following steps sequentially to set up a clean dev environment:

## Step 1: Start Docker services

```bash
docker compose -f docker-compose.dev.yml up -d
```

Wait for all containers to be healthy before proceeding.

## Step 2: Fix uploads directory permissions

The `backend/uploads` and `backend/exports` directories may be created by Docker as `root`. Fix ownership so the backend container can write to them:

```bash
sudo chown -R $(whoami):$(whoami) backend/uploads backend/exports
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

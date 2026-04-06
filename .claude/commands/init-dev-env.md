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

The `backend/uploads` directory may be created by Docker as `root`. Fix ownership so the backend container can write to it:

```bash
sudo chown -R $(whoami):$(whoami) backend/uploads
```

## Step 3: Run database migrations

```bash
docker exec -u root scholarship_backend_dev alembic upgrade head
```

## Step 4: Seed the database

```bash
docker exec -u root scholarship_backend_dev python -m app.seed
```

## Step 5: Restart backend

After migrations and seeding, restart the backend to pick up the initialized database:

```bash
docker compose -f docker-compose.dev.yml restart backend
```

## Step 6: Verify

Check that the backend is running without errors:

```bash
docker compose -f docker-compose.dev.yml logs backend --tail 10
```

Confirm `Application startup complete.` appears in the output.

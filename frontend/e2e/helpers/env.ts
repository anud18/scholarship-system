/**
 * Single source of truth for which deployment the e2e suite targets.
 *
 * Defaults match the localhost dev stack (docker-compose.dev.yml). The
 * staging-e2e lane (.github/workflows/staging-e2e.yml) points these at the
 * ephemeral staging-replica stack instead:
 *
 *   E2E_FRONTEND_URL=http://localhost:13000
 *   E2E_BACKEND_URL=http://localhost:18000
 *   E2E_DATABASE_URL=postgresql://...@localhost:15432/scholarship_db
 *
 * (E2E_DATABASE_URL is consumed by helpers/db.ts.)
 */
export const FRONTEND_URL =
  process.env.E2E_FRONTEND_URL ?? process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";
export const BACKEND_URL = process.env.E2E_BACKEND_URL ?? "http://localhost:8000";

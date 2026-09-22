import { Pool } from "pg";

export const pool = new Pool({
  connectionString:
    process.env.E2E_DATABASE_URL ??
    "postgresql://scholarship_user:scholarship_pass@localhost:5432/scholarship_db",
});

export async function closePool(): Promise<void> {
  await pool.end();
}

export async function getWhitelist(configId: number): Promise<Record<string, string[]>> {
  const { rows } = await pool.query(
    "SELECT whitelist_student_ids FROM scholarship_configurations WHERE id = $1",
    [configId],
  );
  return (rows[0]?.whitelist_student_ids as Record<string, string[]> | null) ?? {};
}

export async function getApplication(appId: string): Promise<Record<string, unknown> | null> {
  const { rows } = await pool.query("SELECT * FROM applications WHERE app_id = $1", [appId]);
  return rows[0] ?? null;
}

export async function getApplicationById(id: number): Promise<Record<string, unknown> | null> {
  const { rows } = await pool.query("SELECT * FROM applications WHERE id = $1", [id]);
  return rows[0] ?? null;
}

export async function getReviews(applicationDbId: number): Promise<Array<Record<string, unknown>>> {
  const { rows } = await pool.query(
    `SELECT id, application_id, reviewer_id, recommendation, comments, reviewed_at
     FROM application_reviews WHERE application_id = $1 ORDER BY id`,
    [applicationDbId],
  );
  return rows;
}

export interface ConfigRow {
  id: number;
  scholarship_type_id: number;
  academic_year: number;
  semester: string | null;
}

export async function getActiveConfig(scholarshipCode: string): Promise<ConfigRow> {
  const { rows } = await pool.query(
    `SELECT sc.id, sc.scholarship_type_id, sc.academic_year, sc.semester
     FROM scholarship_configurations sc
     JOIN scholarship_types st ON st.id = sc.scholarship_type_id
     WHERE st.code = $1 AND sc.is_active = TRUE
     ORDER BY sc.academic_year DESC, sc.semester DESC NULLS LAST
     LIMIT 1`,
    [scholarshipCode],
  );
  if (!rows[0]) {
    throw new Error(`No active scholarship_configuration for code: ${scholarshipCode}`);
  }
  return rows[0] as ConfigRow;
}

/**
 * Resolve a seeded configuration by its stable config_code. Specs must not
 * hardcode serial ids — they shift whenever the seed's insertion order changes.
 */
export async function getConfigByCode(configCode: string): Promise<ConfigRow> {
  const { rows } = await pool.query(
    `SELECT id, scholarship_type_id, academic_year, semester
     FROM scholarship_configurations WHERE config_code = $1`,
    [configCode],
  );
  if (!rows[0]) {
    throw new Error(`No scholarship_configuration for config_code: ${configCode}`);
  }
  return rows[0] as ConfigRow;
}

export async function dumpRelated(opts: {
  appId?: string;
  configId?: number;
}): Promise<Record<string, unknown>> {
  const out: Record<string, unknown> = {};
  if (opts.appId) {
    const app = await getApplication(opts.appId);
    out.application = app;
    if (app && typeof app.id === "number") {
      out.reviews = await getReviews(app.id);
    }
  }
  if (typeof opts.configId === "number") {
    out.whitelist = await getWhitelist(opts.configId);
  }
  return out;
}

/**
 * Remove every ranking a college owns for one scholarship period so a spec can
 * create a fresh one. A college owns ONE ranking per (type, sub-type, year,
 * semester) — finalized or not — so a leftover from a previous run would be
 * handed back by POST /college-review/rankings (with a stale item set that
 * predates the spec's application) instead of a new ranking being created.
 */
export async function deleteCollegeRankings(opts: {
  scholarshipTypeId: number;
  subType: string;
  academicYear: number;
  semester: string | null;
  collegeCode: string;
}): Promise<void> {
  const { rows } = await pool.query<{ id: number }>(
    `SELECT id FROM college_rankings
      WHERE scholarship_type_id = $1
        AND sub_type_code = $2
        AND academic_year = $3
        AND COALESCE(semester, 'yearly') = COALESCE($4::text, 'yearly')
        AND college_code = $5`,
    [opts.scholarshipTypeId, opts.subType, opts.academicYear, opts.semester, opts.collegeCode],
  );
  for (const { id } of rows) {
    // Child clean-up is best-effort (tolerates schema drift); the parent DELETE
    // must surface its error, otherwise a leftover ranking would be silently
    // handed back to the spec and the failure would show up far downstream.
    for (const sql of [
      "UPDATE payment_rosters SET ranking_id = NULL WHERE ranking_id = $1",
      "DELETE FROM college_ranking_items WHERE ranking_id = $1",
    ]) {
      await pool.query(sql, [id]).catch(() => undefined);
    }
    await pool.query("DELETE FROM college_rankings WHERE id = $1", [id]);
  }
}

export async function deleteApplicationCascade(appId: string): Promise<void> {
  // Best-effort idempotent cleanup covering every FK that points at
  // `applications` with ON DELETE NO ACTION (the default for most of the
  // referencing tables in this schema). Order: children first, parent last.
  //
  // Tables whose FK to applications was discovered the hard way by previous
  // E2E flakes (cross-spec dirty state on stuphd001+phd):
  //   - email_history, scheduled_emails (notification queue)
  //   - document_requests (deadline tracker)
  //   - application_files (uploaded supporting docs)
  //   - college_ranking_items, payment_roster_items (review-stage children)
  //   - application_review_items → application_reviews (review tree)
  //   - student_bank_accounts.verification_source_application_id is ON DELETE
  //     SET NULL, so it cleans itself — left out intentionally.
  //
  // Each DELETE tolerates table absence so older/divergent schemas don't
  // wedge the helper.
  const { rows } = await pool.query("SELECT id FROM applications WHERE app_id = $1", [appId]);
  if (!rows[0]) return;
  const id = rows[0].id as number;

  for (const sql of [
    "DELETE FROM email_history WHERE application_id = $1",
    "DELETE FROM scheduled_emails WHERE application_id = $1",
    "DELETE FROM document_requests WHERE application_id = $1",
    "DELETE FROM application_files WHERE application_id = $1",
    "DELETE FROM college_ranking_items WHERE application_id = $1",
    "DELETE FROM payment_roster_items WHERE application_id = $1",
    `DELETE FROM application_review_items
       WHERE review_id IN (SELECT id FROM application_reviews WHERE application_id = $1)`,
    "DELETE FROM application_reviews WHERE application_id = $1",
  ]) {
    await pool.query(sql, [id]).catch(() => undefined);
  }
  // The audit table is `audit_logs` (general-purpose), keyed by
  // (resource_type, resource_id::text). Its rows are removed by the FK
  // cascade on applications, so no explicit DELETE is needed here.
  await pool.query("DELETE FROM applications WHERE id = $1", [id]);
}

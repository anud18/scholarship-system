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

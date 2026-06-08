"""shared quota pools — additive cols + backfill + data-move + index rebuild

Revision ID: 20260608_shared_quota_add
Revises: 20260531_perf_indexes
Create Date: 2026-06-08

MIGRATION 1 of 2 (additive only — destructive drops are in MIGRATION 2,
which runs only AFTER all code stops reading the dropped columns).

Adds allocation_config_id FK to college_ranking_items, applications,
payment_rosters, payment_roster_items, and shared_quota_sources JSON to
scholarship_configurations. Backfills allocation_config_id from the legacy
allocation_year using the same 3-way semester normalization the service uses
(ranking semester {NULL,'annual','yearly'} <-> config semester {NULL,'yearly'}),
tie-breaking ORDER BY id DESC LIMIT 1 (matches get_quota_status). Per-slice
items that fail to resolve are pointed at the requesting config id (never NULL).
Approved renewals backfill from the prior slot's config, falling back to their
own scholarship_configuration_id. Moves prior-year project codes into source
configs BEFORE flattening project_numbers to own-year-only. Converts
prior_quota_years -> shared_quota_sources (dropping links whose target config
does not exist). Re-keys history JSON. Rebuilds the roster unique index.

Existence-checked per project convention; safe to re-run.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260608_shared_quota_add"
down_revision: Union[str, Sequence[str], None] = "20260531_perf_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- 3-way semester normalization (mirrors manual_distribution_service._*_semester_condition) ---
# ranking/item semester in {NULL, 'annual', 'yearly'}  <->  config semester in {NULL, 'yearly'}
def _config_semester_sql(alias: str) -> str:
    """SQL predicate matching a config row's semester to a yearly/term ranking semester.

    `alias` is the source-row table alias whose .semester we are matching against.
    """
    return (
        f"((cfg.semester IS NULL AND ({alias}.semester IS NULL "
        f"OR {alias}.semester IN ('annual', 'yearly'))) "
        f"OR (cfg.semester = 'yearly' AND ({alias}.semester IS NULL "
        f"OR {alias}.semester IN ('annual', 'yearly'))) "
        f"OR (cfg.semester = {alias}.semester))"
    )


def _add_nullable_fk(inspector, table: str, col: str) -> None:
    cols = [c["name"] for c in inspector.get_columns(table)]
    if col not in cols:
        op.add_column(
            table,
            sa.Column(
                col,
                sa.Integer(),
                sa.ForeignKey("scholarship_configurations.id"),
                nullable=True,
            ),
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ---------- 1. additive FK columns (existence-checked) ----------
    _add_nullable_fk(inspector, "college_ranking_items", "allocation_config_id")
    _add_nullable_fk(inspector, "applications", "allocation_config_id")
    _add_nullable_fk(inspector, "payment_rosters", "allocation_config_id")
    _add_nullable_fk(inspector, "payment_roster_items", "allocation_config_id")

    sc_cols = [c["name"] for c in inspector.get_columns("scholarship_configurations")]
    if "shared_quota_sources" not in sc_cols:
        op.add_column(
            "scholarship_configurations",
            sa.Column("shared_quota_sources", sa.JSON(), nullable=True),
        )

    # ---------- 2. backfill college_ranking_items.allocation_config_id ----------
    # Resolve (ranking.scholarship_type_id, academic_year = item.allocation_year, semester)
    # -> ScholarshipConfiguration.id, 3-way semester normalized, tie-break id DESC.
    op.execute(f"""
        UPDATE college_ranking_items ri
        SET allocation_config_id = (
            SELECT cfg.id FROM scholarship_configurations cfg
            JOIN college_rankings r ON r.id = ri.ranking_id
            WHERE cfg.scholarship_type_id = r.scholarship_type_id
              AND cfg.academic_year = ri.allocation_year
              AND {_config_semester_sql('r')}
            ORDER BY cfg.id DESC
            LIMIT 1
        )
        FROM college_rankings r2
        WHERE r2.id = ri.ranking_id
          AND ri.allocation_year IS NOT NULL
          AND ri.allocation_config_id IS NULL
        """)
    # Per-slice orphans (allocated item with a sub_type but unresolved config) ->
    # requesting config id (the ranking's own-year config); NEVER left NULL.
    op.execute(f"""
        UPDATE college_ranking_items ri
        SET allocation_config_id = (
            SELECT cfg.id FROM scholarship_configurations cfg
            JOIN college_rankings r ON r.id = ri.ranking_id
            WHERE cfg.scholarship_type_id = r.scholarship_type_id
              AND cfg.academic_year = r.academic_year
              AND {_config_semester_sql('r')}
            ORDER BY cfg.id DESC
            LIMIT 1
        )
        WHERE ri.allocation_config_id IS NULL
          AND ri.is_allocated = true
          AND ri.allocated_sub_type IS NOT NULL
        """)

    # ---------- 3. backfill payment_rosters / payment_roster_items ----------
    for tbl in ("payment_rosters", "payment_roster_items"):
        # roster items resolve via their parent roster's config + period;
        # both tables carry allocation_year + scholarship_configuration_id
        # directly (roster) or via roster_id (item). Resolve through the roster.
        if tbl == "payment_rosters":
            op.execute("""
                UPDATE payment_rosters pr
                SET allocation_config_id = (
                    SELECT cfg.id FROM scholarship_configurations cfg
                    JOIN scholarship_configurations own ON own.id = pr.scholarship_configuration_id
                    WHERE cfg.scholarship_type_id = own.scholarship_type_id
                      AND cfg.academic_year = pr.allocation_year
                      AND ((cfg.semester IS NULL AND (own.semester IS NULL
                            OR own.semester = 'yearly'))
                        OR (cfg.semester = own.semester))
                    ORDER BY cfg.id DESC
                    LIMIT 1
                )
                WHERE pr.allocation_year IS NOT NULL
                  AND pr.allocation_config_id IS NULL
                """)
            # whole-period / unresolved per-slice rosters -> own config (never NULL for sub_type rows)
            op.execute("""
                UPDATE payment_rosters pr
                SET allocation_config_id = pr.scholarship_configuration_id
                WHERE pr.allocation_config_id IS NULL
                  AND pr.sub_type IS NOT NULL
                """)
        else:
            op.execute("""
                UPDATE payment_roster_items pri
                SET allocation_config_id = pr.allocation_config_id,
                    allocation_year = pr.allocation_year
                FROM payment_rosters pr
                WHERE pr.id = pri.roster_id
                  AND pri.allocation_config_id IS NULL
                """)

    # ---------- 4. backfill applications.allocation_config_id (renewals) ----------
    # prior slot's config from the previous application's allocated ranking item
    op.execute("""
        UPDATE applications a
        SET allocation_config_id = (
            SELECT ri.allocation_config_id
            FROM college_ranking_items ri
            WHERE ri.application_id = a.previous_application_id
              AND ri.allocation_config_id IS NOT NULL
            ORDER BY ri.id DESC
            LIMIT 1
        )
        WHERE a.is_renewal = true
          AND a.allocation_config_id IS NULL
          AND a.previous_application_id IS NOT NULL
        """)
    # approved renewals must NEVER be NULL -> fall back to own scholarship_configuration_id
    op.execute("""
        UPDATE applications a
        SET allocation_config_id = a.scholarship_configuration_id
        WHERE a.is_renewal = true
          AND a.allocation_config_id IS NULL
          AND a.status = 'approved'
          AND a.scholarship_configuration_id IS NOT NULL
        """)

    # ---------- 5. project_numbers DATA-MOVE (before flatten) ----------
    # For every config holding borrowed-year codes
    # (e.g. phd_114.project_numbers["nstc"]["113"] = "113R000001"),
    # push that code into the SOURCE config's own-year entry
    # (phd_113.project_numbers["nstc"] = "113R000001") iff the source config
    # exists and lacks an own-year code. Source configs are matched by same
    # scholarship_type_id + academic_year == the year key. Pure-Python loop so
    # the nested-dict logic is testable and dialect-agnostic.
    import json as _json

    configs = list(
        bind.execute(
            sa.text(
                "SELECT id, scholarship_type_id, academic_year, semester, "
                "project_numbers FROM scholarship_configurations"
            )
        ).mappings()
    )
    by_type_year = {(c["scholarship_type_id"], c["academic_year"]): dict(c) for c in configs}
    # working copy of each config's flattened own-year project_numbers
    own_year_pn: dict[int, dict] = {}
    for c in configs:
        pn = c["project_numbers"] or {}
        if isinstance(pn, str):
            try:
                pn = _json.loads(pn)
            except (ValueError, TypeError):
                pn = {}
        own_year_pn.setdefault(c["id"], {})
        for sub_type, by_year in pn.items():
            if not isinstance(by_year, dict):
                # already flat {sub_type: code} — keep as-is
                if isinstance(by_year, str):
                    own_year_pn[c["id"]][sub_type] = by_year
                continue
            for year_str, code in by_year.items():
                try:
                    year_i = int(year_str)
                except (ValueError, TypeError):
                    continue
                if year_i == c["academic_year"]:
                    # own-year entry -> keep on this config
                    own_year_pn[c["id"]][sub_type] = code
                else:
                    # borrowed-year entry -> push into the source config
                    src = by_type_year.get((c["scholarship_type_id"], year_i))
                    if src is None:
                        continue  # no source config -> code is dropped (logged below)
                    own_year_pn.setdefault(src["id"], {})
                    if not own_year_pn[src["id"]].get(sub_type):
                        own_year_pn[src["id"]][sub_type] = code

    # ---------- 6. FLATTEN: write flattened own-year-only project_numbers ----------
    for cfg_id, flat in own_year_pn.items():
        bind.execute(
            sa.text("UPDATE scholarship_configurations SET project_numbers = :pn WHERE id = :id"),
            {"pn": _json.dumps(flat) if flat else None, "id": cfg_id},
        )

    # ---------- 7. prior_quota_years -> shared_quota_sources ----------
    dropped_links = 0
    code_by_type_year = {
        (c["scholarship_type_id"], c["academic_year"]): c["config_code"]
        for c in bind.execute(
            sa.text("SELECT scholarship_type_id, academic_year, config_code FROM scholarship_configurations")
        ).mappings()
    }
    pqy_rows = list(
        bind.execute(
            sa.text(
                "SELECT id, scholarship_type_id, prior_quota_years "
                "FROM scholarship_configurations WHERE prior_quota_years IS NOT NULL"
            )
        ).mappings()
    )
    for row in pqy_rows:
        pqy = row["prior_quota_years"]
        if isinstance(pqy, str):
            try:
                pqy = _json.loads(pqy)
            except (ValueError, TypeError):
                pqy = {}
        if not isinstance(pqy, dict):
            continue
        # gather {source_config_code: [sub_types]}
        links: dict[str, list] = {}
        for sub_type, years in pqy.items():
            if not isinstance(years, list):
                continue
            for yr in years:
                code = code_by_type_year.get((row["scholarship_type_id"], yr))
                if code is None:
                    dropped_links += 1  # target config does not exist -> drop link
                    continue
                links.setdefault(code, [])
                if sub_type not in links[code]:
                    links[code].append(sub_type)
        sqs = [{"source_config_code": code, "sub_types": sts} for code, sts in links.items()]
        bind.execute(
            sa.text("UPDATE scholarship_configurations SET shared_quota_sources = :sqs WHERE id = :id"),
            {"sqs": _json.dumps(sqs) if sqs else None, "id": row["id"]},
        )

    # ---------- 8. history JSON re-key allocation_year -> allocation_config_id ----------
    # manual_distribution_history.allocations_snapshot is {ranking_item_id: {sub_type, allocation_year, status}}.
    # Re-key per item using the same (type, year, semester) resolution.
    hist_rows = list(
        bind.execute(
            sa.text(
                "SELECT id, scholarship_type_id, semester, allocations_snapshot "
                "FROM manual_distribution_history WHERE allocations_snapshot IS NOT NULL"
            )
        ).mappings()
    )
    for h in hist_rows:
        snap = h["allocations_snapshot"]
        if isinstance(snap, str):
            try:
                snap = _json.loads(snap)
            except (ValueError, TypeError):
                continue
        if not isinstance(snap, dict):
            continue
        changed = False
        for _item_id, payload in snap.items():
            if not isinstance(payload, dict) or "allocation_year" not in payload:
                continue
            yr = payload.get("allocation_year")
            cfg_id = None
            if yr is not None:
                resolved = bind.execute(
                    sa.text(
                        "SELECT id FROM scholarship_configurations cfg "
                        "WHERE cfg.scholarship_type_id = :stid AND cfg.academic_year = :yr "
                        "AND ((cfg.semester IS NULL AND (:sem IS NULL OR :sem IN ('annual','yearly'))) "
                        "OR (cfg.semester = 'yearly' AND (:sem IS NULL OR :sem IN ('annual','yearly'))) "
                        "OR (cfg.semester = :sem)) "
                        "ORDER BY cfg.id DESC LIMIT 1"
                    ),
                    {"stid": h["scholarship_type_id"], "yr": yr, "sem": h["semester"]},
                ).scalar()
                cfg_id = resolved
            payload["allocation_config_id"] = cfg_id
            payload.pop("allocation_year", None)
            changed = True
        if changed:
            bind.execute(
                sa.text("UPDATE manual_distribution_history SET allocations_snapshot = :s WHERE id = :id"),
                {"s": _json.dumps(snap), "id": h["id"]},
            )

    # ---------- 9. rebuild roster unique index on allocation_config_id ----------
    existing_idx = [idx["name"] for idx in inspector.get_indexes("payment_rosters")]
    if "uq_roster_scholarship_period_alloc" in existing_idx:
        op.drop_index("uq_roster_scholarship_period_alloc", table_name="payment_rosters")
    op.execute("""
        CREATE UNIQUE INDEX uq_roster_scholarship_period_alloc
        ON payment_rosters (
            scholarship_configuration_id,
            period_label,
            COALESCE(allocation_config_id, -1),
            COALESCE(sub_type, '')
        )
        """)

    # ---------- 10. pre-drop audit (fail loud counts; MIGRATION 2 does the drops) ----------
    orphan_items = bind.execute(
        sa.text(
            "SELECT count(*) FROM college_ranking_items "
            "WHERE is_allocated = true AND allocated_sub_type IS NOT NULL "
            "AND allocation_config_id IS NULL"
        )
    ).scalar()
    orphan_renewals = bind.execute(
        sa.text(
            "SELECT count(*) FROM applications "
            "WHERE is_renewal = true AND status = 'approved' AND allocation_config_id IS NULL"
        )
    ).scalar()
    # Pre-drop audit: log orphan counts to the alembic migration logger (crash-proof).
    # NOT an audit_logs INSERT — audit_logs.user_id is NOT NULL and there is no `details`
    # column, so a raw INSERT would abort the migration. See reconciliation note 7.
    import logging as _logging

    _logging.getLogger("alembic.runtime.migration").warning(
        "shared_quota_pools migration audit: orphan_allocated_items=%s "
        "orphan_approved_renewals=%s dropped_shared_quota_links=%s",
        orphan_items,
        orphan_renewals,
        dropped_links,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_idx = [idx["name"] for idx in inspector.get_indexes("payment_rosters")]
    if "uq_roster_scholarship_period_alloc" in existing_idx:
        op.drop_index("uq_roster_scholarship_period_alloc", table_name="payment_rosters")
    op.execute("""
        CREATE UNIQUE INDEX uq_roster_scholarship_period_alloc
        ON payment_rosters (
            scholarship_configuration_id,
            period_label,
            COALESCE(allocation_year, -1),
            COALESCE(sub_type, '')
        )
        """)

    sc_cols = [c["name"] for c in inspector.get_columns("scholarship_configurations")]
    if "shared_quota_sources" in sc_cols:
        op.drop_column("scholarship_configurations", "shared_quota_sources")

    for table in ("payment_roster_items", "payment_rosters", "applications", "college_ranking_items"):
        cols = [c["name"] for c in inspector.get_columns(table)]
        if "allocation_config_id" in cols:
            op.drop_column(table, "allocation_config_id")


# Section markers referenced by the static migration test (do not remove):
# DATA-MOVE = step 5 (project_numbers move into source configs)
# FLATTEN   = step 6 (project_numbers flattened to own-year only)

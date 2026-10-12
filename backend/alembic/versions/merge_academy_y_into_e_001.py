"""Merge retired academy Y (電資學院) into E (電機學院)

電資學院 no longer exists. SIS still files the 電資博學程 under academy code Y,
but 電機學院 manages the programme and is the only one of the two that receives
quota, so Y applications must be reviewed, ranked and distributed together
with E's. From now on StudentService remaps Y -> E at the SIS boundary
(core/college_mappings.normalize_student_academy); this migration moves the
data that already exists:

1. applications.student_data — every academy-code key holding Y becomes E, the
   academy name follows, and the raw SIS values are kept under
   ``_sis_academy_codes_original``.
2. college_rankings — a Y ranking with no E ranking for the same period is
   relabelled to E. When both exist, the Y items are appended after E's last
   rank position (item ids are preserved, so manual-distribution history and
   rosters keep pointing at them), rosters are re-pointed, the Y ranking is
   dropped and the quotas summed. The merged E ranking goes back to draft so
   電機學院 reviews the combined order before sending it again — unless
   distribution already ran on either ranking: rosters and the distribution
   grid read finalized rankings only, so such a ranking stays finalized.
   A relabelled ranking's name has 電資學院 replaced by 電機學院.
3. college_ranking_items.backup_allocations — ``college`` Y -> E.
4. scholarship_configurations.quotas — a Y quota is added to E's.
5. users / batch_imports college_code Y -> E (a Y-bound 學院 account now
   reviews 電機學院).
6. departments.academy_code Y -> E, then the academies row Y is deleted.

Downgrade restores the academies row only: merged rankings and moved rows are
indistinguishable from native E rows and stay on E.

Revision ID: merge_academy_y_into_e_001
Revises: college_ranking_single_001
"""

import json
import logging
from typing import Any, Dict, Optional

import sqlalchemy as sa

from alembic import op

logger = logging.getLogger("alembic.runtime.migration")

revision = "merge_academy_y_into_e_001"
down_revision = "college_ranking_single_001"
branch_labels = None
depends_on = None

OLD_CODE = "Y"
NEW_CODE = "E"
NEW_NAME = "電機學院"
OLD_NAME = "電資學院"
REMOVED_ROWS = (("Y", "電資學院", "Electrical Engineering and Computer Science"),)
# Removed code -> surviving college (frozen copy of college_mappings.MERGED_ACADEMY_CODES).
REPLACEMENT_CODES = {OLD_CODE: NEW_CODE}

# Frozen copies of college_mappings.ACADEMY_CODE_KEYS / ACADEMY_NAME_KEYS /
# ORIGINAL_ACADEMY_CODES_KEY.
CODE_KEYS = ("std_academyno", "trm_academyno", "academy_code", "college_code", "std_college")
# academy-name key -> the code key it names
NAME_KEYS = {"trm_academyname": "trm_academyno"}
ORIGINAL_KEY = "_sis_academy_codes_original"

_PREFIX = "merge_academy_y_into_e_001"


def _is_old(value: Any) -> bool:
    return isinstance(value, str) and value.strip() == OLD_CODE


def _normalize_snapshot(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """New snapshot with Y codes remapped, or None when nothing changes."""
    replaced = {key: data[key] for key in CODE_KEYS if _is_old(data.get(key))}
    if not replaced:
        return None
    new_codes = {key: NEW_CODE for key in replaced}
    new_names = {name_key: NEW_NAME for name_key, code_key in NAME_KEYS.items() if code_key in replaced}
    originals = {**(data.get(ORIGINAL_KEY) or {}), **replaced}
    return {**data, **new_codes, **new_names, ORIGINAL_KEY: originals}


def _to_count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        logger.warning("%s: non-numeric quota %r treated as 0", _PREFIX, value)
        return 0


def _merge_counts(counts: Dict[str, Any]) -> Dict[str, Any]:
    if OLD_CODE not in counts:
        return counts
    rest = {key: value for key, value in counts.items() if key != OLD_CODE}
    return {**rest, NEW_CODE: _to_count(rest.get(NEW_CODE)) + _to_count(counts[OLD_CODE])}


def _merge_quotas(quotas: Any) -> Any:
    """Fold Y into E in a flat {college: n} or matrix {sub_type: {college: n}} quota map."""
    if not isinstance(quotas, dict):
        return quotas
    merged = _merge_counts(quotas)
    return {key: _merge_counts(value) if isinstance(value, dict) else value for key, value in merged.items()}


def _load_json(raw: Any) -> Any:
    return json.loads(raw) if isinstance(raw, str) else raw


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _migrate_applications(bind) -> None:
    matches = " OR ".join(f"TRIM(student_data ->> '{key}') = :old" for key in CODE_KEYS)
    rows = bind.execute(
        sa.text(f"SELECT id, student_data::text FROM applications WHERE student_data IS NOT NULL AND ({matches})"),
        {"old": OLD_CODE},
    ).fetchall()
    moved = 0
    for app_id, raw in rows:
        updated = _normalize_snapshot(_load_json(raw))
        if updated is None:
            continue
        bind.execute(
            sa.text("UPDATE applications SET student_data = CAST(:data AS json) WHERE id = :id"),
            {"data": _dump_json(updated), "id": app_id},
        )
        moved += 1
    if moved:
        logger.info("%s: moved %d applications from %s to %s", _PREFIX, moved, OLD_CODE, NEW_CODE)


def _find_target_ranking(bind, ranking) -> Optional[int]:
    return bind.execute(
        sa.text(
            "SELECT id FROM college_rankings "
            "WHERE college_code = :new AND scholarship_type_id = :type_id AND sub_type_code = :sub_type "
            "AND academic_year = :year AND COALESCE(semester, 'yearly') = COALESCE(:semester, 'yearly')"
        ),
        {
            "new": NEW_CODE,
            "type_id": ranking.scholarship_type_id,
            "sub_type": ranking.sub_type_code,
            "year": ranking.academic_year,
            "semester": ranking.semester,
        },
    ).scalar()


def _merge_ranking_into(bind, source, target_id: int) -> None:
    offset = bind.execute(
        sa.text("SELECT COALESCE(MAX(rank_position), 0) FROM college_ranking_items WHERE ranking_id = :id"),
        {"id": target_id},
    ).scalar()
    bind.execute(
        sa.text(
            "UPDATE college_ranking_items SET ranking_id = :target, rank_position = rank_position + :offset "
            "WHERE ranking_id = :source"
        ),
        {"target": target_id, "offset": offset, "source": source.id},
    )
    bind.execute(
        sa.text("UPDATE payment_rosters SET ranking_id = :target WHERE ranking_id = :source"),
        {"target": target_id, "source": source.id},
    )
    target = bind.execute(
        sa.text("SELECT total_quota, is_finalized, distribution_executed FROM college_rankings WHERE id = :id"),
        {"id": target_id},
    ).one()
    quotas = [q for q in (target.total_quota, source.total_quota) if q is not None]
    distributed = bool(target.distribution_executed or source.distribution_executed)
    bind.execute(
        sa.text(
            "UPDATE college_rankings SET "
            "total_applications = (SELECT COUNT(*) FROM college_ranking_items WHERE ranking_id = :target), "
            "allocated_count = COALESCE(allocated_count, 0) + :allocated, "
            "total_quota = :total_quota, distribution_executed = :distributed, updated_at = now() "
            "WHERE id = :target"
        ),
        {
            "target": target_id,
            "allocated": source.allocated_count or 0,
            "total_quota": sum(quotas) if quotas else None,
            "distributed": distributed,
        },
    )
    if distributed:
        # Distribution already ran: rosters and the distribution grid only read
        # finalized rankings, so the merged ranking must stay sent.
        bind.execute(
            sa.text("UPDATE college_rankings SET is_finalized = true, ranking_status = 'finalized' WHERE id = :id"),
            {"id": target_id},
        )
        outcome = "kept finalized (distribution already executed)"
    else:
        # 電機學院 reviews the combined order and sends it again.
        bind.execute(
            sa.text(
                "UPDATE college_rankings SET is_finalized = false, ranking_status = 'draft', "
                "finalized_at = NULL, finalized_by = NULL WHERE id = :id"
            ),
            {"id": target_id},
        )
        outcome = "reverted to draft"
    bind.execute(sa.text("DELETE FROM college_rankings WHERE id = :id"), {"id": source.id})
    logger.info(
        "%s: merged %s ranking %d into %s ranking %d (rank offset %d); %s",
        _PREFIX,
        OLD_CODE,
        source.id,
        NEW_CODE,
        target_id,
        offset,
        outcome,
    )


def _migrate_rankings(bind) -> None:
    rankings = bind.execute(
        sa.text(
            "SELECT id, scholarship_type_id, sub_type_code, academic_year, semester, "
            "allocated_count, total_quota, distribution_executed "
            "FROM college_rankings WHERE TRIM(college_code) = :old ORDER BY id"
        ),
        {"old": OLD_CODE},
    ).fetchall()
    for ranking in rankings:
        target_id = _find_target_ranking(bind, ranking)
        if target_id is None:
            bind.execute(
                sa.text(
                    "UPDATE college_rankings SET college_code = :new, "
                    "ranking_name = REPLACE(ranking_name, :old_name, :new_name), updated_at = now() "
                    "WHERE id = :id"
                ),
                {"new": NEW_CODE, "old_name": OLD_NAME, "new_name": NEW_NAME, "id": ranking.id},
            )
            logger.info("%s: relabelled ranking %d from %s to %s", _PREFIX, ranking.id, OLD_CODE, NEW_CODE)
        else:
            _merge_ranking_into(bind, ranking, target_id)


def _migrate_backup_allocations(bind) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT id, backup_allocations::text FROM college_ranking_items "
            "WHERE backup_allocations IS NOT NULL AND backup_allocations::text LIKE :pattern"
        ),
        {"pattern": '%"college"%'},
    ).fetchall()
    for item_id, raw in rows:
        allocations = _load_json(raw)
        if not isinstance(allocations, list):
            continue
        updated = [
            {**entry, "college": NEW_CODE} if isinstance(entry, dict) and _is_old(entry.get("college")) else entry
            for entry in allocations
        ]
        if updated != allocations:
            bind.execute(
                sa.text("UPDATE college_ranking_items SET backup_allocations = CAST(:data AS jsonb) WHERE id = :id"),
                {"data": _dump_json(updated), "id": item_id},
            )


def _migrate_quotas(bind) -> None:
    rows = bind.execute(
        sa.text("SELECT id, quotas::text FROM scholarship_configurations WHERE quotas IS NOT NULL")
    ).fetchall()
    for config_id, raw in rows:
        quotas = _load_json(raw)
        merged = _merge_quotas(quotas)
        if merged != quotas:
            bind.execute(
                sa.text("UPDATE scholarship_configurations SET quotas = CAST(:data AS json) WHERE id = :id"),
                {"data": _dump_json(merged), "id": config_id},
            )
            logger.info("%s: folded %s quota into %s for configuration %d", _PREFIX, OLD_CODE, NEW_CODE, config_id)


def _move_code_column(bind, table: str, column: str) -> None:
    moved = bind.execute(
        sa.text(f"UPDATE {table} SET {column} = :new WHERE TRIM({column}) = :old"),
        {"old": OLD_CODE, "new": NEW_CODE},
    ).rowcount
    if moved:
        logger.info("%s: moved %d %s rows from %s to %s", _PREFIX, moved, table, OLD_CODE, NEW_CODE)


def upgrade() -> None:
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "applications" in tables:
        _migrate_applications(bind)
    if "college_rankings" in tables and "college_ranking_items" in tables:
        _migrate_rankings(bind)
        _migrate_backup_allocations(bind)
    if "scholarship_configurations" in tables:
        _migrate_quotas(bind)
    for table in ("users", "batch_imports"):
        if table in tables:
            _move_code_column(bind, table, "college_code")
    if "departments" in tables:
        _move_code_column(bind, "departments", "academy_code")
    if "academies" in tables:
        bind.execute(sa.text("DELETE FROM academies WHERE code = :code"), {"code": OLD_CODE})


def downgrade() -> None:
    bind = op.get_bind()
    if "academies" not in sa.inspect(bind).get_table_names():
        return

    bind.execute(
        sa.text(
            "INSERT INTO academies (code, name, name_en) VALUES (:code, :name, :name_en) ON CONFLICT (code) DO NOTHING"
        ),
        [{"code": code, "name": name, "name_en": name_en} for code, name, name_en in REMOVED_ROWS],
    )

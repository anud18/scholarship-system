"""Static guards for the shared-quota MIGRATION 1 module (Phase 1).

These assert the migration's structural contract without a live DB: correct
down_revision (single verified head), existence-checked DDL, the project_numbers
data-move-BEFORE-flatten ordering, and the rebuilt unique index spec. The full
data backfill is exercised by the reset_database.sh smoke (Task 1.7).
"""

import importlib.util
from pathlib import Path

_MIG = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20260608_shared_quota_pools_add.py"


def _load():
    spec = importlib.util.spec_from_file_location("mig_shared_quota_add", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_file_exists():
    assert _MIG.exists(), f"migration not found: {_MIG}"


def test_down_revision_is_verified_head():
    mod = _load()
    assert mod.down_revision == "20260531_perf_indexes"
    assert mod.revision == "20260608_shared_quota_add"


def test_migration_source_contract():
    src = _MIG.read_text(encoding="utf-8")
    # additive FK columns
    assert "college_ranking_items" in src and "allocation_config_id" in src
    assert "applications" in src
    assert "payment_rosters" in src and "payment_roster_items" in src
    # existence-checked DDL (project convention)
    assert "inspector.get_columns" in src
    # data-move BEFORE flatten ordering marker
    assert src.index("DATA-MOVE") < src.index("FLATTEN")
    # rebuilt unique index keys on allocation_config_id, retains sub_type
    assert "COALESCE(allocation_config_id, -1)" in src
    assert "COALESCE(sub_type, '')" in src
    # 3-way semester normalization helpers are inlined
    assert "'annual'" in src and "'yearly'" in src
    # pre-drop audit log emission
    assert "audit" in src.lower()


_MIG2 = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20260608_shared_quota_pools_drop.py"


def _load2():
    spec = importlib.util.spec_from_file_location("mig_shared_quota_drop", _MIG2)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_drop_migration_chains_after_add():
    assert _MIG2.exists(), f"drop migration not found: {_MIG2}"
    mod = _load2()
    assert mod.down_revision == "20260608_shared_quota_add"
    assert mod.revision == "20260608_shared_quota_drop"
    src = _MIG2.read_text(encoding="utf-8")
    # drops exactly the two dead columns, existence-checked
    assert "college_ranking_items" in src and "allocation_year" in src
    assert "prior_quota_years" in src
    assert "inspector.get_columns" in src

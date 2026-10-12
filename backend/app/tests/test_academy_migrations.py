"""Pin the frozen academy rows in the migrations to core/college_mappings.py.

The `academies` table is populated only by migrations, so the rows left after
align_academy_names_003 + remove_academy_8_001 + merge_academy_y_into_e_001 and the static ACADEMY_TABLE the
app reads must be identical or the dropdowns and the fallback labels drift
apart again.
"""

import importlib.util
from pathlib import Path

from app.core.college_mappings import ACADEMY_TABLE

_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"mig_{name}", _VERSIONS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_down_revision_is_verified_head():
    mod = _load("align_academy_names_003")
    assert mod.revision == "align_academy_names_003"
    assert mod.down_revision == "add_fixed_key_columns_001"


def test_remove_academy_8_follows_003():
    mod = _load("remove_academy_8_001")
    assert mod.revision == "remove_academy_8_001"
    assert mod.down_revision == "align_academy_names_003"


_REMOVAL_MIGRATIONS = ("remove_academy_8_001", "merge_academy_y_into_e_001")


def test_merge_academy_y_follows_college_ranking_single():
    mod = _load("merge_academy_y_into_e_001")
    assert mod.revision == "merge_academy_y_into_e_001"
    assert mod.down_revision == "college_ranking_single_001"


def test_migrated_rows_match_academy_table():
    removed = {code for name in _REMOVAL_MIGRATIONS for code, _, _ in _load(name).REMOVED_ROWS}
    remaining = tuple(row for row in _load("align_academy_names_003").CANONICAL_ROWS if row[0] not in removed)
    assert remaining == tuple(ACADEMY_TABLE)


def test_removed_rows_restore_003_values():
    canonical = set(_load("align_academy_names_003").CANONICAL_ROWS)
    for name in _REMOVAL_MIGRATIONS:
        mod = _load(name)
        for row in mod.REMOVED_ROWS:
            assert row in canonical
            assert mod.REPLACEMENT_CODES[row[0]] in {code for code, _, _ in ACADEMY_TABLE}


def test_merge_migration_matches_runtime_mapping():
    """The migration's frozen copies must equal the runtime normalization."""
    from app.core import college_mappings

    mod = _load("merge_academy_y_into_e_001")
    assert mod.REPLACEMENT_CODES == college_mappings.MERGED_ACADEMY_CODES
    assert mod.CODE_KEYS == college_mappings.ACADEMY_CODE_KEYS
    assert mod.NAME_KEYS == college_mappings.ACADEMY_NAME_KEYS
    assert mod.ORIGINAL_KEY == college_mappings.ORIGINAL_ACADEMY_CODES_KEY
    assert mod.NEW_NAME == college_mappings.COLLEGE_MAPPINGS[mod.NEW_CODE]


def test_merge_migration_snapshot_matches_runtime_normalization():
    """Migrated rows must look exactly like rows normalized at the SIS boundary."""
    from app.core.college_mappings import normalize_student_academy

    mod = _load("merge_academy_y_into_e_001")
    cases = [
        {"std_academyno": "Y", "trm_academyno": "Y", "trm_academyname": "電資學院", "std_pid": "enc:x"},
        {"std_academyno": "Y", "trm_academyno": "C", "trm_academyname": "資訊學院"},
        {"std_academyno": " Y", "college_code": "Y"},
    ]
    for snapshot in cases:
        assert mod._normalize_snapshot(snapshot) == normalize_student_academy(snapshot)
    assert mod._normalize_snapshot({"std_academyno": "E"}) is None


def test_merge_migration_folds_y_quota_into_e():
    mod = _load("merge_academy_y_into_e_001")
    matrix = {"nstc": {"E": 3, "C": 2, "Y": 1}, "moe_1w": {"Y": "2"}, "note": "x"}
    assert mod._merge_quotas(matrix) == {"nstc": {"E": 4, "C": 2}, "moe_1w": {"E": 2}, "note": "x"}
    assert mod._merge_quotas({"E": 5, "Y": 2}) == {"E": 7}
    untouched = {"nstc": {"E": 3}}
    assert mod._merge_quotas(untouched) == untouched


def test_added_codes_are_not_in_previous_rows():
    mod = _load("align_academy_names_003")
    previous_codes = {code for code, _, _ in mod.PREVIOUS_ROWS}
    for code in mod.ADDED_CODES:
        assert code not in previous_codes
        assert code in {c for c, _, _ in mod.CANONICAL_ROWS}

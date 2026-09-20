"""Pin the frozen academy rows in the migrations to core/college_mappings.py.

The `academies` table is populated only by migrations, so the rows left after
align_academy_names_003 + remove_academy_8_001 and the static ACADEMY_TABLE the
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


def test_migrated_rows_match_academy_table():
    removed = {code for code, _, _ in _load("remove_academy_8_001").REMOVED_ROWS}
    remaining = tuple(row for row in _load("align_academy_names_003").CANONICAL_ROWS if row[0] not in removed)
    assert remaining == tuple(ACADEMY_TABLE)


def test_removed_rows_restore_003_values():
    canonical = set(_load("align_academy_names_003").CANONICAL_ROWS)
    mod = _load("remove_academy_8_001")
    for row in mod.REMOVED_ROWS:
        assert row in canonical
        assert mod.REPLACEMENT_CODES[row[0]] in {code for code, _, _ in ACADEMY_TABLE}


def test_added_codes_are_not_in_previous_rows():
    mod = _load("align_academy_names_003")
    previous_codes = {code for code, _, _ in mod.PREVIOUS_ROWS}
    for code in mod.ADDED_CODES:
        assert code not in previous_codes
        assert code in {c for c, _, _ in mod.CANONICAL_ROWS}

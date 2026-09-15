"""Pin align_academy_names_003's frozen academy rows to core/college_mappings.py.

The `academies` table is populated only by migrations, so the frozen copy in
the migration and the static ACADEMY_TABLE the app reads must be identical or
the dropdowns and the fallback labels drift apart again.
"""

import importlib.util
from pathlib import Path

from app.core.college_mappings import ACADEMY_TABLE

_MIG = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "align_academy_names_003.py"


def _load():
    spec = importlib.util.spec_from_file_location("mig_align_academy_names_003", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_down_revision_is_verified_head():
    mod = _load()
    assert mod.revision == "align_academy_names_003"
    assert mod.down_revision == "add_fixed_key_columns_001"


def test_canonical_rows_match_academy_table():
    mod = _load()
    assert tuple(mod.CANONICAL_ROWS) == tuple(ACADEMY_TABLE)


def test_added_codes_are_not_in_previous_rows():
    mod = _load()
    previous_codes = {code for code, _, _ in mod.PREVIOUS_ROWS}
    for code in mod.ADDED_CODES:
        assert code not in previous_codes
        assert code in {c for c, _, _ in mod.CANONICAL_ROWS}

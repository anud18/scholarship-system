"""CI invariant: no backend test file may run in zero CI lanes.

Background
---------
`backend/pytest.ini` sets ``asyncio_mode = auto``, so every ``async def test_``
is auto-marked ``asyncio``. The CI **unit** lane runs ``-m "not integration and
not asyncio"`` — it therefore EXCLUDES every async test. The only lane that
collects async tests by mark is **integration** (``-m "integration or
asyncio"``), but it is gated to a ``test-path`` glob. If that glob does not match
a file, the file's async tests run in NO lane — exactly the silent gap that let
~64 files rot outside CI (fixed in the wire-orphaned-async-tests change).

The same class of gap exists for SYNC tests via file placement: every CI lane
addresses files through the non-recursive shell glob ``app/tests/test_*.py`` (or
explicit file lists), so a test file placed in a SUBDIRECTORY of ``app/tests``
or in the legacy ``backend/tests/`` sibling dir is silently skipped by every
lane — that hid 7 files (~73 tests) until the 2026-07 test audit moved them to
the top level.

These tests parse ``.github/workflows/ci.yml`` and assert:

1. every backend test file containing an async test is matched by the
   integration lane's ``test-path`` (or the smoke explicit file list), and
2. every backend test file — sync or async, at ANY depth under ``app/tests``
   or the legacy ``backend/tests/`` location — is matched by at least one
   lane's ``test-path``.

They fail the moment someone adds a test file the lane globs can't reach, or
narrows those globs again. Keep test files DIRECTLY in ``app/tests/`` (no
subdirectories) unless you also widen the CI lane globs.
"""

import ast
import fnmatch
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[3]
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _file_has_async_test(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return False
    return any(isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("test_") for node in ast.walk(tree))


def _lane_paths() -> list[str]:
    """All test-path globs/files across every CI backend-test lane."""
    doc = yaml.safe_load(CI_YML.read_text(encoding="utf-8"))
    includes = doc["jobs"]["backend-tests"]["strategy"]["matrix"]["include"]
    paths: list[str] = []
    for entry in includes:
        tp = entry.get("test-path")
        if tp:
            paths.extend(tp.split())
    return paths


def _all_backend_test_files() -> list[Path]:
    """Every test file a developer could plausibly add: app/tests recursively,
    plus the legacy backend/tests/ sibling dir (historically orphaned)."""
    files = sorted(TESTS_DIR.rglob("test_*.py"))
    legacy_dir = BACKEND_DIR / "tests"
    if legacy_dir.is_dir():
        files.extend(sorted(legacy_dir.rglob("test_*.py")))
    return files


def test_no_orphaned_async_test_files():
    if not CI_YML.exists():
        pytest.skip("ci.yml not found (not running from the repo checkout)")

    lane_paths = _lane_paths()
    assert lane_paths, "could not read any CI backend-test test-path globs from ci.yml"

    orphans = []
    for f in _all_backend_test_files():
        if not _file_has_async_test(f):
            continue
        rel = f.relative_to(BACKEND_DIR).as_posix()
        if not any(fnmatch.fnmatch(rel, glob) for glob in lane_paths):
            orphans.append(rel)

    assert not orphans, (
        "These files contain async tests but match NO CI lane test-path "
        f"({lane_paths}), so their async tests run in no CI lane (asyncio_mode=auto "
        "makes the unit lane's `not asyncio` exclude them). Widen the integration "
        f"lane test-path or add them to a lane: {orphans}"
    )


def test_no_test_files_outside_ci_lanes():
    """Sync counterpart: a test file in an app/tests SUBDIRECTORY or in the
    legacy backend/tests/ dir matches no lane glob and silently never runs in
    CI (7 files / ~73 tests rotted this way until 2026-07). Move new test
    files directly into app/tests/, or widen the lane globs."""
    if not CI_YML.exists():
        pytest.skip("ci.yml not found (not running from the repo checkout)")

    lane_paths = _lane_paths()
    assert lane_paths, "could not read any CI backend-test test-path globs from ci.yml"

    orphans = []
    for f in _all_backend_test_files():
        rel = f.relative_to(BACKEND_DIR).as_posix()
        if not any(fnmatch.fnmatch(rel, glob) for glob in lane_paths):
            orphans.append(rel)

    assert not orphans, (
        f"These test files match NO CI lane test-path ({lane_paths}) and therefore "
        "run in no CI lane at all. Move them directly under app/tests/ (the lane "
        f"globs are non-recursive) or add them to a lane: {orphans}"
    )

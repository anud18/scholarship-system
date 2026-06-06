"""CI invariant: no test file's async tests may run in zero CI lanes.

Background
---------
`backend/pytest.ini` sets ``asyncio_mode = auto``, so every ``async def test_``
is auto-marked ``asyncio``. The CI **unit** lane runs ``-m "not integration and
not asyncio"`` — it therefore EXCLUDES every async test. The only lane that
collects async tests by mark is **integration** (``-m "integration or
asyncio"``), but it is gated to a ``test-path`` glob. If that glob does not match
a file, the file's async tests run in NO lane — exactly the silent gap that let
~64 files rot outside CI (fixed in the wire-orphaned-async-tests change).

This test parses ``.github/workflows/ci.yml`` and asserts every backend test
file that contains an async test is matched by the integration lane's
``test-path`` (or the smoke / critical-workflows explicit file lists). It fails
the moment someone adds an async test file the integration glob can't reach, or
narrows that glob again.
"""

import ast
import fnmatch
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

TESTS_DIR = Path(__file__).resolve().parent
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


def test_no_orphaned_async_test_files():
    if not CI_YML.exists():
        pytest.skip("ci.yml not found (not running from the repo checkout)")

    lane_paths = _lane_paths()
    assert lane_paths, "could not read any CI backend-test test-path globs from ci.yml"

    orphans = []
    for f in sorted(TESTS_DIR.glob("test_*.py")):
        if not _file_has_async_test(f):
            continue
        rel = f"app/tests/{f.name}"
        if not any(fnmatch.fnmatch(rel, glob) for glob in lane_paths):
            orphans.append(f.name)

    assert not orphans, (
        "These files contain async tests but match NO CI lane test-path "
        f"({lane_paths}), so their async tests run in no CI lane (asyncio_mode=auto "
        "makes the unit lane's `not asyncio` exclude them). Widen the integration "
        f"lane test-path or add them to a lane: {orphans}"
    )

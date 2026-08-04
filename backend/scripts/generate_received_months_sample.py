#!/usr/bin/env python3
"""Regenerate docs/samples/received-months-example.xlsx.

The file is the same workbook the 「下載範例」 button serves — both come from
``build_received_months_template()``, so the checked-in copy can never drift
from what admins actually download.

    python3 backend/scripts/generate_received_months_sample.py
"""

import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

# `app.services.__init__` imports the whole service graph, which needs a fully
# configured Settings (DB URLs, MinIO keys...). This script only builds a
# workbook, so pre-register `app` / `app.services` as bare package objects: an
# entry already in sys.modules means Python resolves the submodules below
# without ever executing those __init__ files.
for _name, _path in (("app", BACKEND_ROOT / "app"), ("app.services", BACKEND_ROOT / "app" / "services")):
    if _name not in sys.modules:
        _module = ModuleType(_name)
        _module.__path__ = [str(_path)]
        sys.modules[_name] = _module

from app.services.received_months_template import build_received_months_template  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "docs" / "samples" / "received-months-example.xlsx"


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(build_received_months_template())
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

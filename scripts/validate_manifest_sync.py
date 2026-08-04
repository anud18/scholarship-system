#!/usr/bin/env python3
"""Guard against drift between a service's pyproject.toml and its requirements.txt.

Both backend/ and mock-student-api/ declare their runtime dependencies twice:

  - ``requirements.txt``  — what CI installs, tests and audits
  - ``pyproject.toml``    — what the Dockerfile installs (``uv pip install -r pyproject.toml``)

Nothing kept the two in sync, so ``pyproject.toml`` silently fell ~10 packages
behind and the shipped images ran vulnerable pins (starlette, pillow, PyJWT,
python-multipart, cryptography) while CI stayed green against the patched
``requirements.txt``. Dependabot flagged only the pyproject side, which is easy
to miss when auditing the requirements files alone.

This script fails when the two manifests disagree, so the drift cannot come
back. Run it locally with::

    python3 scripts/validate_manifest_sync.py

Exit code is 0 when every service agrees, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# (service directory, pyproject path, requirements path)
SERVICES = [
    ("backend", "backend/pyproject.toml", "backend/requirements.txt"),
    ("mock-student-api", "mock-student-api/pyproject.toml", "mock-student-api/requirements.txt"),
]


def canonical_name(spec: str) -> str:
    """Return the PEP 503 normalized project name from a requirement spec."""
    name = re.split(r"[\[=<>!~;]", spec, maxsplit=1)[0]
    return re.sub(r"[-_.]+", "-", name.strip()).lower()


def parse_pyproject(path: Path) -> dict[str, list[str]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("dependencies", [])
    grouped: dict[str, list[str]] = {}
    for dep in deps:
        grouped.setdefault(canonical_name(dep), []).append(dep.strip())
    return grouped


def parse_requirements(path: Path) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        # Skip blanks and pip directives (-r includes, --index-url, ...).
        if not line or line.startswith("-"):
            continue
        grouped.setdefault(canonical_name(line), []).append(line)
    return grouped


def check_service(name: str, pyproject_rel: str, requirements_rel: str) -> list[str]:
    """Return a list of human-readable drift messages (empty when in sync)."""
    pyproject_path = REPO_ROOT / pyproject_rel
    requirements_path = REPO_ROOT / requirements_rel
    for path in (pyproject_path, requirements_path):
        if not path.is_file():
            return [f"{name}: missing manifest {path.relative_to(REPO_ROOT)}"]

    pyproject_deps = parse_pyproject(pyproject_path)
    requirements_deps = parse_requirements(requirements_path)

    problems = []
    for package in sorted(set(pyproject_deps) | set(requirements_deps)):
        in_pyproject = sorted(pyproject_deps.get(package, []))
        in_requirements = sorted(requirements_deps.get(package, []))
        if in_pyproject == in_requirements:
            continue
        problems.append(
            f"  {package}\n"
            f"    {pyproject_rel}: {', '.join(in_pyproject) or '(absent)'}\n"
            f"    {requirements_rel}: {', '.join(in_requirements) or '(absent)'}"
        )
    return problems


def main() -> int:
    failed = False
    for name, pyproject_rel, requirements_rel in SERVICES:
        problems = check_service(name, pyproject_rel, requirements_rel)
        if problems:
            failed = True
            print(f"❌ {name}: {pyproject_rel} and {requirements_rel} disagree:")
            print("\n".join(problems))
            print()
        else:
            print(f"✅ {name}: {pyproject_rel} matches {requirements_rel}")

    if failed:
        print(
            "Dependency manifests are out of sync. The Dockerfile installs from "
            "pyproject.toml while CI tests and audits requirements.txt, so drift "
            "ships untested and un-audited versions.\n"
            "Fix: update both files to the same pins."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

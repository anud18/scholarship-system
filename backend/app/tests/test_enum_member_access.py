"""AST invariant: never reference an enum member that does not exist.

`.claude/CLAUDE.md` §4 requires Python enum member names to be **lowercase**,
matching the PostgreSQL values exactly. Writing the TypeScript spelling
(`NotificationPriority.URGENT`) is an easy slip, and Python only notices at
runtime — the attribute lookup raises AttributeError the moment that branch
executes.

`notifications.py` shipped exactly that: `NotificationPriority.URGENT.value`
where the member is `urgent`. Every call to the endpoint 500'd, and the ZAP
active scan hit it 17 times.

This walks the AST rather than importing, so it stays fast and has no
side effects. It only checks attribute access on a bare `Name` that matches a
known enum class, which keeps it conservative: aliased or dynamically-resolved
enums are simply not checked rather than guessed at.
"""

import ast
import pathlib

APP_ROOT = pathlib.Path(__file__).resolve().parents[1]

# Attributes every Enum exposes, plus the ones our code adds by convention.
_ENUM_BUILTINS = {
    "value",
    "name",
    "_name_",
    "_value_",
    "__members__",
    "__class__",
    "__doc__",
    "mro",
}


def _collect_enum_definitions():
    """Map enum class name -> set of legal attribute names."""
    enums: dict[str, set[str]] = {}

    for path in APP_ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue

            base_names = set()
            for base in node.bases:
                base_names.add(getattr(base, "id", None) or getattr(base, "attr", None))
            if not base_names & {"Enum", "IntEnum", "StrEnum"}:
                continue

            legal = set(_ENUM_BUILTINS)
            for stmt in node.body:
                # Members: `low = "low"`
                if isinstance(stmt, ast.Assign):
                    for target in stmt.targets:
                        if isinstance(target, ast.Name):
                            legal.add(target.id)
                elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    legal.add(stmt.target.id)
                # Methods and classmethods are legal attributes too.
                elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    legal.add(stmt.name)

            # A name defined twice (rare) should accept either member set.
            enums.setdefault(node.name, set()).update(legal)

    return enums


def _find_bad_accesses(enums):
    violations = []

    for path in APP_ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute):
                continue
            if not isinstance(node.value, ast.Name):
                continue

            enum_name = node.value.id
            if enum_name not in enums:
                continue
            if node.attr in enums[enum_name]:
                continue

            violations.append(
                f"{path.relative_to(APP_ROOT.parent)}:{node.lineno} "
                f"{enum_name}.{node.attr} does not exist. "
                f"Members are lowercase (CLAUDE.md §4); did you mean "
                f"{enum_name}.{node.attr.lower()}?"
            )

    return violations


def test_no_reference_to_a_nonexistent_enum_member():
    enums = _collect_enum_definitions()
    assert enums, "found no enum definitions - the collector is broken"

    violations = _find_bad_accesses(enums)
    assert not violations, "nonexistent enum member referenced:\n" + "\n".join(violations)

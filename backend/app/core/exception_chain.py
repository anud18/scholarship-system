"""Walk an exception's `__cause__`/`__context__` chain safely.

Shared by the DB-error mapping and the HTTP exception handler, both of which
need to look past a wrapper exception to find what actually went wrong.

Two hazards this exists to contain:
  * `__context__` chains can be cyclic when an exception is raised while
    handling itself, so the walk is identity-guarded.
  * Chains can be arbitrarily deep, so the walk is depth-capped.
"""

from __future__ import annotations

from typing import Iterator, Optional

# Deeper than this and we are almost certainly in a pathological chain; the
# useful cause is always near the top in this codebase.
DEFAULT_MAX_DEPTH = 10


def iter_cause_chain(
    exc: Optional[BaseException],
    max_depth: int = DEFAULT_MAX_DEPTH,
    include_self: bool = True,
) -> Iterator[BaseException]:
    """Yield `exc` and its causes, outermost first.

    `__cause__` (an explicit `raise ... from exc`) is preferred over
    `__context__` (the implicit "raised while handling" link).
    """
    seen: set[int] = set()
    current = exc

    if not include_self and current is not None:
        seen.add(id(current))
        current = current.__cause__ or current.__context__

    for _ in range(max_depth):
        if current is None or id(current) in seen:
            return
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__

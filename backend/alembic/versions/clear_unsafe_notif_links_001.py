"""Clear notification links that are not a site path or an http(s) URL

notifications.action_url / href are navigated to when a recipient clicks a
notification. Until app/core/url_safety.validate_action_url was enforced, an
admin could store `javascript:` / `data:` values (stored XSS; the 2026-10
ZAP active scan left such payloads behind). New writes are now rejected; this
removes what is already stored so no client ever receives it again, and so
announcements carrying a legacy value stay editable.

The SQL mirrors validate_action_url: after trimming, a value survives only if
it has no control characters and is either a path starting with a single "/"
(no backslash) or an http(s) URL with a host. Everything else becomes NULL.

Revision ID: clear_unsafe_notif_links_001
Revises: college_ranking_multi_draft_001
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "clear_unsafe_notif_links_001"
down_revision: Union[str, None] = "college_ranking_multi_draft_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LINK_COLUMNS = ("action_url", "href")


def _is_safe_sql(column: str) -> str:
    value = f"btrim({column})"
    return (
        f"({value} !~ '[[:cntrl:]]' AND ("
        f"({value} ~ '^/' AND {value} !~ '^//' AND strpos({value}, E'\\\\') = 0)"
        f" OR {value} ~* '^https?://[^/?#]'"
        f"))"
    )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "notifications" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("notifications")}
    for column in LINK_COLUMNS:
        if column not in existing:
            continue
        op.execute(
            f"UPDATE notifications SET {column} = NULL " f"WHERE {column} IS NOT NULL AND NOT {_is_safe_sql(column)}"
        )


def downgrade() -> None:
    # Irreversible data cleanup: the cleared values were unsafe and are not restored.
    pass

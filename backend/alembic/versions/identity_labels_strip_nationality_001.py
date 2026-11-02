"""strip the 目前有中華民國國籍生 parenthetical from std_identity 3/4 labels

Revision ID: identity_labels_strip_nat_001
Revises: blank_user_email_to_null_001
Create Date: 2026-11-02 00:00:00.000000

identities.name is rendered verbatim in the UI and exports. Ids 3 and 4 carried
a "(目前有中華民國國籍生)" suffix; the display labels are now just 僑生 / 外籍生.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "identity_labels_strip_nat_001"
down_revision: Union[str, Sequence[str], None] = "blank_user_email_to_null_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_NAMES = ((3, "僑生"), (4, "外籍生"))


def upgrade() -> None:
    # Match on id only so variant spellings of the old label are renamed too.
    for id_, name in _NEW_NAMES:
        op.execute(f"UPDATE identities SET name = '{name}' WHERE id = {id_}")


def downgrade() -> None:
    # Intentionally a no-op: fresh databases are seeded with the short names
    # (see 6d5b1940bf8a), so there is no prior label state to restore.
    pass

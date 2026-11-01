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

_OLD_NEW = (
    (3, "僑生(目前有中華民國國籍生)", "僑生"),
    (4, "外籍生(目前有中華民國國籍生)", "外籍生"),
)


def _rename(id_: int, old: str, new: str) -> None:
    op.execute(f"UPDATE identities SET name = '{new}' WHERE id = {id_} AND name = '{old}'")


def upgrade() -> None:
    for id_, old, new in _OLD_NEW:
        _rename(id_, old, new)


def downgrade() -> None:
    for id_, old, new in _OLD_NEW:
        _rename(id_, new, old)

"""Store NULL instead of '' for users without an email

Revision ID: blank_user_email_to_null_001
Revises: app_file_source_object_001
Create Date: 2026-10-16 00:00:00.000000

NYCU Portal sends `mail: ""` for accounts without a registered address, and SSO used
to store that as `users.email = ''`. EmailStr rejects '' when the user is serialized,
so those accounts could not log in and an admin could not save a role for them.
SSO now stores NULL; this clears the rows older logins left behind.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "blank_user_email_to_null_001"
down_revision: Union[str, None] = "app_file_source_object_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if "users" not in sa.inspect(bind).get_table_names():
        return
    bind.execute(sa.text("UPDATE users SET email = NULL WHERE email IS NOT NULL AND btrim(email) = ''"))


def downgrade() -> None:
    # '' carried no information, so there is nothing to restore.
    pass

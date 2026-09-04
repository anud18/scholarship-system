"""add section to footer_links (相關連結 vs 底部政策列)

The footer's bottom bar (隱私權政策 / 使用條款 / 無障礙聲明 / 網站地圖) was
hardcoded as four ``href="#"`` anchors. It now shares the admin-editable
``footer_links`` table with 相關連結, split by a new ``section`` column.

The four names are seeded as *hidden* ``policy`` rows so an admin only has to
set a real URL (or replace with an upload) and toggle them visible; visitors
never see the placeholder URL. Nothing is seeded when policy rows already
exist.

IMPORTANT: migration 59b65a4de996 runs ``Base.metadata.create_all()``, so on a
fresh database the column already exists by the time this runs. Each step is
guarded individually — an early ``return`` would skip the seed.

Revision ID: add_footer_link_section_001
Revises: professor_notify_both_emails_001
Create Date: 2026-09-03

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "add_footer_link_section_001"
down_revision = "professor_notify_both_emails_001"
branch_labels = None
depends_on = None

_ENUM_NAME = "footerlinksection"
_ENUM_VALUES = ("related", "policy")
_INDEX_NAME = "ix_footer_links_section"

# Hidden placeholders: the admin sets the real target before showing them.
_PLACEHOLDER_URL = "https://www.nycu.edu.tw"
_SEED_POLICY_LINKS = [
    ("隱私權政策", "Privacy Policy", 0),
    ("使用條款", "Terms of Use", 1),
    ("無障礙聲明", "Accessibility", 2),
    ("網站地圖", "Sitemap", 3),
]

_footer_links_table = sa.table(
    "footer_links",
    sa.column("title_zh", sa.String),
    sa.column("title_en", sa.String),
    sa.column("link_type", sa.String),
    sa.column("section", sa.String),
    sa.column("url", sa.String),
    sa.column("sort_order", sa.Integer),
    sa.column("is_active", sa.Boolean),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "footer_links" not in inspector.get_table_names():
        # Table is created by add_footer_links_001; nothing to do on a DB
        # that somehow lacks it.
        return

    # --- 1. Enum type -------------------------------------------------------
    section_enum = postgresql.ENUM(*_ENUM_VALUES, name=_ENUM_NAME)
    section_enum.create(bind, checkfirst=True)

    # --- 2. Column ------------------------------------------------------------
    columns = {c["name"] for c in inspector.get_columns("footer_links")}
    if "section" not in columns:
        op.add_column(
            "footer_links",
            sa.Column(
                "section",
                sa.Enum(*_ENUM_VALUES, name=_ENUM_NAME, create_type=False),
                nullable=False,
                server_default="related",
            ),
        )
        inspector = sa.inspect(bind)

    # --- 3. Index ---------------------------------------------------------------
    indexes = {i["name"] for i in inspector.get_indexes("footer_links")}
    if _INDEX_NAME not in indexes:
        op.create_index(_INDEX_NAME, "footer_links", ["section"])

    # --- 4. Seed the hidden policy placeholders (only when none exist) ----
    has_policy = bind.execute(sa.text("SELECT 1 FROM footer_links WHERE section = 'policy' LIMIT 1")).scalar()
    if not has_policy:
        op.bulk_insert(
            _footer_links_table,
            [
                {
                    "title_zh": title_zh,
                    "title_en": title_en,
                    "link_type": "url",
                    "section": "policy",
                    "url": _PLACEHOLDER_URL,
                    "sort_order": sort_order,
                    "is_active": False,
                }
                for title_zh, title_en, sort_order in _SEED_POLICY_LINKS
            ],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "footer_links" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("footer_links")}
        if "section" in columns:
            op.execute(sa.text("DELETE FROM footer_links WHERE section = 'policy'"))
            op.drop_index(_INDEX_NAME, table_name="footer_links", if_exists=True)
            op.drop_column("footer_links", "section")

    sa.Enum(name=_ENUM_NAME).drop(bind, checkfirst=True)

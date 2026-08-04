"""add footer_links table (admin-editable 相關連結)

Seeds the three real links that were previously hardcoded in
frontend/components/footer.tsx so the footer renders identically after
this migration. The three placeholder entries in that component pointed at
href="#" (獎學金申請指南 / 常見問題 / 系統操作手冊) and are intentionally NOT
seeded — they were dead links; an admin now adds them with a real URL or an
uploaded PDF.

IMPORTANT: migration 59b65a4de996 runs ``Base.metadata.create_all()``, so on a
fresh database ``footer_links`` already exists (with the model's constraint)
by the time this migration runs. Each step below is therefore guarded
individually — an early ``return`` on "table exists" would silently skip the
seed rows on every fresh install.

Revision ID: add_footer_links_001
Revises: roster_counts_included_001
Create Date: 2026-07-29

"""

import sqlalchemy as sa
from alembic import op

revision = "add_footer_links_001"
down_revision = "roster_counts_included_001"
branch_labels = None
depends_on = None


_CHECK_NAME = "ck_footer_links_payload_matches_type"
_CHECK_SQL = (
    "(link_type = 'url' AND url IS NOT NULL AND object_name IS NULL) "
    "OR (link_type = 'file' AND object_name IS NOT NULL AND url IS NULL)"
)

_SEED_LINKS = [
    ("陽明交大首頁", "NYCU Homepage", "https://www.nycu.edu.tw", 0),
    ("教務處", "Academic Affairs", "https://aa.nycu.edu.tw/", 1),
    ("NYCU Portal", "NYCU Portal", "https://portal.nycu.edu.tw", 2),
]

_footer_links_table = sa.table(
    "footer_links",
    sa.column("title_zh", sa.String),
    sa.column("title_en", sa.String),
    sa.column("link_type", sa.String),
    sa.column("url", sa.String),
    sa.column("sort_order", sa.Integer),
    sa.column("is_active", sa.Boolean),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- 1. Table (skipped when create_all already built it) ---------------
    if "footer_links" not in inspector.get_table_names():
        link_type_enum = sa.Enum("url", "file", name="footerlinktype", create_type=True)

        op.create_table(
            "footer_links",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title_zh", sa.String(length=200), nullable=False),
            sa.Column("title_en", sa.String(length=200), nullable=True),
            sa.Column("link_type", link_type_enum, nullable=False, server_default="url"),
            sa.Column("url", sa.String(length=1000), nullable=True),
            sa.Column("object_name", sa.String(length=500), nullable=True),
            sa.Column("original_filename", sa.String(length=500), nullable=True),
            sa.Column("content_type", sa.String(length=100), nullable=True),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.CheckConstraint(_CHECK_SQL, name=_CHECK_NAME),
        )
        # Use the names SQLAlchemy's own ``index=True`` would generate, so a
        # migration-built DB and a create_all-built DB agree. Otherwise
        # `alembic revision --autogenerate` later emits spurious drop/create
        # index pairs, and a follow-up migration written against one name
        # fails on databases built via the other path.
        op.create_index("ix_footer_links_id", "footer_links", ["id"])
        op.create_index("ix_footer_links_sort_order", "footer_links", ["sort_order"])
        inspector = sa.inspect(bind)

    # --- 2. CHECK constraint (for DBs predating the model constraint) ------
    existing_checks = {c["name"] for c in inspector.get_check_constraints("footer_links")}
    if _CHECK_NAME not in existing_checks:
        op.create_check_constraint(_CHECK_NAME, "footer_links", sa.text(_CHECK_SQL))

    # --- 3. Seed the previously hardcoded links (only when empty) ----------
    already_seeded = bind.execute(sa.text("SELECT 1 FROM footer_links LIMIT 1")).scalar()
    if not already_seeded:
        op.bulk_insert(
            _footer_links_table,
            [
                {
                    "title_zh": title_zh,
                    "title_en": title_en,
                    "link_type": "url",
                    "url": url,
                    "sort_order": sort_order,
                    "is_active": True,
                }
                for title_zh, title_en, url, sort_order in _SEED_LINKS
            ],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "footer_links" in inspector.get_table_names():
        op.drop_index("ix_footer_links_sort_order", table_name="footer_links", if_exists=True)
        op.drop_index("ix_footer_links_id", table_name="footer_links", if_exists=True)
        op.drop_table("footer_links")

    sa.Enum(name="footerlinktype").drop(bind, checkfirst=True)

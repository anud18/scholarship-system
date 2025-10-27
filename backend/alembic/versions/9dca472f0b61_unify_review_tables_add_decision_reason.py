"""unify_review_tables_add_decision_reason

統一審查表架構：
- 合併 ProfessorReview, CollegeReview, ApplicationReview 為單一 ApplicationReview 表
- 新增 ApplicationReviewItem 表儲存子項目審查
- 新增 Application.decision_reason 欄位
- 遷移舊資料到新表

Revision ID: 9dca472f0b61
Revises: 2e6c27484cb1
Create Date: 2025-10-27 17:44:55.938577

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9dca472f0b61"
down_revision: Union[str, None] = "2e6c27484cb1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    統一審查表架構
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # Step 1: Drop old indices and rename old application_reviews table if it exists
    if "application_reviews" in existing_tables:
        # Drop indices first before renaming table
        conn = op.get_bind()
        conn.execute(sa.text("DROP INDEX IF EXISTS ix_application_reviews_id"))
        conn.execute(sa.text("DROP INDEX IF EXISTS ix_application_reviews_application_id"))
        conn.execute(sa.text("DROP INDEX IF EXISTS ix_application_reviews_reviewer_id"))
        op.rename_table("application_reviews", "application_reviews_old")
        # Update existing_tables list after rename
        existing_tables = [t for t in existing_tables if t != "application_reviews"]
        existing_tables.append("application_reviews_old")

    # Step 2: Create new application_reviews table with unified structure
    if "application_reviews" not in existing_tables:
        op.create_table(
            "application_reviews",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("application_id", sa.Integer(), nullable=False),
            sa.Column("reviewer_id", sa.Integer(), nullable=False),
            sa.Column("recommendation", sa.String(length=20), nullable=False),
            sa.Column("comments", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(
                ["application_id"],
                ["applications.id"],
            ),
            sa.ForeignKeyConstraint(
                ["reviewer_id"],
                ["users.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )

        # Create indices
        op.create_index(op.f("ix_application_reviews_id"), "application_reviews", ["id"], unique=False)
        op.create_index(
            op.f("ix_application_reviews_application_id"), "application_reviews", ["application_id"], unique=False
        )
        op.create_index(
            op.f("ix_application_reviews_reviewer_id"), "application_reviews", ["reviewer_id"], unique=False
        )
    else:
        print("  ⏭️  application_reviews table already exists, skipping creation")

    # Step 3: Create application_review_items table
    if "application_review_items" not in existing_tables:
        op.create_table(
            "application_review_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("review_id", sa.Integer(), nullable=False),
            sa.Column("sub_type_code", sa.String(length=50), nullable=False),
            sa.Column("recommendation", sa.String(length=20), nullable=False),
            sa.Column("comments", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["review_id"],
                ["application_reviews.id"],
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_application_review_items_id"), "application_review_items", ["id"], unique=False)
        op.create_index(
            op.f("ix_application_review_items_review_id"), "application_review_items", ["review_id"], unique=False
        )
        op.create_index(
            op.f("ix_application_review_items_sub_type_code"),
            "application_review_items",
            ["sub_type_code"],
            unique=False,
        )
    else:
        print("  ⏭️  application_review_items table already exists, skipping creation")

    # Step 4: Add decision_reason column to applications table
    if "decision_reason" not in [col["name"] for col in inspector.get_columns("applications")]:
        op.add_column("applications", sa.Column("decision_reason", sa.Text(), nullable=True))

    # Step 5: Migrate data from old tables to new unified tables

    # 5.1: Migrate from professor_reviews and professor_review_items
    if "professor_reviews" in existing_tables:
        conn = op.get_bind()

        # Get all professor reviews
        professor_reviews = conn.execute(
            sa.text(
                """
            SELECT id, application_id, professor_id, recommendation, reviewed_at, created_at
            FROM professor_reviews
        """
            )
        ).fetchall()

        for pr in professor_reviews:
            # Insert into new application_reviews
            result = conn.execute(
                sa.text(
                    """
                INSERT INTO application_reviews (application_id, reviewer_id, recommendation, comments, reviewed_at, created_at)
                VALUES (:app_id, :reviewer_id, 'pending', :comments, :reviewed_at, :created_at)
                RETURNING id
            """
                ),
                {
                    "app_id": pr.application_id,
                    "reviewer_id": pr.professor_id,
                    "comments": pr.recommendation or "",
                    "reviewed_at": pr.reviewed_at or pr.created_at,
                    "created_at": pr.created_at,
                },
            )
            new_review_id = result.scalar()

            # Get professor review items
            if "professor_review_items" in existing_tables:
                items = conn.execute(
                    sa.text(
                        """
                    SELECT sub_type_code, is_recommended, comments
                    FROM professor_review_items
                    WHERE review_id = :review_id
                """
                    ),
                    {"review_id": pr.id},
                ).fetchall()

                for item in items:
                    conn.execute(
                        sa.text(
                            """
                        INSERT INTO application_review_items (review_id, sub_type_code, recommendation, comments)
                        VALUES (:review_id, :sub_type_code, :recommendation, :comments)
                    """
                        ),
                        {
                            "review_id": new_review_id,
                            "sub_type_code": item.sub_type_code,
                            "recommendation": "approve" if item.is_recommended else "reject",
                            "comments": item.comments,
                        },
                    )

                # Calculate overall recommendation based on items
                approve_count = sum(1 for item in items if item.is_recommended)
                reject_count = sum(1 for item in items if not item.is_recommended)

                if approve_count == len(items):
                    overall_rec = "approve"
                elif reject_count == len(items):
                    overall_rec = "reject"
                else:
                    overall_rec = "partial_approve"

                conn.execute(
                    sa.text(
                        """
                    UPDATE application_reviews
                    SET recommendation = :recommendation
                    WHERE id = :review_id
                """
                    ),
                    {"recommendation": overall_rec, "review_id": new_review_id},
                )

    # 5.2: Migrate from college_review (if exists)
    if "college_review" in existing_tables:
        conn = op.get_bind()

        college_reviews = conn.execute(
            sa.text(
                """
            SELECT application_id, reviewer_id, review_comments, recommendation, reviewed_at, created_at
            FROM college_review
            WHERE reviewer_id IS NOT NULL
        """
            )
        ).fetchall()

        for cr in college_reviews:
            conn.execute(
                sa.text(
                    """
                INSERT INTO application_reviews (application_id, reviewer_id, recommendation, comments, reviewed_at, created_at)
                VALUES (:app_id, :reviewer_id, :recommendation, :comments, :reviewed_at, :created_at)
            """
                ),
                {
                    "app_id": cr.application_id,
                    "reviewer_id": cr.reviewer_id,
                    "recommendation": cr.recommendation or "pending",
                    "comments": cr.review_comments or "",
                    "reviewed_at": cr.reviewed_at or cr.created_at,
                    "created_at": cr.created_at,
                },
            )

    # Step 6: Drop old tables
    if "professor_review_items" in existing_tables:
        op.drop_table("professor_review_items")

    if "professor_reviews" in existing_tables:
        op.drop_table("professor_reviews")

    if "college_review" in existing_tables:
        op.drop_table("college_review")

    # Drop application_reviews_old with CASCADE to handle foreign key dependencies
    # This may exist from previous partial migration runs
    if "application_reviews_old" in existing_tables:
        conn = op.get_bind()
        conn.execute(sa.text("DROP TABLE IF EXISTS application_reviews_old CASCADE"))
        print("  ✓ Dropped application_reviews_old with CASCADE")


def downgrade() -> None:
    """
    Downgrade: Drop new tables and restore basic old structure
    Note: Data migration back is not implemented - data will be lost
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # Drop new tables
    if "application_review_items" in existing_tables:
        op.drop_table("application_review_items")

    if "application_reviews" in existing_tables:
        op.drop_table("application_reviews")

    # Remove decision_reason column
    if "decision_reason" in [col["name"] for col in inspector.get_columns("applications")]:
        op.drop_column("applications", "decision_reason")

    # Recreate basic old application_reviews table structure (without data)
    op.create_table(
        "application_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("reviewer_id", sa.Integer(), nullable=False),
        sa.Column("review_stage", sa.String(length=50), nullable=True),
        sa.Column("review_status", sa.String(length=20), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["application_id"],
            ["applications.id"],
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )

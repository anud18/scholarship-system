"""cleanup_old_applications

Revision ID: 06e8a66d9437
Revises: 7f1085a5bbe0
Create Date: 2025-10-23 10:02:44.400544

"""

import os
from typing import Sequence, Union

from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "06e8a66d9437"
down_revision: Union[str, None] = "7f1085a5bbe0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    清空所有舊的申請數據，為新格式做準備

    這個 migration 會刪除：
    - 所有申請記錄（applications）
    - 所有申請序號（application_sequences）
    - 所有相關的審核、排名、撥款資料

    保留：
    - 用戶帳號（users）
    - 獎學金類型和配置（scholarship_types, scholarship_configurations）
    - 參考數據（degrees, genders, departments 等）
    """
    # 使用 TRUNCATE CASCADE 來自動處理所有外鍵引用
    # 這會清空表並重置序列，同時自動處理外鍵約束

    # Get database connection
    connection = op.get_bind()

    # ------------------------------------------------------------------
    # Destructive-migration guard (issue #963 / audit gap G1).
    #
    # This revision irreversibly TRUNCATEs every application/review/payment
    # table. On a FRESH database (normal `alembic upgrade head` during
    # first-time setup) the tables are empty and the truncate is a no-op, so
    # the guard lets it through. But if it would destroy actual rows — e.g.
    # someone restores a production dump and replays migrations, or points
    # alembic at the wrong DATABASE_URL — refuse to run unless the operator
    # explicitly opts in with ALLOW_DESTRUCTIVE_MIGRATIONS=true.
    #
    # Note: we gate on data-at-risk rather than ENVIRONMENT because staging
    # also runs with ENVIRONMENT=production, and a fresh staging/dev rebuild
    # must not be blocked. 申請紀錄為應依保存年限留存之檔案（會計法 §83/84、
    # 檔案法銷毀核准程序）— 任何會銷毀它們的路徑都必須是顯式且可稽核的。
    # ------------------------------------------------------------------
    applications_exists = connection.execute(text("SELECT to_regclass('applications')")).scalar()
    existing_applications = 0
    if applications_exists:
        existing_applications = connection.execute(text("SELECT count(*) FROM applications")).scalar() or 0

    if existing_applications > 0 and os.getenv("ALLOW_DESTRUCTIVE_MIGRATIONS", "").lower() != "true":
        raise RuntimeError(
            f"Refusing to run destructive migration 06e8a66d9437: it would TRUNCATE "
            f"{existing_applications} existing application row(s) plus every review/ranking/"
            f"payment table, and downgrade() cannot restore them. If this is genuinely "
            f"intended (e.g. a sanctioned data reset), re-run with "
            f"ALLOW_DESTRUCTIVE_MIGRATIONS=true."
        )

    # 清空所有申請相關的表（使用 TRUNCATE 避免外鍵問題）
    tables_to_truncate = [
        "payment_roster_items",
        "roster_audit_logs",
        "payment_rosters",
        "college_ranking_items",
        "college_rankings",
        "college_reviews",
        "application_reviews",
        "professor_reviews",
        "application_files",
        "applications",
        "application_sequences",
    ]

    for table in tables_to_truncate:
        # Use savepoint to isolate each TRUNCATE operation
        # This prevents transaction abort if a table doesn't exist
        savepoint_name = f"truncate_{table}"
        try:
            connection.execute(text(f"SAVEPOINT {savepoint_name}"))
            connection.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
            connection.execute(text(f"RELEASE SAVEPOINT {savepoint_name}"))
            print(f"  ✓ Truncated {table}")
        except Exception as e:
            # Rollback to savepoint on error - keeps main transaction alive
            try:
                connection.execute(text(f"ROLLBACK TO SAVEPOINT {savepoint_name}"))
            except Exception:
                pass  # Savepoint might not exist if creation failed
            # 如果表不存在或其他錯誤，記錄但繼續
            print(f"  ⚠️  Could not truncate {table}: {e}")

    print("  ✅ Old applications and related data cleaned up successfully")


def downgrade() -> None:
    """
    無法恢復已刪除的數據
    """
    print("  ⚠️  Cannot restore deleted applications")
    pass

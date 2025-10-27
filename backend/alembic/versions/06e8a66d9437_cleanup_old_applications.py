"""cleanup_old_applications

Revision ID: 06e8a66d9437
Revises: 7f1085a5bbe0
Create Date: 2025-10-23 10:02:44.400544

"""
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

    # Get database connection
    connection = op.get_bind()

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

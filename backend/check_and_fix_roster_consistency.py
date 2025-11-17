#!/usr/bin/env python3
"""
檢查並修復造冊資料一致性
Check and fix roster data consistency
"""

import os
import sys
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, "/app")

# Database connection (使用同步引擎)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://scholarship_user:scholarship_pass@postgres:5432/scholarship_dev")
# 移除 async 相關的部分,使用純同步引擎
sync_url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://").replace(
    "postgresql://", "postgresql+psycopg2://"
)
engine = create_engine(sync_url)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def check_roster_consistency():
    """檢查造冊資料一致性"""
    db = SessionLocal()
    try:
        # 查詢不一致的造冊
        query = text(
            """
            SELECT
                pr.id,
                pr.roster_code,
                pr.status,
                pr.qualified_count,
                pr.disqualified_count,
                pr.total_amount,
                COUNT(pri.id) as actual_item_count,
                pr.excel_filename,
                pr.minio_object_name,
                pr.created_at,
                CASE
                    WHEN COUNT(pri.id) = 0 THEN '沒有明細資料'
                    WHEN COUNT(pri.id) != (pr.qualified_count + pr.disqualified_count) THEN '明細數量不一致'
                    WHEN pr.excel_filename IS NULL AND pr.minio_object_name IS NULL THEN '缺少 Excel 檔案'
                END as issue_type
            FROM payment_rosters pr
            LEFT JOIN payment_roster_items pri ON pr.id = pri.roster_id
            WHERE pr.status = 'completed'
            GROUP BY pr.id
            HAVING
                COUNT(pri.id) = 0
                OR COUNT(pri.id) != (pr.qualified_count + pr.disqualified_count)
                OR (pr.excel_filename IS NULL AND pr.minio_object_name IS NULL)
            ORDER BY pr.id DESC;
        """
        )

        result = db.execute(query)
        inconsistent_rosters = result.fetchall()

        if not inconsistent_rosters:
            print("✅ 沒有發現不一致的造冊資料")
            return []

        print(f"\n⚠️  發現 {len(inconsistent_rosters)} 個不一致的造冊:\n")
        print(f"{'ID':<5} {'造冊代碼':<30} {'狀態':<12} {'合格/不合格':<15} {'實際明細':<10} {'問題類型':<20}")
        print("=" * 110)

        inconsistent_list = []
        for row in inconsistent_rosters:
            print(
                f"{row.id:<5} {row.roster_code:<30} {row.status:<12} "
                f"{row.qualified_count}/{row.disqualified_count:<10} "
                f"{row.actual_item_count:<10} {row.issue_type:<20}"
            )
            inconsistent_list.append({"id": row.id, "roster_code": row.roster_code, "issue": row.issue_type})

        return inconsistent_list

    finally:
        db.close()


def fix_inconsistent_rosters(roster_ids: list):
    """修復不一致的造冊資料"""
    if not roster_ids:
        return

    db = SessionLocal()
    try:
        # 將不一致的造冊標記為 FAILED
        update_query = text(
            """
            UPDATE payment_rosters
            SET
                status = 'failed',
                notes = COALESCE(notes || E'\\n', '') || :note,
                updated_at = :updated_at
            WHERE id = ANY(:roster_ids)
            RETURNING id, roster_code;
        """
        )

        note = f"[{datetime.now(timezone.utc).isoformat()}] 數據一致性檢查失敗，已自動標記為 FAILED"

        result = db.execute(
            update_query, {"note": note, "updated_at": datetime.now(timezone.utc), "roster_ids": roster_ids}
        )

        updated = result.fetchall()
        db.commit()

        print(f"\n✅ 已將 {len(updated)} 個造冊標記為 FAILED:")
        for row in updated:
            print(f"   - ID {row.id}: {row.roster_code}")

        return updated

    except Exception as e:
        db.rollback()
        print(f"\n❌ 修復失敗: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 110)
    print("造冊資料一致性檢查與修復工具")
    print("=" * 110)

    # 檢查
    inconsistent = check_roster_consistency()

    if inconsistent:
        print("\n發現的問題:")
        for item in inconsistent:
            print(f"  - 造冊 ID {item['id']} ({item['roster_code']}): {item['issue']}")

        # 修復
        print(f"\n準備修復 {len(inconsistent)} 個不一致的造冊...")
        roster_ids = [item["id"] for item in inconsistent]
        fix_inconsistent_rosters(roster_ids)

        print("\n修復完成！這些造冊現在已標記為 FAILED 狀態，可以重新產生。")
    else:
        print("\n所有造冊資料一致性檢查通過！")

    print("\n" + "=" * 110)

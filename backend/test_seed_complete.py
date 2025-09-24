#!/usr/bin/env python3
"""
測試完整的 seed 流程
"""

import asyncio
import os
import sys

# Set test environment
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["TESTING"] = "true"

async def test_seed_complete():
    """測試完整的 seed 流程"""

    from sqlalchemy import text
    from app.core.init_db import initDatabase
    from app.db.session import AsyncSessionLocal

    print("🧪 測試完整 Seed 流程")
    print("=" * 60)

    # 初始化資料庫（使用舊的 init_db 來建立 schema）
    print("\n1️⃣ 初始化資料庫 schema...")
    from app.db.base import Base
    from app.db.session import async_engine

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    print("  ✓ Schema 已建立")

    # 執行 seed script
    print("\n2️⃣ 執行 Seed Script...")
    from app.seed import seed_development

    async with AsyncSessionLocal() as session:
        # 手動執行 seed 的各個部分（繞過 advisory lock）
        from app.seed import seed_lookup_tables, seed_test_users, seed_scholarships, seed_application_fields

        await seed_lookup_tables(session)
        await seed_test_users(session)
        await seed_scholarships(session)
        await seed_application_fields(session)

    # 驗證結果
    print("\n3️⃣ 驗證資料...")
    async with AsyncSessionLocal() as session:
        # 檢查 lookup tables
        result = await session.execute(text("SELECT COUNT(*) FROM degree"))
        degree_count = result.scalar()
        print(f"  ✓ Degrees: {degree_count}")

        result = await session.execute(text("SELECT COUNT(*) FROM department"))
        dept_count = result.scalar()
        print(f"  ✓ Departments: {dept_count}")

        # 檢查用戶
        result = await session.execute(text("SELECT COUNT(*) FROM users"))
        user_count = result.scalar()
        print(f"  ✓ Users: {user_count}")

        # 檢查獎學金
        result = await session.execute(text("SELECT COUNT(*) FROM scholarship_types"))
        scholarship_count = result.scalar()
        print(f"  ✓ Scholarship Types: {scholarship_count}")

        # 檢查應用欄位
        result = await session.execute(text("SELECT COUNT(*) FROM application_fields"))
        field_count = result.scalar()
        print(f"  ✓ Application Fields: {field_count}")

    print("\n" + "=" * 60)
    print("✅ Seed 流程測試完成！")
    print("\n📊 資料統計:")
    print(f"  - Degrees: {degree_count} (預期: 4)")
    print(f"  - Departments: {dept_count} (預期: 17)")
    print(f"  - Users: {user_count} (預期: 16)")
    print(f"  - Scholarship Types: {scholarship_count} (預期: 3)")
    print(f"  - Application Fields: {field_count} (預期: 2)")

    # 驗證預期值
    success = (
        degree_count == 4 and
        dept_count == 17 and
        user_count == 16 and
        scholarship_count == 3 and
        field_count == 2
    )

    if success:
        print("\n🎉 所有驗證通過！")
        return True
    else:
        print("\n❌ 部分驗證失敗，請檢查上述數據")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_seed_complete())
    sys.exit(0 if success else 1)
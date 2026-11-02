"""
系所代碼 → 名稱（departments 表）。

學籍快照的系所名稱以 API 1 的系所代碼（std_depno）對應這張表，見
``app.utils.application_helpers.get_department_name_from_data``。表很小且只由 seed / migration 異動，
所以整張表讀一次、在 Redis 留 1 小時，每個請求／匯出再把 dict 往下傳。
空的對照表不留在快取裡：重建資料庫或 seed 之前讀到的空表，不該讓所有系所名稱空白一小時。
"""

from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached, invalidate
from app.models.student import Department

DEPARTMENT_NAMES_TTL_SECONDS = 3600
DEPARTMENT_NAMES_CACHE_KEY = "refdata:department-names:v1"


@cached(key_fn=lambda *_, **__: DEPARTMENT_NAMES_CACHE_KEY, ttl=DEPARTMENT_NAMES_TTL_SECONDS)
async def _read_department_names(db: AsyncSession) -> Dict[str, str]:
    rows = await db.execute(select(Department.code, Department.name).where(Department.code.is_not(None)))
    return {code.strip(): name for code, name in rows.all()}


async def load_department_names(db: AsyncSession) -> Dict[str, str]:
    names = await _read_department_names(db)
    if not names:
        await invalidate(DEPARTMENT_NAMES_CACHE_KEY)
    return names

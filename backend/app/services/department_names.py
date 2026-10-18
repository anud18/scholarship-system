"""
系所代碼 → 名稱（departments 表）。

學籍快照的系所名稱以 API 1 的系所代碼（std_depno）對應這張表，見
``app.utils.application_helpers.get_department_name_from_data``。表很小且只由 seed / migration 異動，
所以整張表讀一次、在 Redis 留 1 小時，列表類頁面逐筆序列化也不會逐筆查詢。
"""

from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cached
from app.models.student import Department

DEPARTMENT_NAMES_TTL_SECONDS = 3600


@cached(key_fn=lambda *_, **__: "refdata:department-names:v1", ttl=DEPARTMENT_NAMES_TTL_SECONDS)
async def load_department_names(db: AsyncSession) -> Dict[str, str]:
    rows = await db.execute(select(Department.code, Department.name).where(Department.code.is_not(None)))
    return {code: name for code, name in rows.all()}

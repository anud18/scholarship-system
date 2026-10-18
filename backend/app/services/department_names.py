"""
系所代碼 → 名稱（departments 表）。

學籍快照的系所名稱以 API 1 的系所代碼（std_depno）對應這張表，見
``app.utils.application_helpers.get_department_name_from_data``。表很小（一次一個查詢），
每個請求／匯出讀一次後把 dict 往下傳；不快取，所以重建資料庫或 seed 之後不會讀到過時的空表。
"""

from typing import Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.student import Department


async def load_department_names(db: AsyncSession) -> Dict[str, str]:
    rows = await db.execute(select(Department.code, Department.name).where(Department.code.is_not(None)))
    return {code.strip(): name for code, name in rows.all()}

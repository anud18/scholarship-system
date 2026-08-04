"""
Admin cache management API endpoints.

Manual purge buttons for ops. The cache layer (`app.core.cache`) auto-
expires every entry, so this is a "I edited rows directly in psql, please
refresh" escape hatch — not the primary invalidation path. Normal write
paths invalidate themselves.
"""

import logging

from fastapi import APIRouter, Depends

from app.core.cache import invalidate
from app.core.security import require_admin
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/cache/nycu-employees/refresh")
async def refresh_nycu_employee_cache(current_user: User = Depends(require_admin)):
    """Drop the cached NYCU employee directory.

    The next /employees/all, /employees/search, or /employees/{no} call
    will re-paginate the upstream directory. Useful right after a known
    HR data change.
    """
    deleted = await invalidate("nycu:employees:")
    logger.info("admin cache flush: nycu:employees: by user=%s, deleted=%d", current_user.id, deleted)
    return {
        "success": True,
        "message": f"NYCU employee cache invalidated ({deleted} keys removed)",
        "data": {"deleted_keys": deleted},
    }

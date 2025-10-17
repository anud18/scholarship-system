"""
College Review API Routes

This package aggregates all college review endpoints:
- Application Review (申請審查)
- Ranking Management (排名管理)
- Distribution & Quotas (配額分配)
- Utilities & Statistics (工具與統計)

Note: The prefix "/college-review" is set in api.py, not here.
This allows the router to be flexible and reusable.
"""

from fastapi import APIRouter

from .application_review import router as application_router
from .distribution import router as distribution_router
from .ranking_management import router as ranking_router
from .utilities import router as utilities_router

# Create main router for college review (without prefix - it's set in api.py)
router = APIRouter(tags=["College Review"])

# Include all sub-routers with their respective tags
router.include_router(application_router, tags=["College Review - Applications"])
router.include_router(ranking_router, tags=["College Review - Rankings"])
router.include_router(distribution_router, tags=["College Review - Distribution"])
router.include_router(utilities_router, tags=["College Review - Utilities"])

__all__ = ["router"]

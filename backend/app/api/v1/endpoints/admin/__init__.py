"""
Admin API Routes (Modularized)

This package aggregates all admin endpoints organized by functionality:
- Dashboard & Statistics (儀表板與統計) - ✅ dashboard.py
- System Settings (系統設定) - ✅ system_settings.py
- Applications Management (申請管理) - ✅ applications.py
- Announcements Management (公告管理) - ✅ announcements.py
- Scholarships Management (獎學金管理) - ✅ scholarships.py
- Permissions Management (權限管理) - ✅ permissions.py
- Rules Management (規則管理) - ✅ rules.py
- Email Templates Management (郵件模板管理) - ✅ email_templates.py
- Configurations Management (配置管理) - ✅ configurations.py
- Professors Management (教授管理) - ✅ professors.py
- Bank Verification (銀行帳戶驗證) - ✅ bank_verification.py
- Students Management (學生管理) - ✅ students.py

Note: The prefix "/admin" is set in api.py, not here.

Migration Status: ✅ COMPLETE - All endpoints have been migrated to modular structure
"""

from fastapi import APIRouter

# Import all modularized routers (✅ All Completed)
from .announcements import router as announcements_router
from .applications import router as applications_router
from .bank_verification import router as bank_verification_router
from .configurations import router as configurations_router
from .dashboard import router as dashboard_router
from .email_templates import router as email_templates_router
from .permissions import router as permissions_router
from .professors import router as professors_router
from .rules import router as rules_router
from .scholarships import router as scholarships_router
from .students import router as students_router
from .system_settings import router as system_settings_router

# Create main router for admin (without prefix - it's set in api.py)
router = APIRouter(tags=["Admin"])

# ===== Include all modularized sub-routers (✅ All Migrated) =====
router.include_router(dashboard_router, tags=["Admin - Dashboard"])
router.include_router(system_settings_router, tags=["Admin - System Settings"])
router.include_router(applications_router, tags=["Admin - Applications"])
router.include_router(announcements_router, tags=["Admin - Announcements"])
router.include_router(scholarships_router, tags=["Admin - Scholarships"])
router.include_router(permissions_router, tags=["Admin - Permissions"])
router.include_router(rules_router, tags=["Admin - Rules"])
router.include_router(email_templates_router, tags=["Admin - Email Templates"])
router.include_router(configurations_router, tags=["Admin - Configurations"])
router.include_router(professors_router, tags=["Admin - Professors"])
router.include_router(bank_verification_router, tags=["Admin - Bank Verification"])
router.include_router(students_router, prefix="/students", tags=["Admin - Students"])

__all__ = ["router"]

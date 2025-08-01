"""
API v1 router aggregation
"""

from fastapi import APIRouter
from app.api.v1.endpoints import auth, applications, users, admin, scholarships, files, notifications, scholarship_management, quota_dashboard, application_fields

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(applications.router, prefix="/applications", tags=["Applications"])
api_router.include_router(admin.router, prefix="/admin", tags=["Administration"])
api_router.include_router(scholarships.router, prefix="/scholarships", tags=["Scholarships"])
api_router.include_router(scholarship_management.router, prefix="/scholarship-management", tags=["Scholarship Management"])
api_router.include_router(quota_dashboard.router, prefix="/quota-dashboard", tags=["Quota Dashboard"])
api_router.include_router(files.router, prefix="/files", tags=["Files"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(application_fields.router, prefix="/application-fields", tags=["Application Fields"]) 
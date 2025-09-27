"""
API v1 router aggregation
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    application_fields,
    applications,
    auth,
    college_review,
    email_management,
    files,
    notifications,
    nycu_employee,
    professor,
    quota_dashboard,
    reference_data,
    scholarship_configurations,
    scholarship_management,
    scholarship_rules,
    scholarships,
    user_profiles,
    users,
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(applications.router, prefix="/applications", tags=["Applications"])
api_router.include_router(admin.router, prefix="/admin", tags=["Administration"])
api_router.include_router(scholarships.router, prefix="/scholarships", tags=["Scholarships"])
api_router.include_router(
    scholarship_management.router,
    prefix="/scholarship-management",
    tags=["Scholarship Management"],
)
api_router.include_router(quota_dashboard.router, prefix="/quota-dashboard", tags=["Quota Dashboard"])
api_router.include_router(files.router, prefix="/files", tags=["Files"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(application_fields.router, prefix="/application-fields", tags=["Application Fields"])
api_router.include_router(
    scholarship_configurations.router,
    prefix="/scholarship-configurations",
    tags=["Scholarship Configurations"],
)
api_router.include_router(reference_data.router, prefix="/reference-data", tags=["Reference Data"])
api_router.include_router(user_profiles.router, prefix="/user-profiles", tags=["User Profiles"])
api_router.include_router(scholarship_rules.router, prefix="/scholarship-rules", tags=["Scholarship Rules"])
api_router.include_router(professor.router, prefix="/professor", tags=["Professor Review"])
api_router.include_router(college_review.router, prefix="/college", tags=["College Review"])
api_router.include_router(email_management.router, prefix="/email-management", tags=["Email Management"])
api_router.include_router(nycu_employee.router, prefix="/nycu-employee", tags=["NYCU Employee"])

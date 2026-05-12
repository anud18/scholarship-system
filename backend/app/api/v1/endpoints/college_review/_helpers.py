"""
Shared helper functions for college review endpoints
"""

import logging
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_field import ApplicationField, FieldType
from app.models.professor_student import ProfessorStudentRelationship
from app.models.scholarship import ScholarshipType
from app.models.user import AdminScholarship, User
from app.models.user_profile import UserProfile
from app.services.college_ranking_export_service import DynamicFieldSpec

logger = logging.getLogger(__name__)


def normalize_semester_value(value: Optional[Any]) -> Optional[str]:
    """Normalize semester representations (None/yearly/enum) to canonical values."""
    if value is None:
        return None

    candidate = value.value if hasattr(value, "value") else str(value).strip()
    candidate_lower = candidate.lower()

    if candidate_lower.startswith("semester."):
        candidate_lower = candidate_lower.split(".", 1)[1]

    if candidate_lower in {"", "none", "yearly"}:
        return None

    return candidate_lower


async def _check_scholarship_permission(user: User, scholarship_type_id: int, db: AsyncSession) -> bool:
    """
    Check if a user has permission to access a specific scholarship type.

    Returns True if:
    - User is super_admin or admin
    - User has explicit permission for this scholarship
    """
    if user.is_super_admin() or user.is_admin():
        return True

    # Check if scholarship type exists and is active
    scholarship_stmt = select(ScholarshipType).where(ScholarshipType.id == scholarship_type_id)
    scholarship_result = await db.execute(scholarship_stmt)
    scholarship = scholarship_result.scalar_one_or_none()

    if not scholarship or scholarship.status != "active":
        return False

    # For college users, check if they have explicit permission
    if user.is_college():
        permission_stmt = select(AdminScholarship).where(
            AdminScholarship.admin_id == user.id, AdminScholarship.scholarship_id == scholarship_type_id
        )
        permission_result = await db.execute(permission_stmt)
        return permission_result.scalar_one_or_none() is not None

    return False


async def _check_academic_year_permission(user: User, academic_year: int, db: AsyncSession) -> bool:
    """
    Check if a user has permission to access a specific academic year.

    Returns True if:
    - User is super_admin or admin
    - User has configurations for this academic year
    """
    from app.models.scholarship import ScholarshipConfiguration

    if user.is_super_admin() or user.is_admin():
        return True

    # For college users, check if they have any configuration for this year
    if user.is_college():
        # Get scholarship IDs that user has permission for
        scholarship_ids_stmt = select(AdminScholarship.scholarship_id).where(AdminScholarship.admin_id == user.id)
        scholarship_ids_result = await db.execute(scholarship_ids_stmt)
        scholarship_ids = [row[0] for row in scholarship_ids_result.fetchall()]

        if not scholarship_ids:
            return False

        # Check if there are active configurations for this year
        config_stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.scholarship_type_id.in_(scholarship_ids),
            ScholarshipConfiguration.academic_year == academic_year,
            ScholarshipConfiguration.is_active.is_(True),
        )
        config_result = await db.execute(config_stmt)
        return config_result.scalar_one_or_none() is not None

    return False


async def _check_application_review_permission(user: User, application_id: int, db: AsyncSession) -> bool:
    """
    Check if a user has permission to review a specific application.

    Returns True if:
    - User is super_admin or admin
    - User is college and has permission for the application's scholarship type
    """
    if user.is_super_admin() or user.is_admin():
        return True

    if not user.is_college():
        return False

    # Get the application and its scholarship type
    from app.models.application import Application

    app_stmt = select(Application).where(Application.id == application_id)
    app_result = await db.execute(app_stmt)
    application = app_result.scalar_one_or_none()

    if not application:
        return False

    # Check if user has permission for this scholarship type
    return await _check_scholarship_permission(user, application.scholarship_type_id, db)


async def load_export_aux_data(
    db: AsyncSession,
    *,
    scholarship_type,  # ScholarshipType ORM object or None
    applications: Iterable[Any],
) -> tuple[
    list[DynamicFieldSpec],
    dict[str, str],
    dict[int, str],
    dict[int, str],
]:
    """Bulk-load auxiliary data shared by the 學生資料彙整表 exports.

    Returns:
        (dynamic_fields, sub_type_labels, account_number_by_user, advisor_string_by_user)
    """

    # 1. Dynamic text fields flagged for export
    dynamic_fields: list[DynamicFieldSpec] = []
    scholarship_type_code = scholarship_type.code if scholarship_type else None
    if scholarship_type_code:
        df_stmt = (
            select(ApplicationField)
            .where(
                ApplicationField.scholarship_type == scholarship_type_code,
                ApplicationField.include_in_college_export.is_(True),
                ApplicationField.is_active.is_(True),
                ApplicationField.field_type == FieldType.TEXT.value,
            )
            .order_by(ApplicationField.display_order, ApplicationField.id)
        )
        rows = (await db.execute(df_stmt)).scalars().all()
        dynamic_fields = [
            DynamicFieldSpec(
                field_name=f.field_name,
                field_label=f.field_label,
                export_column_label=f.export_column_label,
                display_order=f.display_order or 0,
            )
            for f in rows
        ]

    # 2. Sub-type Chinese labels
    sub_type_labels: dict[str, str] = {}
    if scholarship_type:
        for cfg in getattr(scholarship_type, "sub_type_configs", []) or []:
            if cfg.sub_type_code and cfg.name:
                sub_type_labels[cfg.sub_type_code] = cfg.name

    # 3. Profile lookups (account_number, advisor_name fallback)
    user_ids: set[int] = set()
    for app in applications:
        if app is None:
            continue
        uid = getattr(app, "user_id", None)
        if uid is not None:
            user_ids.add(uid)

    account_number_by_user: dict[int, str] = {}
    advisor_name_by_user: dict[int, str] = {}

    if user_ids:
        profile_stmt = select(
            UserProfile.user_id, UserProfile.account_number, UserProfile.advisor_name
        ).where(UserProfile.user_id.in_(user_ids))
        for uid, acct, adv in (await db.execute(profile_stmt)).all():
            if acct:
                account_number_by_user[uid] = acct
            if adv:
                advisor_name_by_user[uid] = adv

    # 4. Advisor names from relationships
    advisor_names_by_user: dict[int, list[str]] = {uid: [] for uid in user_ids}
    if user_ids:
        from app.models.user import User  # local to avoid circular imports

        rel_stmt = (
            select(ProfessorStudentRelationship.student_id, User.name)
            .join(User, User.id == ProfessorStudentRelationship.professor_id)
            .where(
                ProfessorStudentRelationship.student_id.in_(user_ids),
                ProfessorStudentRelationship.is_active.is_(True),
                ProfessorStudentRelationship.relationship_type.in_(["advisor", "co_advisor"]),
            )
            .order_by(ProfessorStudentRelationship.student_id, User.name)
        )
        for student_id, prof_name in (await db.execute(rel_stmt)).all():
            if prof_name:
                advisor_names_by_user[student_id].append(prof_name)

    advisor_string_by_user: dict[int, str] = {}
    for uid in user_ids:
        names = advisor_names_by_user.get(uid) or []
        if names:
            advisor_string_by_user[uid] = "、".join(names)
        elif uid in advisor_name_by_user:
            advisor_string_by_user[uid] = advisor_name_by_user[uid]

    return dynamic_fields, sub_type_labels, account_number_by_user, advisor_string_by_user

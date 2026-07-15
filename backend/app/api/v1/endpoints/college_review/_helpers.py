"""
Shared helper functions for college review endpoints
"""

import logging
from collections import defaultdict
from typing import Any, Dict, Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application import Application
from app.models.application_field import ApplicationField, FieldType
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.professor_student import ProfessorStudentRelationship
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import AdminScholarship, User
from app.models.user_profile import UserProfile
from app.services.college_ranking_export_service import DynamicFieldSpec
from app.utils.application_helpers import (
    get_college_code_from_data,
    get_nycu_id_from_data,
    get_student_name_from_data,
)

logger = logging.getLogger(__name__)


def assert_can_manage_ranking(ranking: Any, user: User) -> None:
    """Authorize a college reviewer (or admin) to act on a specific ranking.

    Rankings are college-owned (issue #1034): every reviewer of the owning college
    — not only the original creator — may manage them, and admins/super_admins may
    manage any. This keeps the write/read-by-id paths consistent with create/list
    (already college-scoped) and blocks cross-college access. Authoritative source is
    the ranking's own college_code column (NULL = admin/global ranking).

    Raises HTTP 403 when the user is neither an admin nor a reviewer of the owning
    college.
    """
    if user.is_admin() or user.is_super_admin():
        return
    # Both codes must be present and non-empty to match — an empty/whitespace code is
    # not a valid college and must never satisfy the comparison (mirrors the defensive
    # `(... or "").strip()` checks in export-excel / supplementary-import).
    ranking_college = (getattr(ranking, "college_code", None) or "").strip()
    user_college = (getattr(user, "college_code", None) or "").strip()
    if ranking_college and user_college and ranking_college == user_college:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="只有該學院的審核員或管理員可以操作此排名",
    )


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
    profile_advisor_by_user: dict[int, str] = {}

    if user_ids:
        profile_stmt = select(UserProfile.user_id, UserProfile.account_number, UserProfile.advisor_name).where(
            UserProfile.user_id.in_(user_ids)
        )
        for uid, acct, adv in (await db.execute(profile_stmt)).all():
            if acct:
                account_number_by_user[uid] = acct
            if adv:
                profile_advisor_by_user[uid] = adv

    # 4. Advisor names from relationships
    advisor_names_by_user: dict[int, list[str]] = {uid: [] for uid in user_ids}
    if user_ids:
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
        elif uid in profile_advisor_by_user:
            advisor_string_by_user[uid] = profile_advisor_by_user[uid]

    return dynamic_fields, sub_type_labels, account_number_by_user, advisor_string_by_user


async def load_college_distribution_results(
    db: AsyncSession,
    *,
    current_user: User,
    scholarship_type_id: int,
    academic_year: int,
    semester: Optional[str] = None,
) -> Dict[str, Any]:
    """Load this college's own students' distribution outcomes, grouped by sub-type.

    Single source of truth for the college-facing distribution read: BOTH the JSON
    endpoint and the Excel/PDF export call this, so the two surfaces can never
    disagree about which students a college may see. Allocation outcome only — no
    payment PII, no allocation-year labels (outcomes for one sub-type are merged
    across years).

    Gate order is deliberate: permission before flag, so a college with no binding
    never learns the toggle's state.
    """
    college_code = current_user.college_code
    if not college_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="使用者未綁定學院")

    normalized_semester = normalize_semester_value(semester)

    config_stmt = select(ScholarshipConfiguration).where(
        and_(
            ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
            ScholarshipConfiguration.academic_year == academic_year,
            ScholarshipConfiguration.is_active.is_(True),
        )
    )
    if normalized_semester:
        config_stmt = config_stmt.where(ScholarshipConfiguration.semester == normalized_semester)
    else:
        config_stmt = config_stmt.where(ScholarshipConfiguration.semester.is_(None))
    config = (await db.execute(config_stmt)).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到對應的獎學金配置")

    if not config.allow_college_view_distribution:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="分發結果尚未開放查看")

    ranking_stmt = select(CollegeRanking).where(
        and_(
            CollegeRanking.scholarship_type_id == scholarship_type_id,
            CollegeRanking.academic_year == academic_year,
        )
    )
    if normalized_semester:
        ranking_stmt = ranking_stmt.where(CollegeRanking.semester == normalized_semester)
    else:
        ranking_stmt = ranking_stmt.where(CollegeRanking.semester.is_(None))
    rankings = (await db.execute(ranking_stmt)).scalars().all()
    ranking_ids = [r.id for r in rankings]
    ranking_sub_type = {r.id: r.sub_type_code for r in rankings}
    distribution_executed = any(r.distribution_executed for r in rankings)

    if not ranking_ids or not distribution_executed:
        return {"distribution_executed": distribution_executed, "sub_types": []}

    st_stmt = (
        select(ScholarshipType)
        .options(selectinload(ScholarshipType.sub_type_configs))
        .where(ScholarshipType.id == scholarship_type_id)
    )
    scholarship_type = (await db.execute(st_stmt)).scalar_one_or_none()
    label_map: Dict[str, Dict[str, str]] = {}
    if scholarship_type and getattr(scholarship_type, "sub_type_configs", None):
        for sc in scholarship_type.sub_type_configs:
            if sc.sub_type_code:
                label_map[sc.sub_type_code] = {
                    "label": sc.name or sc.sub_type_code,
                    "label_en": sc.name_en or sc.name or sc.sub_type_code,
                }

    items_stmt = (
        select(CollegeRankingItem)
        .options(
            selectinload(CollegeRankingItem.application).load_only(Application.student_data, Application.deleted_at)
        )
        .where(CollegeRankingItem.ranking_id.in_(ranking_ids))
    )
    items = (await db.execute(items_stmt)).scalars().all()

    groups: Dict[str, Dict[str, list]] = defaultdict(lambda: {"admitted": [], "backup": [], "rejected": []})

    for item in items:
        appn = item.application
        if not appn or not appn.student_data:
            continue
        if appn.deleted_at is not None:
            continue
        sd = appn.student_data
        # College scoping (Python-side; student_data is encrypted JSON, the academy
        # code is plaintext). Reuse the canonical accessor so key-alias changes stay
        # in one place.
        if get_college_code_from_data(sd) != college_code:
            continue
        student = {
            "student_number": get_nycu_id_from_data(sd) or "N/A",
            "student_name": get_student_name_from_data(sd),
            # 系所 name from the 申請當時 snapshot. There is no canonical accessor for
            # the department NAME (get_department_code_from_data returns the CODE), so
            # read trm_depname directly — the same key manual_distribution.py:492,
            # payment_rosters.py:1373 and college_ranking_export_service.py:292 use.
            "department": sd.get("trm_depname") or "",
        }
        fallback_code = ranking_sub_type.get(item.ranking_id) or "unallocated"

        handled = False
        if item.is_allocated and item.allocated_sub_type:
            groups[item.allocated_sub_type]["admitted"].append({**student, "rank_position": item.rank_position})
            handled = True
        if item.backup_allocations and isinstance(item.backup_allocations, list):
            for ba in item.backup_allocations:
                if not isinstance(ba, dict):
                    continue
                st_code = ba.get("sub_type")
                if not st_code:
                    continue
                groups[st_code]["backup"].append({**student, "backup_position": ba.get("backup_position")})
                handled = True
        if not handled:
            groups[fallback_code]["rejected"].append(student)

    sub_types = []
    for code in sorted(groups.keys()):
        m = label_map.get(code, {"label": code, "label_en": code})
        g = groups[code]
        sub_types.append(
            {
                "code": code,
                "label": m["label"],
                "label_en": m["label_en"],
                "admitted": sorted(g["admitted"], key=lambda s: s.get("rank_position") or 0),
                "backup": sorted(g["backup"], key=lambda s: s.get("backup_position") or 0),
                "rejected": g["rejected"],
            }
        )

    return {"distribution_executed": True, "sub_types": sub_types}

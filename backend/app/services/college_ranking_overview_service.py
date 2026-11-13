"""各學院排名繳交總覽 — which colleges have (not) handed in their ranking.

For one scholarship and period, every college that is expected to rank (it has
applications a ranking would contain) or that already holds a ranking gets one
row, with the status of its rankings and the last Excel import of each.

"已匯入" is derived from the audit log only: creating a ranking pre-fills its
items in a default order, so a draft existing proves nothing about an import.
Imports into drafts that 確認排名 later deleted are not attributed to the kept
ranking (the audit rows are keyed on the deleted ranking's id).
"""

from datetime import datetime
from typing import Any, Dict, Iterable, List, NamedTuple, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.college_mappings import get_college_name
from app.models.audit_log import AuditAction, AuditLog
from app.models.college_review import CollegeRanking
from app.models.enums import Semester
from app.models.student import Academy
from app.models.user import User
from app.services.college_review_service import CollegeReviewService

STATUS_NOT_CREATED = "not_created"  # 尚未建立排名
STATUS_DRAFT = "draft"  # 草稿（未匯入）
STATUS_DRAFT_IMPORTED = "draft_imported"  # 草稿已匯入
STATUS_FINALIZED = "finalized"  # 已確認

# Least to most complete: a college is only as far along as its least complete scope.
_STATUS_ORDER = (STATUS_NOT_CREATED, STATUS_DRAFT, STATUS_DRAFT_IMPORTED, STATUS_FINALIZED)

RANKING_AUDIT_RESOURCE_TYPE = "college_ranking"
# Row key of admin/super_admin global rankings (college_code NULL or "").
ADMIN_GLOBAL_COLLEGE_NAME = "全校（管理員建立）"
# Every sub-type: the widest set of applications any ranking of the period can contain.
_ALL_SUB_TYPES = "default"


class ImportRecord(NamedTuple):
    imported_at: Optional[datetime]
    actor_name: Optional[str]
    actor_nycu_id: Optional[str]


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _import_fields(record: Optional[ImportRecord]) -> Dict[str, Optional[str]]:
    if record is None:
        return {"last_import_at": None, "last_import_by": None}
    return {
        "last_import_at": _iso(record.imported_at),
        "last_import_by": record.actor_name or record.actor_nycu_id,
    }


def _least_complete(statuses: Iterable[str]) -> str:
    return min(statuses, key=_STATUS_ORDER.index)


def _scope_status(rankings: List[CollegeRanking], imports: Dict[int, ImportRecord]) -> str:
    """Status of one (college, sub-type) scope from its rankings."""
    if any(ranking.is_finalized for ranking in rankings):
        return STATUS_FINALIZED
    if any(ranking.id in imports for ranking in rankings):
        return STATUS_DRAFT_IMPORTED
    return STATUS_DRAFT


class CollegeRankingOverviewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def build_overview(
        self, *, scholarship_type_id: int, academic_year: int, semester: Optional[str]
    ) -> Dict[str, Any]:
        """Per-college ranking status of one scholarship period (``semester`` None = yearly)."""
        review_service = CollegeReviewService(self.db)
        applications = await review_service._eligible_applications(
            scholarship_type_id, _ALL_SUB_TYPES, academic_year, semester, None
        )
        # Same college field the per-college ranking filter reads (std_academyno).
        applicant_counts: Dict[str, int] = {}
        for application in applications:
            college_code = (application.student_data or {}).get("std_academyno")
            if college_code:
                applicant_counts[college_code] = applicant_counts.get(college_code, 0) + 1

        rankings = await self._load_rankings(review_service, scholarship_type_id, academic_year, semester)
        imports = await self._load_last_imports([ranking.id for ranking in rankings])
        user_names = await self._load_user_names(
            {user_id for ranking in rankings for user_id in (ranking.created_by, ranking.finalized_by) if user_id}
        )

        rankings_by_college: Dict[str, List[CollegeRanking]] = {}
        for ranking in rankings:
            rankings_by_college.setdefault(ranking.college_code or "", []).append(ranking)

        college_codes = sorted(set(applicant_counts) | set(rankings_by_college))
        college_names = await self._load_college_names(college_codes)

        colleges = [
            self._college_row(
                college_code=code,
                college_name=college_names.get(code) or code,
                applicant_count=applicant_counts.get(code, 0),
                rankings=rankings_by_college.get(code, []),
                imports=imports,
                user_names=user_names,
            )
            for code in college_codes
        ]
        summary = {status: sum(1 for row in colleges if row["status"] == status) for status in _STATUS_ORDER}
        return {"colleges": colleges, "summary": {**summary, "total": len(colleges)}}

    async def _load_rankings(
        self,
        review_service: CollegeReviewService,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
    ) -> List[CollegeRanking]:
        """Every college's rankings of the period; yearly matches NULL or 'yearly' as the scope does."""
        normalized_semester = review_service._normalize_semester_value(semester)
        if normalized_semester is None:
            semester_condition = or_(
                CollegeRanking.semester.is_(None), CollegeRanking.semester == Semester.yearly.value
            )
        else:
            semester_condition = CollegeRanking.semester == normalized_semester
        result = await self.db.execute(
            select(CollegeRanking)
            .where(
                and_(
                    CollegeRanking.scholarship_type_id == scholarship_type_id,
                    CollegeRanking.academic_year == academic_year,
                    semester_condition,
                )
            )
            .order_by(CollegeRanking.id)
        )
        return list(result.scalars().all())

    async def _load_last_imports(self, ranking_ids: List[int]) -> Dict[int, ImportRecord]:
        """Latest Excel import per ranking (rankings never imported are absent)."""
        if not ranking_ids:
            return {}
        actor = aliased(User)
        result = await self.db.execute(
            select(AuditLog.resource_id, AuditLog.created_at, actor.name, actor.nycu_id)
            .outerjoin(actor, actor.id == AuditLog.user_id)
            .where(
                AuditLog.resource_type == RANKING_AUDIT_RESOURCE_TYPE,
                AuditLog.action == AuditAction.import_.value,
                AuditLog.resource_id.in_([str(ranking_id) for ranking_id in ranking_ids]),
            )
            .order_by(AuditLog.created_at, AuditLog.id)
        )
        # Ascending order: a later row overwrites an earlier one, leaving the latest.
        return {
            int(resource_id): ImportRecord(imported_at=created_at, actor_name=name, actor_nycu_id=nycu_id)
            for resource_id, created_at, name, nycu_id in result.all()
        }

    async def _load_user_names(self, user_ids: Iterable[int]) -> Dict[int, str]:
        ids = list(user_ids)
        if not ids:
            return {}
        result = await self.db.execute(select(User.id, User.name, User.nycu_id).where(User.id.in_(ids)))
        return {user_id: name or nycu_id for user_id, name, nycu_id in result.all()}

    async def _load_college_names(self, college_codes: List[str]) -> Dict[str, str]:
        """學院代碼 → 名稱, academies table first, static map as the fallback."""
        real_codes = [code for code in college_codes if code]
        names: Dict[str, str] = {"": ADMIN_GLOBAL_COLLEGE_NAME}
        if not real_codes:
            return names
        result = await self.db.execute(select(Academy.code, Academy.name).where(Academy.code.in_(real_codes)))
        table_names = {code: name for code, name in result.all() if name}
        for code in real_codes:
            name = table_names.get(code) or get_college_name(code)
            if name:
                names[code] = name
        return names

    @staticmethod
    def _college_row(
        *,
        college_code: str,
        college_name: str,
        applicant_count: int,
        rankings: List[CollegeRanking],
        imports: Dict[int, ImportRecord],
        user_names: Dict[int, str],
    ) -> Dict[str, Any]:
        scopes: Dict[str, List[CollegeRanking]] = {}
        for ranking in rankings:
            scopes.setdefault(ranking.sub_type_code, []).append(ranking)
        status = (
            _least_complete(_scope_status(scope, imports) for scope in scopes.values())
            if scopes
            else STATUS_NOT_CREATED
        )

        ranking_imports = [imports[ranking.id] for ranking in rankings if ranking.id in imports]
        last_import = max(ranking_imports, key=lambda record: record.imported_at, default=None)

        return {
            "college_code": college_code,
            "college_name": college_name,
            "applicant_count": applicant_count,
            "status": status,
            **_import_fields(last_import),
            "rankings": [
                {
                    "id": ranking.id,
                    "ranking_name": ranking.ranking_name,
                    "sub_type_code": ranking.sub_type_code,
                    "is_finalized": bool(ranking.is_finalized),
                    "distribution_executed": bool(ranking.distribution_executed),
                    "total_applications": ranking.total_applications or 0,
                    "created_at": _iso(ranking.created_at),
                    "created_by": user_names.get(ranking.created_by),
                    "finalized_at": _iso(ranking.finalized_at),
                    "finalized_by": user_names.get(ranking.finalized_by),
                    **_import_fields(imports.get(ranking.id)),
                }
                for ranking in rankings
            ],
        }

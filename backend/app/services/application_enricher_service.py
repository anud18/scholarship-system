"""
Application Enricher Service

批量增強申請數據，包括：
- 並行獲取缺失的學生基本數據
- 並行獲取獎學金期間數據
- 格式化申請數據供前端使用

性能優化：
- 使用 asyncio.gather 並行處理 API 調用
- 避免 N+1 查詢問題
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.services.student_service import StudentService
from app.utils.application_helpers import (
    get_academy_code_from_data,
    get_department_code_from_data,
    get_nycu_id_from_data,
    get_student_name_from_data,
    get_term_count_from_data,
)
from app.utils.i18n import ScholarshipI18n

logger = logging.getLogger(__name__)

# Cap concurrent live SIS term lookups so a large list cannot flood the external API
MAX_CONCURRENT_PERIOD_LOOKUPS = 8

# Semester → SIS term code; yearly scholarships (None) accept either term
SEMESTER_TERM_CODES = {"first": "1", "second": "2"}


class ApplicationEnricherService:
    """批量增強申請數據服務"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.student_service = StudentService()

    async def enrich_applications_for_review(self, applications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量增強申請數據

        Args:
            applications: 原始申請數據列表

        Returns:
            增強後的申請數據列表
        """
        if not applications:
            return []

        logger.info(f"Enriching {len(applications)} applications...")

        # 步驟 1: 並行獲取缺失的學生基本數據
        await self._fetch_missing_student_data(applications)

        # 步驟 2: 並行獲取獎學金期間數據
        scholarship_period_map = await self._fetch_scholarship_period_data(applications)

        # 步驟 3: 格式化輸出
        formatted = self._format_applications(applications, scholarship_period_map)

        logger.info(f"Enrichment completed for {len(formatted)} applications")
        return formatted

    async def _fetch_missing_student_data(self, applications: List[Dict]) -> None:
        """
        並行獲取缺失的學生數據

        如果 student_data 缺失關鍵欄位，則從 API 獲取
        """
        tasks = []
        missing_indices = []

        for i, app in enumerate(applications):
            student_data = app.get("student_data", {}) if isinstance(app.get("student_data"), dict) else {}

            # 檢查是否缺失關鍵欄位
            if self._is_student_data_missing(student_data) and app.get("student_id"):
                tasks.append(self.student_service.get_student_basic_info(app["student_id"]))
                missing_indices.append(i)

        if not tasks:
            logger.debug("No missing student data to fetch")
            return

        logger.info(f"Found {len(tasks)} applications with missing student data, fetching in parallel...")

        # 並行執行所有 API 調用
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 更新成功獲取的數據
        success_count = 0
        for idx, result in zip(missing_indices, results):
            if isinstance(result, Exception):
                logger.warning(f"Failed to fetch student data for application {applications[idx].get('id')}: {result}")
                continue

            if result:
                applications[idx]["student_data"] = result
                success_count += 1

                # 可選：更新數據庫中的快照
                try:
                    app_stmt = select(Application).where(Application.id == applications[idx].get("id"))
                    app_result = await self.db.execute(app_stmt)
                    app_obj = app_result.scalar_one_or_none()

                    if app_obj:
                        app_obj.student_data = result
                        await self.db.commit()
                        logger.debug(f"Updated application {applications[idx].get('id')} with fetched student data")
                except Exception as db_err:
                    logger.warning(
                        f"Failed to update application {applications[idx].get('id')} with student data: {str(db_err)}"
                    )

        logger.info(f"Student data fetch completed: {success_count}/{len(tasks)} succeeded")

    def _is_student_data_missing(self, student_data: Dict) -> bool:
        """
        檢查學生數據是否缺失關鍵欄位

        Returns:
            True if missing critical fields
        """
        if not student_data:
            return True

        # 檢查是否缺少學號和姓名
        has_student_id = bool(
            student_data.get("nycu_id") or student_data.get("std_stdcode") or student_data.get("student_id")
        )
        has_name = bool(student_data.get("name") or student_data.get("std_cname") or student_data.get("student_name"))

        return not (has_student_id and has_name)

    async def _fetch_scholarship_period_data(self, applications: List[Dict]) -> Dict[int, Optional[Dict]]:
        """
        取得所有申請的獎學金期間數據

        優先使用 student_data 快照中的 trm_* 欄位（送件時已用同樣的學期規則抓取），
        只有快照缺少對應學期資料的申請才即時查詢 SIS，且限制並行數，
        避免清單每筆都打一次（學年制最多兩次）外部 API。

        Returns:
            {application_id: period_data}
        """
        period_map: Dict[int, Optional[Dict]] = {}
        live_lookups = []

        for app in applications:
            # Skip only if academic_year is missing (semester can be None for yearly scholarships)
            if not app.get("academic_year"):
                continue

            student_data = app.get("student_data", {}) if isinstance(app.get("student_data"), dict) else {}
            snapshot_period = self._period_data_from_snapshot(student_data, app["academic_year"], app.get("semester"))
            if snapshot_period is not None:
                period_map[app["id"]] = snapshot_period
                continue

            student_id = get_nycu_id_from_data(student_data)
            if student_id and student_id != "N/A" and student_id != "未提供學號":
                live_lookups.append((app["id"], student_id, app["academic_year"], app.get("semester")))

        if not live_lookups:
            return period_map

        logger.info(
            f"Fetching live scholarship period data for {len(live_lookups)} applications without snapshot term data"
        )

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_PERIOD_LOOKUPS)

        async def bounded_lookup(student_id: str, academic_year: int, semester: Optional[str]) -> Optional[Dict]:
            async with semaphore:
                return await self._get_period_data_for_app(student_id, academic_year, semester)

        results = await asyncio.gather(
            *(bounded_lookup(sid, year, sem) for _, sid, year, sem in live_lookups), return_exceptions=True
        )

        success_count = 0
        for (app_id, *_), result in zip(live_lookups, results):
            if isinstance(result, Exception):
                logger.debug(f"Failed to fetch period data for application {app_id}: {result}")
                period_map[app_id] = None
            else:
                period_map[app_id] = result
                success_count += result is not None
        logger.info(f"Scholarship period data fetch completed: {success_count}/{len(live_lookups)} succeeded")

        return period_map

    @staticmethod
    def _period_data_from_snapshot(student_data: Dict, academic_year: int, semester: Optional[str]) -> Optional[Dict]:
        """
        從 student_data 快照取出與申請學年/學期相符的學期資料

        快照的學期規則與 _get_period_data_for_app 相同（first→1、second→2、
        學年制→先 2 後 1），所以只需確認年度與學期別一致。

        Returns:
            含 trm_* 欄位的快照 dict，或 None（快照沒有對應學期資料）
        """
        if student_data.get("trm_studystatus") is None or student_data.get("trm_year") is None:
            return None
        if str(student_data["trm_year"]) != str(academic_year):
            return None

        expected_term = SEMESTER_TERM_CODES.get(semester)
        if expected_term is not None and str(student_data.get("trm_term")) != expected_term:
            return None

        return student_data

    async def _get_period_data_for_app(
        self, student_id: str, academic_year: int, semester: Optional[str]
    ) -> Optional[Dict]:
        """
        獲取單個申請的獎學金期間數據

        查詢邏輯（參考 application_helpers.py）：
        1. Semester.first → 只查 term="1"
        2. Semester.second → 只查 term="2"
        3. None (學年制) → 先查 term="2"，無資料再查 term="1"
        """
        try:
            if semester == "first":
                # 學期制 - 只查第一學期
                return await self.student_service.get_student_term_info(student_id, str(academic_year), "1")
            elif semester == "second":
                # 學期制 - 只查第二學期
                return await self.student_service.get_student_term_info(student_id, str(academic_year), "2")
            else:
                # 學年制 - 先查第二學期，無資料再查第一學期
                data = await self.student_service.get_student_term_info(student_id, str(academic_year), "2")
                if not data:
                    data = await self.student_service.get_student_term_info(student_id, str(academic_year), "1")
                return data
        except Exception as e:
            logger.debug(f"Failed to fetch period data for {student_id}: {e}")
            return None

    def _format_applications(
        self, applications: List[Dict], scholarship_period_map: Dict[int, Optional[Dict]]
    ) -> List[Dict[str, Any]]:
        """
        格式化申請數據供前端使用

        使用 application_helpers 的函數統一提取數據
        只返回 codes，不返回 names（前端 SWR 會處理）
        """
        formatted = []

        for app in applications:
            student_data = app.get("student_data", {}) if isinstance(app.get("student_data"), dict) else {}

            # 使用 application_helpers 的函數提取數據
            student_id = get_nycu_id_from_data(student_data) or "未提供學號"
            student_name = get_student_name_from_data(student_data)
            student_termcount = get_term_count_from_data(student_data) or "N/A"
            department_code = get_department_code_from_data(student_data) or "N/A"
            academy_code = get_academy_code_from_data(student_data)

            formatted_app = {
                "id": app.get("id"),
                "app_id": app.get("app_id"),
                "status": app.get("status"),
                "status_zh": ScholarshipI18n.get_application_status_text(app.get("status", "")),
                "scholarship_type": app.get("scholarship_type"),
                "scholarship_type_zh": app.get("scholarship_type_zh", app.get("scholarship_type")),
                "sub_type": app.get("sub_type"),
                "academic_year": app.get("academic_year"),
                "semester": app.get("semester"),
                "is_renewal": app.get("is_renewal", False),
                "created_at": app.get("created_at"),
                "submitted_at": app.get("submitted_at"),
                # 學生基本信息（使用 helpers 統一提取）
                "student_id": student_id,
                "student_name": student_name,
                "student_termcount": student_termcount,
                # 只返回 codes（前端 SWR 會查名稱）
                "department_code": department_code,
                "academy_code": academy_code,
                # #68: 國籍/身分 — expose only the snapshot keys the college
                # review list reads, not the full SIS snapshot.
                "student_data": {
                    "std_nation": student_data.get("std_nation") or student_data.get("nationality"),
                    "std_identity": (
                        student_data.get("std_identity")
                        if student_data.get("std_identity") is not None
                        else student_data.get("identity")
                    ),
                },
                # 審查狀態
                "review_status": {
                    "has_review": len(app.get("reviews", [])) > 0,
                    "review_count": len(app.get("reviews", [])),
                    "files_count": len(app.get("files", [])),
                },
                # 教授審核資訊
                "requires_professor_recommendation": app.get("requires_professor_recommendation", False),
                "professor_review_completed": app.get("professor_review_completed", False),
                "professor_review_items": app.get("professor_review_items", []),
            }

            # 添加獎學金期間數據（如果存在）
            period_data = scholarship_period_map.get(app["id"])
            if period_data:
                formatted_app["scholarship_period_status"] = period_data.get("trm_studystatus")
                formatted_app["scholarship_period_gpa"] = period_data.get("trm_ascore_gpa")
            else:
                formatted_app["scholarship_period_status"] = None
                formatted_app["scholarship_period_gpa"] = None

            formatted.append(formatted_app)

        return formatted

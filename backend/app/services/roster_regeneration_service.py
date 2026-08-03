"""造冊重新生成服務

「重新生成造冊」：以當前的分發名單、學生資料、獎學金規則與配置，重建一份**既有**
造冊的全部明細。不需要人員有異動也能執行——這正是它與「比對分發名單」(reconcile)
的分工：

  * reconcile 只處理**名單成員**的增減，名單一致時無事可做；
  * 重新生成則刷新**每一筆明細的內容**：金額、計畫編號、學籍驗證、獎學金規則
    判定、分發子類型、備取資訊、郵局帳號等，全部依當下資料重算。

跨重建保留的狀態（否則重建等同撤銷管理員的決定）：
  * 人為排除／移除（學生繳回、學生放棄、鎖定後移除…）——若不保留，已排除的
    學生會被重新納入造冊，並灌水該生的累計領取月份（博士 36 個月上限的依據）。
  * 人工銀行帳戶覆核狀態——由銀行覆核流程寫入，重建不會重新推導。

已鎖定的造冊不得重新生成（與 RosterService 的既有規則一致）；請先解鎖。
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from sqlalchemy import and_
from sqlalchemy.orm import joinedload

from app.core.exceptions import RosterLockedError, RosterNotFoundError
from app.models.application import Application
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.roster_audit import RosterAuditAction, RosterAuditLevel
from app.models.scholarship import ScholarshipConfiguration
from app.models.user import User
from app.services.audit_service import audit_service
from app.services.roster_service import PreservedItemState, RosterService

logger = logging.getLogger(__name__)


@dataclass
class RosterRegenerationResult:
    """重新生成造冊的結果摘要。"""

    roster: PaymentRoster
    rebuilt_items: int
    failed_items: int
    preserved_exclusions: int
    #: 先前納入、依當下資料重新排除的明細數（例如學籍已變更、或規則調整後不再符合）。
    #: 單獨回報，因為這也會撤銷管理員先前的「回復」動作——必須讓管理員看得見。
    newly_excluded: int
    #: 先前納入、如今整筆不在名單中的學生數（申請已撤回／改判／退出分發）。
    #: 這些人不進入重建迴圈，既非 rebuilt 亦非 failed，不單獨回報就會無聲消失。
    dropped_members: int
    excel_exported: bool


class RosterRegenerationService(RosterService):
    """以 roster_id 為單位重新生成造冊明細（同步 Session）。

    繼承 RosterService 以共用其名單解析、明細建立與人為狀態保留原語，確保
    重新生成的成員判定與產生造冊完全一致，不會各自漂移。

    已知的不對稱（刻意）：管理員的「排除」會跨重建保留，但管理員的「回復」
    （把自動排除的學生手動納回）不會——自動判定本來就該依當下資料重算，否則
    一位真的已畢業的學生會永遠留在造冊裡。重建因此可能撤銷一次回復，所以
    `newly_excluded` 會單獨回報，讓管理員看得見而不是靜默發生。
    """

    def regenerate_roster(
        self,
        roster_id: int,
        admin_user_id: int,
        student_verification_enabled: Optional[bool] = None,
    ) -> RosterRegenerationResult:
        """重建造冊明細並提交。

        Args:
            roster_id: 造冊 ID
            admin_user_id: 操作者
            student_verification_enabled: 本次是否重新驗證學籍；None 代表沿用造冊原
                設定。這是「單次」覆寫，不會寫回造冊——否則勾選一次之後就再也關不掉。

        Raises:
            RosterNotFoundError: 找不到造冊
            RosterLockedError: 造冊已鎖定
            ValueError: 造冊處理中、找不到配置、或目前沒有可造冊的名單
        """
        roster = self.db.get(PaymentRoster, roster_id)
        if roster is None:
            raise RosterNotFoundError(str(roster_id))
        if roster.is_locked:
            raise RosterLockedError(
                f"無法重新生成已鎖定的造冊：{roster.roster_code}。請先解鎖再重新生成。",
                roster=roster,
            )
        if roster.status == RosterStatus.PROCESSING:
            raise ValueError(f"造冊 {roster.roster_code} 正在產生中，請稍候再試")

        config = self.db.get(ScholarshipConfiguration, roster.scholarship_configuration_id)
        if config is None:
            raise ValueError(f"找不到獎學金配置：scholarship_configuration_id={roster.scholarship_configuration_id}")

        # 名單必須在「刪除舊明細之前」解析完成並確認非空 —— 否則一份分發已被撤下的
        # 造冊會被清空、標記完成、再匯出一份空白 Excel，訊息卻只說「0 筆明細」。
        applications = self._load_rebuild_applications(roster, config)
        if not applications:
            raise ValueError(
                "沒有可造冊的資料：目前的分發名單中找不到屬於本造冊的已核准學生。"
                "請先完成矩陣分發（或匯入續領通過名單）後再重新生成。"
            )

        preserved = self._snapshot_manual_state(roster_id)
        rebuild_ids = {application.id for application in applications}
        # 先前納入、如今已不在名單中的學生（申請被撤回／改判、或已退出分發）。
        # 這些人不會進入重建迴圈，因此既不算 rebuilt 也不算 failed —— 必須單獨回報。
        dropped_members = sum(
            1 for app_id, state in preserved.items() if state.was_included and app_id not in rebuild_ids
        )

        self._reset_roster_for_rebuild(roster, config)

        counts = self._rebuild_items(roster, applications, preserved, student_verification_enabled)
        rebuilt, failed, verification_failures, preserved_applied, newly_excluded = counts

        self.db.flush()
        roster.verification_api_failures = verification_failures
        # 統計一律由明細列推導，不另外加計 failed —— 否則 total_applications 會與
        # 實際明細筆數不符，並在下一次 reconcile/排除 重算時無聲地跳回去。
        # failed 走 result / 訊息 / 稽核紀錄回報。
        self._recompute_roster_totals_sync(roster_id)
        roster.status = RosterStatus.COMPLETED
        roster.completed_at = datetime.now(timezone.utc)
        self.db.flush()

        excel_exported = self._reexport_excel(roster)
        # Excel 重新產生成功即與明細一致，可清除「需重新匯出」提示；失敗則保留提示。
        roster.excel_stale = not excel_exported

        self._log_regeneration(
            roster=roster,
            admin_user_id=admin_user_id,
            rebuilt=rebuilt,
            failed=failed,
            preserved_exclusions=preserved_applied,
            newly_excluded=newly_excluded,
            dropped_members=dropped_members,
            excel_exported=excel_exported,
        )

        self.db.commit()
        logger.info(
            "Roster %s regenerated: %s rebuilt, %s failed, %s manual exclusions preserved, "
            "%s newly excluded, %s dropped",
            roster.roster_code,
            rebuilt,
            failed,
            preserved_applied,
            newly_excluded,
            dropped_members,
        )
        return RosterRegenerationResult(
            roster=roster,
            rebuilt_items=rebuilt,
            failed_items=failed,
            preserved_exclusions=preserved_applied,
            newly_excluded=newly_excluded,
            dropped_members=dropped_members,
            excel_exported=excel_exported,
        )

    def _load_rebuild_applications(self, roster: PaymentRoster, config: ScholarshipConfiguration) -> List[Application]:
        """本造冊要重建的已核准申請。

        Eager-loads the to-one relationships `_create_roster_item` reads per row
        (`scholarship_configuration.scholarship_type.name`) — the path this
        mirrors does the same, and without it a few-hundred-row roster fires
        hundreds of extra round-trips while holding the regenerate lock.
        """
        application_ids = self._resolve_membership(roster, config)
        if not application_ids:
            return []
        return (
            self.db.query(Application)
            .options(
                joinedload(Application.student),
                joinedload(Application.scholarship_configuration).joinedload(ScholarshipConfiguration.scholarship_type),
            )
            .filter(and_(Application.id.in_(application_ids), Application.status == "approved"))
            .all()
        )

    # ------------------------------------------------------------------
    # 名單解析
    # ------------------------------------------------------------------

    def _resolve_membership(self, roster: PaymentRoster, config: ScholarshipConfiguration) -> Set[int]:
        """本造冊應包含的申請 id 集合，沿用「產生造冊」既有的成員判定規則。"""
        # 全期造冊（generate_roster 路徑）：sub_type / allocation_config_id 皆為 NULL，
        # 名單即該路徑的申請篩選結果，不做分組切片。
        if roster.sub_type is None and roster.allocation_config_id is None:
            applications = self._get_eligible_applications(
                roster.scholarship_configuration_id,
                roster.period_label,
                roster.academic_year,
                roster.ranking_id,
            )
            return {application.id for application in applications}

        # 分組造冊（矩陣分發路徑）：本分組的正取 + 本分組已核准的續領。
        allocated_ids = set(self._resolve_distribution_for_roster(roster, config=config))
        return allocated_ids | self._renewal_application_ids(roster, config)

    def _renewal_application_ids(self, roster: PaymentRoster, config: ScholarshipConfiguration) -> Set[int]:
        """本分組已核准的續領申請 id。

        續領永遠不會產生 CollegeRankingItem（不參與配額分發），分發比對看不到
        它們——分組 key 與 generate_rosters_from_distribution 一致。
        """
        semester = (
            (config.semester.value if hasattr(config.semester, "value") else config.semester)
            if config.semester
            else None
        )
        renewals = (
            self.db.query(Application)
            .filter(
                and_(
                    Application.scholarship_type_id == config.scholarship_type_id,
                    Application.academic_year == config.academic_year,
                    Application.is_renewal.is_(True),
                    Application.status == "approved",
                    Application.deleted_at.is_(None),
                    self._build_application_semester_filter(semester),
                )
            )
            .all()
        )
        roster_key = (roster.allocation_config_id or config.id, roster.sub_type or "general")
        return {
            application.id
            for application in renewals
            if (
                application.allocation_config_id or config.id,
                application.sub_scholarship_type or "general",
            )
            == roster_key
        }

    # ------------------------------------------------------------------
    # 重建
    # ------------------------------------------------------------------

    def _reset_roster_for_rebuild(self, roster: PaymentRoster, config: ScholarshipConfiguration) -> None:
        """清空舊明細並把造冊主檔重設為「產生中」，同時刷新設定面的快照欄位。"""
        # 計畫編號的真實來源是獎學金配置；管理員事後補填後，唯有重新生成才會生效。
        if roster.sub_type:
            consumed_config = (
                self.db.get(ScholarshipConfiguration, roster.allocation_config_id)
                if roster.allocation_config_id is not None
                else config
            ) or config
            roster.project_number = (consumed_config.project_numbers or {}).get(roster.sub_type)

        roster.status = RosterStatus.PROCESSING
        roster.trigger_type = RosterTriggerType.MANUAL
        roster.started_at = datetime.now(timezone.utc)
        roster.completed_at = None
        roster.total_applications = 0
        roster.qualified_count = 0
        roster.disqualified_count = 0
        roster.total_amount = 0
        roster.verification_api_failures = 0

        self.db.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster.id).delete()
        # flush + expire：Excel 匯出讀的是 roster.items 關聯集合，若不失效，
        # 本 Session 先前載入的舊集合會讓匯出寫出過期名單。
        self.db.flush()
        self.db.expire(roster, ["items"])

    def _rebuild_items(
        self,
        roster: PaymentRoster,
        applications: List[Application],
        preserved: Dict[int, PreservedItemState],
        verification_enabled: Optional[bool],
    ) -> tuple:
        """逐筆重建明細。

        Returns:
            (rebuilt, failed, verification_failures, preserved_applied, newly_excluded)
        """
        rebuilt = 0
        failed = 0
        verification_failures = 0
        preserved_applied = 0
        newly_excluded = 0

        for application in applications:
            try:
                item = self._verify_and_create_item(roster, application, verification_enabled=verification_enabled)
            except Exception:
                logger.exception(
                    "Roster %s: failed to rebuild item for application %s", roster.roster_code, application.id
                )
                failed += 1
                continue

            if item.verification_status == StudentVerificationStatus.API_ERROR:
                verification_failures += 1
            state = preserved.get(application.id)
            if self._apply_preserved_state(item, state):
                preserved_applied += 1
            elif state is not None and state.was_included and not item.is_included:
                # 先前納入、現在被自動判定排除。這也會撤銷管理員先前的「回復」，
                # 所以要計數回報，不能靜默發生。
                newly_excluded += 1
            rebuilt += 1

        return rebuilt, failed, verification_failures, preserved_applied, newly_excluded

    def _reexport_excel(self, roster: PaymentRoster) -> bool:
        """依重建後的明細重新產生 Excel 並上傳。失敗僅記錄，不推翻整次重建。"""
        from app.services.excel_export_service import ExcelExportService

        try:
            ExcelExportService().export_roster_to_excel(
                roster=roster,
                template_name="STD_UP_MIXLISTA",
                include_header=True,
                include_statistics=True,
                include_excluded=False,
            )
            self.db.flush()  # 保存 minio_object_name / excel_filename
            return True
        except Exception:
            logger.exception("Failed to regenerate Excel for roster %s", roster.roster_code)
            return False

    def _log_regeneration(
        self,
        roster: PaymentRoster,
        admin_user_id: int,
        rebuilt: int,
        failed: int,
        preserved_exclusions: int,
        newly_excluded: int,
        dropped_members: int,
        excel_exported: bool,
    ) -> None:
        user = self.db.get(User, admin_user_id)
        audit_service.log_roster_operation(
            roster_id=roster.id,
            action=RosterAuditAction.UPDATE,
            title=f"重新生成造冊: {roster.roster_code} 納入造冊{roster.qualified_count}人",
            user_id=admin_user_id,
            user_name=user.name if user else "Unknown",
            description=(
                f"依當下分發名單與學生資料重建 {rebuilt} 筆明細"
                f"（保留人為排除 {preserved_exclusions} 筆，新增排除 {newly_excluded} 筆，"
                f"移出名單 {dropped_members} 筆，建立失敗 {failed} 筆）；"
                f"計畫編號: {roster.project_number or '未設定'}，總金額: ${roster.total_amount}"
            ),
            old_values=None,
            new_values=None,
            level=(
                RosterAuditLevel.WARNING if (failed or newly_excluded or dropped_members) else RosterAuditLevel.INFO
            ),
            affected_items_count=rebuilt,
            metadata={
                "rebuilt_items": rebuilt,
                "failed_items": failed,
                "preserved_exclusions": preserved_exclusions,
                "newly_excluded": newly_excluded,
                "dropped_members": dropped_members,
                "excel_exported": excel_exported,
                "qualified_count": roster.qualified_count,
                "disqualified_count": roster.disqualified_count,
                "total_amount": float(roster.total_amount or 0),
            },
            tags=["regenerate", roster.sub_type or "whole_period"],
            db=self.db,
        )

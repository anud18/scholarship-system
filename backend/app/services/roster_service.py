"""
造冊服務核心邏輯
Roster service core logic for scholarship payment roster generation
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, case as sa_case, func, or_
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    RosterAlreadyExistsError,
    RosterGenerationError,
    RosterLockedError,
    RosterNotFoundError,
)
from app.core.metrics import payment_rosters_total
from app.core.pii_crypto import redact_dict_pii
from app.models.application import Application
from app.models.enums import QuotaManagementMode
from app.models.payment_roster import (
    MANUAL_REMOVAL_PREFIX_LOCKED,
    MANUAL_REMOVAL_PREFIX_RECONCILE,
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.roster_audit import RosterAuditAction, RosterAuditLevel, RosterAuditLog
from app.models.scholarship import ScholarshipConfiguration, ScholarshipRule
from app.models.user import User
from app.schemas.payment_roster import DistributionDiffEntry, RevokedSuspendedEntry
from app.services.audit_service import audit_service
from app.services.student_verification_service import StudentVerificationService
from app.utils.pii_masking import mask_id_number

logger = logging.getLogger(__name__)


@dataclass
class RosterGenerationResult:
    """Outcome of a batch roster generation (issue #1033).

    `created` are the rosters newly produced (or rebuilt under
    force_regenerate); `skipped` are pre-existing rosters left untouched
    because they already existed and force_regenerate was not set; `locked`
    are pre-existing rosters that force_regenerate could NOT rebuild because
    they are locked. Carrying these lets the API tell the admin honestly what
    happened instead of returning a misleading "produced 0" success — or, for
    locked rosters under force, aborting the whole batch with a 500.
    """

    created: List["PaymentRoster"] = field(default_factory=list)
    skipped: List["PaymentRoster"] = field(default_factory=list)
    locked: List["PaymentRoster"] = field(default_factory=list)


class RosterService:
    """造冊服務"""

    def __init__(self, db: Session):
        self.db = db
        self.student_verification_service = StudentVerificationService()

    def generate_roster(
        self,
        scholarship_configuration_id: int,
        period_label: str,
        roster_cycle: RosterCycle,
        academic_year: int,
        created_by_user_id: int,
        trigger_type: RosterTriggerType = RosterTriggerType.MANUAL,
        student_verification_enabled: bool = True,
        force_regenerate: bool = False,
        ranking_id: Optional[int] = None,  # 新增：指定排名ID
    ) -> PaymentRoster:
        """
        產生造冊

        Args:
            scholarship_configuration_id: 獎學金配置ID
            period_label: 期間標記 (YYYY-MM, YYYY-H1/H2, YYYY)
            roster_cycle: 造冊週期
            academic_year: 學年度
            created_by_user_id: 建立者用戶ID
            trigger_type: 觸發方式
            student_verification_enabled: 是否啟用學籍驗證
            force_regenerate: 是否強制重新產生

        Returns:
            PaymentRoster: 造冊對象

        Raises:
            RosterAlreadyExistsError: 造冊已存在且未強制重新產生
            RosterGenerationError: 造冊產生過程中發生錯誤
        """
        try:
            # 強化的冪等性檢查
            existing_roster = self.check_roster_exists(scholarship_configuration_id, period_label)

            if existing_roster and not force_regenerate:
                # 檢查是否有重複記錄
                duplicate_rosters = self.get_duplicate_rosters(scholarship_configuration_id, period_label)
                if len(duplicate_rosters) > 1:
                    logger.warning(
                        f"Found {len(duplicate_rosters)} duplicate rosters for scholarship {scholarship_configuration_id}, period {period_label}"
                    )

                raise RosterAlreadyExistsError(
                    f"Roster already exists for scholarship {scholarship_configuration_id} "
                    f"and period {period_label}. Use force_regenerate=True to override."
                )

            if existing_roster and existing_roster.is_locked:
                raise RosterLockedError(f"Cannot regenerate locked roster {existing_roster.roster_code}")

            # 取得獎學金配置以檢查配額模式
            scholarship_config = (
                self.db.query(ScholarshipConfiguration)
                .filter(ScholarshipConfiguration.id == scholarship_configuration_id)
                .first()
            )

            if not scholarship_config:
                raise ValueError(f"找不到獎學金配置: ID {scholarship_configuration_id}")

            # 根據配額管理模式進行驗證
            if scholarship_config.quota_management_mode == QuotaManagementMode.matrix_based:
                # Matrix 模式：必須有 ranking 且已執行分發
                if ranking_id:
                    from app.models.college_review import CollegeRanking

                    ranking = self.db.query(CollegeRanking).filter(CollegeRanking.id == ranking_id).first()

                    if not ranking:
                        raise ValueError(f"找不到排名: ID {ranking_id}")

                    if not ranking.distribution_executed:
                        raise ValueError(
                            f"無法從排名 {ranking_id} 產生造冊：尚未執行分發。" f"請先執行矩陣分發後再產生造冊。"
                        )

                    logger.info(f"已驗證排名 {ranking_id} 已執行分發 " f"({ranking.allocated_count} 位學生已分配)")
                else:
                    # Matrix 模式但沒有提供 ranking_id，後續會自動偵測
                    logger.info("Matrix 模式獎學金但未提供 ranking_id，將在篩選申請時自動偵測最新的已執行分發的排名")
            else:
                # 非 Matrix 模式：不應使用 ranking_id
                if ranking_id is not None:
                    logger.warning(
                        f"獎學金配置 {scholarship_configuration_id} 使用 '{scholarship_config.quota_management_mode.value}' 模式，"
                        f"但提供了 ranking_id {ranking_id}。此參數將被忽略。"
                    )
                    # 將 ranking_id 設為 None 以確保不會被使用
                    ranking_id = None

            # 產生造冊代碼
            roster_code = self._generate_roster_code(scholarship_configuration_id, period_label, academic_year)

            # 建立造冊主檔
            if existing_roster and force_regenerate:
                # 更新現有造冊
                roster = existing_roster
                roster.status = RosterStatus.PROCESSING
                roster.trigger_type = trigger_type
                roster.student_verification_enabled = student_verification_enabled
                roster.started_at = datetime.now(timezone.utc)
                roster.completed_at = None
                roster.total_applications = 0
                roster.qualified_count = 0
                roster.disqualified_count = 0
                roster.total_amount = 0
                roster.verification_api_failures = 0
                roster.processing_log = []

                # 清除舊的明細
                self.db.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster.id).delete()
                self.db.flush()
                self.db.expire(roster, ["items"])

                logger.info(f"Regenerating roster {roster_code}")
            else:
                # 建立新造冊
                roster = PaymentRoster(
                    roster_code=roster_code,
                    scholarship_configuration_id=scholarship_configuration_id,
                    period_label=period_label,
                    academic_year=academic_year,
                    roster_cycle=roster_cycle,
                    status=RosterStatus.PROCESSING,
                    trigger_type=trigger_type,
                    created_by=created_by_user_id,
                    student_verification_enabled=student_verification_enabled,
                    ranking_id=ranking_id,  # 新增：關聯排名ID
                    started_at=datetime.now(timezone.utc),
                )
                self.db.add(roster)
                self.db.flush()  # 取得ID

                logger.info(f"Creating new roster {roster_code}")

                # Business metric: count roster creations so the
                # Scholarship System Overview dashboard reflects when
                # admins kick off a new payment cycle (issue #159).
                payment_rosters_total.labels(status="processing").inc()

            # 記錄稽核日誌
            user = self.db.query(User).filter(User.id == created_by_user_id).first()
            user_name = user.name if user else "Unknown"

            if existing_roster:
                audit_service.log_roster_operation(
                    roster_id=roster.id,
                    action=RosterAuditAction.UPDATE,
                    title=f"重新產生造冊: {roster_code}",
                    user_id=created_by_user_id,
                    user_name=user_name,
                    description=f"強制重新產生造冊，觸發方式: {trigger_type.value}",
                    old_values={"status": "completed"} if existing_roster.status == RosterStatus.COMPLETED else {},
                    new_values={"status": "processing", "trigger_type": trigger_type.value},
                    level=RosterAuditLevel.INFO,
                    tags=["regenerate", trigger_type.value],
                    db=self.db,
                )
            else:
                scholarship_config = (
                    self.db.query(ScholarshipConfiguration)
                    .filter(ScholarshipConfiguration.id == scholarship_configuration_id)
                    .first()
                )

                audit_service.log_roster_creation(
                    roster_id=roster.id,
                    roster_code=roster_code,
                    user_id=created_by_user_id,
                    user_name=user_name,
                    scholarship_config_name=scholarship_config.config_name if scholarship_config else "Unknown",
                    period_label=period_label,
                    trigger_type=trigger_type.value,
                    db=self.db,
                )

            # 取得符合條件的申請
            applications = self._get_eligible_applications(
                scholarship_configuration_id, period_label, academic_year, ranking_id
            )

            roster.total_applications = len(applications)
            logger.info(f"Found {len(applications)} eligible applications")

            # 產生造冊明細
            qualified_count = 0
            disqualified_count = 0
            total_amount = 0
            verification_failures = 0

            for application in applications:
                try:
                    # 取得申請中的學生資料
                    stored_student_data = application.student_data or {}
                    student_id_number = stored_student_data.get("std_stdcode")
                    student_name = stored_student_data.get("std_cname")

                    if not student_id_number or not student_name:
                        logger.warning(f"Application {application.id} missing student ID or name")
                        disqualified_count += 1
                        continue

                    # 學籍API驗證並取得最新資料
                    verification_result = None
                    verification_status = StudentVerificationStatus.VERIFIED
                    fresh_student_data = None  # 儲存 API 當下拉取的新鮮資料

                    if student_verification_enabled:
                        # 呼叫學籍API取得最新資料
                        verification_result = self.student_verification_service.verify_student(
                            student_id_number, student_name
                        )
                        verification_status = verification_result.get("status", StudentVerificationStatus.VERIFIED)

                        if verification_status == StudentVerificationStatus.API_ERROR:
                            verification_failures += 1
                        else:
                            # 取得 API 回傳的新鮮資料（用於資格驗證）
                            fresh_student_data = verification_result.get("student_info", {})

                    # ✅ 優先使用新鮮 API 資料進行資格驗證
                    eligibility_result = self._validate_student_eligibility(
                        application, roster.academic_year, roster.period_label, fresh_api_data=fresh_student_data
                    )

                    # ⬇️ 驗證完成後，才更新 student_data（作為稽核記錄）
                    if fresh_student_data:
                        # 檢查並更新 student_data
                        has_changes = False
                        updated_fields = []

                        # 合併 API 資料到 stored_student_data
                        for key, value in fresh_student_data.items():
                            if stored_student_data.get(key) != value:
                                old_value = stored_student_data.get(key)
                                stored_student_data[key] = value
                                has_changes = True
                                updated_fields.append(key)
                                logger.info(f"Updated {key} for application {application.id}: {old_value} -> {value}")

                        if has_changes:
                            # 更新Application的student_data欄位（稽核用）。
                            # stored_student_data is the same dict reference as
                            # application.student_data; flag_modified() is required
                            # because SQLAlchemy's default JSON change detection
                            # compares object identity, not contents — without
                            # this, the in-place mutations on line 270 would be
                            # silently discarded on commit.
                            from sqlalchemy.orm.attributes import flag_modified

                            application.student_data = stored_student_data
                            flag_modified(application, "student_data")
                            self.db.add(application)

                            # 記錄更新日誌
                            audit_service.log_roster_operation(
                                roster_id=roster.id,
                                action=RosterAuditAction.ITEM_UPDATE,
                                title=f"更新申請 {application.id} 的學生資料",
                                user_id=created_by_user_id,
                                user_name=user_name,
                                description=f"學籍驗證後更新欄位: {', '.join(updated_fields)}",
                                # Redact std_pid (and any other PII keys configured in
                                # `redact_dict_pii` defaults) before persisting to
                                # audit_logs.old_values / new_values. The ORM-loaded
                                # `stored_student_data` has already been decrypted by
                                # the PII TypeDecorator, so without this guard a
                                # `std_pid` entry in `updated_fields` would write
                                # plaintext into the audit trail and bypass at-rest
                                # encryption. Defense in depth — see PR #202.
                                old_values=redact_dict_pii({f: stored_student_data.get(f) for f in updated_fields}),
                                new_values=redact_dict_pii(
                                    {f: fresh_student_data[f] for f in updated_fields if f in fresh_student_data}
                                ),
                                level=RosterAuditLevel.INFO,
                                metadata={
                                    "application_id": application.id,
                                    "updated_fields": updated_fields,
                                    "verification_status": (
                                        verification_result.get("status").value
                                        if verification_result.get("status")
                                        else None
                                    ),
                                    "verification_message": (
                                        verification_result.get("message") if verification_result else None
                                    ),
                                },
                                tags=["student_data_update", "verification"],
                                db=self.db,
                            )

                    # 建立造冊明細
                    roster_item = self._create_roster_item(
                        roster, application, verification_result, verification_status, eligibility_result
                    )

                    if roster_item.is_qualified:
                        qualified_count += 1
                        total_amount += roster_item.scholarship_amount
                    else:
                        disqualified_count += 1

                except Exception as e:
                    logger.exception(f"Error processing application {application.id}")
                    disqualified_count += 1

                    # 記錄錯誤日誌
                    audit_service.log_roster_error(
                        roster_id=roster.id,
                        error_code="APPLICATION_PROCESSING_ERROR",
                        error_message=str(e),
                        operation=f"處理申請 {application.id}",
                        user_id=created_by_user_id,
                        user_name=user_name,
                        exception_details={"application_id": application.id},
                        db=self.db,
                    )

            # 更新統計資訊
            roster.qualified_count = qualified_count
            roster.disqualified_count = disqualified_count
            roster.total_amount = total_amount
            roster.verification_api_failures = verification_failures

            # 關鍵改進：在設置為 COMPLETED 前進行資料一致性驗證
            validation = self.validate_roster_consistency(roster)
            if not validation["is_valid"]:
                error_details = "; ".join(validation["errors"])
                logger.error(f"Roster data inconsistency detected: {error_details}")
                raise RosterGenerationError(f"造冊資料一致性驗證失敗: {error_details}")

            # 記錄警告（如果有）
            if validation["warnings"]:
                for warning in validation["warnings"]:
                    logger.warning(f"Roster {roster_code} validation warning: {warning}")

            # 驗證通過後 flush 資料到資料庫（但不 commit）
            # 這確保 lazy loading 的關聯資料（如 roster.items）可以被存取
            # 狀態設置將由 API 端點在所有操作成功後進行
            self.db.flush()

            # 記錄產生日誌（狀態尚未設置為 COMPLETED）
            audit_service.log_roster_operation(
                roster_id=roster.id,
                action=RosterAuditAction.CREATE,
                title=f"造冊資料產生: 合格{qualified_count}人, 不合格{disqualified_count}人",
                user_id=created_by_user_id,
                user_name=user_name,
                description=f"造冊資料產生完成，總金額: ${total_amount}，API失敗: {verification_failures}次",
                old_values=None,
                new_values=None,
                level=RosterAuditLevel.INFO,
                affected_items_count=qualified_count + disqualified_count,
                metadata={
                    "qualified_count": qualified_count,
                    "disqualified_count": disqualified_count,
                    "total_amount": float(total_amount),
                    "verification_failures": verification_failures,
                },
                tags=["generation", trigger_type.value],
                db=self.db,
            )

            # 重要：不再在此處 commit，讓調用者決定何時提交
            # 這確保了造冊產生和後續操作（如 Excel 匯出）在同一個事務中
            logger.info(f"Roster {roster_code} generated successfully (not yet committed)")

            return roster

        except Exception as e:
            # 不在此處執行 rollback，讓調用者決定如何處理事務
            # 這避免了與 API 端點的 rollback 重複執行
            logger.exception("Error generating roster")
            raise RosterGenerationError(f"Failed to generate roster: {e}") from e

    def validate_roster_consistency(self, roster: PaymentRoster) -> Dict[str, Any]:
        """
        驗證造冊資料一致性
        Validate roster data consistency

        Args:
            roster: 要驗證的造冊物件

        Returns:
            {
                "is_valid": bool,  # 是否通過驗證
                "errors": List[str],  # 錯誤列表
                "warnings": List[str]  # 警告列表
            }
        """
        errors = []
        warnings = []

        # 1. 檢查明細數量是否與統計一致
        item_count = len(roster.items) if roster.items else 0
        expected_count = roster.qualified_count + roster.disqualified_count

        if item_count != expected_count:
            errors.append(
                f"明細數量不一致: 實際 {item_count} 筆，但統計顯示應有 {expected_count} 筆 "
                f"(合格={roster.qualified_count}, 不合格={roster.disqualified_count})"
            )

        # 2. 檢查金額總計是否正確
        # Skip None amounts in the sum — the per-item check below catches them
        # as an error. Without this guard, sum() raises TypeError on None and
        # the validator crashes instead of returning a clean error dict.
        if roster.items:
            actual_total = sum(
                item.scholarship_amount
                for item in roster.items
                if item.is_included and item.is_qualified and item.scholarship_amount is not None
            )
            if abs(float(actual_total) - float(roster.total_amount)) > 0.01:
                errors.append(f"總金額不一致: 計算值={actual_total}, 儲存值={roster.total_amount}")

        # 3. 檢查是否有明細資料（至少應該有 qualified + disqualified > 0）
        if expected_count > 0 and item_count == 0:
            errors.append(f"統計顯示有 {expected_count} 筆資料，但沒有任何明細項目")

        # 4. 檢查所有明細項目的必需欄位
        if roster.items:
            for idx, item in enumerate(roster.items):
                if not item.student_id_number:
                    errors.append(f"明細項目 #{idx + 1} 缺少學生身分證字號")
                if not item.student_name:
                    errors.append(f"明細項目 #{idx + 1} 缺少學生姓名")
                if item.scholarship_amount is None or item.scholarship_amount <= 0:
                    errors.append(f"明細項目 #{idx + 1} 獎學金金額無效")

        # 5. 檢查狀態為 COMPLETED 時是否有 Excel 檔案（警告級別）
        if roster.status == RosterStatus.COMPLETED:
            if not roster.excel_filename and not roster.minio_object_name:
                warnings.append("造冊狀態為已完成，但沒有關聯的 Excel 檔案")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def get_roster_by_id(self, roster_id: int) -> Optional[PaymentRoster]:
        """根據ID取得造冊"""
        return self.db.query(PaymentRoster).filter(PaymentRoster.id == roster_id).first()

    def get_roster_by_code(self, roster_code: str) -> Optional[PaymentRoster]:
        """根據代碼取得造冊"""
        return self.db.query(PaymentRoster).filter(PaymentRoster.roster_code == roster_code).first()

    def get_roster_by_period(self, scholarship_configuration_id: int, period_label: str) -> Optional[PaymentRoster]:
        """根據獎學金配置和期間取得造冊"""
        return (
            self.db.query(PaymentRoster)
            .filter(
                and_(
                    PaymentRoster.scholarship_configuration_id == scholarship_configuration_id,
                    PaymentRoster.period_label == period_label,
                )
            )
            .first()
        )

    def lock_roster(self, roster_id: int, locked_by_user_id: int) -> PaymentRoster:
        """鎖定造冊"""
        roster = self.get_roster_by_id(roster_id)
        if not roster:
            raise RosterNotFoundError(f"Roster {roster_id} not found")

        if roster.is_locked:
            raise RosterLockedError(f"Roster {roster.roster_code} is already locked")

        roster.lock(locked_by_user_id)

        user = self.db.query(User).filter(User.id == locked_by_user_id).first()
        user_name = user.name if user else "Unknown"

        audit_service.log_roster_lock(
            roster_id=roster.id,
            user_id=locked_by_user_id,
            user_name=user_name,
            db=self.db,
        )

        self.db.commit()
        return roster

    def unlock_roster(self, roster_id: int, unlocked_by_user_id: int) -> PaymentRoster:
        """解鎖造冊"""
        roster = self.get_roster_by_id(roster_id)
        if not roster:
            raise RosterNotFoundError(f"Roster {roster_id} not found")

        if not roster.is_locked:
            raise ValueError(f"Roster {roster.roster_code} is not locked")

        roster.status = RosterStatus.COMPLETED
        roster.locked_at = None
        roster.locked_by = None

        user = self.db.query(User).filter(User.id == unlocked_by_user_id).first()
        user_name = user.name if user else "Unknown"

        audit_service.log_roster_operation(
            roster_id=roster.id,
            action=RosterAuditAction.UNLOCK,
            title="解鎖造冊",
            user_id=unlocked_by_user_id,
            user_name=user_name,
            description="造冊已解鎖，可以再次進行修改",
            old_values={"status": "locked"},
            new_values={"status": "completed"},
            level=RosterAuditLevel.INFO,
            tags=["unlock"],
            db=self.db,
        )

        self.db.commit()
        return roster

    def get_roster_items(self, roster_id: int, include_excluded: bool = True) -> List[PaymentRosterItem]:
        """取得造冊明細"""
        query = self.db.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster_id)

        if not include_excluded:
            query = query.filter(PaymentRosterItem.is_included.is_(True))

        return query.all()

    def _generate_roster_code(self, scholarship_configuration_id: int, period_label: str, academic_year: int) -> str:
        """產生造冊代碼"""
        # 取得獎學金配置
        config = (
            self.db.query(ScholarshipConfiguration)
            .filter(ScholarshipConfiguration.id == scholarship_configuration_id)
            .first()
        )

        if not config:
            raise ValueError(f"Scholarship configuration {scholarship_configuration_id} not found")

        # 格式: ROSTER-{academic_year}-{period_label}-{config_code}
        return f"ROSTER-{academic_year}-{period_label}-{config.config_code}"

    def _get_eligible_applications(
        self, scholarship_configuration_id: int, period_label: str, academic_year: int, ranking_id: Optional[int] = None
    ) -> List[Application]:
        """
        取得符合條件的申請

        根據配額管理模式使用不同的篩選邏輯：
        - matrix_based: 必須使用 ranking_id，只選取已分配(is_allocated=True)的申請
        - 其他模式(none/simple/college_based): 選取所有 approved 狀態的申請
        """
        from app.models.college_review import CollegeRanking, CollegeRankingItem

        # 1. 取得獎學金配置以判斷配額模式
        config = (
            self.db.query(ScholarshipConfiguration)
            .filter(ScholarshipConfiguration.id == scholarship_configuration_id)
            .first()
        )

        if not config:
            raise ValueError(f"找不到獎學金配置: ID {scholarship_configuration_id}")

        # 2. 基本查詢：已核准的申請
        # 容錯處理：如果 scholarship_configuration_id 為 NULL，則比對 scholarship_type_id
        # Eager-load the to-one relationships that _create_roster_item / verification
        # loops read per row (student, scholarship_configuration → scholarship_type),
        # otherwise each roster row triggers extra lazy round-trips (N+1).
        query = (
            self.db.query(Application)
            .options(
                joinedload(Application.student),
                joinedload(Application.scholarship_configuration).joinedload(ScholarshipConfiguration.scholarship_type),
            )
            .filter(
                and_(
                    or_(
                        Application.scholarship_configuration_id == scholarship_configuration_id,
                        and_(
                            Application.scholarship_configuration_id.is_(None),
                            Application.scholarship_type_id == config.scholarship_type_id,
                        ),
                    ),
                    Application.status == "approved",  # 已核准
                    Application.academic_year == academic_year,
                    Application.deleted_at.is_(None),  # 排除已退件
                )
            )
        )

        logger.info(
            f"Querying applications for config {scholarship_configuration_id} "
            f"(scholarship_type {config.scholarship_type_id}), fallback enabled for NULL config_id"
        )

        # 3. 根據配額管理模式使用不同的過濾邏輯
        if config.quota_management_mode == QuotaManagementMode.matrix_based:
            # Matrix 模式：必須使用 ranking + is_allocated 過濾
            logger.info(f"Using matrix-based filtering for scholarship config {scholarship_configuration_id}")

            # 未指定 ranking_id：聚合「所有」已執行分發的排名 → 多學院全院納入。
            # matrix 分發下每個學院各有一份 CollegeRanking；過去只取最新一份
            # (.order_by(finalized_at.desc()).first()) 會讓造冊只含最後鎖定的那一院。
            if ranking_id is None:
                rankings = (
                    self.db.query(CollegeRanking)
                    .filter(
                        and_(
                            CollegeRanking.scholarship_type_id == config.scholarship_type_id,
                            CollegeRanking.academic_year == academic_year,
                            CollegeRanking.is_finalized.is_(True),
                            CollegeRanking.distribution_executed.is_(True),
                        )
                    )
                    .all()
                )

                if not rankings:
                    raise ValueError(
                        f"找不到已執行分發的排名。Matrix 模式獎學金必須先執行矩陣分發才能產生造冊。"
                        f"獎學金類型ID: {config.scholarship_type_id}, 學年度: {academic_year}"
                    )

                ranking_ids = [r.id for r in rankings]
                logger.info(
                    f"Aggregating {len(ranking_ids)} executed ranking(s) {ranking_ids} for "
                    f"all-college roster (type {config.scholarship_type_id}, year {academic_year})"
                )

                # 聚合所有排名：一個申請最多屬於一份排名，故 .in_() 不會重複。
                ranking_filter = CollegeRankingItem.ranking_id.in_(ranking_ids)
            else:
                # 明確指定排名：僅該排名（管理員刻意選擇單一排名）。
                ranking_filter = CollegeRankingItem.ranking_id == ranking_id

            # 只選取 ranking 中已分配(正取)的申請。
            query = query.join(CollegeRankingItem, CollegeRankingItem.application_id == Application.id).filter(
                and_(
                    ranking_filter,
                    CollegeRankingItem.is_allocated.is_(True),
                )
            )
        else:
            # 非 Matrix 模式 (none/simple/college_based)：直接從 approved 狀態選取
            logger.info(
                f"Using non-matrix filtering mode '{config.quota_management_mode.value}' "
                f"for scholarship config {scholarship_configuration_id}"
            )

            # 如果誤傳了 ranking_id，記錄警告但忽略
            if ranking_id is not None:
                logger.warning(
                    f"ranking_id {ranking_id} provided for non-matrix scholarship mode "
                    f"'{config.quota_management_mode.value}', will be ignored"
                )

        # 4. 根據期間標記進行額外篩選
        # 重要：只有當獎學金配置本身是學期制時才應用學期過濾
        if config.semester is not None:
            # 學期制獎學金：應用學期過濾
            if period_label.endswith("-H1") or period_label.endswith("-H2"):
                # 半年期間 - 根據學期篩選
                semester = "first" if period_label.endswith("-H1") else "second"
                query = query.filter(Application.semester == semester)
                logger.info(f"Filtering semester-based scholarship for semester '{semester}'")
            elif "-" in period_label and len(period_label.split("-")) == 2:
                # 月份期間 - 根據月份對應學期
                year, month = period_label.split("-")
                try:
                    month_int = int(month)
                    if not 1 <= month_int <= 12:
                        # Out-of-range months (e.g. 0, 13, 999) used to fall through
                        # both `if` branches silently — no semester filter applied,
                        # caller got an unfiltered query and didn't know.
                        raise ValueError(f"month must be 1-12, got {month_int}")
                    # 2-7月 = 下學期(second), 8-1月 = 上學期(first)
                    if month_int in [2, 3, 4, 5, 6, 7]:
                        semester = "second"
                        query = query.filter(Application.semester == semester)
                        logger.info(
                            f"Filtering semester-based scholarship for semester '{semester}' (month {month_int})"
                        )
                    else:
                        # months 1, 8, 9, 10, 11, 12 → first semester
                        semester = "first"
                        query = query.filter(Application.semester == semester)
                        logger.info(
                            f"Filtering semester-based scholarship for semester '{semester}' (month {month_int})"
                        )
                except ValueError:
                    logger.warning("Invalid month in period_label: %s", month, exc_info=True)
        else:
            # 學年制獎學金：不應用學期過濾
            # 申請的 semester 應該是 NULL
            logger.info(
                f"Yearly scholarship detected (config.semester=NULL), "
                f"not applying semester filter for period {period_label}"
            )

        return query.order_by(Application.is_renewal.desc(), Application.submitted_at).all()

    def _extract_semester_from_period(self, period_label: str) -> Optional[str]:
        """從期間標記提取學期資訊"""
        if period_label.endswith("-H1"):
            return "first"
        elif period_label.endswith("-H2"):
            return "second"
        elif "-" in period_label and len(period_label.split("-")) == 2:
            year, month = period_label.split("-")
            try:
                month_int = int(month)
                if month_int in [2, 3, 4, 5, 6, 7]:
                    return "second"
                elif month_int in [8, 9, 10, 11, 12, 1]:
                    return "first"
            except ValueError:
                pass
        return None

    def _create_roster_item(
        self,
        roster: PaymentRoster,
        application: Application,
        verification_result: Optional[Dict],
        verification_status: StudentVerificationStatus,
        eligibility_result: Optional[Dict] = None,
    ) -> PaymentRosterItem:
        """建立造冊明細"""
        # 從申請中取得學生資料
        student_data = application.student_data or {}

        # 判斷是否納入造冊 — 收集「所有」排除原因，不得互相覆蓋 (#1142)
        exclusion_reasons: list[str] = []

        # 1. 檢查學籍驗證狀態
        if verification_status != StudentVerificationStatus.VERIFIED:
            exclusion_reasons.append(f"學籍驗證未通過: {verification_status.value}")
        # 2. 檢查獎學金規則符合性
        elif eligibility_result and not eligibility_result.get("is_eligible", True):
            failed_rules = eligibility_result.get("failed_rules", [])
            if failed_rules:
                exclusion_reasons.append(f"不符合獎學金規則: {'; '.join(failed_rules)}")
            else:
                exclusion_reasons.append("不符合獎學金資格條件")
        # 3. 檢查銀行帳戶資訊
        # IMPORTANT: Support both nested (schema-compliant) and flat (legacy) data structures
        form_data = application.submitted_form_data or {}
        form_fields = form_data.get("fields", {})

        # Extract bank_account from various possible field names
        bank_account = ""
        for field_name in ["postal_account", "bank_account", "account_number", "帳戶號碼", "帳號", "郵局帳號"]:
            # Check nested structure first (schema-compliant)
            if field_name in form_fields and form_fields[field_name].get("value"):
                bank_account = str(form_fields[field_name]["value"])
                logger.debug(f"Found bank account '{bank_account}' in nested structure (field: {field_name})")
                break
            # Check flat structure (backward compatibility for existing data)
            elif field_name in form_data and form_data.get(field_name):
                bank_account = str(form_data[field_name])
                logger.debug(f"Found bank account '{bank_account}' in flat structure (field: {field_name})")
                break

        if not bank_account:
            exclusion_reasons.append("缺少銀行帳戶資訊")
            logger.warning(
                f"Application {application.id} missing bank account. "
                f"Checked nested and flat structures. submitted_form_data keys: {list(form_data.keys())}"
            )

        is_included = not exclusion_reasons
        exclusion_reason = "；".join(exclusion_reasons) if exclusion_reasons else None

        # 查詢 CollegeRankingItem 以取得備取資訊與分發子類型
        backup_info = None
        allocated_sub_type = None
        from app.models.college_review import CollegeRanking, CollegeRankingItem

        if roster.ranking_id:
            ranking_item = (
                self.db.query(CollegeRankingItem)
                .filter(
                    and_(
                        CollegeRankingItem.application_id == application.id,
                        CollegeRankingItem.ranking_id == roster.ranking_id,
                    )
                )
                .first()
            )

            if ranking_item:
                if ranking_item.backup_allocations:
                    backup_info = ranking_item.backup_allocations
                    logger.info(f"Application {application.id} has backup allocations: {len(backup_info)} positions")
                allocated_sub_type = ranking_item.allocated_sub_type

        # 若無 ranking_id（月份造冊），從同學年度已分發排名中查詢子類型。
        # 此處僅 gate 在 is_allocated + academic_year（未含 is_finalized /
        # distribution_executed）。其正確性依賴 _get_eligible_applications 已先以
        # 「finalized + executed」篩選過申請：一個申請在同學年度只會有一筆有效正取
        # （finalize 時會反鎖同 slot 的其他排名），故 .first() 取到的即為授權子類型。
        if not allocated_sub_type:
            alloc_item = (
                self.db.query(CollegeRankingItem)
                .join(CollegeRanking, CollegeRankingItem.ranking_id == CollegeRanking.id)
                .filter(
                    and_(
                        CollegeRankingItem.application_id == application.id,
                        CollegeRankingItem.is_allocated.is_(True),
                        CollegeRanking.academic_year == roster.academic_year,
                    )
                )
                .first()
            )
            if alloc_item:
                allocated_sub_type = alloc_item.allocated_sub_type

        # 續領申請沒有 CollegeRankingItem；子類型直接取自申請本身。
        if not allocated_sub_type and application.is_renewal:
            allocated_sub_type = application.sub_scholarship_type

        # 載入消耗配置 (consumed config) — 借用前年度配額時不同於發放配置。
        # allocation_config_id NULL ⇒ 全期 sentinel，退回造冊自身的發放配置。
        consumed_config = None
        if roster.allocation_config_id is not None:
            consumed_config = self.db.get(ScholarshipConfiguration, roster.allocation_config_id)
        if consumed_config is None:
            consumed_config = application.scholarship_configuration
        # allocation_year 顯示快照取自造冊（= 消耗配置學年度）
        allocation_year = roster.allocation_year

        # 計算申請身分別
        application_identity = None
        if application.is_renewal:
            application_identity = f"{application.academic_year}續領"
        else:
            application_identity = f"{application.academic_year}新申請"

        roster_item = PaymentRosterItem(
            roster_id=roster.id,
            application_id=application.id,
            student_id_number=student_data.get("std_pid", ""),  # 身分證字號 (national ID)
            student_number=student_data.get("std_stdcode", ""),  # 學號 — identity-matching key
            student_name=student_data.get("std_cname", ""),
            student_email=student_data.get("com_email", ""),
            bank_account=bank_account,  # From submitted_form_data, not student_data
            scholarship_name=application.scholarship_configuration.scholarship_type.name,
            scholarship_amount=application.amount or consumed_config.amount,
            scholarship_subtype=application.sub_scholarship_type,
            allocation_config_id=roster.allocation_config_id,  # 消耗配置 id 快照
            allocation_year=allocation_year,  # 消耗配置學年度顯示快照
            allocated_sub_type=allocated_sub_type,  # 分發到的子類型快照
            application_identity=application_identity,  # 申請身分快照
            verification_status=verification_status,
            verification_message=verification_result.get("message") if verification_result else None,
            verification_at=datetime.now(timezone.utc) if verification_result else None,
            verification_snapshot=self._serialize_verification_result(verification_result),
            is_included=is_included,
            exclusion_reason=exclusion_reason,
            # 儲存規則驗證結果
            rule_validation_result=eligibility_result,
            failed_rules=eligibility_result.get("failed_rules", []) if eligibility_result else [],
            warning_rules=eligibility_result.get("warning_rules", []) if eligibility_result else [],
            backup_info=backup_info,
        )

        self.db.add(roster_item)
        return roster_item

    def _serialize_verification_result(self, verification_result: Optional[Dict]) -> Optional[Dict]:
        """將驗證結果中的enum和datetime轉換為可JSON序列化的格式"""
        if not verification_result:
            return None

        def serialize_value(value):
            """遞歸序列化值"""
            if hasattr(value, "value"):  # Enum對象
                return value.value
            elif hasattr(value, "isoformat"):  # datetime對象
                return value.isoformat()
            elif isinstance(value, dict):
                return {k: serialize_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [serialize_value(item) for item in value]
            else:
                return value

        # 複製驗證結果以避免修改原始資料
        serialized_result = verification_result.copy()

        # 遞歸轉換所有值
        return serialize_value(serialized_result)

    def generate_period_label(self, roster_cycle: RosterCycle, target_date: datetime) -> str:
        """
        產生期間標記

        Args:
            roster_cycle: 造冊週期
            target_date: 目標日期

        Returns:
            str: 期間標記 (YYYY-MM, YYYY-H1/H2, YYYY)
        """
        if roster_cycle == RosterCycle.MONTHLY:
            return target_date.strftime("%Y-%m")  # 2025-01
        elif roster_cycle == RosterCycle.SEMI_YEARLY:
            half = "H1" if target_date.month <= 6 else "H2"
            return f"{target_date.year}-{half}"  # 2025-H1
        elif roster_cycle == RosterCycle.YEARLY:
            return str(target_date.year)  # 2025
        else:
            raise ValueError(f"Unsupported roster cycle: {roster_cycle}")

    def check_roster_exists(
        self, scholarship_configuration_id: int, period_label: str, include_locked: bool = True
    ) -> Optional[PaymentRoster]:
        """
        檢查指定獎學金配置和期間的造冊是否已存在

        Args:
            scholarship_configuration_id: 獎學金配置ID
            period_label: 期間標記
            include_locked: 是否包含已鎖定的造冊

        Returns:
            Optional[PaymentRoster]: 存在的造冊或None
        """
        query = self.db.query(PaymentRoster).filter(
            and_(
                PaymentRoster.scholarship_configuration_id == scholarship_configuration_id,
                PaymentRoster.period_label == period_label,
            )
        )

        if not include_locked:
            query = query.filter(PaymentRoster.status != RosterStatus.LOCKED)

        return query.first()

    def get_duplicate_rosters(self, scholarship_configuration_id: int, period_label: str) -> List[PaymentRoster]:
        """
        取得重複的造冊記錄（用於除錯）

        Args:
            scholarship_configuration_id: 獎學金配置ID
            period_label: 期間標記

        Returns:
            List[PaymentRoster]: 重複的造冊列表
        """
        return (
            self.db.query(PaymentRoster)
            .filter(
                and_(
                    PaymentRoster.scholarship_configuration_id == scholarship_configuration_id,
                    PaymentRoster.period_label == period_label,
                )
            )
            .order_by(PaymentRoster.created_at.desc())
            .all()
        )

    def _validate_student_eligibility(
        self,
        application: Application,
        academic_year: int,
        period_label: str,
        fresh_api_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        驗證學生是否符合該期的獎學金規則

        Args:
            application: 申請記錄
            academic_year: 學年度
            period_label: 期間標記 (YYYY-MM, YYYY-H1/H2, YYYY)
            fresh_api_data: 從 API 拉取的新鮮學生資料（優先使用）

        Returns:
            Dict[str, Any]: 驗證結果
            {
                "is_eligible": bool,
                "failed_rules": List[str],
                "warning_rules": List[str],
                "details": Dict[str, Any]
            }
        """
        try:
            student = application.student
            scholarship_config = application.scholarship_configuration

            if not scholarship_config or not student:
                if not student and not scholarship_config:
                    missing_reason = "缺少學生資訊/獎學金配置"
                elif not student:
                    missing_reason = "缺少學生資訊"
                else:
                    missing_reason = "缺少獎學金配置"

                return {
                    "is_eligible": False,
                    "failed_rules": [missing_reason],
                    "warning_rules": [],
                    "details": {},
                }

            # 取得該獎學金類型在該學年度的規則
            rules = self._get_scholarship_rules(
                scholarship_config.scholarship_type_id, academic_year, period_label, application.sub_scholarship_type
            )

            if not rules:
                # 沒有特定規則，假設符合資格
                return {
                    "is_eligible": True,
                    "failed_rules": [],
                    "warning_rules": [],
                    "details": {"no_rules_found": True},
                }

            # 驗證每條規則（使用新鮮 API 資料）
            failed_rules = []
            warning_rules = []
            details = {}

            for rule in rules:
                rule_result = self._evaluate_scholarship_rule(rule, student, application, fresh_api_data=fresh_api_data)

                if not rule_result["passed"]:
                    if rule.is_hard_rule:
                        failed_rules.append(rule_result["message"])
                    else:
                        # 軟性規則失敗不影響 is_eligible，但必須留下紀錄，
                        # 讓造冊 Excel 的資格欄位看得到（#1139）
                        warning_rules.append(rule_result["message"])

                details[f"rule_{rule.id}"] = rule_result

            # 如果有硬性規則未通過，則不符合資格
            is_eligible = len(failed_rules) == 0

            logger.info(
                f"Student eligibility check for application {application.id}: "
                f"eligible={is_eligible}, failed_rules={len(failed_rules)}, warnings={len(warning_rules)}"
            )

            return {
                "is_eligible": is_eligible,
                "failed_rules": failed_rules,
                "warning_rules": warning_rules,
                "details": details,
            }

        except Exception as e:
            logger.exception(f"Error validating student eligibility for application {application.id}")
            return {
                "is_eligible": False,
                "failed_rules": [f"驗證過程發生錯誤: {str(e)}"],
                "warning_rules": [],
                "details": {"error": str(e)},
            }

    def _get_scholarship_rules(
        self, scholarship_type_id: int, academic_year: int, period_label: str, sub_type: Optional[str] = None
    ) -> List[ScholarshipRule]:
        """取得特定獎學金類型和期間的規則"""

        # 從期間標記推導學期
        semester = None
        if period_label.endswith("-H1"):
            semester = "first"
        elif period_label.endswith("-H2"):
            semester = "second"
        elif period_label.endswith("-annual"):
            semester = None  # 全年度獎學金，不限學期
        elif "-" in period_label and len(period_label.split("-")) == 2:
            # 月份格式，可能需要根據月份推導學期
            year, month = period_label.split("-")
            try:
                month_int = int(month)
                if month_int in [2, 3, 4, 5, 6, 7]:
                    semester = "second"  # 下學期
                elif month_int in [8, 9, 10, 11, 12, 1]:
                    semester = "first"  # 上學期
            except ValueError:
                # month is not a number, leave semester as None
                logger.debug(f"Period label '{period_label}' does not contain numeric month, semester remains None")

        query = (
            self.db.query(ScholarshipRule)
            .filter(
                and_(
                    ScholarshipRule.scholarship_type_id == scholarship_type_id,
                    ScholarshipRule.is_active.is_(True),
                    or_(
                        ScholarshipRule.academic_year == academic_year,
                        ScholarshipRule.academic_year.is_(None),  # 通用規則
                    ),
                    or_(ScholarshipRule.semester == semester, ScholarshipRule.semester.is_(None)),  # 不限學期
                    or_(ScholarshipRule.sub_type == sub_type, ScholarshipRule.sub_type.is_(None)),  # 通用子類型
                )
            )
            .order_by(ScholarshipRule.priority.desc(), ScholarshipRule.id)
        )

        return query.all()

    def _evaluate_scholarship_rule(
        self, rule: ScholarshipRule, student, application: Application, fresh_api_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """評估單一獎學金規則"""

        try:
            # 根據規則類型獲取學生資料中的對應值（優先使用新鮮 API 資料）
            actual_value = self._get_student_field_value(
                rule.condition_field, student, application, fresh_api_data=fresh_api_data
            )

            # 評估條件
            passed = self._evaluate_condition(actual_value, rule.operator, rule.expected_value)

            message = rule.message or f"{rule.rule_name}: {rule.description}"

            return {
                "passed": passed,
                "rule_name": rule.rule_name,
                "rule_type": rule.rule_type,
                "actual_value": actual_value,
                "expected_value": rule.expected_value,
                "operator": rule.operator,
                "message": message,
                "is_hard_rule": rule.is_hard_rule,
                "is_warning": rule.is_warning,
            }

        except Exception as e:
            logger.exception(f"Error evaluating rule {rule.id}")
            return {
                "passed": False,
                "rule_name": rule.rule_name,
                "rule_type": rule.rule_type,
                "message": f"規則評估錯誤: {str(e)}",
                "error": str(e),
            }

    def _get_student_field_value(
        self, field_name: str, student, application: Application, fresh_api_data: Optional[Dict[str, Any]] = None
    ):
        """從學生或申請資料中獲取指定欄位的值"""

        # 最優先：檢查 fresh_api_data（API 當下拉取的資料）
        if fresh_api_data and (field_name.startswith("std_") or field_name.startswith("trm_")):
            value = fresh_api_data.get(field_name)
            if value is not None:
                logger.debug(f"Found field '{field_name}' = {value} in fresh_api_data (current API data)")
                return value

        # 次優先：檢查 application.student_data JSON 中的 API 資料（申請時的快照）
        if application.student_data and (field_name.startswith("std_") or field_name.startswith("trm_")):
            value = application.student_data.get(field_name)
            if value is not None:
                logger.debug(f"Found field '{field_name}' = {value} in application.student_data (snapshot)")
                return value

        # 常見的欄位映射
        field_mapping = {
            "gpa": lambda: getattr(student, "gpa", None),
            "ranking": lambda: getattr(student, "ranking", None),
            "nationality": lambda: getattr(student, "nationality", None),
            "department": lambda: getattr(student, "department", None),
            "grade": lambda: getattr(student, "grade", None),
            "student_type": lambda: getattr(student, "student_type", None),
            "term_count": lambda: getattr(application, "term_count", None),
            "previous_scholarship": lambda: getattr(application, "previous_scholarship", None),
        }

        if field_name in field_mapping:
            return field_mapping[field_name]()

        # 嘗試直接從學生物件獲取屬性
        if hasattr(student, field_name):
            return getattr(student, field_name)

        # 嘗試從申請物件獲取屬性
        if hasattr(application, field_name):
            return getattr(application, field_name)

        logger.warning(f"Unknown field name: {field_name}")
        return None

    def _evaluate_condition(self, actual_value, operator: str, expected_value: str) -> bool:
        """評估條件是否滿足"""

        if actual_value is None:
            return False

        try:
            # 根據操作符評估條件
            if operator == ">=":
                return float(actual_value) >= float(expected_value)
            elif operator == "<=":
                return float(actual_value) <= float(expected_value)
            elif operator == ">":
                return float(actual_value) > float(expected_value)
            elif operator == "<":
                return float(actual_value) < float(expected_value)
            elif operator == "==":
                return str(actual_value).strip() == str(expected_value).strip()
            elif operator == "!=":
                return str(actual_value).strip() != str(expected_value).strip()
            elif operator == "in":
                expected_list = [v.strip() for v in expected_value.split(",")]
                return str(actual_value).strip() in expected_list
            elif operator == "not_in":
                expected_list = [v.strip() for v in expected_value.split(",")]
                return str(actual_value).strip() not in expected_list
            elif operator == "contains":
                return str(expected_value).strip() in str(actual_value).strip()
            elif operator == "not_contains":
                return str(expected_value).strip() not in str(actual_value).strip()
            else:
                logger.warning(f"Unknown operator: {operator}")
                return False

        except (ValueError, TypeError):
            logger.exception(
                "Error evaluating condition: actual=%s, operator=%s, expected=%s",
                actual_value,
                operator,
                expected_value,
            )
            return False

    def dry_run_generate_roster(
        self,
        scholarship_configuration_id: int,
        period_label: str,
        roster_cycle: RosterCycle,
        academic_year: int,
        student_verification_enabled: bool = True,
    ) -> Dict[str, Any]:
        """
        造冊產生預演 - 模擬造冊產生過程但不實際建立資料
        Dry run roster generation - simulate the process without creating actual data
        """
        try:
            logger.info(
                f"Starting dry run for scholarship config {scholarship_configuration_id}, period {period_label}"
            )

            # 1. 檢查獎學金配置
            scholarship_config = (
                self.db.query(ScholarshipConfiguration)
                .filter(ScholarshipConfiguration.id == scholarship_configuration_id)
                .first()
            )

            if not scholarship_config:
                raise ValueError(f"找不到獎學金配置: ID {scholarship_configuration_id}")

            # 2. 檢查重複造冊
            existing_roster = self.check_roster_exists(scholarship_configuration_id, period_label)
            duplicate_check = {
                "has_duplicate": existing_roster is not None,
                "existing_roster_id": existing_roster.id if existing_roster else None,
                "existing_roster_code": existing_roster.roster_code if existing_roster else None,
                "existing_status": existing_roster.status.value if existing_roster else None,
            }

            # 3. 取得符合條件的申請
            eligible_applications = self._get_eligible_applications(
                scholarship_configuration_id, period_label, academic_year, ranking_id=None
            )

            # 4. 模擬學籍驗證和規則驗證
            estimated_items = []
            estimated_total_amount = 0
            potential_issues = []
            verification_summary = {"verified": 0, "failed": 0, "not_required": 0}

            for application in eligible_applications:
                try:
                    # 模擬規則驗證
                    eligibility_result = self._validate_student_eligibility(application, academic_year, period_label)
                    is_rule_passed = eligibility_result.get("is_eligible", False)

                    # 模擬學籍驗證
                    verification_status = StudentVerificationStatus.VERIFIED
                    verification_passed = True

                    if student_verification_enabled:
                        # 這裡只是模擬，不實際呼叫API
                        if application.student and application.student.student_number:
                            verification_status = StudentVerificationStatus.VERIFIED
                            verification_summary["verified"] += 1
                        else:
                            verification_status = StudentVerificationStatus.NOT_FOUND
                            verification_passed = False
                            verification_summary["failed"] += 1
                            potential_issues.append(
                                f"學生 {application.student.name if application.student else 'Unknown'} 缺少學號"
                            )
                    else:
                        verification_summary["not_required"] += 1

                    # 判斷是否合格
                    is_qualified = is_rule_passed and verification_passed

                    # 計算金額
                    amount = application.amount or scholarship_config.amount or 0
                    if is_qualified:
                        estimated_total_amount += amount

                    # 檢查學生資料完整性
                    if application.student:
                        if not application.student.bank_account:
                            potential_issues.append(f"學生 {application.student.name} 銀行資訊不完整")

                    estimated_items.append(
                        {
                            "application_id": application.id,
                            "student_name": application.student.name if application.student else "Unknown",
                            "student_id": application.student.student_number if application.student else "",
                            "amount": float(amount),
                            "is_qualified": is_qualified,
                            "verification_status": verification_status.value,
                            "rule_validation_passed": is_rule_passed,
                            "failed_rules": eligibility_result.get("failed_rules", []),
                        }
                    )

                except Exception as e:
                    potential_issues.append(f"處理申請 {application.id} 時發生錯誤: {str(e)}")
                    logger.warning(f"Error processing application {application.id} in dry run", exc_info=True)

            # 5. 產生驗證摘要
            validation_summary = {
                "total_applications": len(eligible_applications),
                "estimated_qualified": len([item for item in estimated_items if item["is_qualified"]]),
                "estimated_disqualified": len([item for item in estimated_items if not item["is_qualified"]]),
                "estimated_total_amount": float(estimated_total_amount),
                "verification_enabled": student_verification_enabled,
                "verification_stats": verification_summary,
                "potential_issues_count": len(potential_issues),
            }

            # 6. 產生期間標籤驗證
            try:
                target_date = datetime.now()
                generated_period_label = self.generate_period_label(roster_cycle, target_date)
                period_label_validation = {
                    "requested_period": period_label,
                    "generated_period": generated_period_label,
                    "period_match": period_label == generated_period_label,
                }
            except Exception as e:
                period_label_validation = {
                    "error": str(e),
                    "period_match": False,
                }

            result = {
                "scholarship_configuration_id": scholarship_configuration_id,
                "scholarship_name": (
                    scholarship_config.scholarship_type.name if scholarship_config.scholarship_type else "Unknown"
                ),
                "period_label": period_label,
                "roster_cycle": roster_cycle.value,
                "academic_year": academic_year,
                "estimated_items": len(estimated_items),
                "estimated_total_amount": float(estimated_total_amount),
                "potential_issues": potential_issues[:20],  # 限制問題數量
                "validation_summary": validation_summary,
                "duplicate_check": duplicate_check,
                "period_label_validation": period_label_validation,
                "generated_at": datetime.now().isoformat(),
                "dry_run": True,
            }

            logger.info(
                f"Dry run completed: {validation_summary['estimated_qualified']} qualified out of {len(eligible_applications)} applications"
            )

            return result

        except Exception as e:
            logger.exception("Dry run failed")
            raise ValueError("預演失敗") from e

    @staticmethod
    def _build_semester_filter(semester: Optional[str]):
        """SQLAlchemy filter selecting CollegeRanking rows for a semester.
        None / "annual" / "yearly" / "" all map to the yearly bucket
        (semester IS NULL OR "annual" OR "yearly"); otherwise exact match.
        Single source of truth shared by generation and reconcile so the diff
        stays the exact inverse of generation."""
        from app.models.college_review import CollegeRanking

        if semester in (None, "annual", "yearly", ""):
            return or_(
                CollegeRanking.semester.is_(None),
                CollegeRanking.semester == "annual",
                CollegeRanking.semester == "yearly",
            )
        return CollegeRanking.semester == semester

    def _build_application_semester_filter(self, semester: Optional[str]):
        """Semester predicate on Application.semester.
        None / "annual" / "yearly" / "" all map to the yearly bucket
        (semester IS NULL OR "yearly"); otherwise exact match.

        Unlike CollegeRanking.semester (String(20)), Application.semester is a
        native Postgres enum {first, second, yearly} — emitting "annual" here
        aborts the whole query with `invalid input value for enum semester`.
        Mirror _config_semester_condition, not the String-column helpers."""
        if semester in (None, "", "annual", "yearly"):
            return or_(
                Application.semester.is_(None),
                Application.semester == "yearly",
            )
        return Application.semester == semester

    def generate_rosters_from_distribution(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: str,
        created_by_user_id: int,
        student_verification_enabled: bool = True,
        force_regenerate: bool = False,
    ) -> "RosterGenerationResult":
        """
        從矩陣分發結果批次產生造冊

        針對每個唯一的 (allocation_config_id, sub_type) 組合建立獨立的造冊。
        例如：
          - 115 學年度分發完成後，若 nstc 借用了 phd_114/phd_113 的配額，
            產生 nstc·115、nstc·114、nstc·113、moe_1w·115 四個造冊，各自記錄消耗配置。

        Args:
            scholarship_type_id: 獎學金類型 ID
            academic_year: 學年度
            semester: 學期
            created_by_user_id: 操作者用戶 ID
            student_verification_enabled: 是否啟用學籍驗證
            force_regenerate: 是否強制重新產生已存在的造冊

        Returns:
            RosterGenerationResult: `.created` 為新產生的造冊，`.skipped` 為
            已存在且未重新產生的造冊（force_regenerate=False 時）。

        Raises:
            ValueError: 找不到排名、尚未完成分發、或其他驗證錯誤
        """
        from app.models.college_review import CollegeRanking, CollegeRankingItem

        # 1. 取得所有已完成分發的排名
        sem_filter = self._build_semester_filter(semester)

        rankings = (
            self.db.query(CollegeRanking)
            .filter(
                and_(
                    CollegeRanking.scholarship_type_id == scholarship_type_id,
                    CollegeRanking.academic_year == academic_year,
                    sem_filter,
                    CollegeRanking.is_finalized.is_(True),
                    CollegeRanking.distribution_executed.is_(True),
                )
            )
            .all()
        )

        ranking_ids = [r.id for r in rankings]

        # 2. 取得對應的獎學金配置
        scholarship_config = (
            self.db.query(ScholarshipConfiguration)
            .filter(
                and_(
                    ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                    ScholarshipConfiguration.academic_year == academic_year,
                )
            )
            .first()
        )

        if not scholarship_config:
            raise ValueError(
                f"找不到對應的獎學金配置：scholarship_type_id={scholarship_type_id}, " f"academic_year={academic_year}"
            )

        # 3a. 取得已核准的續領申請。續領申請永遠不會贏得 CollegeRankingItem
        # （它們被排除在配額分發之外），所以矩陣分發造冊路徑看不到它們。此處直接撈出，
        # 並以 (allocation_config_id, sub_scholarship_type) 為 key 併入分組 —— 與
        # ManualDistributionService 消耗配額所用的 key 一致。
        renewal_apps = (
            self.db.query(Application)
            .filter(
                and_(
                    Application.scholarship_type_id == scholarship_type_id,
                    Application.academic_year == academic_year,
                    Application.is_renewal.is_(True),
                    Application.status == "approved",
                    Application.deleted_at.is_(None),
                    self._build_application_semester_filter(semester),
                )
            )
            .all()
        )

        # 3b. 取得所有已分配的 ranking items，並按 (allocation_config_id, allocated_sub_type) 分組
        allocated_items = (
            self.db.query(CollegeRankingItem)
            .filter(
                and_(
                    CollegeRankingItem.ranking_id.in_(ranking_ids),
                    CollegeRankingItem.is_allocated.is_(True),
                )
            )
            .all()
            if ranking_ids
            else []
        )

        if not allocated_items and not renewal_apps:
            raise ValueError(
                "沒有可造冊的資料：找不到已分配的排名學生，也沒有已核准的續領。"
                "請先完成矩陣分發，或先匯入續領通過名單。"
            )

        # 分組：{(allocation_config_id, sub_type): [ranking_item, ...]}
        # allocation_config_id NULL ⇒ 消耗本配置（requesting config）的配額。
        groups: Dict[tuple, List] = {}
        for item in allocated_items:
            alloc_config_id = item.allocation_config_id or scholarship_config.id
            sub_type = item.allocated_sub_type or "general"
            key = (alloc_config_id, sub_type)
            groups.setdefault(key, []).append(item)

        # 將已核准的續領併入（可能是全新的）分組；記錄每個 key 的續領 application id。
        renewal_ids_by_key: Dict[tuple, set] = {}
        for app in renewal_apps:
            key = (app.allocation_config_id or scholarship_config.id, app.sub_scholarship_type or "general")
            renewal_ids_by_key.setdefault(key, set()).add(app.id)
            groups.setdefault(key, [])

        # 預先載入每個分組的「消耗配置」(consumed config) — 借用配額時是前年度的同代碼配置
        consumed_configs: Dict[int, ScholarshipConfiguration] = {scholarship_config.id: scholarship_config}
        for alloc_config_id, _sub_type in groups:
            if alloc_config_id not in consumed_configs:
                consumed = self.db.get(ScholarshipConfiguration, alloc_config_id)
                if consumed is None:
                    raise ValueError(f"找不到消耗配置 scholarship_configuration_id={alloc_config_id}")
                consumed_configs[alloc_config_id] = consumed

        logger.info(
            f"Rankings {ranking_ids}: found {len(allocated_items)} allocated items in {len(groups)} groups: "
            + ", ".join(f"{sub_type}-cfg{cid}({len(items)}人)" for (cid, sub_type), items in groups.items())
        )

        # 4. 為每個分組建立造冊（以該分組的消耗配置為準）
        created_rosters: List[PaymentRoster] = []
        skipped_rosters: List[PaymentRoster] = []
        locked_rosters: List[PaymentRoster] = []

        for (alloc_config_id, sub_type), group_items in groups.items():
            application_ids_in_group = {item.application_id for item in group_items}
            application_ids_in_group |= renewal_ids_by_key.get((alloc_config_id, sub_type), set())
            consumed_config = consumed_configs[alloc_config_id]

            try:
                roster = self._generate_one_sub_type_roster(
                    requesting_config=scholarship_config,
                    consumed_config=consumed_config,
                    ranking_ids=ranking_ids,
                    sub_type=sub_type,
                    application_ids_in_group=application_ids_in_group,
                    created_by_user_id=created_by_user_id,
                    student_verification_enabled=student_verification_enabled,
                    force_regenerate=force_regenerate,
                )
                created_rosters.append(roster)
            except RosterAlreadyExistsError as e:
                logger.info(f"Roster for (cfg={alloc_config_id}, {sub_type}) already exists, skipping.")
                if e.existing_roster is not None:
                    skipped_rosters.append(e.existing_roster)
                continue
            except RosterLockedError as e:
                # force_regenerate can't rebuild a locked roster. Report it
                # rather than aborting the whole batch (issue #1033) — the
                # honest message tells admins to use force, so don't let that
                # advice 500 when one roster in the batch is locked.
                logger.info(f"Roster for (cfg={alloc_config_id}, {sub_type}) is locked, cannot rebuild.")
                if e.roster is not None:
                    locked_rosters.append(e.roster)
                continue
            except Exception:
                logger.exception(f"Failed to generate roster for (cfg={alloc_config_id}, {sub_type})")
                raise

        self.db.commit()
        logger.info(
            f"Generated {len(created_rosters)} rosters "
            f"({len(skipped_rosters)} skipped as already-existing, "
            f"{len(locked_rosters)} locked) "
            f"from distribution rankings {ranking_ids}"
        )
        return RosterGenerationResult(created=created_rosters, skipped=skipped_rosters, locked=locked_rosters)

    def _generate_one_sub_type_roster(
        self,
        requesting_config: ScholarshipConfiguration,
        consumed_config: ScholarshipConfiguration,
        ranking_ids: List[int],
        sub_type: str,
        application_ids_in_group: set,
        created_by_user_id: int,
        student_verification_enabled: bool,
        force_regenerate: bool,
    ) -> PaymentRoster:
        """
        為特定 (consumed_config, sub_type) 組合產生一個造冊。

        計畫編號 / 金額 / allocation_year 顯示快照取自「消耗配置」(consumed_config)；
        造冊歸屬於發放配置 (requesting_config)。借用前年度配額時兩者不同。

        Returns:
            PaymentRoster: 已建立的造冊
        """
        academic_year = requesting_config.academic_year
        period_label = str(consumed_config.academic_year)  # 以消耗配置的學年度為期間 key
        allocation_year = consumed_config.academic_year  # 顯示快照

        # 取得計畫編號（扁平：consumed_config.project_numbers[sub_type]，無年度 key）
        project_number = None
        if consumed_config.project_numbers:
            project_number = consumed_config.project_numbers.get(sub_type)

        # 產生造冊代碼（包含 sub_type 與消耗配置代碼以確保唯一性）
        roster_code = f"ROSTER-{academic_year}-{sub_type}-{consumed_config.config_code}-{requesting_config.config_code}"

        # 檢查是否已存在（unique key: scholarship_configuration_id + period_label
        # + allocation_config_id + sub_type）
        existing_roster = (
            self.db.query(PaymentRoster)
            .filter(
                and_(
                    PaymentRoster.scholarship_configuration_id == requesting_config.id,
                    PaymentRoster.period_label == period_label,
                    PaymentRoster.sub_type == sub_type,
                    PaymentRoster.allocation_config_id == consumed_config.id,
                )
            )
            .first()
        )

        if existing_roster and not force_regenerate:
            raise RosterAlreadyExistsError(
                f"造冊已存在：{sub_type} {allocation_year} 年度。使用 force_regenerate=True 可覆蓋。",
                existing_roster=existing_roster,
            )

        if existing_roster and existing_roster.is_locked:
            raise RosterLockedError(
                f"無法重新產生已鎖定的造冊：{existing_roster.roster_code}",
                roster=existing_roster,
            )

        user = self.db.query(User).filter(User.id == created_by_user_id).first()
        user_name = user.name if user else "Unknown"

        if existing_roster and force_regenerate:
            roster = existing_roster
            roster.status = RosterStatus.PROCESSING
            roster.trigger_type = RosterTriggerType.MANUAL
            roster.student_verification_enabled = student_verification_enabled
            roster.started_at = datetime.now(timezone.utc)
            roster.completed_at = None
            roster.total_applications = 0
            roster.qualified_count = 0
            roster.disqualified_count = 0
            roster.total_amount = 0
            roster.verification_api_failures = 0
            roster.project_number = project_number
            roster.allocation_config_id = consumed_config.id
            roster.allocation_year = allocation_year
            self.db.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster.id).delete()
            logger.info(f"Regenerating roster {roster_code}")
        else:
            roster = PaymentRoster(
                roster_code=roster_code,
                scholarship_configuration_id=requesting_config.id,
                allocation_config_id=consumed_config.id,
                ranking_id=ranking_ids[0] if ranking_ids else None,  # Use first ranking_id for reference
                period_label=period_label,
                academic_year=academic_year,
                roster_cycle=RosterCycle.YEARLY,
                sub_type=sub_type,
                allocation_year=allocation_year,  # 顯示快照 = 消耗配置學年度
                project_number=project_number,
                status=RosterStatus.PROCESSING,
                trigger_type=RosterTriggerType.MANUAL,
                created_by=created_by_user_id,
                student_verification_enabled=student_verification_enabled,
                started_at=datetime.now(timezone.utc),
            )
            self.db.add(roster)
            self.db.flush()
            logger.info(f"Creating roster {roster_code} ({len(application_ids_in_group)} students)")

        # 取得本組的申請
        applications = (
            self.db.query(Application)
            .filter(
                and_(
                    Application.id.in_(application_ids_in_group),
                    Application.status == "approved",
                )
            )
            .all()
        )

        roster.total_applications = len(applications)

        qualified_count = 0
        disqualified_count = 0
        total_amount = 0
        verification_failures = 0

        for application in applications:
            try:
                stored_student_data = application.student_data or {}
                student_id_number = stored_student_data.get("std_stdcode")
                student_name = stored_student_data.get("std_cname")

                if not student_id_number or not student_name:
                    logger.warning(f"Application {application.id} missing student ID or name")
                    disqualified_count += 1
                    continue

                verification_result = None
                verification_status = StudentVerificationStatus.VERIFIED
                fresh_student_data = None

                if student_verification_enabled:
                    verification_result = self.student_verification_service.verify_student(
                        student_id_number, student_name
                    )
                    verification_status = verification_result.get("status", StudentVerificationStatus.VERIFIED)
                    if verification_status == StudentVerificationStatus.API_ERROR:
                        verification_failures += 1
                    else:
                        fresh_student_data = verification_result.get("student_info", {})

                eligibility_result = self._validate_student_eligibility(
                    application, academic_year, period_label, fresh_api_data=fresh_student_data
                )

                roster_item = self._create_roster_item(
                    roster, application, verification_result, verification_status, eligibility_result
                )

                if roster_item.is_qualified:
                    qualified_count += 1
                    total_amount += roster_item.scholarship_amount
                else:
                    disqualified_count += 1

            except Exception:
                logger.exception(f"Error processing application {application.id}")
                disqualified_count += 1

        roster.qualified_count = qualified_count
        roster.disqualified_count = disqualified_count
        roster.total_amount = total_amount
        roster.verification_api_failures = verification_failures
        roster.status = RosterStatus.COMPLETED
        roster.completed_at = datetime.now(timezone.utc)

        # Business metric: roster reached the completed state. Pairs
        # with the "processing" increment at creation so dashboards can
        # show completion ratio over time (issue #159).
        payment_rosters_total.labels(status="completed").inc()

        self.db.flush()

        logger.info(
            f"Roster {roster_code} completed: {qualified_count} qualified, "
            f"{disqualified_count} disqualified, total {total_amount}"
        )

        # 產生 Excel 並上傳至 MinIO（在 sync 環境中執行，避免 greenlet 問題）
        from app.services.excel_export_service import ExcelExportService

        try:
            export_service = ExcelExportService()
            export_service.export_roster_to_excel(
                roster=roster,
                template_name="STD_UP_MIXLISTA",
                include_header=True,
                include_statistics=True,
                include_excluded=False,
            )
            self.db.flush()  # Persist minio_object_name and excel_filename
            logger.info(f"Excel generated for roster {roster_code}: {roster.minio_object_name}")
        except Exception:
            logger.exception(f"Failed to generate Excel for roster {roster_code}")

        audit_service.log_roster_operation(
            roster_id=roster.id,
            action=RosterAuditAction.CREATE,
            title=f"批次造冊產生: {sub_type} {allocation_year}年度 合格{qualified_count}人",
            user_id=created_by_user_id,
            user_name=user_name,
            description=f"計畫編號: {project_number or '未設定'}，總金額: ${total_amount}",
            old_values=None,
            new_values=None,
            level=RosterAuditLevel.INFO,
            affected_items_count=qualified_count + disqualified_count,
            metadata={
                "sub_type": sub_type,
                "allocation_year": allocation_year,
                "project_number": project_number,
                "qualified_count": qualified_count,
                "disqualified_count": disqualified_count,
                "total_amount": float(total_amount),
            },
            tags=["batch_generation", sub_type],
            db=self.db,
        )

        return roster

    # ------------------------------------------------------------------
    # Post-lock roster item management
    # ------------------------------------------------------------------

    def get_revoked_suspended_for_roster(self, roster_id: int) -> dict:
        """Return revoked / suspended entries for a roster — i.e. items still
        present in this (LOCKED) roster whose linked Application has been
        revoked or suspended after the lock."""
        rows = (
            self.db.query(PaymentRosterItem, Application)
            .join(Application, PaymentRosterItem.application_id == Application.id)
            .filter(
                PaymentRosterItem.roster_id == roster_id,
                # Only items STILL active in the roster. A soft-removed item
                # (is_included=False, e.g. 鎖定後移除 / 排除) has already been
                # handled and must NOT linger in the 撤銷/停發 needs-attention
                # panel (pre soft-delete it was hard-deleted, so it vanished).
                PaymentRosterItem.is_included.is_(True),
                Application.quota_allocation_status.in_(("revoked", "suspended")),
            )
            .all()
        )
        revoked, suspended = [], []
        for item, app in rows:
            entry = RevokedSuspendedEntry(
                application_id=app.id,
                student_name=item.student_name,
                # 身分證字號 masked for the needs-attention panel (display only).
                # The roster Excel export reads item.student_id_number directly
                # and keeps the full national ID for the payment process.
                student_id_number=mask_id_number(item.student_id_number),
                event_at=(app.revoked_at if app.quota_allocation_status == "revoked" else app.suspended_at),
                reason=(app.revoke_reason if app.quota_allocation_status == "revoked" else app.suspend_reason),
                item_id=item.id,
            )
            (revoked if app.quota_allocation_status == "revoked" else suspended).append(entry)
        return {"revoked": revoked, "suspended": suspended}

    def _recompute_roster_totals_sync(self, roster_id: int) -> tuple:
        """Recompute + persist total_applications / qualified_count /
        disqualified_count / total_amount for a roster from its items.
        Returns (qualified, total_count, total_amount). SYNC."""
        total_count, qualified, total_amount = (
            self.db.query(
                func.count(PaymentRosterItem.id),
                func.coalesce(
                    func.sum(sa_case((PaymentRosterItem.is_included.is_(True), 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        sa_case(
                            (PaymentRosterItem.is_included.is_(True), PaymentRosterItem.scholarship_amount),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .filter(PaymentRosterItem.roster_id == roster_id)
            .one()
        )
        roster = self.db.get(PaymentRoster, roster_id)
        roster.total_applications = total_count
        roster.qualified_count = qualified
        roster.disqualified_count = total_count - qualified
        roster.total_amount = total_amount
        return qualified, total_count, total_amount

    _AUDIT_ACTION_LABELS = {
        RosterAuditAction.ITEM_REMOVE: "移除",
        RosterAuditAction.ITEM_ADD: "新增",
        RosterAuditAction.ITEM_RESTORE: "回復",
    }

    def _write_roster_item_audit(
        self,
        roster_id: int,
        action: "RosterAuditAction",
        item: "PaymentRosterItem",
        admin_user_id: int,
        source: str,
        reason: Optional[str] = None,
    ) -> None:
        """Add (not commit) one RosterAuditLog row for an item-level mutation.
        Caller commits. `source` is one of exclude/reconcile/locked_remove/restore."""
        user = self.db.get(User, admin_user_id)
        student_id = None
        if item.application is not None and item.application.student_data:
            student_id = item.application.student_data.get("std_stdcode")
        label = self._AUDIT_ACTION_LABELS.get(action, action.value)
        self.db.add(
            RosterAuditLog.create_audit_log(
                roster_id=roster_id,
                action=action,
                title=f"{label} {item.student_name}",
                description=f"{label} {item.student_name}（原因：{reason or '—'}）",
                user_id=admin_user_id,
                user_name=user.name if user else None,
                user_role=(user.role.value if user and user.role else None),
                audit_metadata={
                    "student_name": item.student_name,
                    "student_id": student_id,
                    "application_id": item.application_id,
                    "source": source,
                    "reason": reason,
                },
                affected_items_count=1,
            )
        )

    def _resolve_distribution_for_roster(
        self, roster: PaymentRoster, config: Optional[ScholarshipConfiguration] = None
    ) -> dict:
        """Return {application_id: CollegeRankingItem} for allocated ranking
        items that belong in THIS roster's (allocation_year, sub_type) group,
        across all finalized + distribution_executed rankings for the roster's
        scholarship_type / academic_year / semester. Mirrors
        generate_rosters_from_distribution grouping exactly."""
        from app.models.college_review import CollegeRanking, CollegeRankingItem

        if config is None:
            config = self.db.get(ScholarshipConfiguration, roster.scholarship_configuration_id)
        if config is None:
            raise ValueError(f"Scholarship configuration {roster.scholarship_configuration_id} not found")

        semester = (
            (config.semester.value if hasattr(config.semester, "value") else config.semester)
            if config.semester
            else None
        )
        sem_filter = self._build_semester_filter(semester)

        rankings = (
            self.db.query(CollegeRanking)
            .filter(
                and_(
                    CollegeRanking.scholarship_type_id == config.scholarship_type_id,
                    CollegeRanking.academic_year == config.academic_year,
                    sem_filter,
                    CollegeRanking.is_finalized.is_(True),
                    CollegeRanking.distribution_executed.is_(True),
                )
            )
            .all()
        )
        ranking_ids = [r.id for r in rankings]
        if not ranking_ids:
            return {}

        allocated = (
            self.db.query(CollegeRankingItem)
            .options(joinedload(CollegeRankingItem.application))
            .filter(
                and_(
                    CollegeRankingItem.ranking_id.in_(ranking_ids),
                    CollegeRankingItem.is_allocated.is_(True),
                )
            )
            .all()
        )

        # Whole-period roster (generate_roster / 立即產生造冊): sub_type and
        # allocation_config_id are both NULL because that path holds EVERY
        # allocated item in the ranking regardless of sub_type (mirrors
        # _get_eligible_applications matrix mode). Slicing by a derived "general"
        # sub_type would exclude every nstc/moe item → empty diff. So for these,
        # the distribution is the full allocated set, no slicing.
        if roster.sub_type is None and roster.allocation_config_id is None:
            return {item.application_id: item for item in allocated}

        # Per-slice roster (generate_rosters_from_distribution): one roster per
        # (allocation_config_id, sub_type) group — match that exact group.
        # allocation_config_id NULL on an item ⇒ consumed the requesting config.
        roster_config_id = roster.allocation_config_id or config.id
        roster_sub = roster.sub_type or "general"

        result: dict = {}
        for item in allocated:
            item_config_id = item.allocation_config_id or config.id
            item_sub = item.allocated_sub_type or "general"
            if item_config_id == roster_config_id and item_sub == roster_sub:
                result[item.application_id] = item
        return result

    def get_distribution_diff_for_roster(self, roster_id: int) -> dict:
        """Compute the diff between this roster and its slice of the
        distribution. Returns a dict with to_add (allocated-but-missing) and
        to_remove (in-roster-but-unallocated) lists of DistributionDiffEntry."""
        from app.models.application import ApplicationStatus

        roster = self.db.get(PaymentRoster, roster_id)
        if roster is None:
            raise ValueError(f"Roster {roster_id} not found")

        config = self.db.get(ScholarshipConfiguration, roster.scholarship_configuration_id)
        if config is None:
            raise ValueError(f"Scholarship configuration {roster.scholarship_configuration_id} not found")
        allocated_map = self._resolve_distribution_for_roster(roster, config=config)

        existing_items = self.db.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster_id).all()
        existing_app_ids = {it.application_id for it in existing_items}

        to_add = []
        for app_id, ranking_item in allocated_map.items():
            if app_id in existing_app_ids:
                continue
            application = ranking_item.application
            if application is None or application.status != ApplicationStatus.approved:
                continue
            sd = application.student_data or {}
            std_code = sd.get("std_stdcode")
            std_name = sd.get("std_cname")
            if not std_code or not std_name:
                # _verify_and_create_item rejects these (ValueError), so offering
                # them as addable would mislead the admin. Skip — but log rather
                # than silently drop so a bad snapshot is still visible.
                logger.warning(
                    "Roster %s: skipping to_add candidate application %s — "
                    "student_data missing std_stdcode/std_cname",
                    roster_id,
                    app_id,
                )
                continue
            consumed = (
                self.db.get(ScholarshipConfiguration, ranking_item.allocation_config_id)
                if ranking_item.allocation_config_id is not None
                else config
            ) or config
            to_add.append(
                DistributionDiffEntry(
                    application_id=app_id,
                    item_id=None,
                    student_id=std_code,
                    student_name=std_name,
                    department_name=sd.get("trm_depname"),
                    college_name=sd.get("trm_academyname"),
                    allocation_year=consumed.academic_year,
                    allocated_sub_type=ranking_item.allocated_sub_type,
                    application_identity=None,
                    scholarship_amount=float(application.amount or consumed.amount or 0),
                )
            )

        orphan_app_ids = {it.application_id for it in existing_items if it.application_id not in allocated_map}
        orphan_apps = (
            self.db.query(Application).filter(Application.id.in_(orphan_app_ids)).all() if orphan_app_ids else []
        )
        apps_by_id = {a.id: a for a in orphan_apps}

        to_remove = []
        for item in existing_items:
            if item.application_id in allocated_map:
                continue
            if not item.is_included:
                # Already soft-removed — not an actionable orphan anymore.
                continue
            app = apps_by_id.get(item.application_id)
            sd = (app.student_data or {}) if app else {}
            to_remove.append(
                DistributionDiffEntry(
                    application_id=item.application_id,
                    item_id=item.id,
                    # 學號 (std_stdcode) only — do NOT fall back to
                    # item.student_id_number (that is the national ID / std_pid,
                    # which would render under the 學號 column in the UI).
                    student_id=sd.get("std_stdcode"),
                    student_name=item.student_name,
                    department_name=sd.get("trm_depname"),
                    college_name=sd.get("trm_academyname"),
                    allocation_year=item.allocation_year,
                    allocated_sub_type=item.allocated_sub_type,
                    application_identity=item.application_identity,
                    scholarship_amount=float(item.scholarship_amount or 0),
                )
            )

        return {
            "roster_id": roster.id,
            "roster_code": roster.roster_code,
            "status": roster.status.value,
            "allocation_year": roster.allocation_year,
            "sub_type": roster.sub_type,
            "to_add": to_add,
            "to_remove": to_remove,
        }

    def _verify_and_create_item(self, roster: PaymentRoster, application: Application) -> PaymentRosterItem:
        """Verify (if enabled) + validate eligibility + build a PaymentRosterItem.
        Mirrors the generation per-application block. self.db.add()s the item
        (does NOT flush/commit) and returns it."""
        sd = application.student_data or {}
        student_id_number = sd.get("std_stdcode")
        student_name = sd.get("std_cname")
        if not student_id_number or not student_name:
            raise ValueError(f"Application {application.id} is missing student ID or name in student_data")

        verification_result = None
        verification_status = StudentVerificationStatus.VERIFIED
        fresh_student_data = None

        if roster.student_verification_enabled:
            verification_result = self.student_verification_service.verify_student(
                sd.get("std_stdcode"), sd.get("std_cname")
            )
            verification_status = verification_result.get("status", StudentVerificationStatus.VERIFIED)
            if verification_status != StudentVerificationStatus.API_ERROR:
                fresh_student_data = verification_result.get("student_info", {})

        eligibility_result = self._validate_student_eligibility(
            application, roster.academic_year, roster.period_label, fresh_api_data=fresh_student_data
        )
        return self._create_roster_item(
            roster, application, verification_result, verification_status, eligibility_result
        )

    def reconcile_roster(
        self,
        roster_id: int,
        add_application_ids: List[int],
        remove_item_ids: List[int],
        admin_user_id: int,
        reason: Optional[str] = None,
    ) -> dict:
        """Apply a selective add/remove against a generated roster, validated
        against the server-re-derived distribution diff. Works on COMPLETED and
        LOCKED rosters. Recomputes totals, sets excel_stale=True, audits each
        change, commits. NEVER touches quota_allocation_status."""
        from app.models.application import ApplicationStatus

        roster = self.db.get(PaymentRoster, roster_id)
        if roster is None:
            raise ValueError(f"Roster {roster_id} not found")
        if roster.status not in (RosterStatus.COMPLETED, RosterStatus.LOCKED):
            raise RosterLockedError(
                f"Roster {roster_id} must be COMPLETED or LOCKED to reconcile " f"(status={roster.status.value})"
            )

        add_ids = list(dict.fromkeys(add_application_ids or []))
        remove_ids = list(dict.fromkeys(remove_item_ids or []))

        # Re-derive allowed sets — never trust the client.
        allocated_map = self._resolve_distribution_for_roster(roster)
        existing_items = self.db.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster_id).all()
        existing_app_ids = {it.application_id for it in existing_items}
        items_by_id = {it.id: it for it in existing_items}

        allowed_add = {
            aid
            for aid, ri in allocated_map.items()
            if aid not in existing_app_ids
            and ri.application is not None
            and ri.application.status == ApplicationStatus.approved
        }
        allowed_remove = {it.id for it in existing_items if it.is_included and it.application_id not in allocated_map}

        bad_add = [a for a in add_ids if a not in allowed_add]
        if bad_add:
            raise ValueError(f"Applications {bad_add} are not addable from the current distribution diff")
        bad_remove = [r for r in remove_ids if r not in allowed_remove]
        if bad_remove:
            raise ValueError(f"Items {bad_remove} are not removable from the current distribution diff")

        added, removed = [], []

        for app_id in add_ids:
            application = self.db.get(Application, app_id)
            if application is None:
                raise ValueError(f"Application {app_id} not found")
            # Defensive: if a (soft-removed) item already exists for this app,
            # restore it instead of creating a duplicate row (no DB unique
            # constraint protects us). Unreachable via the gated diff today,
            # but keeps the invariant if gating changes.
            existing = next((it for it in existing_items if it.application_id == app_id), None)
            if existing is not None:
                existing.is_included = True
                existing.exclusion_reason = None
                item = existing
                action = RosterAuditAction.ITEM_RESTORE
            else:
                item = self._verify_and_create_item(roster, application)
                action = RosterAuditAction.ITEM_ADD
            self.db.flush()
            added.append(
                {
                    "application_id": app_id,
                    "item_id": item.id,
                    "is_included": item.is_included,
                    "exclusion_reason": item.exclusion_reason,
                }
            )
            self._write_roster_item_audit(
                roster_id=roster_id,
                action=action,
                item=item,
                admin_user_id=admin_user_id,
                source="reconcile",
                reason=reason,
            )

        for item_id in remove_ids:
            item = items_by_id[item_id]
            item.is_included = False
            item.exclusion_reason = f"{MANUAL_REMOVAL_PREFIX_RECONCILE}：不在分發名單"
            removed.append({"item_id": item_id, "application_id": item.application_id})
            self._write_roster_item_audit(
                roster_id=roster_id,
                action=RosterAuditAction.ITEM_REMOVE,
                item=item,
                admin_user_id=admin_user_id,
                source="reconcile",
                reason=reason,
            )

        self.db.flush()
        qualified, total_count, total_amount = self._recompute_roster_totals_sync(roster_id)
        if added or removed:
            roster.excel_stale = True

        self.db.commit()

        return {
            "added": added,
            "removed": removed,
            "qualified_count": qualified,
            "total_applications": total_count,
            "total_amount": float(total_amount),
            "excel_stale": roster.excel_stale,
        }

    def remove_item_from_locked_roster(
        self,
        roster_id: int,
        item_id: int,
        admin_user_id: int,
        reason: Optional[str],
        reason_category: Optional[str] = None,
    ) -> dict:
        """Soft-remove a PaymentRosterItem from a LOCKED roster (sets is_included=False; row survives for restore).
        Recompute roster totals, set excel_stale=True, write RosterAuditLog. Roster stays LOCKED."""
        roster = self.db.get(PaymentRoster, roster_id)
        if roster is None:
            raise ValueError(f"Roster {roster_id} not found")
        if roster.status != RosterStatus.LOCKED:
            raise RosterLockedError(f"Roster {roster_id} is not LOCKED (status={roster.status.value})")

        item = self.db.get(PaymentRosterItem, item_id)
        if item is None or item.roster_id != roster_id:
            raise ValueError(f"Item {item_id} not found in roster {roster_id}")

        item.is_included = False
        # G26 (#988): keep the structured category in front of the free text
        # so removals are classifiable (e.g. "鎖定後移除[withdrawal]：休學").
        category_tag = f"[{reason_category}]" if reason_category else ""
        item.exclusion_reason = (
            f"{MANUAL_REMOVAL_PREFIX_LOCKED}{category_tag}：{reason}"
            if reason
            else f"{MANUAL_REMOVAL_PREFIX_LOCKED}{category_tag}"
        )
        self.db.flush()

        # Recompute totals via the shared sync helper (persists
        # total_applications / qualified_count / disqualified_count / total_amount).
        qualified, total_count, total_amount = self._recompute_roster_totals_sync(roster_id)
        roster.excel_stale = True

        self._write_roster_item_audit(
            roster_id=roster_id,
            action=RosterAuditAction.ITEM_REMOVE,
            item=item,
            admin_user_id=admin_user_id,
            source="locked_remove",
            reason=reason,
        )
        self.db.commit()
        return {
            "roster_id": roster_id,
            "removed_item_id": item_id,
            "qualified_count": qualified,
            "total_amount": float(total_amount),
            "excel_stale": True,
        }

    def restore_item(
        self,
        roster_id: int,
        item_id: int,
        admin_user_id: int,
        reason: Optional[str] = None,
    ) -> dict:
        """Re-include a soft-removed PaymentRosterItem. Works on COMPLETED and
        LOCKED rosters. Recompute totals, set excel_stale=True, write
        RosterAuditLog(ITEM_RESTORE).

        Raises (mapped to HTTP by the global ScholarshipException handler / the
        endpoint): RosterNotFoundError / NotFoundError -> 404, ConflictError
        (already-included, idempotency) -> 409, ValueError (wrong roster / not a
        restorable status) -> 400."""
        roster = self.db.get(PaymentRoster, roster_id)
        if roster is None:
            raise RosterNotFoundError(str(roster_id))

        if roster.status not in (RosterStatus.COMPLETED, RosterStatus.LOCKED):
            raise ValueError(
                f"Roster {roster_id} must be COMPLETED or LOCKED to restore items " f"(status={roster.status.value})"
            )

        item = self.db.get(PaymentRosterItem, item_id)
        if item is None:
            raise NotFoundError("Roster item", str(item_id))
        if item.roster_id != roster_id:
            raise ValueError(f"Item {item_id} does not belong to roster {roster_id}")
        if item.is_included:
            raise ConflictError("明細未被移除，無需回復")

        # #1081 finding K: re-read the underlying application's status before
        # re-including. restore_item legitimately handles the quota
        # revoke/suspend flow (status == cancelled), so we do NOT require
        # `approved`; but an application the student has since WITHDRAWN, or that
        # was REJECTED/DELETED, must not be silently re-included — that would
        # inflate the student's received_months (feeds the PhD 36-month cap).
        from app.models.application import ApplicationStatus

        _NON_RESTORABLE = {
            ApplicationStatus.withdrawn,
            ApplicationStatus.rejected,
            ApplicationStatus.deleted,
        }
        # A missing application row cannot happen in production (item.application_id
        # is a NOT-NULL FK), so we only BLOCK on a positively-bad status — never on
        # None — to avoid changing behavior for dangling-id contract fixtures.
        application = self.db.get(Application, item.application_id)
        if application is not None and application.status in _NON_RESTORABLE:
            raise ValueError(
                f"無法回復：申請目前狀態為 {application.status.value}，" "已撤回／駁回／刪除的申請不可回復造冊明細"
            )

        item.is_included = True
        item.exclusion_reason = None
        self.db.flush()

        qualified, total_count, total_amount = self._recompute_roster_totals_sync(roster_id)
        roster.excel_stale = True

        self._write_roster_item_audit(
            roster_id=roster_id,
            action=RosterAuditAction.ITEM_RESTORE,
            item=item,
            admin_user_id=admin_user_id,
            source="restore",
            reason=reason,
        )
        self.db.commit()
        return {
            "roster_id": roster_id,
            "restored_item_id": item_id,
            "qualified_count": qualified,
            "total_amount": float(total_amount),
            "excel_stale": True,
        }

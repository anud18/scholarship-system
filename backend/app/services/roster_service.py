"""
造冊服務核心邏輯
Roster service core logic for scholarship payment roster generation
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.exceptions import RosterAlreadyExistsError, RosterGenerationError, RosterLockedError, RosterNotFoundError
from app.models.application import Application
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.roster_audit import RosterAuditAction, RosterAuditLevel
from app.models.scholarship import ScholarshipConfiguration, ScholarshipRule
from app.models.user import User
from app.services.audit_service import audit_service
from app.services.student_verification_service import StudentVerificationService

logger = logging.getLogger(__name__)


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
                    started_at=datetime.now(timezone.utc),
                )
                self.db.add(roster)
                self.db.flush()  # 取得ID

                logger.info(f"Creating new roster {roster_code}")

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
            applications = self._get_eligible_applications(scholarship_configuration_id, period_label, academic_year)

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

                    # 學籍API驗證並更新學生資料
                    verification_result = None
                    verification_status = StudentVerificationStatus.VERIFIED

                    if student_verification_enabled:
                        # 呼叫學籍API取得最新資料
                        verification_result = self.student_verification_service.verify_student(
                            student_id_number, student_name
                        )
                        verification_status = verification_result.get("status", StudentVerificationStatus.VERIFIED)

                        if verification_status == StudentVerificationStatus.API_ERROR:
                            verification_failures += 1
                        else:
                            # 檢查API回傳的學生資料是否與Application中的資料有差異
                            api_student_data = verification_result.get("student_info", {})
                            if api_student_data:
                                # 比較關鍵欄位，如有差異則更新
                                fields_to_check = [
                                    "name",
                                    "department",
                                    "grade",
                                    "gpa",
                                    "email",
                                    "phone",
                                    "address",
                                    "bank_account",
                                ]
                                has_changes = False
                                updated_fields = []

                                for field in fields_to_check:
                                    if field in api_student_data and api_student_data[field] != stored_student_data.get(
                                        field
                                    ):
                                        old_value = stored_student_data.get(field)
                                        stored_student_data[field] = api_student_data[field]
                                        has_changes = True
                                        updated_fields.append(field)
                                        logger.info(
                                            f"Updated {field} for application {application.id}: {old_value} -> {api_student_data[field]}"
                                        )

                                if has_changes:
                                    # 更新Application的student_data欄位
                                    application.student_data = stored_student_data
                                    self.db.add(application)

                                    # 記錄更新日誌
                                    audit_service.log_roster_operation(
                                        roster_id=roster.id,
                                        action=RosterAuditAction.ITEM_UPDATE,
                                        title=f"更新申請 {application.id} 的學生資料",
                                        user_id=created_by_user_id,
                                        user_name=user_name,
                                        description=f"學籍驗證後更新欄位: {', '.join(updated_fields)}",
                                        old_values={f: stored_student_data.get(f) for f in updated_fields},
                                        new_values={
                                            f: api_student_data[f] for f in updated_fields if f in api_student_data
                                        },
                                        level=RosterAuditLevel.INFO,
                                        metadata={
                                            "application_id": application.id,
                                            "updated_fields": updated_fields,
                                            "verification_status": verification_result.get("status").value
                                            if verification_result.get("status")
                                            else None,
                                            "verification_message": verification_result.get("message")
                                            if verification_result
                                            else None,
                                        },
                                        tags=["student_data_update", "verification"],
                                        db=self.db,
                                    )

                    # 驗證學生是否符合該期的獎學金規則
                    eligibility_result = self._validate_student_eligibility(
                        application, roster.academic_year, roster.period_label
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
                    logger.error(f"Error processing application {application.id}: {e}")
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
            roster.completed_at = datetime.now(timezone.utc)
            roster.status = RosterStatus.COMPLETED

            # 記錄完成日誌
            audit_service.log_roster_operation(
                roster_id=roster.id,
                action=RosterAuditAction.STATUS_CHANGE,
                title=f"造冊產生完成: 合格{qualified_count}人, 不合格{disqualified_count}人",
                user_id=created_by_user_id,
                user_name=user_name,
                description=f"造冊產生完成，總金額: ${total_amount}，API失敗: {verification_failures}次",
                old_values={"status": "processing"},
                new_values={"status": "completed"},
                level=RosterAuditLevel.INFO,
                affected_items_count=qualified_count + disqualified_count,
                metadata={
                    "qualified_count": qualified_count,
                    "disqualified_count": disqualified_count,
                    "total_amount": float(total_amount),
                    "verification_failures": verification_failures,
                },
                tags=["completion", trigger_type.value],
                db=self.db,
            )

            self.db.commit()
            logger.info(f"Roster {roster_code} generated successfully")

            return roster

        except Exception as e:
            self.db.rollback()
            logger.error(f"Error generating roster: {e}")
            raise RosterGenerationError(f"Failed to generate roster: {e}")

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
        self, scholarship_configuration_id: int, period_label: str, academic_year: int
    ) -> List[Application]:
        """取得符合條件的申請"""
        # 基本條件：已核准的申請
        query = (
            self.db.query(Application)
            .join(ScholarshipConfiguration)
            .filter(
                and_(
                    ScholarshipConfiguration.id == scholarship_configuration_id,
                    Application.status == "approved",  # 已核准
                    Application.academic_year == academic_year,
                )
            )
        )

        # 根據期間標記篩選
        if period_label.endswith("-H1") or period_label.endswith("-H2"):
            # 半年期間 - 根據學期篩選
            semester = "first" if period_label.endswith("-H1") else "second"
            query = query.filter(Application.semester == semester)
        elif "-" in period_label and len(period_label.split("-")) == 2:
            # 月份期間 - 可以根據申請日期或其他條件篩選
            year, month = period_label.split("-")
            # 這裡可以加入更細緻的月份篩選邏輯
            pass

        return query.all()

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

        # 判斷是否納入造冊
        is_included = True
        exclusion_reason = None

        # 1. 檢查學籍驗證狀態
        if verification_status != StudentVerificationStatus.VERIFIED:
            is_included = False
            exclusion_reason = f"學籍驗證未通過: {verification_status.value}"
        # 2. 檢查獎學金規則符合性
        elif eligibility_result and not eligibility_result.get("is_eligible", True):
            is_included = False
            failed_rules = eligibility_result.get("failed_rules", [])
            if failed_rules:
                exclusion_reason = f"不符合獎學金規則: {'; '.join(failed_rules)}"
            else:
                exclusion_reason = "不符合獎學金資格條件"
        # 3. 檢查銀行帳戶資訊
        elif not student_data.get("bank_account"):
            is_included = False
            exclusion_reason = "缺少銀行帳戶資訊"

        roster_item = PaymentRosterItem(
            roster_id=roster.id,
            application_id=application.id,
            student_id_number=student_data.get("std_stdcode", ""),
            student_name=student_data.get("std_cname", ""),
            student_email=student_data.get("com_email", ""),
            bank_account=student_data.get("bank_account", ""),
            scholarship_name=application.scholarship_configuration.scholarship_type.name,
            scholarship_amount=application.amount or application.scholarship_configuration.amount,
            scholarship_subtype=application.sub_scholarship_type,
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
        self, application: Application, academic_year: int, period_label: str
    ) -> Dict[str, Any]:
        """
        驗證學生是否符合該期的獎學金規則

        Args:
            application: 申請記錄
            academic_year: 學年度
            period_label: 期間標記 (YYYY-MM, YYYY-H1/H2, YYYY)

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
                return {"is_eligible": False, "failed_rules": ["缺少學生或獎學金配置資訊"], "warning_rules": [], "details": {}}

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

            # 驗證每條規則
            failed_rules = []
            warning_rules = []
            details = {}

            for rule in rules:
                rule_result = self._evaluate_scholarship_rule(rule, student, application)

                if not rule_result["passed"]:
                    if rule.is_hard_rule:
                        failed_rules.append(rule_result["message"])
                    elif rule.is_warning:
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
            logger.error(f"Error validating student eligibility for application {application.id}: {e}")
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
        elif "-" in period_label and len(period_label.split("-")) == 2:
            # 月份格式，可能需要根據月份推導學期
            year, month = period_label.split("-")
            month_int = int(month)
            if month_int in [2, 3, 4, 5, 6, 7]:
                semester = "second"  # 下學期
            elif month_int in [8, 9, 10, 11, 12, 1]:
                semester = "first"  # 上學期

        query = (
            self.db.query(ScholarshipRule)
            .filter(
                and_(
                    ScholarshipRule.scholarship_type_id == scholarship_type_id,
                    ScholarshipRule.is_active.is_(True),
                    or_(
                        ScholarshipRule.academic_year == academic_year, ScholarshipRule.academic_year.is_(None)  # 通用規則
                    ),
                    or_(ScholarshipRule.semester == semester, ScholarshipRule.semester.is_(None)),  # 不限學期
                    or_(ScholarshipRule.sub_type == sub_type, ScholarshipRule.sub_type.is_(None)),  # 通用子類型
                )
            )
            .order_by(ScholarshipRule.priority.desc(), ScholarshipRule.id)
        )

        return query.all()

    def _evaluate_scholarship_rule(self, rule: ScholarshipRule, student, application: Application) -> Dict[str, Any]:
        """評估單一獎學金規則"""

        try:
            # 根據規則類型獲取學生資料中的對應值
            actual_value = self._get_student_field_value(rule.condition_field, student, application)

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
            logger.error(f"Error evaluating rule {rule.id}: {e}")
            return {
                "passed": False,
                "rule_name": rule.rule_name,
                "rule_type": rule.rule_type,
                "message": f"規則評估錯誤: {str(e)}",
                "error": str(e),
            }

    def _get_student_field_value(self, field_name: str, student, application: Application):
        """從學生或申請資料中獲取指定欄位的值"""

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

        except (ValueError, TypeError) as e:
            logger.error(
                f"Error evaluating condition: actual={actual_value}, operator={operator}, expected={expected_value}, error={e}"
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
            eligible_applications = self._get_eligible_applications(scholarship_configuration_id, academic_year)

            # 4. 模擬學籍驗證和規則驗證
            estimated_items = []
            estimated_total_amount = 0
            potential_issues = []
            verification_summary = {"verified": 0, "failed": 0, "not_required": 0}

            for application in eligible_applications:
                try:
                    # 模擬規則驗證
                    eligibility_result = self._validate_eligibility_rules(application, scholarship_config)
                    is_rule_passed = eligibility_result.get("is_eligible", False)

                    # 模擬學籍驗證
                    verification_status = StudentVerificationStatus.NOT_VERIFIED
                    verification_passed = True

                    if student_verification_enabled:
                        # 這裡只是模擬，不實際呼叫API
                        if application.student and application.student.student_number:
                            verification_status = StudentVerificationStatus.VERIFIED
                            verification_summary["verified"] += 1
                        else:
                            verification_status = StudentVerificationStatus.FAILED
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
                    logger.warning(f"Error processing application {application.id} in dry run: {e}")

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
                "scholarship_name": scholarship_config.scholarship_type.name
                if scholarship_config.scholarship_type
                else "Unknown",
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
            logger.error(f"Dry run failed: {e}")
            raise ValueError(f"預演失敗: {str(e)}")

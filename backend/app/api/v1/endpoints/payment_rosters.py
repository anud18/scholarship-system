"""
Payment roster API endpoints
造冊相關API端點
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql.functions import count

from app.core.deps import get_current_user
from app.core.exceptions import RosterAlreadyExistsError, RosterGenerationError, RosterLockedError, RosterNotFoundError
from app.core.path_security import validate_object_name_minio
from app.core.security import check_user_roles
from app.db.deps import get_db, get_sync_db
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.user import User, UserRole
from app.schemas.response import ApiResponse
from app.schemas.roster import (
    RosterAuditLogResponse,
    RosterCreateRequest,
    RosterExportRequest,
    RosterItemResponse,
    RosterListResponse,
    RosterResponse,
    RosterStatisticsResponse,
)
from app.services.excel_export_service import ExcelExportService
from app.services.roster_service import RosterService
from app.services.student_verification_service import StudentVerificationService
from app.utils.academic_period import get_roster_period_dates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/generate")
def generate_payment_roster(
    request: RosterCreateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    產生造冊
    Generate payment roster
    """
    # 檢查權限：只有管理員和處理人員可以產生造冊
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    roster = None  # 用於錯誤處理時檢查是否需要標記為 FAILED
    try:
        roster_service = RosterService(db)

        # 階段 1: 產生造冊（但不提交，狀態為 COMPLETED 但未持久化）
        roster = roster_service.generate_roster(
            scholarship_configuration_id=request.scholarship_configuration_id,
            period_label=request.period_label,
            roster_cycle=request.roster_cycle,
            academic_year=request.academic_year,
            created_by_user_id=current_user.id,
            trigger_type=RosterTriggerType.MANUAL,
            student_verification_enabled=request.student_verification_enabled,
            ranking_id=request.ranking_id,
            force_regenerate=request.force_regenerate,
        )

        logger.info(f"Roster {roster.roster_code} generated (not yet committed) by user {current_user.id}")

        # 先 commit 造冊記錄 (狀態: PROCESSING)
        # 這樣如果 Excel 匯出失敗，錯誤處理器可以正確標記為 FAILED
        db.commit()
        logger.info(f"Roster {roster.roster_code} committed with status=PROCESSING")

        # 階段 2: Excel 匯出（使用已 committed 的造冊）
        excel_export_result = None
        if request.auto_export_excel:
            export_service = ExcelExportService()
            excel_export_result = export_service.export_roster_to_excel(
                roster=roster,
                template_name="STD_UP_MIXLISTA",
                include_header=True,
                include_statistics=True,
                include_excluded=False,
            )
            logger.info(
                f"Excel file exported for roster {roster.roster_code}: "
                f"{excel_export_result.get('minio_object_name', 'N/A')}"
            )

        # 階段 3: 記錄稽核日誌，然後設置狀態並提交事務
        # 先記錄稽核日誌，確保日誌成功後才標記為 COMPLETED
        from app.models.roster_audit import RosterAuditAction, RosterAuditLevel
        from app.services.audit_service import audit_service

        audit_service.log_roster_operation(
            roster_id=roster.id,
            action=RosterAuditAction.STATUS_CHANGE,
            title="造冊狀態設置為已完成",
            user_id=current_user.id,
            user_name=current_user.name,
            description="所有操作成功完成，造冊狀態設置為 COMPLETED",
            old_values={"status": "processing"},
            new_values={"status": "completed"},
            level=RosterAuditLevel.INFO,
            metadata={
                "excel_exported": bool(excel_export_result),
            },
            tags=["status_change", "completion"],
            db=db,
        )

        # 稽核日誌成功後，才設置狀態為 COMPLETED
        roster.status = RosterStatus.COMPLETED
        roster.completed_at = datetime.now(timezone.utc)

        db.commit()
        logger.info(f"Roster {roster.roster_code} committed successfully with status={roster.status.value}")

        # 造冊產生成功
        message = "造冊產生成功"
        if excel_export_result and "error" not in excel_export_result:
            message += "，Excel檔案已自動產生並上傳"

        # 使用 Pydantic model_validate 自動處理 Field alias 映射
        response_data = RosterResponse.model_validate(roster)
        response_dict = response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict()

        # Include export result if available
        if excel_export_result:
            response_dict["excel_export"] = excel_export_result

        return {
            "success": True,
            "message": message,
            "data": response_dict,
        }

    except RosterAlreadyExistsError as e:
        # Roster already exists for this configuration/period
        logger.warning(f"Roster already exists: {e}")
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    except RosterLockedError as e:
        # Trying to regenerate a locked roster
        logger.warning(f"Roster is locked: {e}")
        db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    except RosterNotFoundError as e:
        # Referenced roster not found (for regeneration)
        logger.warning(f"Roster not found: {e}")
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    except RosterGenerationError as e:
        # General roster generation failure (including data consistency errors)
        logger.error(f"Roster generation error: {e}")

        # 保存 roster ID (如果存在) 用於後續標記
        roster_id_to_mark = roster.id if (roster and hasattr(roster, "id") and roster.id) else None

        # 回滾主事務
        db.rollback()

        # 如果 roster 已創建，使用獨立 session 標記為 FAILED
        if roster_id_to_mark:
            from app.db.session import SessionLocal

            independent_db = SessionLocal()
            try:
                roster_to_mark = (
                    independent_db.query(PaymentRoster).filter(PaymentRoster.id == roster_id_to_mark).first()
                )

                if roster_to_mark:
                    roster_to_mark.status = RosterStatus.FAILED
                    roster_to_mark.notes = f"[{datetime.now(timezone.utc).isoformat()}] 產生失敗: {str(e)}"
                    independent_db.commit()
                    logger.info(f"Roster {roster_id_to_mark} marked as FAILED due to generation error")
            except Exception as mark_error:
                logger.error(f"Failed to mark roster {roster_id_to_mark} as FAILED: {mark_error}")
                independent_db.rollback()
            finally:
                independent_db.close()

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    except ValueError as e:
        # Validation errors (missing data, invalid parameters)
        logger.warning(f"Roster generation validation error: {e}")
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    except Exception as e:
        # Unexpected errors (including Excel export failures)
        logger.error(f"Unexpected error generating roster: {e}", exc_info=True)

        # 保存 roster ID (如果存在) 用於後續標記
        roster_id_to_mark = roster.id if (roster and hasattr(roster, "id") and roster.id) else None

        # 如果 roster 已經被 commit (在 Excel 匯出前)，直接更新狀態為 FAILED
        # 如果 roster 尚未 commit (錯誤發生在 Excel 匯出之前)，rollback 並使用獨立 session
        try:
            if roster_id_to_mark:
                # 嘗試在當前 session 更新狀態
                if roster and roster.status == RosterStatus.PROCESSING:
                    roster.status = RosterStatus.FAILED
                    roster.notes = f"[{datetime.now(timezone.utc).isoformat()}] 錯誤: {str(e)}"
                    db.commit()
                    logger.info(f"Roster {roster.roster_code} marked as FAILED in current session")
                else:
                    # Rollback 當前 session 並使用獨立 session
                    db.rollback()
                    from app.db.session import SessionLocal

                    independent_db = SessionLocal()
                    try:
                        roster_to_mark = (
                            independent_db.query(PaymentRoster).filter(PaymentRoster.id == roster_id_to_mark).first()
                        )

                        if roster_to_mark:
                            roster_to_mark.status = RosterStatus.FAILED
                            roster_to_mark.notes = f"[{datetime.now(timezone.utc).isoformat()}] 錯誤: {str(e)}"
                            independent_db.commit()
                            logger.info(f"Roster {roster_id_to_mark} marked as FAILED in independent session")
                    except Exception as mark_error:
                        logger.error(f"Failed to mark roster {roster_id_to_mark} as FAILED: {mark_error}")
                        independent_db.rollback()
                    finally:
                        independent_db.close()
            else:
                # roster 不存在，直接 rollback
                db.rollback()
        except Exception as update_error:
            logger.error(f"Error updating roster status to FAILED: {update_error}")
            db.rollback()

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"造冊產生失敗: {str(e)}")


@router.get("/available-rankings")
def get_available_rankings(
    scholarship_configuration_id: int = Query(..., description="獎學金配置ID"),
    academic_year: int = Query(..., description="學年度"),
    semester: Optional[str] = Query(None, description="學期"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    查詢可用於造冊的排名清單
    Get available rankings for roster generation

    Returns rankings that have executed distribution and can be used for roster creation.
    """
    from app.models.college_review import CollegeRanking
    from app.models.scholarship import ScholarshipConfiguration

    # 檢查權限
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    try:
        # 驗證配置存在
        config = (
            db.query(ScholarshipConfiguration)
            .filter(ScholarshipConfiguration.id == scholarship_configuration_id)
            .first()
        )

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scholarship configuration {scholarship_configuration_id} not found",
            )

        # 查詢已執行分配的排名
        query = db.query(CollegeRanking).filter(
            and_(
                CollegeRanking.scholarship_type_id == config.scholarship_type_id,
                CollegeRanking.academic_year == academic_year,
                CollegeRanking.distribution_executed == True,  # 必須已執行分配
            )
        )

        # 學期篩選
        if semester:
            query = query.filter(CollegeRanking.semester == semester)
        else:
            query = query.filter(CollegeRanking.semester.is_(None))

        rankings = query.order_by(CollegeRanking.distribution_date.desc()).all()

        # 格式化回應
        ranking_list = [
            {
                "id": r.id,
                "ranking_name": r.ranking_name,
                "sub_type_code": r.sub_type_code,
                "total_applications": r.total_applications,
                "allocated_count": r.allocated_count,
                "distribution_date": r.distribution_date.isoformat() if r.distribution_date else None,
                "is_finalized": r.is_finalized,
                "ranking_status": r.ranking_status,
            }
            for r in rankings
        ]

        return {
            "success": True,
            "message": f"Found {len(ranking_list)} available rankings",
            "data": {
                "rankings": ranking_list,
                "scholarship_configuration_id": scholarship_configuration_id,
                "academic_year": academic_year,
                "semester": semester,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching available rankings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch available rankings"
        )


@router.get("")
async def list_payment_rosters(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    scholarship_configuration_id: Optional[int] = Query(None),
    status_filter: Optional[RosterStatus] = Query(None),
    period_label: Optional[str] = Query(None),
    academic_year: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    取得造冊清單
    Get payment roster list
    """
    try:
        # Build query with eager loading to avoid MissingGreenlet errors
        stmt = select(PaymentRoster).options(
            selectinload(PaymentRoster.items),
            selectinload(PaymentRoster.audit_logs),
            selectinload(PaymentRoster.creator),
            selectinload(PaymentRoster.locker),
            selectinload(PaymentRoster.scholarship_configuration),  # 增加獎學金配置的 eager loading
        )

        # 套用篩選條件
        if scholarship_configuration_id:
            stmt = stmt.where(PaymentRoster.scholarship_configuration_id == scholarship_configuration_id)
        if status_filter:
            stmt = stmt.where(PaymentRoster.status == status_filter)
        if period_label:
            stmt = stmt.where(PaymentRoster.period_label == period_label)
        if academic_year:
            stmt = stmt.where(PaymentRoster.academic_year == academic_year)

        # 計算總數
        count_stmt = select(count()).select_from(stmt.subquery())
        total_result = await db.execute(count_stmt)
        total = total_result.scalar()

        # 套用分頁
        stmt = stmt.order_by(PaymentRoster.created_at.desc()).offset(skip).limit(limit)
        result = await db.execute(stmt)
        rosters = result.scalars().all()

        # 使用 model_validate 處理基本映射，然後添加前端額外欄位
        roster_responses = []
        for roster in rosters:
            # 先使用 Pydantic 自動映射處理基本欄位（包含 alias）
            roster_response = RosterResponse.model_validate(roster)
            roster_dict = roster_response.model_dump()

            # 添加前端需要的額外欄位
            roster_dict["scholarship_config_name"] = (
                roster.scholarship_configuration.config_name if roster.scholarship_configuration else None
            )
            roster_dict["student_count"] = roster.qualified_count + roster.disqualified_count
            roster_dict["roster_name"] = roster.roster_code
            roster_dict["roster_period"] = roster.roster_cycle.value

            # 添加關聯資料（已 eager loaded，避免 MissingGreenlet）
            if roster.items:
                roster_dict["items"] = [RosterItemResponse.model_validate(item).model_dump() for item in roster.items]
            if roster.audit_logs:
                roster_dict["audit_logs"] = [
                    RosterAuditLogResponse.model_validate(log).model_dump() for log in roster.audit_logs
                ]

            roster_responses.append(RosterResponse(**roster_dict))

        response_data = RosterListResponse(items=roster_responses, total=total or 0, skip=skip, limit=limit)
        return ApiResponse(
            success=True,
            message="查詢成功",
            data=response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict(),
        )

    except Exception as e:
        logger.error(f"Failed to list rosters: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="取得造冊清單失敗")


@router.get("/preview-students")
async def preview_roster_students(
    config_id: int = Query(..., description="獎學金配置ID"),
    ranking_id: Optional[int] = Query(None, description="排名ID (如有 Matrix Distribution)"),
    period_label: Optional[str] = Query(None, description="造冊期別標籤（可選，預設自動產生）"),
    academic_year: Optional[int] = Query(None, description="學年度（可選，預設從配置取得）"),
    student_verification_enabled: bool = Query(True, description="是否啟用學籍驗證"),
    current_user: User = Depends(get_current_user),
):
    """
    預覽造冊學生名單（包含完整驗證）
    Preview student list for roster generation with full validation

    Returns:
        - has_matrix_distribution: 是否有 Matrix 分配
        - students: 學生列表（包含驗證狀態）
        - summary: 統計摘要（包含排除原因統計）
    """
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    # Create sync DB session for RosterService
    from app.db.session import SessionLocal

    db = SessionLocal()

    try:
        from app.models.application import Application
        from app.models.college_review import CollegeRanking
        from app.models.enums import QuotaManagementMode
        from app.models.scholarship import ScholarshipConfiguration

        # Initialize services
        roster_service = RosterService(db)
        verification_service = StudentVerificationService()

        # Helper function to extract bank account
        def extract_bank_account(application: Application) -> tuple[str, Optional[str]]:
            """Extract bank account from submitted_form_data. Returns (account, field_name)."""
            form_data = application.submitted_form_data or {}
            form_fields = form_data.get("fields", {})

            # List of possible field names for bank account
            field_names = ["postal_account", "bank_account", "account_number", "帳戶號碼", "帳號", "郵局帳號"]

            for field_name in field_names:
                # Check nested structure (schema-compliant)
                if field_name in form_fields and form_fields[field_name].get("value"):
                    return str(form_fields[field_name]["value"]), field_name
                # Check flat structure (backward compatibility)
                elif field_name in form_data and form_data.get(field_name):
                    return str(form_data[field_name]), field_name

            return "", None

        # Get scholarship configuration (sync query)
        config = db.query(ScholarshipConfiguration).filter(ScholarshipConfiguration.id == config_id).first()
        if not config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到獎學金配置")

        # Use config values if not provided
        if academic_year is None:
            academic_year = config.academic_year
            logger.info(f"Using academic_year from config: {academic_year}")

        if period_label is None:
            # Generate default period label based on semester
            if config.semester:
                period_label = f"{academic_year}-{config.semester}"
            else:
                period_label = f"{academic_year}-annual"
            logger.info(f"Generated default period_label: {period_label}")

        # Check if has matrix distribution
        has_matrix_distribution = config.quota_management_mode == QuotaManagementMode.matrix_based

        # Auto-detect ranking_id if needed
        if has_matrix_distribution and not ranking_id:
            ranking = (
                db.query(CollegeRanking)
                .filter(
                    and_(
                        CollegeRanking.scholarship_type_id == config.scholarship_type_id,
                        CollegeRanking.distribution_executed == True,
                    )
                )
                .order_by(CollegeRanking.created_at.desc())
                .first()
            )
            if ranking:
                ranking_id = ranking.id
                logger.info(f"Auto-detected ranking_id: {ranking_id}")

        # Get eligible applications using RosterService
        logger.info(
            f"Getting eligible applications for config {config_id}, "
            f"ranking_id={ranking_id}, academic_year={academic_year}, period={period_label}"
        )
        applications = roster_service._get_eligible_applications(
            scholarship_configuration_id=config_id,
            period_label=period_label,
            academic_year=academic_year,
            ranking_id=ranking_id,
        )
        logger.info(f"Found {len(applications)} eligible applications")

        # Initialize summary statistics
        students = []
        summary = {
            "total_students": 0,
            "included_count": 0,
            "excluded_count": 0,
            "exclusion_breakdown": {
                "missing_data": 0,
                "verification_failed": 0,
                "rules_failed": 0,
                "no_bank_account": 0,
            },
            "total_amount": 0.0,
            "verification_stats": {
                "verified": 0,
                "api_errors": 0,
                "not_verified": 0,
            },
            "by_college": {},
        }

        # Validate each application
        for application in applications:
            student_data = application.student_data or {}
            student_id_number = student_data.get("std_stdcode")
            student_name = student_data.get("std_cname")
            college = student_data.get("std_academyno", "Unknown")

            # Initialize student info with basic data
            student_info = {
                "application_id": application.id,
                "student_name": student_name or "",
                "student_id": student_id_number or "",
                "student_id_number": student_data.get("std_pid", ""),
                "email": student_data.get("com_email", ""),
                "college": college,
                "department": student_data.get("std_depno", ""),
                "term_count": student_data.get("trm_termcount", ""),
                "sub_type": application.sub_scholarship_type,
                "amount": float(application.amount or config.amount or 0),
                "rank_position": None,
                "backup_info": [],
                # Validation fields
                "is_included": False,
                "exclusion_reason": None,
                "verification_status": "not_verified",
                "verification_message": None,
                "has_fresh_data": False,
                "is_eligible": True,
                "failed_rules": [],
                "warning_rules": [],
                "has_bank_account": False,
                "bank_account_field": None,
            }

            summary["total_students"] += 1

            # Validation Step 1: Check basic student data
            if not student_id_number or not student_name:
                student_info["is_included"] = False
                student_info["exclusion_reason"] = "缺少學生基本資料（學號或姓名）"
                summary["excluded_count"] += 1
                summary["exclusion_breakdown"]["missing_data"] += 1
                students.append(student_info)
                continue

            # Validation Step 2: Student verification API (if enabled)
            verification_status = StudentVerificationStatus.VERIFIED
            fresh_student_data = None

            if student_verification_enabled:
                try:
                    verification_result = verification_service.verify_student(student_id_number, student_name)
                    verification_status = verification_result.get("status", StudentVerificationStatus.VERIFIED)
                    student_info["verification_status"] = verification_status.value
                    student_info["verification_message"] = verification_result.get("message")

                    if verification_status == StudentVerificationStatus.API_ERROR:
                        summary["verification_stats"]["api_errors"] += 1
                    else:
                        summary["verification_stats"]["verified"] += 1
                        fresh_student_data = verification_result.get("student_info", {})
                        student_info["has_fresh_data"] = bool(fresh_student_data)

                except Exception as e:
                    logger.warning(f"Verification failed for student {student_id_number}: {e}")
                    student_info["verification_status"] = "error"
                    student_info["verification_message"] = str(e)
                    summary["verification_stats"]["api_errors"] += 1
            else:
                summary["verification_stats"]["not_verified"] += 1

            # Validation Step 3: Eligibility rules validation
            try:
                eligibility_result = roster_service._validate_student_eligibility(
                    application, academic_year, period_label, fresh_api_data=fresh_student_data
                )
                student_info["is_eligible"] = eligibility_result.get("is_eligible", True)
                student_info["failed_rules"] = eligibility_result.get("failed_rules", [])
                student_info["warning_rules"] = eligibility_result.get("warning_rules", [])
            except Exception as e:
                logger.warning(f"Eligibility validation failed for application {application.id}: {e}")
                student_info["is_eligible"] = True  # Don't exclude on validation error

            # Validation Step 4: Bank account check
            bank_account, field_name = extract_bank_account(application)
            student_info["has_bank_account"] = bool(bank_account)
            student_info["bank_account_field"] = field_name

            # Validation Step 5: Final inclusion decision
            is_included = True
            exclusion_reason = None

            # Check verification status
            if verification_status != StudentVerificationStatus.VERIFIED:
                is_included = False
                exclusion_reason = f"學籍驗證未通過: {verification_status.value}"
                summary["exclusion_breakdown"]["verification_failed"] += 1

            # Check eligibility rules
            elif not student_info["is_eligible"]:
                is_included = False
                failed_rules = student_info["failed_rules"]
                exclusion_reason = f"不符合獎學金規則: {'; '.join(failed_rules)}"
                summary["exclusion_breakdown"]["rules_failed"] += 1

            # Check bank account
            elif not bank_account:
                is_included = False
                exclusion_reason = "缺少銀行帳戶資訊"
                summary["exclusion_breakdown"]["no_bank_account"] += 1

            student_info["is_included"] = is_included
            student_info["exclusion_reason"] = exclusion_reason

            if is_included:
                summary["included_count"] += 1
                summary["total_amount"] += student_info["amount"]

                # Update college statistics
                if college not in summary["by_college"]:
                    summary["by_college"][college] = {"included": 0, "excluded": 0, "total_amount": 0.0}
                summary["by_college"][college]["included"] += 1
                summary["by_college"][college]["total_amount"] += student_info["amount"]
            else:
                summary["excluded_count"] += 1
                if college not in summary["by_college"]:
                    summary["by_college"][college] = {"included": 0, "excluded": 0, "total_amount": 0.0}
                summary["by_college"][college]["excluded"] += 1

            students.append(student_info)

        logger.info(
            f"Preview complete: {summary['included_count']} included, "
            f"{summary['excluded_count']} excluded out of {summary['total_students']} total"
        )

        return ApiResponse(
            success=True,
            message=f"預覽完成: {summary['included_count']} 位學生將進入造冊，{summary['excluded_count']} 位排除",
            data={
                "has_matrix_distribution": has_matrix_distribution,
                "ranking_id": ranking_id,
                "students": students,
                "summary": summary,
            },
        )

    except HTTPException:
        raise
    except ValueError as e:
        # Handle validation errors with specific messages (e.g., missing ranking)
        logger.error(f"Failed to preview students for config {config_id}: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to preview students for config {config_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="預覽學生名單失敗")
    finally:
        db.close()


@router.get("/cycle-status")
async def get_roster_cycle_status(
    config_id: int = Query(..., description="獎學金配置ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    取得造冊週期狀態
    Get roster cycle status for a scholarship configuration

    Returns:
        - schedule: 排程資訊
        - roster_cycle: 造冊週期 (monthly/semi_yearly/yearly)
        - periods: 期間列表 (已完成 + 等待造冊)
    """
    check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

    try:
        from app.models.roster_schedule import RosterSchedule
        from app.models.scholarship import ScholarshipConfiguration

        # Get scholarship configuration
        stmt = select(ScholarshipConfiguration).where(ScholarshipConfiguration.id == config_id)
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到獎學金配置")

        # Get schedule for this config
        stmt = select(RosterSchedule).where(RosterSchedule.scholarship_configuration_id == config_id)
        result = await db.execute(stmt)
        schedule = result.scalar_one_or_none()

        if not schedule:
            return ApiResponse(
                success=True,
                message="未找到排程",
                data={
                    "schedule": None,
                    "roster_cycle": None,
                    "periods": [],
                },
            )

        # Get existing rosters for this config
        stmt = (
            select(PaymentRoster)
            .where(PaymentRoster.scholarship_configuration_id == config_id)
            .order_by(PaymentRoster.period_label.desc())
        )
        result = await db.execute(stmt)
        existing_rosters = result.scalars().all()

        # Create a map of period_label -> roster
        roster_map = {roster.period_label: roster for roster in existing_rosters}

        # Generate period list based on roster_cycle
        periods = []
        academic_year = config.academic_year

        if schedule.roster_cycle.value == "monthly":
            # Determine if this is a yearly (academic year) scholarship
            is_yearly = config.semester is None or config.semester.value == "annual"

            # Generate 12 months
            # For yearly scholarships: September to August (9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8)
            # For semester scholarships: January to December (1, 2, 3, ..., 12)
            if is_yearly:
                month_sequence = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8]
            else:
                month_sequence = list(range(1, 13))

            for month in month_sequence:
                period_label = f"{academic_year}-{month:02d}"
                roster = roster_map.get(period_label)

                # Calculate period dates
                period_dates = get_roster_period_dates(
                    academic_year=academic_year,
                    semester=config.semester.value if config.semester else None,
                    roster_cycle="monthly",
                    period_label=period_label,
                )

                # Calculate western calendar year-month for display
                western_year = academic_year + 1911
                calendar_year = western_year if month >= 9 else western_year + 1
                western_date = f"{calendar_year}-{month:02d}"
                display_label = f"{period_label} ({calendar_year}年{month}月)"

                # 根據造冊的實際狀態決定期間狀態
                if roster and roster.status in [RosterStatus.COMPLETED, RosterStatus.LOCKED]:
                    periods.append(
                        {
                            "label": period_label,
                            "western_date": western_date,
                            "display_label": display_label,
                            "status": "completed",
                            "roster_id": roster.id,
                            "roster_code": roster.roster_code,
                            "roster_status": roster.status.value,
                            "completed_at": roster.completed_at.isoformat() if roster.completed_at else None,
                            "total_amount": float(roster.total_amount) if roster.total_amount else 0,
                            "qualified_count": roster.qualified_count,
                            "period_start_date": period_dates["start_date"].isoformat(),
                            "period_end_date": period_dates["end_date"].isoformat(),
                        }
                    )
                elif roster and roster.status == RosterStatus.FAILED:
                    periods.append(
                        {
                            "label": period_label,
                            "western_date": western_date,
                            "display_label": display_label,
                            "status": "failed",
                            "roster_id": roster.id,
                            "roster_code": roster.roster_code,
                            "roster_status": roster.status.value,
                            "error_message": roster.notes,
                            "total_amount": float(roster.total_amount) if roster.total_amount else 0,
                            "qualified_count": roster.qualified_count,
                            "period_start_date": period_dates["start_date"].isoformat(),
                            "period_end_date": period_dates["end_date"].isoformat(),
                        }
                    )
                elif roster and roster.status == RosterStatus.PROCESSING:
                    periods.append(
                        {
                            "label": period_label,
                            "western_date": western_date,
                            "display_label": display_label,
                            "status": "processing",
                            "roster_id": roster.id,
                            "roster_code": roster.roster_code,
                            "roster_status": roster.status.value,
                            "period_start_date": period_dates["start_date"].isoformat(),
                            "period_end_date": period_dates["end_date"].isoformat(),
                        }
                    )
                else:
                    periods.append(
                        {
                            "label": period_label,
                            "western_date": western_date,
                            "display_label": display_label,
                            "status": "waiting",
                            "next_schedule": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
                            "estimated_count": 0,  # TODO: Calculate estimated count
                            "period_start_date": period_dates["start_date"].isoformat(),
                            "period_end_date": period_dates["end_date"].isoformat(),
                        }
                    )

        elif schedule.roster_cycle.value == "semi_yearly":
            # Generate 2 half-year periods
            for half in ["H1", "H2"]:
                period_label = f"{academic_year}-{half}"
                roster = roster_map.get(period_label)

                # Calculate period dates
                period_dates = get_roster_period_dates(
                    academic_year=academic_year,
                    semester=config.semester.value if config.semester else None,
                    roster_cycle="semi_yearly",
                    period_label=period_label,
                )

                # 根據造冊的實際狀態決定期間狀態
                if roster and roster.status in [RosterStatus.COMPLETED, RosterStatus.LOCKED]:
                    periods.append(
                        {
                            "label": period_label,
                            "status": "completed",
                            "roster_id": roster.id,
                            "roster_code": roster.roster_code,
                            "roster_status": roster.status.value,
                            "completed_at": roster.completed_at.isoformat() if roster.completed_at else None,
                            "total_amount": float(roster.total_amount) if roster.total_amount else 0,
                            "qualified_count": roster.qualified_count,
                            "period_start_date": period_dates["start_date"].isoformat(),
                            "period_end_date": period_dates["end_date"].isoformat(),
                        }
                    )
                elif roster and roster.status == RosterStatus.FAILED:
                    periods.append(
                        {
                            "label": period_label,
                            "status": "failed",
                            "roster_id": roster.id,
                            "roster_code": roster.roster_code,
                            "roster_status": roster.status.value,
                            "error_message": roster.notes,
                            "total_amount": float(roster.total_amount) if roster.total_amount else 0,
                            "qualified_count": roster.qualified_count,
                            "period_start_date": period_dates["start_date"].isoformat(),
                            "period_end_date": period_dates["end_date"].isoformat(),
                        }
                    )
                elif roster and roster.status == RosterStatus.PROCESSING:
                    periods.append(
                        {
                            "label": period_label,
                            "status": "processing",
                            "roster_id": roster.id,
                            "roster_code": roster.roster_code,
                            "roster_status": roster.status.value,
                            "period_start_date": period_dates["start_date"].isoformat(),
                            "period_end_date": period_dates["end_date"].isoformat(),
                        }
                    )
                else:
                    periods.append(
                        {
                            "label": period_label,
                            "status": "waiting",
                            "next_schedule": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
                            "estimated_count": 0,
                            "period_start_date": period_dates["start_date"].isoformat(),
                            "period_end_date": period_dates["end_date"].isoformat(),
                        }
                    )

        elif schedule.roster_cycle.value == "yearly":
            # Generate 1 yearly period
            period_label = str(academic_year)
            roster = roster_map.get(period_label)

            # Calculate period dates
            period_dates = get_roster_period_dates(
                academic_year=academic_year,
                semester=config.semester.value if config.semester else None,
                roster_cycle="yearly",
                period_label=period_label,
            )

            # 根據造冊的實際狀態決定期間狀態
            if roster and roster.status in [RosterStatus.COMPLETED, RosterStatus.LOCKED]:
                periods.append(
                    {
                        "label": period_label,
                        "status": "completed",
                        "roster_id": roster.id,
                        "roster_code": roster.roster_code,
                        "roster_status": roster.status.value,
                        "completed_at": roster.completed_at.isoformat() if roster.completed_at else None,
                        "total_amount": float(roster.total_amount) if roster.total_amount else 0,
                        "qualified_count": roster.qualified_count,
                        "period_start_date": period_dates["start_date"].isoformat(),
                        "period_end_date": period_dates["end_date"].isoformat(),
                    }
                )
            elif roster and roster.status == RosterStatus.FAILED:
                periods.append(
                    {
                        "label": period_label,
                        "status": "failed",
                        "roster_id": roster.id,
                        "roster_code": roster.roster_code,
                        "roster_status": roster.status.value,
                        "error_message": roster.notes,
                        "total_amount": float(roster.total_amount) if roster.total_amount else 0,
                        "qualified_count": roster.qualified_count,
                        "period_start_date": period_dates["start_date"].isoformat(),
                        "period_end_date": period_dates["end_date"].isoformat(),
                    }
                )
            elif roster and roster.status == RosterStatus.PROCESSING:
                periods.append(
                    {
                        "label": period_label,
                        "status": "processing",
                        "roster_id": roster.id,
                        "roster_code": roster.roster_code,
                        "roster_status": roster.status.value,
                        "period_start_date": period_dates["start_date"].isoformat(),
                        "period_end_date": period_dates["end_date"].isoformat(),
                    }
                )
            else:
                periods.append(
                    {
                        "label": period_label,
                        "status": "waiting",
                        "next_schedule": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
                        "estimated_count": 0,
                        "period_start_date": period_dates["start_date"].isoformat(),
                        "period_end_date": period_dates["end_date"].isoformat(),
                    }
                )

        return ApiResponse(
            success=True,
            message="查詢成功",
            data={
                "schedule": {
                    "id": schedule.id,
                    "schedule_name": schedule.schedule_name,
                    "roster_cycle": schedule.roster_cycle.value,
                    "cron_expression": schedule.cron_expression,
                    "status": schedule.status.value,
                    "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
                    "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
                },
                "roster_cycle": schedule.roster_cycle.value,
                "periods": periods,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cycle status for config {config_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="查詢造冊週期狀態失敗")


@router.get("/{roster_id}")
async def get_payment_roster(
    roster_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    取得特定造冊詳細資訊
    Get specific payment roster details
    """
    try:
        # 使用 eager loading 避免 MissingGreenlet 錯誤
        stmt = (
            select(PaymentRoster)
            .where(PaymentRoster.id == roster_id)
            .options(
                selectinload(PaymentRoster.items),
                selectinload(PaymentRoster.audit_logs),
                selectinload(PaymentRoster.creator),
                selectinload(PaymentRoster.locker),
                selectinload(PaymentRoster.scholarship_configuration),
            )
        )
        result = await db.execute(stmt)
        roster = result.scalar_one_or_none()

        if not roster:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的造冊")

        # 使用 Pydantic model_validate 自動處理 Field alias 映射
        response_data = RosterResponse.model_validate(roster)
        return ApiResponse(
            success=True,
            message="查詢成功",
            data=response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get roster {roster_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="取得造冊詳情失敗")


@router.get("/{roster_id}/items")
async def get_roster_items(
    roster_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    verification_status: Optional[StudentVerificationStatus] = Query(None),
    is_qualified: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    取得造冊明細項目
    Get roster items
    """
    try:
        # 檢查造冊是否存在
        roster_stmt = select(PaymentRoster).where(PaymentRoster.id == roster_id)
        roster_result = await db.execute(roster_stmt)
        roster = roster_result.scalar_one_or_none()

        if not roster:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的造冊")

        stmt = select(PaymentRosterItem).where(PaymentRosterItem.roster_id == roster_id)

        # 套用篩選條件
        if verification_status:
            stmt = stmt.where(PaymentRosterItem.verification_status == verification_status)
        if is_qualified is not None:
            stmt = stmt.where(PaymentRosterItem.is_qualified == is_qualified)

        # 分頁查詢
        stmt = stmt.order_by(PaymentRosterItem.created_at).offset(skip).limit(limit)
        result = await db.execute(stmt)
        items = result.scalars().all()

        items_data = [RosterItemResponse.from_orm(item) for item in items]
        return ApiResponse(
            success=True,
            message="查詢成功",
            data=[item.model_dump() if hasattr(item, "model_dump") else item.dict() for item in items_data],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get roster items for {roster_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="取得造冊明細失敗")


@router.post("/{roster_id}/lock")
async def lock_roster(
    roster_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    鎖定造冊
    Lock roster
    """
    # 檢查權限：只有管理員可以鎖定造冊
    check_user_roles([UserRole.admin], current_user)

    try:
        stmt = select(PaymentRoster).where(PaymentRoster.id == roster_id)
        result = await db.execute(stmt)
        roster = result.scalar_one_or_none()

        if not roster:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的造冊")

        if roster.status == RosterStatus.LOCKED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="造冊已經被鎖定")

        roster.status = RosterStatus.LOCKED
        roster.locked_at = datetime.utcnow()
        roster.locked_by_user_id = current_user.id

        await db.commit()

        logger.info(f"Roster {roster.roster_code} locked by user {current_user.id}")

        return ApiResponse(
            success=True,
            message="造冊已鎖定",
            data={"roster_code": roster.roster_code},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to lock roster {roster_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="鎖定造冊失敗")


@router.post("/{roster_id}/unlock")
async def unlock_roster(
    roster_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    解鎖造冊
    Unlock roster
    """
    # 檢查權限：只有管理員可以解鎖造冊
    check_user_roles([UserRole.admin], current_user)

    try:
        stmt = select(PaymentRoster).where(PaymentRoster.id == roster_id)

        result = await db.execute(stmt)

        roster = result.scalar_one_or_none()

        if not roster:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的造冊")

        if roster.status != RosterStatus.LOCKED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="造冊未被鎖定")

        roster.status = RosterStatus.COMPLETED
        roster.locked_at = None
        roster.locked_by_user_id = None

        await db.commit()

        logger.info(f"Roster {roster.roster_code} unlocked by user {current_user.id}")

        return ApiResponse(
            success=True,
            message="造冊已解鎖",
            data={"roster_code": roster.roster_code},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to unlock roster {roster_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="解鎖造冊失敗")


@router.get("/{roster_id}/preview")
def preview_roster_export(
    roster_id: int,
    template_name: str = Query("STD_UP_MIXLISTA", description="Excel範本名稱"),
    include_header: bool = Query(True, description="是否包含標題行"),
    max_preview_rows: int = Query(10, description="預覽模式最大行數"),
    include_excluded: bool = Query(False, description="是否包含排除項目"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    預覽造冊Excel匯出內容
    Preview roster Excel export content
    """
    try:
        roster = db.query(PaymentRoster).filter(PaymentRoster.id == roster_id).first()

        if not roster:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的造冊")

        export_service = ExcelExportService()

        # 預覽模式：只產生資料預覽，不實際建立檔案
        preview_result = export_service.preview_roster_export(
            roster=roster,
            template_name=template_name,
            include_header=include_header,
            max_preview_rows=max_preview_rows or 10,
            include_excluded=include_excluded,
        )

        logger.info(f"Roster {roster.roster_code} preview generated by user {current_user.id}")

        return ApiResponse(
            success=True,
            message="預覽產生成功",
            data={
                "roster_code": roster.roster_code,
                "preview_data": preview_result["preview_data"],
                "total_rows": preview_result["total_rows"],
                "column_headers": preview_result["column_headers"],
                "validation_result": preview_result["validation_result"],
                "export_metadata": preview_result["metadata"],
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to preview roster {roster_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="預覽產生失敗")


@router.post("/{roster_id}/dry-run")
def dry_run_roster_generation(
    roster_id: int,
    request: RosterCreateRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    造冊產生預演 (不實際建立造冊)
    Dry run roster generation (without actually creating roster)
    """
    try:
        # 檢查權限
        check_user_roles([UserRole.admin, UserRole.super_admin], current_user)

        roster_service = RosterService(db)

        # 執行預演模式
        dry_run_result = roster_service.dry_run_generate_roster(
            scholarship_configuration_id=request.scholarship_configuration_id,
            period_label=request.period_label,
            roster_cycle=request.roster_cycle,
            academic_year=request.academic_year,
            student_verification_enabled=request.student_verification_enabled,
        )

        logger.info(
            f"Dry run completed for scholarship config {request.scholarship_configuration_id} "
            f"by user {current_user.id}"
        )

        return ApiResponse(
            success=True,
            message="預演完成",
            data={
                "dry_run_result": dry_run_result,
                "estimated_items": dry_run_result["estimated_items"],
                "estimated_total_amount": dry_run_result["estimated_total_amount"],
                "potential_issues": dry_run_result["potential_issues"],
                "validation_summary": dry_run_result["validation_summary"],
                "duplicate_check": dry_run_result["duplicate_check"],
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to dry run roster generation: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="預演失敗")


@router.post("/{roster_id}/export")
def export_roster_to_excel(
    roster_id: int,
    request: RosterExportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """
    匯出造冊至Excel (STD_UP_MIXLISTA格式)
    Export roster to Excel (STD_UP_MIXLISTA format)
    """
    try:
        roster = db.query(PaymentRoster).filter(PaymentRoster.id == roster_id).first()

        if not roster:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的造冊")

        export_service = ExcelExportService()

        # 使用新的STD_UP_MIXLISTA格式匯出
        export_result = export_service.export_roster_to_excel(
            roster=roster,
            template_name=request.template_name or "STD_UP_MIXLISTA",
            include_header=request.include_header,
            include_statistics=request.include_statistics,
            include_excluded=request.include_excluded,
            async_mode=request.async_mode or False,
        )

        if request.async_mode:
            background_tasks.add_task(
                export_service.process_async_export,
                roster_id,
                export_result["task_id"],
                current_user.id,
                template_name=request.template_name,
                include_header=request.include_header,
                include_statistics=request.include_statistics,
                include_excluded=request.include_excluded,
            )

            logger.info(
                "Roster %s export queued in async mode by user %s (task %s)",
                roster.roster_code,
                current_user.id,
                export_result["task_id"],
            )

            return ApiResponse(
                success=True,
                message="Excel檔案匯出已開始 (非同步模式)",
                data={
                    "task_id": export_result["task_id"],
                    "status": export_result["status"],
                    "estimated_completion": export_result.get("estimated_completion"),
                },
            )

        logger.info(
            "Roster %s exported to %s by user %s",
            roster.roster_code,
            export_result["file_path"],
            current_user.id,
        )

        return ApiResponse(
            success=True,
            message="Excel檔案匯出成功",
            data={
                "file_path": export_result["file_path"],
                "file_size": export_result["file_size"],
                "validation_result": export_result["validation_result"],
                "download_url": f"/api/v1/payment-rosters/{roster_id}/download",
                "minio_object_name": export_result.get("minio_object_name"),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export roster {roster_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Excel匯出失敗")


@router.get("/{roster_id}/download")
async def download_roster_excel(
    roster_id: int,
    use_minio: bool = Query(True, description="是否使用MinIO下載"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    下載造冊Excel檔案 (支援MinIO和本地檔案)
    Download roster Excel file (supports MinIO and local files)
    """
    try:
        stmt = select(PaymentRoster).where(PaymentRoster.id == roster_id)

        result = await db.execute(stmt)

        roster = result.scalar_one_or_none()

        if not roster:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的造冊")

        from app.services.audit_service import audit_service
        from app.services.minio_service import minio_service

        if use_minio and hasattr(roster, "minio_object_name") and roster.minio_object_name:
            # SECURITY: Validate MinIO object name (CLAUDE.md requirement)
            try:
                validate_object_name_minio(roster.minio_object_name)
            except HTTPException:
                logger.error(f"Invalid minio_object_name from database: {roster.minio_object_name}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="MinIO object name驗證失敗"
                )

            # 使用MinIO下載
            try:
                file_content, metadata = minio_service.download_roster_file(roster.minio_object_name)

                # 記錄下載日誌
                audit_service.log_file_download(
                    roster_id=roster_id,
                    filename=roster.minio_object_name,
                    user_id=current_user.id,
                    user_name=current_user.name,
                    download_method="minio",
                    db=db,
                )

                logger.info(f"Roster {roster.roster_code} downloaded from MinIO by user {current_user.id}")

                # 直接返回二進制檔案內容
                from fastapi.responses import Response

                filename = metadata.get("original-filename", f"{roster.roster_code}.xlsx")
                content_type = metadata.get(
                    "Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                return Response(
                    content=file_content,
                    media_type=content_type,
                    headers={
                        "Content-Disposition": f'attachment; filename="{filename}"',
                        "Content-Length": str(len(file_content)),
                    },
                )

            except Exception as e:
                logger.warning(f"MinIO download failed, falling back to local file: {e}")
                use_minio = False

        if not use_minio:
            # 本地檔案下載或MinIO失敗後的回退方案
            if hasattr(roster, "excel_file_path") and roster.excel_file_path and os.path.exists(roster.excel_file_path):
                # 記錄下載日誌
                audit_service.log_file_download(
                    roster_id=roster_id,
                    filename=os.path.basename(roster.excel_file_path),
                    user_id=current_user.id,
                    user_name=current_user.name,
                    download_method="local",
                    db=db,
                )

                logger.info(f"Roster {roster.roster_code} downloaded locally by user {current_user.id}")

                return FileResponse(
                    path=roster.excel_file_path,
                    filename=f"{roster.roster_code}.xlsx",
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                # 沒有可用的檔案，重新產生
                export_service = ExcelExportService()
                export_result = export_service.export_roster_to_excel(
                    roster=roster,
                    template_name="STD_UP_MIXLISTA",
                    include_header=True,
                    include_statistics=True,
                    include_excluded=False,
                )

                logger.info(f"Roster {roster.roster_code} re-generated and downloaded by user {current_user.id}")

                return FileResponse(
                    path=export_result["file_path"],
                    filename=f"{roster.roster_code}.xlsx",
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download roster {roster_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="下載造冊失敗")


@router.get("/{roster_id}/statistics")
async def get_roster_statistics(
    roster_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    取得造冊統計資訊
    Get roster statistics
    """
    try:
        stmt = select(PaymentRoster).where(PaymentRoster.id == roster_id)

        result = await db.execute(stmt)

        roster = result.scalar_one_or_none()

        if not roster:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的造冊")

        # 統計各驗證狀態的人數
        verification_stats = {}
        for status_val in StudentVerificationStatus:
            item_count = (
                await db.execute(
                    select(count())
                    .select_from(PaymentRosterItem)
                    .where(
                        PaymentRosterItem.roster_id == roster_id, PaymentRosterItem.verification_status == status_val
                    )
                )
            ).scalar()
            verification_stats[status_val.value] = item_count

        # 統計合格/不合格人數
        qualified_stmt = (
            select(count())
            .select_from(PaymentRosterItem)
            .where(PaymentRosterItem.roster_id == roster_id, PaymentRosterItem.is_qualified.is_(True))
        )
        qualified_result = await db.execute(qualified_stmt)
        qualified_count = qualified_result.scalar() or 0

        disqualified_stmt = (
            select(count())
            .select_from(PaymentRosterItem)
            .where(PaymentRosterItem.roster_id == roster_id, PaymentRosterItem.is_qualified.is_(False))
        )
        disqualified_result = await db.execute(disqualified_stmt)
        disqualified_count = disqualified_result.scalar() or 0

        response_data = RosterStatisticsResponse(
            roster_id=roster_id,
            total_items=qualified_count + disqualified_count,
            qualified_count=qualified_count,
            disqualified_count=disqualified_count,
            total_amount=roster.total_amount,
            verification_status_counts=verification_stats,
            created_at=roster.created_at,
            status=roster.status,
        )
        return ApiResponse(
            success=True,
            message="查詢成功",
            data=response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get roster statistics for {roster_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="取得造冊統計失敗")


@router.delete("/{roster_id}")
async def delete_roster(
    roster_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    刪除造冊（僅限未鎖定的造冊）
    Delete roster (only unlocked rosters)
    """
    # 檢查權限：只有管理員可以刪除造冊
    check_user_roles([UserRole.admin], current_user)

    try:
        stmt = select(PaymentRoster).where(PaymentRoster.id == roster_id)

        result = await db.execute(stmt)

        roster = result.scalar_one_or_none()

        if not roster:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的造冊")

        if roster.status == RosterStatus.LOCKED:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="無法刪除已鎖定的造冊")

        # 刪除造冊項目和稽核記錄（透過cascade）
        await db.delete(roster)
        await db.commit()

        logger.info(f"Roster {roster.roster_code} deleted by user {current_user.id}")

        return ApiResponse(
            success=True,
            message="造冊已刪除",
            data=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete roster {roster_id}: {e}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="刪除造冊失敗")


@router.get("/{roster_id}/audit-logs")
async def get_roster_audit_logs(
    roster_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    取得造冊稽核日誌
    Get roster audit logs
    """
    try:
        stmt = select(PaymentRoster).where(PaymentRoster.id == roster_id)

        result = await db.execute(stmt)

        roster = result.scalar_one_or_none()

        if not roster:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到指定的造冊")

        from app.models.roster_audit import RosterAuditLog

        stmt = (
            select(RosterAuditLog)
            .where(RosterAuditLog.roster_id == roster_id)
            .order_by(RosterAuditLog.created_at.desc())
        )

        count_result = await db.execute(select(count()).select_from(stmt.subquery()))
        total = count_result.scalar()
        stmt = stmt.offset(skip).limit(limit)
        result = await db.execute(stmt)
        logs = result.scalars().all()

        return ApiResponse(
            success=True,
            message="查詢成功",
            data={
                "items": [
                    {
                        "id": log.id,
                        "action": log.action.value,
                        "level": log.level.value,
                        "title": log.title,
                        "description": log.description,
                        "created_by_user_id": log.created_by_user_id,
                        "created_at": log.created_at,
                        "audit_metadata": log.audit_metadata,
                    }
                    for log in logs
                ],
                "total": total,
                "skip": skip,
                "limit": limit,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get audit logs for roster {roster_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="查詢稽核日誌失敗")

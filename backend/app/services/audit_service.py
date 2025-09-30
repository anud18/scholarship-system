"""
Roster audit logging service
造冊稽核日誌服務
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.roster_audit import RosterAuditAction, RosterAuditLevel, RosterAuditLog


def get_db_sync():
    """Get synchronous database session"""
    db = SessionLocal()
    try:
        return db
    finally:
        db.close()


logger = logging.getLogger(__name__)


class AuditService:
    """造冊稽核日誌服務"""

    def __init__(self):
        pass

    def log_roster_operation(
        self,
        roster_id: int,
        action: RosterAuditAction,
        title: str,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        user_role: Optional[str] = None,
        request: Optional[Request] = None,
        description: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        level: RosterAuditLevel = RosterAuditLevel.INFO,
        affected_items_count: int = 0,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        warning_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        db: Optional[Session] = None,
    ) -> RosterAuditLog:
        """
        記錄造冊操作日誌

        Args:
            roster_id: 造冊ID
            action: 操作類型
            title: 操作標題
            user_id: 使用者ID (可選)
            user_name: 使用者名稱 (可選)
            user_role: 使用者角色 (可選)
            request: FastAPI Request物件 (可選)
            description: 詳細描述 (可選)
            old_values: 變更前的值 (可選)
            new_values: 變更後的值 (可選)
            level: 日誌等級
            affected_items_count: 影響的項目數量
            error_code: 錯誤代碼 (可選)
            error_message: 錯誤訊息 (可選)
            warning_message: 警告訊息 (可選)
            metadata: 額外metadata (可選)
            tags: 標籤 (可選)
            db: 資料庫session (可選)

        Returns:
            RosterAuditLog: 建立的稽核日誌記錄
        """
        # 從request提取額外資訊
        client_ip = None
        user_agent = None
        api_endpoint = None
        request_method = None
        request_payload = None

        if request:
            client_ip = self._get_client_ip(request)
            user_agent = request.headers.get("user-agent")
            api_endpoint = str(request.url.path)
            request_method = request.method

            # 安全地提取request payload (避免敏感資訊)
            if hasattr(request, "json") and request_method in ["POST", "PUT", "PATCH"]:
                # 這裡可以實作payload過濾邏輯，移除敏感欄位
                # 暫時不記錄payload避免敏感資訊洩漏
                pass

        # 建立稽核日誌記錄
        audit_log = RosterAuditLog.create_audit_log(
            roster_id=roster_id,
            action=action,
            title=title,
            user_id=user_id,
            user_name=user_name,
            user_role=user_role,
            client_ip=client_ip,
            user_agent=user_agent,
            description=description,
            old_values=old_values,
            new_values=new_values,
            level=level,
            api_endpoint=api_endpoint,
            request_method=request_method,
            request_payload=request_payload,
            affected_items_count=affected_items_count,
            error_code=error_code,
            error_message=error_message,
            warning_message=warning_message,
            audit_metadata=metadata,
            tags=tags,
        )

        # 儲存到資料庫
        should_close_db = False
        if db is None:
            db = next(get_db_sync())
            should_close_db = True

        try:
            db.add(audit_log)
            db.commit()
            db.refresh(audit_log)

            logger.info(
                f"Audit log created: roster_id={roster_id}, action={action.value}, "
                f"user={user_name or 'system'}, level={level.value}"
            )

            return audit_log

        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create audit log: {e}")
            # 即使稽核失敗也不應該影響主要業務邏輯
            # 這裡可以考慮將失敗的稽核記錄到檔案系統
            self._fallback_log(roster_id, action, title, str(e))
            raise
        finally:
            if should_close_db:
                db.close()

    def log_roster_creation(
        self,
        roster_id: int,
        roster_code: str,
        user_id: int,
        user_name: str,
        scholarship_config_name: str,
        period_label: str,
        trigger_type: str,
        request: Optional[Request] = None,
        db: Optional[Session] = None,
    ) -> RosterAuditLog:
        """記錄造冊建立"""
        return self.log_roster_operation(
            roster_id=roster_id,
            action=RosterAuditAction.CREATE,
            title=f"建立造冊: {roster_code}",
            user_id=user_id,
            user_name=user_name,
            request=request,
            description=f"為{scholarship_config_name}建立{period_label}造冊，觸發方式: {trigger_type}",
            new_values={
                "roster_code": roster_code,
                "scholarship_config": scholarship_config_name,
                "period_label": period_label,
                "trigger_type": trigger_type,
            },
            level=RosterAuditLevel.INFO,
            tags=["creation", trigger_type],
            db=db,
        )

    def log_roster_status_change(
        self,
        roster_id: int,
        old_status: str,
        new_status: str,
        user_id: Optional[int],
        user_name: Optional[str],
        reason: Optional[str] = None,
        request: Optional[Request] = None,
        db: Optional[Session] = None,
    ) -> RosterAuditLog:
        """記錄造冊狀態變更"""
        title = f"造冊狀態變更: {old_status} → {new_status}"
        description = f"造冊狀態從 {old_status} 變更為 {new_status}"
        if reason:
            description += f"，原因: {reason}"

        return self.log_roster_operation(
            roster_id=roster_id,
            action=RosterAuditAction.STATUS_CHANGE,
            title=title,
            user_id=user_id,
            user_name=user_name,
            request=request,
            description=description,
            old_values={"status": old_status},
            new_values={"status": new_status, "reason": reason},
            level=RosterAuditLevel.INFO,
            tags=["status_change", new_status],
            db=db,
        )

    def log_roster_lock(
        self,
        roster_id: int,
        user_id: int,
        user_name: str,
        request: Optional[Request] = None,
        db: Optional[Session] = None,
    ) -> RosterAuditLog:
        """記錄造冊鎖定"""
        return self.log_roster_operation(
            roster_id=roster_id,
            action=RosterAuditAction.LOCK,
            title="鎖定造冊",
            user_id=user_id,
            user_name=user_name,
            request=request,
            description="造冊已被鎖定，無法再進行修改",
            new_values={"locked_by": user_id, "locked_at": datetime.now().isoformat()},
            level=RosterAuditLevel.INFO,
            tags=["lock"],
            db=db,
        )

    def log_excel_export(
        self,
        roster_id: int,
        filename: str,
        file_size: int,
        record_count: int,
        user_id: Optional[int],
        user_name: Optional[str],
        export_format: str = "xlsx",
        request: Optional[Request] = None,
        db: Optional[Session] = None,
    ) -> RosterAuditLog:
        """記錄Excel匯出"""
        return self.log_roster_operation(
            roster_id=roster_id,
            action=RosterAuditAction.EXPORT,
            title=f"匯出Excel檔案: {filename}",
            user_id=user_id,
            user_name=user_name,
            request=request,
            description=f"匯出{record_count}筆造冊資料為{export_format}格式",
            new_values={
                "filename": filename,
                "file_size": file_size,
                "record_count": record_count,
                "export_format": export_format,
            },
            level=RosterAuditLevel.INFO,
            affected_items_count=record_count,
            tags=["export", export_format],
            db=db,
        )

    def log_file_download(
        self,
        roster_id: int,
        filename: str,
        user_id: Optional[int],
        user_name: Optional[str],
        download_method: str = "direct",
        request: Optional[Request] = None,
        db: Optional[Session] = None,
    ) -> RosterAuditLog:
        """記錄檔案下載"""
        return self.log_roster_operation(
            roster_id=roster_id,
            action=RosterAuditAction.DOWNLOAD,
            title=f"下載檔案: {filename}",
            user_id=user_id,
            user_name=user_name,
            request=request,
            description=f"透過{download_method}方式下載造冊檔案",
            metadata={
                "filename": filename,
                "download_method": download_method,
            },
            level=RosterAuditLevel.INFO,
            tags=["download", download_method],
            db=db,
        )

    def log_student_verification(
        self,
        roster_id: int,
        total_students: int,
        verified_count: int,
        failed_count: int,
        api_mode: str,
        verification_duration_ms: int,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        request: Optional[Request] = None,
        db: Optional[Session] = None,
    ) -> RosterAuditLog:
        """記錄學籍驗證"""
        success_rate = (verified_count / total_students * 100) if total_students > 0 else 0

        level = RosterAuditLevel.INFO
        if failed_count > total_students * 0.1:  # 失敗率超過10%
            level = RosterAuditLevel.WARNING
        if failed_count > total_students * 0.3:  # 失敗率超過30%
            level = RosterAuditLevel.ERROR

        return self.log_roster_operation(
            roster_id=roster_id,
            action=RosterAuditAction.STUDENT_VERIFY,
            title=f"學籍驗證完成: {verified_count}/{total_students} 成功",
            user_id=user_id,
            user_name=user_name or "system",
            request=request,
            description=f"使用{api_mode}模式驗證{total_students}位學生，成功率: {success_rate:.1f}%",
            metadata={
                "total_students": total_students,
                "verified_count": verified_count,
                "failed_count": failed_count,
                "success_rate": success_rate,
                "api_mode": api_mode,
                "duration_ms": verification_duration_ms,
            },
            level=level,
            affected_items_count=total_students,
            warning_message=f"有{failed_count}位學生驗證失敗" if failed_count > 0 else None,
            tags=["verification", api_mode],
            db=db,
        )

    def log_roster_error(
        self,
        roster_id: int,
        error_code: str,
        error_message: str,
        operation: str,
        user_id: Optional[int] = None,
        user_name: Optional[str] = None,
        request: Optional[Request] = None,
        exception_details: Optional[Dict] = None,
        db: Optional[Session] = None,
    ) -> RosterAuditLog:
        """記錄造冊錯誤"""
        return self.log_roster_operation(
            roster_id=roster_id,
            action=RosterAuditAction.STATUS_CHANGE,  # 或建立專門的ERROR action
            title=f"操作失敗: {operation}",
            user_id=user_id,
            user_name=user_name,
            request=request,
            description=f"造冊操作 '{operation}' 執行失敗",
            error_code=error_code,
            error_message=error_message,
            level=RosterAuditLevel.ERROR,
            metadata=exception_details,
            tags=["error", operation],
            db=db,
        )

    def get_roster_audit_trail(
        self,
        roster_id: int,
        limit: int = 100,
        offset: int = 0,
        action_filter: Optional[RosterAuditAction] = None,
        level_filter: Optional[RosterAuditLevel] = None,
        user_filter: Optional[int] = None,
        db: Optional[Session] = None,
    ) -> List[RosterAuditLog]:
        """
        取得造冊稽核軌跡

        Args:
            roster_id: 造冊ID
            limit: 筆數限制
            offset: 偏移量
            action_filter: 動作篩選
            level_filter: 等級篩選
            user_filter: 使用者篩選
            db: 資料庫session

        Returns:
            List[RosterAuditLog]: 稽核日誌列表
        """
        should_close_db = False
        if db is None:
            db = next(get_db_sync())
            should_close_db = True

        try:
            query = db.query(RosterAuditLog).filter(RosterAuditLog.roster_id == roster_id)

            if action_filter:
                query = query.filter(RosterAuditLog.action == action_filter)

            if level_filter:
                query = query.filter(RosterAuditLog.level == level_filter)

            if user_filter:
                query = query.filter(RosterAuditLog.user_id == user_filter)

            audit_logs = query.order_by(RosterAuditLog.created_at.desc()).offset(offset).limit(limit).all()

            return audit_logs

        finally:
            if should_close_db:
                db.close()

    def _get_client_ip(self, request: Request) -> Optional[str]:
        """從request中提取客戶端IP"""
        # 檢查常見的代理header
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # X-Forwarded-For可能包含多個IP，取第一個
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # 如果沒有代理header，使用直接連線IP
        if hasattr(request, "client") and request.client:
            return request.client.host

        return None

    def _fallback_log(self, roster_id: int, action: RosterAuditAction, title: str, error: str):
        """當資料庫稽核失敗時的fallback logging"""
        fallback_message = (
            f"[AUDIT FALLBACK] roster_id={roster_id}, action={action.value}, " f"title={title}, db_error={error}"
        )
        logger.error(fallback_message)

        # 也可以寫到檔案或外部系統
        # 這裡只是簡單的logger記錄


# 全域稽核服務實例
audit_service = AuditService()

"""
Application audit logging service
申請稽核日誌服務
"""

import logging
from typing import Any, Dict, List, Optional

import sqlalchemy
from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditLog
from app.models.user import User

logger = logging.getLogger(__name__)


class ApplicationAuditService:
    """申請稽核日誌服務"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_application_operation(
        self,
        application_id: int,
        action: AuditAction,
        user: User,
        request: Optional[Request] = None,
        description: Optional[str] = None,
        old_values: Optional[Dict[str, Any]] = None,
        new_values: Optional[Dict[str, Any]] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        meta_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[AuditLog]:
        """
        記錄申請操作日誌

        Args:
            application_id: 申請ID
            action: 操作類型
            user: 操作使用者
            request: FastAPI Request物件 (可選)
            description: 詳細描述 (可選)
            old_values: 變更前的值 (可選)
            new_values: 變更後的值 (可選)
            status: 操作狀態 (success, failed, error)
            error_message: 錯誤訊息 (可選)
            meta_data: 額外metadata (可選)

        Returns:
            AuditLog: 建立的稽核日誌記錄
        """
        try:
            # 從request提取額外資訊
            ip_address = None
            user_agent = None
            request_method = None
            request_url = None

            if request:
                ip_address = self._get_client_ip(request)
                user_agent = request.headers.get("user-agent")
                request_method = request.method
                request_url = str(request.url.path)

            # 建立稽核日誌記錄
            audit_log = AuditLog(
                user_id=user.id,
                action=action.value,
                resource_type="application",
                resource_id=str(application_id),
                description=description,
                old_values=old_values,
                new_values=new_values,
                ip_address=ip_address,
                user_agent=user_agent,
                request_method=request_method,
                request_url=request_url,
                status=status,
                error_message=error_message,
                meta_data=meta_data,
            )

            # 儲存到資料庫
            self.db.add(audit_log)
            await self.db.commit()
            await self.db.refresh(audit_log)

            logger.info(
                f"Audit log created: application_id={application_id}, action={action.value}, "
                f"user={user.name or user.nycu_id}, status={status}"
            )

            return audit_log

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create audit log for application {application_id}: {e}")
            # 即使稽核失敗也不應該影響主要業務邏輯
            self._fallback_log(application_id, action, user, str(e))
            return None

    async def log_view_application(
        self,
        application_id: int,
        app_id: str,
        user: User,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄查看申請"""
        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.view,
            user=user,
            request=request,
            description=f"查看申請 {app_id}",
            meta_data={"app_id": app_id},
        )

    async def log_status_update(
        self,
        application_id: int,
        app_id: str,
        old_status: str,
        new_status: str,
        user: User,
        reason: Optional[str] = None,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄申請狀態更新"""
        description = f"更新申請 {app_id} 狀態: {old_status} → {new_status}"
        if reason:
            description += f"，原因: {reason}"

        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.update,
            user=user,
            request=request,
            description=description,
            old_values={"status": old_status},
            new_values={"status": new_status, "reason": reason},
            meta_data={"app_id": app_id, "update_type": "status"},
        )

    async def log_delete_application(
        self,
        application_id: int,
        app_id: str,
        user: User,
        reason: str,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄刪除申請"""
        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.delete,
            user=user,
            request=request,
            description=f"刪除申請 {app_id}，原因: {reason}",
            meta_data={"app_id": app_id, "deletion_reason": reason},
        )

    async def log_document_upload(
        self,
        application_id: int,
        app_id: str,
        file_type: str,
        filename: str,
        file_size: int,
        user: User,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄文件上傳"""
        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.create,
            user=user,
            request=request,
            description=f"上傳文件到申請 {app_id}: {filename} ({file_type})",
            new_values={
                "file_type": file_type,
                "filename": filename,
                "file_size": file_size,
            },
            meta_data={"app_id": app_id, "operation_type": "document_upload"},
        )

    async def log_document_request(
        self,
        application_id: int,
        app_id: str,
        requested_documents: List[Dict[str, str]],
        user: User,
        request_message: str,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄補件請求"""
        doc_names = [doc.get("name", doc.get("type", "")) for doc in requested_documents]
        description = f"請求補件: {app_id}，需補文件: {', '.join(doc_names)}"

        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.request_documents,
            user=user,
            request=request,
            description=description,
            new_values={
                "requested_documents": requested_documents,
                "request_message": request_message,
            },
            meta_data={"app_id": app_id, "document_count": len(requested_documents)},
        )

    async def log_application_submit(
        self,
        application_id: int,
        app_id: str,
        user: User,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄申請提交"""
        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.submit,
            user=user,
            request=request,
            description=f"提交申請 {app_id}",
            new_values={"submitted_at": "now"},
            meta_data={"app_id": app_id},
        )

    async def log_application_approve(
        self,
        application_id: int,
        app_id: str,
        user: User,
        comments: Optional[str] = None,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄申請核准"""
        description = f"核准申請 {app_id}"
        if comments:
            description += f"，意見: {comments}"

        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.approve,
            user=user,
            request=request,
            description=description,
            new_values={"approved_by": user.id, "comments": comments},
            meta_data={"app_id": app_id},
        )

    async def log_application_reject(
        self,
        application_id: int,
        app_id: str,
        user: User,
        reason: str,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄申請駁回"""
        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.reject,
            user=user,
            request=request,
            description=f"駁回申請 {app_id}，原因: {reason}",
            new_values={"rejected_by": user.id, "rejection_reason": reason},
            meta_data={"app_id": app_id},
        )

    async def log_application_create(
        self,
        application_id: int,
        app_id: str,
        user: User,
        scholarship_type: str,
        is_draft: bool = False,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄申請建立"""
        status_text = "草稿" if is_draft else "申請"
        description = f"建立{status_text} {app_id} ({scholarship_type})"

        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.create,
            user=user,
            request=request,
            description=description,
            new_values={
                "app_id": app_id,
                "scholarship_type": scholarship_type,
                "is_draft": is_draft,
                "created_by": user.id,
            },
            meta_data={"app_id": app_id, "is_draft": is_draft},
        )

    async def log_application_update(
        self,
        application_id: int,
        app_id: str,
        user: User,
        updated_fields: Optional[List[str]] = None,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄申請更新"""
        description = f"更新申請 {app_id}"
        if updated_fields:
            description += f"，變更欄位: {', '.join(updated_fields)}"

        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.update,
            user=user,
            request=request,
            description=description,
            new_values={"updated_fields": updated_fields},
            meta_data={"app_id": app_id, "update_type": "form_data"},
        )

    async def log_application_withdraw(
        self,
        application_id: int,
        app_id: str,
        user: User,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄申請撤回"""
        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.withdraw,
            user=user,
            request=request,
            description=f"撤回申請 {app_id}",
            new_values={"withdrawn_by": user.id},
            meta_data={"app_id": app_id},
        )

    async def log_student_data_update(
        self,
        application_id: int,
        app_id: str,
        user: User,
        updated_fields: Optional[List[str]] = None,
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄學生資料更新 (銀行帳號、指導教授資訊等)"""
        description = f"更新學生資料 {app_id}"
        if updated_fields:
            description += f"，變更欄位: {', '.join(updated_fields)}"

        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.update,
            user=user,
            request=request,
            description=description,
            new_values={"updated_fields": updated_fields},
            meta_data={"app_id": app_id, "update_type": "student_data"},
        )

    async def log_bank_verification(
        self,
        application_id: int,
        app_id: str,
        user: User,
        verification_result: Dict[str, Any],
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄銀行帳戶驗證操作"""
        success = verification_result.get("success", False)
        verification_status = verification_result.get("verification_status", "unknown")

        if success:
            overall_match = verification_result.get("overall_match", False)
            average_confidence = verification_result.get("average_confidence", 0.0)
            compared_fields = verification_result.get("compared_fields", 0)

            match_text = "相符" if overall_match else "不相符"
            description = f"驗證銀行帳戶 {app_id}: {match_text} (信心度: {average_confidence:.2f}, 比對欄位: {compared_fields})"

            meta_data = {
                "app_id": app_id,
                "verification_status": verification_status,
                "overall_match": overall_match,
                "average_confidence": average_confidence,
                "compared_fields": compared_fields,
            }
        else:
            error = verification_result.get("error", "Unknown error")
            description = f"驗證銀行帳戶失敗 {app_id}: {error}"
            meta_data = {
                "app_id": app_id,
                "verification_status": verification_status,
                "error": error,
            }

        return await self.log_application_operation(
            application_id=application_id,
            action=AuditAction.verify_bank_account,
            user=user,
            request=request,
            description=description,
            new_values=verification_result,
            status="success" if success else "failed",
            error_message=verification_result.get("error") if not success else None,
            meta_data=meta_data,
        )

    async def log_batch_bank_verification(
        self,
        application_ids: List[int],
        user: User,
        batch_result: Dict[str, Any],
        request: Optional[Request] = None,
    ) -> Optional[AuditLog]:
        """記錄批次銀行帳戶驗證操作"""
        total_processed = batch_result.get("total_processed", 0)
        successful_verifications = batch_result.get("successful_verifications", 0)
        failed_verifications = batch_result.get("failed_verifications", 0)
        summary = batch_result.get("summary", {})

        description = (
            f"批次驗證銀行帳戶: 處理 {total_processed} 筆申請, " f"成功 {successful_verifications} 筆, 失敗 {failed_verifications} 筆"
        )

        # Use the first application ID as the resource ID for batch operations
        primary_app_id = application_ids[0] if application_ids else 0

        return await self.log_application_operation(
            application_id=primary_app_id,
            action=AuditAction.batch_verify_bank_accounts,
            user=user,
            request=request,
            description=description,
            new_values={
                "total_processed": total_processed,
                "successful_verifications": successful_verifications,
                "failed_verifications": failed_verifications,
                "summary": summary,
            },
            meta_data={
                "application_ids": application_ids,
                "batch_size": len(application_ids),
                "verification_summary": summary,
            },
        )

    async def get_application_audit_trail(
        self,
        application_id: int,
        limit: int = 50,
        offset: int = 0,
        action_filter: Optional[str] = None,
        user_filter: Optional[int] = None,
    ) -> List[AuditLog]:
        """
        取得申請稽核軌跡

        Args:
            application_id: 申請ID
            limit: 筆數限制
            offset: 偏移量
            action_filter: 動作篩選
            user_filter: 使用者篩選

        Returns:
            List[AuditLog]: 稽核日誌列表（包含使用者資訊）
        """
        try:
            from sqlalchemy.orm import selectinload

            query = (
                select(AuditLog)
                .options(selectinload(AuditLog.user))  # Eager load user to avoid lazy loading issues in async
                .where(AuditLog.resource_type == "application")
                .where(AuditLog.resource_id == str(application_id))
            )

            if action_filter:
                query = query.where(AuditLog.action == action_filter)

            if user_filter:
                query = query.where(AuditLog.user_id == user_filter)

            query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)

            result = await self.db.execute(query)
            audit_logs = result.scalars().all()

            return audit_logs

        except Exception as e:
            logger.error(f"Failed to retrieve audit trail for application {application_id}: {e}")
            return []

    async def get_scholarship_audit_trail(
        self,
        scholarship_type_id: int,
        limit: int = 500,
        offset: int = 0,
        action_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        取得獎學金類型的所有稽核軌跡（包含已刪除申請的日誌）

        Args:
            scholarship_type_id: 獎學金類型ID
            limit: 筆數限制
            offset: 偏移量
            action_filter: 動作篩選

        Returns:
            List[Dict]: 稽核日誌列表（包含申請和學生資訊）
        """
        try:
            from sqlalchemy.orm import selectinload

            from app.models.application import Application

            # Join audit logs with applications to filter by scholarship type
            # Note: We DON'T filter by application status - this ensures deleted app logs are included
            query = (
                select(AuditLog, Application)
                .join(
                    Application,
                    AuditLog.resource_id == Application.id.cast(sqlalchemy.String),
                )
                .options(selectinload(AuditLog.user))  # Eager load user to avoid lazy loading issues
                .where(AuditLog.resource_type == "application")
                .where(Application.scholarship_type_id == scholarship_type_id)
            )

            if action_filter:
                query = query.where(AuditLog.action == action_filter)

            query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)

            result = await self.db.execute(query)
            rows = result.all()

            # Enrich audit logs with application information
            enriched_logs = []
            for audit_log, application in rows:
                log_dict = {
                    "id": audit_log.id,
                    "action": audit_log.action,
                    "user_id": audit_log.user_id,
                    "user_name": audit_log.user.name if audit_log.user else "Unknown",
                    "description": audit_log.description,
                    "old_values": audit_log.old_values,
                    "new_values": audit_log.new_values,
                    "ip_address": audit_log.ip_address,
                    "request_method": audit_log.request_method,
                    "request_url": audit_log.request_url,
                    "status": audit_log.status,
                    "error_message": audit_log.error_message,
                    "meta_data": audit_log.meta_data,
                    "created_at": audit_log.created_at,
                    # Add application context
                    "application_id": application.id,
                    "app_id": application.app_id,
                    "scholarship_type_id": application.scholarship_type_id,
                    "student_name": application.student_data.get("std_cname") if application.student_data else None,
                }
                enriched_logs.append(log_dict)

            return enriched_logs

        except Exception as e:
            logger.error(
                f"Failed to retrieve scholarship audit trail for scholarship_type_id {scholarship_type_id}: {e}"
            )
            return []

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

    def _fallback_log(self, application_id: int, action: AuditAction, user: User, error: str):
        """當資料庫稽核失敗時的fallback logging"""
        # Safely extract user identifier without triggering lazy loading
        # which would fail if session is aborted
        try:
            user_identifier = f"{user.nycu_id} (ID: {user.id})"
        except Exception:
            user_identifier = "Unknown"

        fallback_message = (
            f"[AUDIT FALLBACK] application_id={application_id}, action={action.value}, "
            f"user={user_identifier}, db_error={error}"
        )
        logger.error(fallback_message)

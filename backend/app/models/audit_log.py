"""
Audit log model for tracking system activities
"""

import enum

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class AuditAction(enum.Enum):
    """Audit action enum"""

    create = "create"
    update = "update"
    delete = "delete"
    view = "view"
    submit = "submit"
    approve = "approve"
    reject = "reject"
    login = "login"
    logout = "logout"
    export = "export"
    import_ = "import"  # Use import_ to avoid Python keyword conflict
    request_documents = "request_documents"  # Request missing documents from student

    # Review operations for different roles
    professor_review = "professor_review"  # Professor review
    admin_review = "admin_review"  # Admin/super admin review

    # College-side operations
    college_review = "college_review"  # College initial review (approve/reject/conditional)
    college_review_update = "college_review_update"  # Update existing review
    finalize_ranking = "finalize_ranking"  # Lock ranking (make read-only)
    unfinalize_ranking = "unfinalize_ranking"  # Unlock ranking
    execute_distribution = "execute_distribution"  # Execute quota distribution
    delete_ranking = "delete_ranking"  # Delete ranking
    withdraw = "withdraw"  # Withdraw application

    # Bank verification operations
    verify_bank_account = "verify_bank_account"  # Verify single bank account
    batch_verify_bank_accounts = "batch_verify_bank_accounts"  # Batch verify bank accounts


class AuditLog(Base):
    """Audit log model for tracking user activities"""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # 活動資訊
    action = Column(String(50), nullable=False)
    resource_type = Column(String(50), nullable=False)  # user, application, review, etc.
    resource_id = Column(String(50))  # 資源ID
    resource_name = Column(String(200))  # 資源名稱

    # 活動詳情
    description = Column(Text)
    old_values = Column(JSON)  # 修改前的值
    new_values = Column(JSON)  # 修改後的值

    # 請求資訊
    ip_address = Column(String(45))  # IPv6 最長45字元
    user_agent = Column(Text)
    request_method = Column(String(10))
    request_url = Column(String(500))
    request_headers = Column(JSON)

    # 結果資訊
    status = Column(String(20))  # success, failed, error
    error_message = Column(Text)
    response_time_ms = Column(Integer)  # 回應時間(毫秒)

    # 時間戳記
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 追蹤ID
    trace_id = Column(String(100))  # 用於追蹤同一次請求的多個操作
    session_id = Column(String(100))  # 用於追蹤用戶會話

    # 額外資料
    meta_data = Column(JSON)  # 額外的日誌資料

    # 關聯
    user = relationship("User", back_populates="audit_logs")

    def __repr__(self):
        return f"<AuditLog(id={self.id}, user_id={self.user_id}, action={self.action})>"

    @classmethod
    def create_log(
        cls,
        user_id: int,
        action: str,
        resource_type: str,
        resource_id: str = None,
        description: str = None,
        **kwargs,
    ):
        """Create audit log entry"""
        return cls(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            **kwargs,
        )

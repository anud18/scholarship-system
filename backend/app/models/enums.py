"""
Shared enums for the scholarship system
"""

import enum


class Semester(enum.Enum):
    """Semester enum"""

    first = "first"
    second = "second"
    yearly = "yearly"  # 全年


class ApplicationStatus(enum.Enum):
    """
    Application status - User-facing outcome
    顯示給學生/管理者看的申請結果
    """

    # 編輯中狀態
    draft = "draft"  # 草稿

    # 進行中狀態
    submitted = "submitted"  # 已送出
    under_review = "under_review"  # 審批中
    pending_documents = "pending_documents"  # 補件中

    # 完成狀態（最終結果）
    approved = "approved"  # 核准
    partial_approved = "partial_approved"  # 部分核准
    rejected = "rejected"  # 駁回

    # 特殊狀態
    returned = "returned"  # 退回修改
    withdrawn = "withdrawn"  # 撤回
    cancelled = "cancelled"  # 取消
    manual_excluded = "manual_excluded"  # 手動排除
    deleted = "deleted"  # 刪除


class ReviewStage(enum.Enum):
    """
    Review stage - Internal workflow position
    追蹤申請在審核流程中的位置
    """

    # 學生階段
    student_draft = "student_draft"  # 學生編輯中
    student_submitted = "student_submitted"  # 學生已送出

    # 教授審核階段
    professor_review = "professor_review"  # 教授審核中
    professor_reviewed = "professor_reviewed"  # 教授已審核

    # 學院審核階段
    college_review = "college_review"  # 學院審核中
    college_reviewed = "college_reviewed"  # 學院已審核

    # 學院排名階段
    college_ranking = "college_ranking"  # 學院排名中
    college_ranked = "college_ranked"  # 學院已排名

    # 管理員審核階段
    admin_review = "admin_review"  # 管理員審核中
    admin_reviewed = "admin_reviewed"  # 管理員已審核

    # 配額分發階段
    quota_distribution = "quota_distribution"  # 配額分發中
    quota_distributed = "quota_distributed"  # 配額已分發

    # 造冊階段
    roster_preparation = "roster_preparation"  # 造冊準備中
    roster_prepared = "roster_prepared"  # 造冊已完成
    roster_submitted = "roster_submitted"  # 造冊已送出

    # 完成階段
    completed = "completed"  # 流程完成
    archived = "archived"  # 已歸檔


class SubTypeSelectionMode(enum.Enum):
    """Sub-type selection mode enum"""

    single = "single"  # 僅能選擇一個子項目
    multiple = "multiple"  # 可自由多選
    hierarchical = "hierarchical"  # 需依序選取：A → AB → ABC


class ApplicationCycle(enum.Enum):
    """Application cycle/period type enum"""

    semester = "semester"
    yearly = "yearly"


class QuotaManagementMode(enum.Enum):
    """Quota management mode enum"""

    none = "none"  # 無配額限制
    simple = "simple"  # 簡單總配額
    college_based = "college_based"  # 學院分配配額
    matrix_based = "matrix_based"  # 矩陣配額管理 (子類型×學院)


class BatchImportStatus(enum.Enum):
    """Batch import status enum"""

    pending = "pending"  # 待確認
    processing = "processing"  # 處理中
    completed = "completed"  # 完成
    failed = "failed"  # 失敗
    cancelled = "cancelled"  # 已取消
    partial = "partial"  # 部分成功

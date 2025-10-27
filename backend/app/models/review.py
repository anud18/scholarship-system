"""
Review Models

統一審查模型，處理所有角色的審查邏輯
"""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base


class ApplicationReview(Base):
    """
    統一審查表

    用於記錄所有角色（教授、學院、管理員）的審查記錄
    """

    __tablename__ = "application_reviews"
    __table_args__ = (UniqueConstraint("application_id", "reviewer_id", name="uq_application_reviewer"),)

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False, index=True)
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    recommendation = Column(String(20), nullable=False)  # 'approve' | 'partial_approve' | 'reject'（自動計算）
    comments = Column(Text)  # 自動從 items 組合而成
    reviewed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    application = relationship("Application", back_populates="reviews")
    reviewer = relationship("User", foreign_keys=[reviewer_id])
    items = relationship("ApplicationReviewItem", back_populates="review", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ApplicationReview(id={self.id}, application_id={self.application_id}, recommendation='{self.recommendation}')>"


class ApplicationReviewItem(Base):
    """
    子項目審查記錄

    每個審查可以包含多個子項目（對應不同的獎學金子類型）
    """

    __tablename__ = "application_review_items"

    id = Column(Integer, primary_key=True, index=True)
    review_id = Column(Integer, ForeignKey("application_reviews.id"), nullable=False, index=True)
    sub_type_code = Column(String(50), nullable=False, index=True)  # 子項目代碼（例如 'nstc', 'moe_1w', 'default'）
    recommendation = Column(String(20), nullable=False)  # 'approve' | 'reject'
    comments = Column(Text)  # 評論（拒絕時建議必填，同意時可空）

    # Relationships
    review = relationship("ApplicationReview", back_populates="items")

    def __repr__(self):
        return f"<ApplicationReviewItem(id={self.id}, sub_type_code='{self.sub_type_code}', recommendation='{self.recommendation}')>"

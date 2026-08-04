from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class SupplementaryDoc(Base):
    """Admin-managed supplementary reference document shown to students
    in the application wizard's 參考文件 list."""

    __tablename__ = "supplementary_docs"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    object_name = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=False)
    file_size = Column(Integer, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    created_by_user = relationship("User", foreign_keys=[created_by])

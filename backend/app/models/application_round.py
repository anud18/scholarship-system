"""
多梯次申請 (additional application rounds) model

A ScholarshipConfiguration's own ``application_start_date`` / ``application_end_date``
is always the first round (第一梯次); its ``first_round_open_sub_types`` names the
sub-types round 1 opens (NULL = every sub-type). Each row here opens one more round (第二梯次, 第三梯次, ...) with its own application window, the subset of
sub-types students may apply for, and optional per-round review windows. A NULL
review window falls back to the configuration's general window.

College rankings keep later rounds behind earlier ones (see app.services.ranking_groups).
"""

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base

# Round number of the configuration's own application window.
FIRST_APPLICATION_ROUND = 1


def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Treat naive datetimes as UTC (same convention as ScholarshipConfiguration)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def normalize_sub_type_codes(codes: Optional[Iterable]) -> List[str]:
    """Lowercase, stripped, de-duplicated sub-type codes in their original order."""
    normalized = [str(code).strip().lower() for code in (codes or []) if code is not None and str(code).strip()]
    return list(dict.fromkeys(normalized))


def window_contains(start: Optional[datetime], end: Optional[datetime], now: datetime) -> bool:
    """True when both bounds are set and ``start <= now <= end``."""
    start_utc, end_utc = as_utc(start), as_utc(end)
    if start_utc is None or end_utc is None:
        return False
    return start_utc <= now <= end_utc


class ScholarshipApplicationRound(Base):
    """一個額外的申請梯次（第二梯次起）"""

    __tablename__ = "scholarship_application_rounds"

    id = Column(Integer, primary_key=True, index=True)
    configuration_id = Column(
        Integer,
        ForeignKey("scholarship_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    round_number = Column(Integer, nullable=False)  # 2 = 第二梯次, 3 = 第三梯次 ...

    application_start_date = Column(DateTime(timezone=True), nullable=False)
    application_end_date = Column(DateTime(timezone=True), nullable=False)

    # Sub-type codes open in this round, e.g. ["nstc", "moe_1w"]
    open_sub_types = Column(JSON, nullable=False, default=list)

    # Per-round review windows; NULL → the configuration's general window
    professor_review_start = Column(DateTime(timezone=True), nullable=True)
    professor_review_end = Column(DateTime(timezone=True), nullable=True)
    college_review_start = Column(DateTime(timezone=True), nullable=True)
    college_review_end = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    configuration = relationship("ScholarshipConfiguration", back_populates="application_rounds")

    __table_args__ = (UniqueConstraint("configuration_id", "round_number", name="uq_application_round_config_number"),)

    def __repr__(self):
        return f"<ScholarshipApplicationRound(config={self.configuration_id}, round={self.round_number})>"

    @property
    def open_sub_type_codes(self) -> List[str]:
        return normalize_sub_type_codes(self.open_sub_types)

    def is_open(self, now: Optional[datetime] = None) -> bool:
        return window_contains(
            self.application_start_date, self.application_end_date, now or datetime.now(timezone.utc)
        )

    def to_dict(self) -> dict:
        def iso(value: Optional[datetime]) -> Optional[str]:
            return value.isoformat() if value else None

        return {
            "id": self.id,
            "round_number": self.round_number,
            "application_start_date": iso(self.application_start_date),
            "application_end_date": iso(self.application_end_date),
            "open_sub_types": self.open_sub_type_codes,
            "professor_review_start": iso(self.professor_review_start),
            "professor_review_end": iso(self.professor_review_end),
            "college_review_start": iso(self.college_review_start),
            "college_review_end": iso(self.college_review_end),
            "is_open": self.is_open(),
        }

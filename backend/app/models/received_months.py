"""
Imported received-months ledger (匯入已領月份數).

Two tables:

``received_month_imports``
    One row per upload run. Created in ``pending`` state by the preview
    endpoint (holding the parsed rows in ``parsed_data``) and flipped to
    ``completed`` once the admin confirms. Nothing reaches the ledger until
    that confirmation.

``student_received_month_records``
    The ledger itself: one live row per (學號, scholarship_type), holding the
    lifetime 匯入月份數 plus the verbatim source row so an admin can always see
    what the original file said.

``student_number`` is a plain string with NO foreign key on purpose — the file
comes from 國科會 and may list students this system has never seen. The record
simply waits until they appear.

See docs/received-months-calculation.md for how this composes with the
system-computed value.
"""

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base_class import Base
from app.models.college_review import get_json_type

# Import run lifecycle. Kept as plain strings rather than a PG enum: this is an
# internal workflow flag, not a domain value shared with the frontend enums.
IMPORT_STATUS_PENDING = "pending"
IMPORT_STATUS_COMPLETED = "completed"
IMPORT_STATUS_CANCELLED = "cancelled"

# Marks ledger rows carried over from the retired
# /manual-distribution/import-received-months path, which stored only a bare
# month count — those rows have no source row and no covered range.
LEGACY_IMPORT_FILE_NAME = "legacy-migration"


class ReceivedMonthImport(Base):
    """One 匯入已領月份數 upload run."""

    __tablename__ = "received_month_imports"

    id = Column(Integer, primary_key=True, index=True)

    importer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=False, index=True)

    file_name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default=IMPORT_STATUS_PENDING, index=True)

    # Parsed rows awaiting confirmation. Cleared on confirm/cancel so a pending
    # upload never leaves student PII sitting in the table indefinitely.
    parsed_data = Column(get_json_type(), nullable=True)
    data_expires_at = Column(DateTime(timezone=True), nullable=True, index=True)

    total_rows = Column(Integer, nullable=False, default=0)
    valid_rows = Column(Integer, nullable=False, default=0)
    warning_rows = Column(Integer, nullable=False, default=0)
    error_rows = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    importer = relationship("User", foreign_keys=[importer_id])
    scholarship_type = relationship("ScholarshipType", foreign_keys=[scholarship_type_id])
    records = relationship("StudentReceivedMonthRecord", back_populates="import_run")

    def __repr__(self) -> str:
        return (
            f"<ReceivedMonthImport(id={self.id}, file={self.file_name!r}, "
            f"status={self.status}, rows={self.total_rows})>"
        )


class StudentReceivedMonthRecord(Base):
    """Lifetime 匯入月份數 for one student under one scholarship type."""

    __tablename__ = "student_received_month_records"
    __table_args__ = (
        UniqueConstraint("student_number", "scholarship_type_id", name="uq_received_months_student_type"),
        Index("ix_received_months_type_student", "scholarship_type_id", "student_number"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # 學號 / std_stdcode. No FK — see module docstring.
    student_number = Column(String(20), nullable=False, index=True)
    scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=False)

    # Inclusive month span derived from 領獎起始月份 → 目前領獎月份.
    months = Column(Integer, nullable=False)

    # The covered range as ROC yyyymm integers (113年9月 -> 11309), so the UI can
    # show「匯入 24 (113/9–115/8)」without re-parsing raw_row. NULL for rows
    # carried over by the legacy migration, which had no range.
    award_start_month = Column(Integer, nullable=True)
    award_current_month = Column(Integer, nullable=True)

    # Verbatim source row, keyed by the file's own header text. This is what
    # backs「看當初匯入文件 column 的值」and is why NSTC can add or rename
    # columns without a migration.
    raw_row = Column(get_json_type(), nullable=True)

    import_id = Column(Integer, ForeignKey("received_month_imports.id"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    import_run = relationship("ReceivedMonthImport", back_populates="records")
    scholarship_type = relationship("ScholarshipType", foreign_keys=[scholarship_type_id])

    def __repr__(self) -> str:
        return (
            f"<StudentReceivedMonthRecord(student={self.student_number}, "
            f"type={self.scholarship_type_id}, months={self.months})>"
        )

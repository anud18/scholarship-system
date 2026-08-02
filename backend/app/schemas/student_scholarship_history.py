"""Response schemas for admin student scholarship history endpoint."""

import re
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

# Shared by the admin single-lookup and the batch endpoints; mirrored client-side
# in frontend/components/admin/student-history/parse-student-numbers.ts.
STUDENT_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9]{4,15}$")


class AcademicBasicInfo(BaseModel):
    """SIS basic info subset rendered on the page.

    Numeric reference fields (std_degree, std_studingstatus) and code fields
    (std_academyno) are forwarded as strings; the frontend resolves them to
    display labels via the reference-data hooks.
    """

    std_cname: Optional[str] = None
    std_ename: Optional[str] = None
    std_degree: Optional[str] = None
    std_studingstatus: Optional[str] = None
    std_academyno: Optional[str] = None
    std_aca_cname: Optional[str] = None
    std_depname: Optional[str] = None
    std_depno: Optional[str] = None
    com_email: Optional[str] = None


class AcademicInfo(BaseModel):
    """Wraps SIS lookup result. available=False when SIS errored."""

    available: bool
    error: Optional[str] = None
    basic_info: Optional[AcademicBasicInfo] = None


class PaymentRecord(BaseModel):
    """One paid roster item belonging to the student.

    "Paid" = the parent roster's status is COMPLETED or LOCKED (Excel produced,
    distribution finalised). In-flight statuses (DRAFT/PROCESSING/FAILED) are
    excluded by the service layer.
    """

    roster_id: int
    roster_code: str
    period_label: str
    academic_year: int
    roster_cycle: str  # monthly / semi_yearly / yearly
    scholarship_name: str
    scholarship_amount: Decimal
    scholarship_subtype: Optional[str] = None
    # Resolved via the roster's configuration; groups payments under the same
    # scholarship type as the imported received-months records.
    scholarship_type_id: Optional[int] = None
    allocation_year: Optional[int] = None
    locked_at: Optional[datetime] = None

    # G25 (#987): post-payment revocation/suspension context. A student whose
    # allocation was revoked AFTER the roster locked still shows up here (the
    # payment happened / was finalized) — the viewer must see that context
    # instead of an unqualified「已領取」row.
    quota_allocation_status: Optional[str] = None
    revoked_at: Optional[datetime] = None
    revoke_reason: Optional[str] = None
    suspended_at: Optional[datetime] = None
    suspend_reason: Optional[str] = None


class HistorySummary(BaseModel):
    """Aggregates across all payment_records."""

    total_records: int
    total_amount: Decimal
    scholarship_type_count: int = Field(..., description="Number of distinct scholarship_name values")
    total_received_months: int = Field(
        0,
        description=(
            "總領月份數 — 匯入 + 系統 summed across every scholarship type. "
            "Caps such as the 36-month PhD limit apply per scholarship type, "
            "not to this total; the per-type split is in received_months."
        ),
    )
    snapshot_name: Optional[str] = Field(
        None,
        description="Student name from the most recent roster item; used when SIS fails",
    )


class ReceivedMonthsBreakdown(BaseModel):
    """已領月份數 for one scholarship type, split into its two halves.

    ``total = imported_months + system_months``. The halves never cover the same
    month — the imported file records payments made before this system took over
    roster generation. See docs/adr/0001-received-months-are-additive.md.

    On this page the system half is counted over the student's whole payment
    history (the page has no academic-year context), unlike the 手動分發 panel
    which counts only the year being distributed.
    """

    scholarship_type_id: Optional[int] = None
    scholarship_name: str
    total_months: int
    imported_months: int
    system_months: int

    # Present only when an import exists for this (學號, scholarship type).
    award_start_month: Optional[str] = Field(None, description="領獎起始月份, e.g. 113年9月")
    award_current_month: Optional[str] = Field(None, description="目前領獎月份, e.g. 115年8月")
    raw_row: Optional[dict] = Field(
        None,
        description="Verbatim source row keyed by the imported file's own header text",
    )
    file_name: Optional[str] = None
    imported_at: Optional[str] = None


class StudentScholarshipHistoryData(BaseModel):
    """Full response payload (data of the ApiResponse envelope)."""

    student_number: str
    academic_info: AcademicInfo
    summary: HistorySummary
    payment_records: List[PaymentRecord]
    received_months: List[ReceivedMonthsBreakdown] = Field(
        default_factory=list,
        description="已領月份數 per scholarship type (匯入 + 系統)",
    )


class BatchStudentHistoryRequest(BaseModel):
    """Multi-student lookup request body for POST /student-history/batch.

    Size and per-number format limits are enforced in the endpoint (uniform
    400s with zh-TW messages) rather than as Field constraints (422s).
    """

    student_numbers: List[str]


class StudentHistoryVisibilityUpdate(BaseModel):
    """Admin toggle body for PUT /student-history/visibility.

    Both fields are optional and applied independently: omitting one leaves
    that audience's setting untouched, so the two switches never clobber each
    other. Sending neither is a 422 (nothing to do).

    The response shape (both switches) is produced by
    ``StudentHistoryVisibility.to_dict()`` in the service layer; endpoints in
    this project return plain ApiResponse dicts, never a ``response_model``.
    """

    student_enabled: Optional[bool] = None
    college_enabled: Optional[bool] = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> "StudentHistoryVisibilityUpdate":
        if self.student_enabled is None and self.college_enabled is None:
            raise ValueError("請至少指定一項開放設定")
        return self

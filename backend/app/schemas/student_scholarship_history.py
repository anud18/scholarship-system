"""Response schemas for admin student scholarship history endpoint."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


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
    allocation_year: Optional[int] = None
    locked_at: Optional[datetime] = None


class HistorySummary(BaseModel):
    """Aggregates across all payment_records."""

    total_records: int
    total_amount: Decimal
    scholarship_type_count: int = Field(..., description="Number of distinct scholarship_name values")
    snapshot_name: Optional[str] = Field(
        None,
        description="Student name from the most recent roster item; used when SIS fails",
    )


class StudentScholarshipHistoryData(BaseModel):
    """Full response payload (data of the ApiResponse envelope)."""

    student_number: str
    academic_info: AcademicInfo
    summary: HistorySummary
    payment_records: List[PaymentRecord]

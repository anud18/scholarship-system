"""
College Review Pydantic Schemas

This module contains all request/response schemas for college review operations including:
- College review creation and updates
- Ranking management
- Quota distribution
- Student preview
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CollegeReviewCreate(BaseModel):
    """
    Schema for creating a college review.

    Note: Scoring fields removed. Review is based on ranking position and comments only.
    """

    review_comments: Optional[str] = Field(None, max_length=2000, description="Detailed review comments")
    recommendation: str = Field(..., description="Review recommendation", pattern="^(approve|reject|conditional)$")
    decision_reason: Optional[str] = Field(None, max_length=1000, description="Reason for the recommendation")
    is_priority: Optional[bool] = Field(False, description="Mark as priority application")
    needs_special_attention: Optional[bool] = Field(False, description="Flag for special review")
    preliminary_rank: Optional[int] = Field(None, description="Initial ranking position within sub-type")
    final_rank: Optional[int] = Field(None, description="Final ranking position after adjustments")


class CollegeReviewUpdate(BaseModel):
    """
    Schema for updating a college review.

    Note: Scoring fields removed. Update ranking position and comments only.
    """

    review_comments: Optional[str] = Field(None, max_length=2000)
    recommendation: Optional[str] = Field(None, pattern="^(approve|reject|conditional)$")
    decision_reason: Optional[str] = Field(None, max_length=1000)
    is_priority: Optional[bool] = None
    needs_special_attention: Optional[bool] = None
    preliminary_rank: Optional[int] = None
    final_rank: Optional[int] = None


class CollegeReviewResponse(BaseModel):
    """
    Schema for college review response.

    Note: Scoring fields removed. Returns ranking position and comments only.
    """

    id: int
    application_id: int
    reviewer_id: int
    # Note: All score fields removed (ranking_score, academic_score, etc.)
    review_comments: Optional[str]
    recommendation: str
    decision_reason: Optional[str]
    preliminary_rank: Optional[int]
    final_rank: Optional[int]
    sub_type_group: Optional[str]
    review_status: str
    is_priority: bool
    needs_special_attention: bool
    reviewed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RankingOrderUpdate(BaseModel):
    """Schema for updating ranking order"""

    item_id: int
    position: int


class QuotaDistributionRequest(BaseModel):
    """Schema for quota distribution request"""

    distribution_rules: Optional[Dict[str, Any]] = Field(None, description="Custom distribution rules")


class RankingUpdate(BaseModel):
    """Schema for updating ranking metadata"""

    ranking_name: str = Field(..., min_length=1, max_length=200, description="New ranking name")


class StudentPreviewBasic(BaseModel):
    """Schema for student basic information in preview"""

    student_id: str = Field(..., description="Student ID")
    student_name: str = Field(..., description="Student name")
    department_name: Optional[str] = Field(None, description="Department name")
    academy_name: Optional[str] = Field(None, description="Academy name")
    term_count: Optional[int] = Field(None, description="Number of terms enrolled")
    degree: Optional[str] = Field(None, description="Degree level")
    enrollyear: Optional[str] = Field(None, description="Enrollment year")
    sex: Optional[str] = Field(None, description="Gender")


class StudentTermData(BaseModel):
    """Schema for student term data - includes all available fields from student API"""

    # Basic term info
    academic_year: str = Field(..., description="Academic year")
    term: str = Field(..., description="Term")
    term_count: Optional[int] = Field(None, description="Total terms enrolled")

    # Academic performance
    gpa: Optional[float] = Field(None, description="GPA for this term")
    ascore_gpa: Optional[float] = Field(None, description="Alternative score GPA")

    # Rankings
    placings: Optional[int] = Field(None, description="Overall ranking position")
    placings_rate: Optional[float] = Field(None, description="Overall ranking percentage")
    dept_placing: Optional[int] = Field(None, description="Department ranking position")
    dept_placing_rate: Optional[float] = Field(None, description="Department ranking percentage")

    # Student status
    studying_status: Optional[int] = Field(None, description="Studying status code")
    degree: Optional[int] = Field(None, description="Degree level code")

    # Academic organization
    academy_no: Optional[str] = Field(None, description="Academy/College code")
    academy_name: Optional[str] = Field(None, description="Academy/College name")
    dept_no: Optional[str] = Field(None, description="Department code")
    dept_name: Optional[str] = Field(None, description="Department name")


class StudentPreviewResponse(BaseModel):
    """Schema for student preview response"""

    basic: StudentPreviewBasic
    recent_terms: List[StudentTermData] = Field(default_factory=list, description="Recent term data")


class RankingImportItem(BaseModel):
    """Schema for importing ranking data from Excel"""

    student_id: str = Field(..., description="Student ID (學號)")
    student_name: str = Field(..., description="Student name (姓名)")
    rank_position: int = Field(..., ge=1, description="Ranking position (排名)")

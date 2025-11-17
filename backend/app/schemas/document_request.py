"""
Document Request schemas for API requests and responses
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DocumentRequestCreate(BaseModel):
    """Schema for creating a document request"""

    requested_documents: List[str] = Field(
        ...,
        description="List of document types/categories needed",
        example=["transcript", "recommendation_letter", "research_plan"],
    )
    reason: str = Field(
        ...,
        description="Why these documents are needed",
        min_length=10,
        max_length=1000,
        example="需要補充成績單以確認學業成績",
    )
    notes: Optional[str] = Field(
        None,
        description="Additional notes or instructions for the student",
        max_length=2000,
        example="請於一週內上傳，並確保文件清晰可讀",
    )


class DocumentRequestFulfill(BaseModel):
    """Schema for fulfilling a document request"""

    notes: Optional[str] = Field(None, description="Notes when marking request as fulfilled", max_length=500)


class DocumentRequestCancel(BaseModel):
    """Schema for cancelling a document request"""

    cancellation_reason: str = Field(
        ...,
        description="Reason for cancelling the request",
        min_length=5,
        max_length=500,
        example="申請已被駁回，無需補件",
    )


class DocumentRequestResponse(BaseModel):
    """Full document request response schema"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    requested_by_id: int
    requested_at: datetime

    requested_documents: List[str]
    reason: str
    notes: Optional[str] = None

    status: str  # Using string value from enum
    fulfilled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancelled_by_id: Optional[int] = None
    cancellation_reason: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    # Additional fields for response
    requested_by_name: Optional[str] = None
    cancelled_by_name: Optional[str] = None
    application_app_id: Optional[str] = None  # For display purposes


class DocumentRequestListItem(BaseModel):
    """Lightweight document request schema for listing"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    application_app_id: Optional[str] = None
    requested_by_id: int
    requested_by_name: Optional[str] = None
    requested_at: datetime
    requested_documents: List[str]
    reason: str
    status: str
    fulfilled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    created_at: datetime


class StudentDocumentRequestResponse(BaseModel):
    """Document request response for student view with application context"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    application_app_id: str
    scholarship_type_name: Optional[str] = None
    academic_year: Optional[int] = None
    semester: Optional[str] = None

    requested_by_name: str
    requested_at: datetime
    requested_documents: List[str]
    reason: str
    notes: Optional[str] = None
    status: str

    created_at: datetime

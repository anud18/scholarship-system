# backend/app/schemas/supplementary_doc.py
from datetime import datetime
from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SupplementaryDocResponse(BaseModel):
    id: int
    title: str
    object_name: str
    original_filename: str
    content_type: str
    file_size: int
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SupplementaryDocUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def _strip_title(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title cannot be empty")
        return stripped


class ReorderItem(BaseModel):
    id: int
    sort_order: int


class ReorderRequest(BaseModel):
    items: List[ReorderItem] = Field(..., min_length=1)

    @field_validator("items")
    @classmethod
    def _unique_orders(cls, v: List[ReorderItem]) -> List[ReorderItem]:
        orders = [i.sort_order for i in v]
        if len(orders) != len(set(orders)):
            raise ValueError("sort_order values must be unique within payload")
        ids = [i.id for i in v]
        if len(ids) != len(set(ids)):
            raise ValueError("id values must be unique within payload")
        return v

# backend/app/schemas/footer_link.py
"""Schemas for the admin-managed footer 相關連結 list."""

from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.footer_link import FooterLinkType

MAX_TITLE_LENGTH = 200
MAX_URL_LENGTH = 1000

# Only these schemes may be stored. The footer renders each entry as an
# <a href>, so permitting javascript:/data:/vbscript: would turn the admin
# form into a stored-XSS vector for every visitor of the site.
_ALLOWED_URL_SCHEMES = {"http", "https"}


def _normalize_title(value: Optional[str]) -> Optional[str]:
    """Trim a title, collapsing blank/whitespace-only input to None."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _validate_url(value: str) -> str:
    """Reject non-http(s) URLs and URLs missing a host."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("url cannot be empty")
    if len(stripped) > MAX_URL_LENGTH:
        raise ValueError(f"url must be <= {MAX_URL_LENGTH} chars")

    parsed = urlparse(stripped)
    if parsed.scheme.lower() not in _ALLOWED_URL_SCHEMES:
        raise ValueError("url must start with http:// or https://")
    if not parsed.netloc:
        raise ValueError("url must include a host")
    return stripped


class FooterLinkResponse(BaseModel):
    id: int
    title_zh: str
    title_en: Optional[str] = None
    link_type: FooterLinkType
    url: Optional[str] = None
    object_name: Optional[str] = None
    original_filename: Optional[str] = None
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    sort_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class FooterLinkCreate(BaseModel):
    """Create an external-URL footer link (file links use the upload endpoint)."""

    title_zh: str = Field(..., min_length=1, max_length=MAX_TITLE_LENGTH)
    title_en: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)
    url: str = Field(..., min_length=1, max_length=MAX_URL_LENGTH)
    is_active: bool = True

    @field_validator("title_zh")
    @classmethod
    def _strip_title_zh(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("title_zh cannot be empty")
        return stripped

    @field_validator("title_en")
    @classmethod
    def _strip_title_en(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_title(v)

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return _validate_url(v)


class FooterLinkUpdate(BaseModel):
    """Partial update. ``url`` is only accepted for link_type == url rows,
    which the endpoint enforces against the persisted row."""

    title_zh: Optional[str] = Field(default=None, min_length=1, max_length=MAX_TITLE_LENGTH)
    title_en: Optional[str] = Field(default=None, max_length=MAX_TITLE_LENGTH)
    url: Optional[str] = Field(default=None, max_length=MAX_URL_LENGTH)
    is_active: Optional[bool] = None

    @field_validator("title_zh")
    @classmethod
    def _strip_title_zh(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = v.strip()
        if not stripped:
            raise ValueError("title_zh cannot be empty")
        return stripped

    @field_validator("title_en")
    @classmethod
    def _strip_title_en(cls, v: Optional[str]) -> Optional[str]:
        return _normalize_title(v)

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return _validate_url(v)

    @model_validator(mode="after")
    def _require_at_least_one_field(self) -> "FooterLinkUpdate":
        # Test which fields the caller actually SENT, not which ones ended up
        # non-None. `{"title_en": ""}` normalizes to None but is a legitimate
        # "clear the English label" request; a value-based check would reject
        # it as an empty payload and make clearing impossible.
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class FooterLinkReorderItem(BaseModel):
    id: int
    sort_order: int


class FooterLinkReorderRequest(BaseModel):
    items: List[FooterLinkReorderItem] = Field(..., min_length=1)

    @field_validator("items")
    @classmethod
    def _unique(cls, v: List[FooterLinkReorderItem]) -> List[FooterLinkReorderItem]:
        orders = [i.sort_order for i in v]
        if len(orders) != len(set(orders)):
            raise ValueError("sort_order values must be unique within payload")
        ids = [i.id for i in v]
        if len(ids) != len(set(ids)):
            raise ValueError("id values must be unique within payload")
        return v

"""Pydantic schemas for renewal and challenge application flows.

These models cover:
- `EligibleRenewalItem`: shape of items returned by GET /api/v1/renewals/eligible
- `CreateRenewalRequest`: payload for POST /api/v1/renewals/
- `CreateChallengeRequest`: payload for POST /api/v1/renewals/challenge
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict


class EligibleRenewalItem(BaseModel):
    """A prior-year approved application surfaced as a renewal candidate."""

    model_config = ConfigDict(from_attributes=True)

    previous_application_id: int  # source application's id
    scholarship_type_id: int
    scholarship_type_name: str
    sub_scholarship_type: str  # e.g. "nstc"
    target_academic_year: int  # current_academic_year
    renewal_year: int  # = previous renewal_year if set, else previous.academic_year
    renewal_deadline: Optional[str]  # ISO datetime string


class CreateRenewalRequest(BaseModel):
    """Body for POST /api/v1/renewals/ — create renewal from a prior approved app."""

    previous_application_id: int


class CreateChallengeRequest(BaseModel):
    """Body for POST /api/v1/renewals/challenge — create challenge from an approved renewal."""

    renewal_application_id: int
    target_sub_type: str

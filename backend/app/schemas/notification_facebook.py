"""
Pydantic request schemas for Facebook-style notification endpoints.

These schemas were extracted from
``app/api/v1/endpoints/notifications_facebook_demo.py`` so the test
contract (``backend/app/tests/test_facebook_notification_request_schemas.py``)
survives the removal of the demo endpoint file. See issue #665 (category C —
dead module not router-mounted) for the cleanup context.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class CreateNotificationRequest(BaseModel):
    user_id: Optional[int] = None
    notification_type: str
    data: Dict[str, Any]
    channels: Optional[List[str]] = None
    priority: str = "normal"
    href: Optional[str] = None
    group_key: Optional[str] = None


class BatchNotificationRequest(BaseModel):
    user_ids: List[int]
    notification_type: str
    data: Dict[str, Any]
    batch_size: int = 100
    delay_minutes: int = 5


class PreferenceUpdateRequest(BaseModel):
    notification_type: str
    in_app_enabled: bool = True
    email_enabled: bool = True
    sms_enabled: bool = False
    push_enabled: bool = False
    frequency: str = "immediate"

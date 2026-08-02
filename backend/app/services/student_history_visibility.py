"""Admin-controlled visibility of 學生領獎紀錄查詢.

Two INDEPENDENT switches, stored as ``system_settings`` rows so they are
editable at runtime (no redeploy) and audited by ``ConfigurationAuditLog``:

- ``student_history_visible_to_student`` — a student may see their own
  已領獎學金總月數.
- ``student_history_visible_to_college`` — a college account may look up the
  領獎紀錄 of students in its own college.

Admin/super_admin access is never gated by these switches; they are what the
admin uses to open or close the feature for everyone else.

A missing row reads as **open**: the feature shipped unrestricted, so a
database that predates these keys keeps behaving as it does today until an
admin closes it.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import ConfigCategory, ConfigDataType, SystemSetting
from app.services.config_management_service import ConfigurationService

logger = logging.getLogger(__name__)

STUDENT_VISIBILITY_KEY = "student_history_visible_to_student"
COLLEGE_VISIBILITY_KEY = "student_history_visible_to_college"

STUDENT_VISIBILITY_DESCRIPTION = "開放學生查詢自己的獎學金領獎紀錄（已領總月數）"
COLLEGE_VISIBILITY_DESCRIPTION = "開放學院查詢本學院學生的獎學金領獎紀錄"

DEFAULT_ENABLED = True

# Same truthy set ConfigurationService.get_decrypted_value uses, so a value
# written through the generic 系統設定 editor reads back identically here.
_TRUTHY_VALUES = frozenset({"true", "1", "yes", "on"})

STUDENT_DISABLED_MESSAGE = "管理者已關閉學生查詢領獎紀錄功能"
COLLEGE_DISABLED_MESSAGE = "管理者已關閉學院查詢學生領獎紀錄功能"


@dataclass(frozen=True)
class StudentHistoryVisibility:
    """Resolved state of both switches."""

    student_enabled: bool
    college_enabled: bool

    def to_dict(self) -> Dict[str, bool]:
        return {
            "student_enabled": self.student_enabled,
            "college_enabled": self.college_enabled,
        }


def _to_bool(raw: Optional[str]) -> bool:
    if raw is None:
        return DEFAULT_ENABLED
    return raw.strip().lower() in _TRUTHY_VALUES


async def get_student_history_visibility(db: AsyncSession) -> StudentHistoryVisibility:
    """Read both switches in a single statement."""
    stmt = select(SystemSetting.key, SystemSetting.value).where(
        SystemSetting.key.in_((STUDENT_VISIBILITY_KEY, COLLEGE_VISIBILITY_KEY))
    )
    rows = (await db.execute(stmt)).all()
    values = {key: value for key, value in rows}
    return StudentHistoryVisibility(
        student_enabled=_to_bool(values.get(STUDENT_VISIBILITY_KEY)),
        college_enabled=_to_bool(values.get(COLLEGE_VISIBILITY_KEY)),
    )


async def set_student_history_visibility(
    db: AsyncSession,
    user_id: int,
    student_enabled: Optional[bool] = None,
    college_enabled: Optional[bool] = None,
) -> StudentHistoryVisibility:
    """Write the switches an admin actually changed.

    ``None`` means "leave this one alone" — the two audiences are decided
    separately, so toggling 學生 must never overwrite a concurrent 學院 change.
    Rows are created on first write (the seed may predate this feature).
    """
    config_service = ConfigurationService(db)
    updates = (
        (STUDENT_VISIBILITY_KEY, student_enabled, STUDENT_VISIBILITY_DESCRIPTION),
        (COLLEGE_VISIBILITY_KEY, college_enabled, COLLEGE_VISIBILITY_DESCRIPTION),
    )

    for key, value, description in updates:
        if value is None:
            continue
        await config_service.set_configuration(
            key=key,
            value=value,
            user_id=user_id,
            category=ConfigCategory.features,
            data_type=ConfigDataType.boolean,
            description=description,
            default_value=str(DEFAULT_ENABLED).lower(),
            change_reason="學生領獎紀錄查詢開放設定",
        )
        logger.info(
            "Student history visibility updated",
            extra={"config_key": key, "new_value": value, "changed_by": user_id},
        )

    return await get_student_history_visibility(db)

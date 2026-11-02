"""Which value an application shows for the form fields a UserProfile owns.

郵局帳號 and the 指導教授 trio are form-config fields, but the application
wizard saves them on the student's UserProfile, while imported applications
and older submissions carry copies in `submitted_form_data.fields`. The review
dialog (frontend `withProfileOwnedFields`), the staff form edit, the 學生資料彙整表
and the export package's summary PDF must all pick the same value, so every
backend reader takes it from this table.
"""

import enum
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_profile import UserProfile
from app.services.application_field_service import FIXED_ADVISOR_KEYS, FIXED_KEY_POSTAL_ACCOUNT


class Store(enum.Enum):
    FORM = "form"
    PROFILE = "profile"


Source = Tuple[Store, str]

# The account typed with this application (`account_number`) wins over the
# profile. A submitted `postal_account` ranks below the profile because the
# wizard's copy may be another student's account leaked through the shared
# form-config prefill (#1443); batch/renewal imports carry only that key.
# A submitted `bank_account` is a separate 銀行帳戶 answer, never the 郵局帳號.
POSTAL_ACCOUNT_SOURCES: Tuple[Source, ...] = (
    (Store.FORM, "account_number"),
    (Store.PROFILE, "account_number"),
    (Store.FORM, "postal_account"),
)

# form-config field id -> where its shown value comes from, first non-blank wins.
PROFILE_OWNED_FIELD_SOURCES: Dict[str, Tuple[Source, ...]] = {
    FIXED_KEY_POSTAL_ACCOUNT: POSTAL_ACCOUNT_SOURCES,
    **{key: ((Store.PROFILE, key), (Store.FORM, key)) for key in FIXED_ADVISOR_KEYS},
}

PROFILE_ATTRS = frozenset(
    key for sources in PROFILE_OWNED_FIELD_SOURCES.values() for store, key in sources if store is Store.PROFILE
)

# The submitted keys an effective value is read from: a surface that shows the
# effective value must not also show these raw copies.
PROFILE_OWNED_FORM_KEYS = frozenset(
    key for sources in PROFILE_OWNED_FIELD_SOURCES.values() for store, key in sources if store is Store.FORM
)


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def submitted_value(entry: Any) -> Any:
    return entry.get("value") if isinstance(entry, Mapping) else entry


def effective_value(
    sources: Tuple[Source, ...], submitted_fields: Mapping[str, Any], profile_values: Mapping[str, Any]
) -> Any:
    """The first non-blank source; when all are blank, the first source's own value."""
    values = [
        submitted_value(submitted_fields.get(key)) if store is Store.FORM else profile_values.get(key)
        for store, key in sources
    ]
    return next((value for value in values if not is_blank(value)), values[0])


def has_submitted_copy(field_id: str, submitted_fields: Mapping[str, Any]) -> bool:
    return any(
        store is Store.FORM and not is_blank(submitted_value(submitted_fields.get(key)))
        for store, key in PROFILE_OWNED_FIELD_SOURCES[field_id]
    )


@dataclass(frozen=True)
class EffectiveProfileFields:
    """The shown value of each profile-owned field; None when every source is blank."""

    postal_account: Optional[str]
    advisor_name: Optional[str]
    advisor_email: Optional[str]
    advisor_nycu_id: Optional[str]

    def by_field_id(self) -> Dict[str, Optional[str]]:
        return {field_id: getattr(self, field_id) for field_id in PROFILE_OWNED_FIELD_SOURCES}


def resolve_effective_profile_fields(
    submitted_form_data: Optional[Mapping[str, Any]], profile_values: Mapping[str, Any]
) -> EffectiveProfileFields:
    submitted_fields = (submitted_form_data or {}).get("fields") or {}
    resolved = {
        field_id: effective_value(sources, submitted_fields, profile_values)
        for field_id, sources in PROFILE_OWNED_FIELD_SOURCES.items()
    }
    return EffectiveProfileFields(
        **{field_id: None if is_blank(value) else str(value) for field_id, value in resolved.items()}
    )


def profile_values_of(profile: Optional[UserProfile]) -> Dict[str, Any]:
    return {attr: getattr(profile, attr) if profile else None for attr in PROFILE_ATTRS}


async def load_profile_values_by_user(db: AsyncSession, applications: Iterable[Any]) -> Dict[int, Dict[str, Any]]:
    """One query for the profile-owned values of every applicant; users without a profile are absent."""
    user_ids = {app.user_id for app in applications if app is not None and app.user_id is not None}
    if not user_ids:
        return {}
    columns = sorted(PROFILE_ATTRS)
    stmt = select(UserProfile.user_id, *(getattr(UserProfile, attr) for attr in columns)).where(
        UserProfile.user_id.in_(user_ids)
    )
    return {row[0]: dict(zip(columns, row[1:])) for row in (await db.execute(stmt)).all()}

import enum
import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, FrozenSet, Iterable, Mapping, Tuple

from app.core.exceptions import ValidationError
from app.core.regex_validator import RegexValidationError, safe_regex_match
from app.models.application_field import FieldType
from app.schemas.application_field import ApplicationFieldResponse
from app.services.application_field_service import FIXED_ADVISOR_KEYS, FIXED_KEY_POSTAL_ACCOUNT
from app.services.profile_owned_fields import (
    PROFILE_OWNED_FIELD_SOURCES,
    Source,
    Store,
    effective_value,
    is_blank,
)
from app.utils.bank_account_fields import normalize_account_number, validate_postal_account_format

FieldDefinition = ApplicationFieldResponse

ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class FieldChange:
    old: Any
    new: Any


def _label(definition: FieldDefinition) -> str:
    return definition.field_label or definition.field_name


def _invalid(definition: FieldDefinition, reason: str) -> ValidationError:
    return ValidationError(f"「{_label(definition)}」{reason}", field=definition.field_name)


def _full_match(definition: FieldDefinition, pattern: str, value: str) -> bool:
    try:
        match = safe_regex_match(pattern, value)
    except RegexValidationError as exc:
        raise _invalid(definition, "的驗證規則設定有誤，請聯絡系統管理員") from exc
    return bool(match) and match.end() == len(value)


def _parse_text(definition: FieldDefinition, raw: Any) -> str:
    if not isinstance(raw, str):
        raise _invalid(definition, "必須是文字")
    value = raw.strip()
    if definition.max_length and len(value) > definition.max_length:
        raise _invalid(definition, f"不可超過 {definition.max_length} 字")
    rules = definition.validation_rules or {}
    pattern = rules.get("pattern")
    if pattern and not _full_match(definition, pattern, value):
        raise _invalid(definition, f"格式不符：{rules.get('patternMessage') or pattern}")
    return value


def _parse_email(definition: FieldDefinition, raw: Any) -> str:
    value = _parse_text(definition, raw)
    if not EMAIL_PATTERN.match(value):
        raise _invalid(definition, "不是有效的電子郵件")
    return value


def _parse_number(definition: FieldDefinition, raw: Any) -> float | int:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise _invalid(definition, "必須是數字")
    if definition.min_value is not None and raw < definition.min_value:
        raise _invalid(definition, f"不可小於 {definition.min_value:g}")
    if definition.max_value is not None and raw > definition.max_value:
        raise _invalid(definition, f"不可大於 {definition.max_value:g}")
    return raw


def _parse_date(definition: FieldDefinition, raw: Any) -> str:
    value = raw.strip() if isinstance(raw, str) else None
    if value is None or not ISO_DATE_PATTERN.match(value):
        raise _invalid(definition, "必須是 YYYY-MM-DD 格式的日期")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise _invalid(definition, "不是有效的日期") from exc
    return value


def _parse_choice(definition: FieldDefinition, raw: Any) -> str:
    allowed = {str(option.get("value")) for option in definition.field_options or []}
    if not isinstance(raw, str) or raw not in allowed:
        raise _invalid(definition, "的值不在可選選項中")
    return raw


def _parse_checkbox(definition: FieldDefinition, raw: Any) -> bool:
    if not isinstance(raw, bool):
        raise _invalid(definition, "必須是勾選或未勾選")
    return raw


def _parse_postal_account(definition: FieldDefinition, raw: Any) -> str:
    value = _parse_text(definition, raw)
    is_valid, message = validate_postal_account_format(value)
    if not is_valid:
        raise _invalid(definition, f"格式不符：{message}")
    return normalize_account_number(value)


@dataclass(frozen=True)
class FieldCodec:
    parse: Callable[[FieldDefinition, Any], Any]
    cleared_value: Any


FIELD_CODECS: Dict[str, FieldCodec] = {
    FieldType.TEXT.value: FieldCodec(_parse_text, ""),
    FieldType.TEXTAREA.value: FieldCodec(_parse_text, ""),
    FieldType.EMAIL.value: FieldCodec(_parse_email, ""),
    FieldType.NUMBER.value: FieldCodec(_parse_number, None),
    FieldType.DATE.value: FieldCodec(_parse_date, ""),
    FieldType.SELECT.value: FieldCodec(_parse_choice, ""),
    FieldType.RADIO.value: FieldCodec(_parse_choice, ""),
    FieldType.CHECKBOX.value: FieldCodec(_parse_checkbox, False),
}


@dataclass(frozen=True)
class FieldRoute:
    """Where a staff edit of one form-config field lands.

    `store`/`key` name the write target: a `submitted_form_data.fields` key or
    a UserProfile attribute. `reads` lists the sources the shown value comes
    from (see profile_owned_fields); the edit diffs against that value.
    `stale_meta_keys` are application meta_data markers that describe
    the old value and stop being true once it changes.
    """

    store: Store
    key: str
    reads: Tuple[Source, ...]
    codec: FieldCodec | None = None
    stale_meta_keys: FrozenSet[str] = frozenset()


BANK_VERIFICATION_META_KEYS = frozenset({"bank_verification", "bank_verification_status"})

# The 郵局帳號 the student typed is folded into `account_number`, which roster
# generation and bank verification read first (BANK_ACCOUNT_FIELD_KEYS). A
# submitted `postal_account` may be another student's (#1443), so a correction
# never writes there, and the student's profile account stays theirs.
POSTAL_ACCOUNT_ROUTE = FieldRoute(
    store=Store.FORM,
    key="account_number",
    reads=PROFILE_OWNED_FIELD_SOURCES[FIXED_KEY_POSTAL_ACCOUNT],
    codec=FieldCodec(_parse_postal_account, ""),
    stale_meta_keys=BANK_VERIFICATION_META_KEYS,
)

ROUTED_FIELDS: Dict[str, FieldRoute] = {
    FIXED_KEY_POSTAL_ACCOUNT: POSTAL_ACCOUNT_ROUTE,
    **{
        attr: FieldRoute(store=Store.PROFILE, key=attr, reads=PROFILE_OWNED_FIELD_SOURCES[attr])
        for attr in FIXED_ADVISOR_KEYS
    },
}


def _route_for(definition: FieldDefinition) -> FieldRoute:
    routed = ROUTED_FIELDS.get(definition.fixed_key or "") or ROUTED_FIELDS.get(definition.field_name)
    if routed is not None:
        return routed
    return FieldRoute(store=Store.FORM, key=definition.field_name, reads=((Store.FORM, definition.field_name),))


@dataclass(frozen=True)
class EditableField:
    definition: FieldDefinition
    route: FieldRoute


@dataclass(frozen=True)
class EditableFormSpec:
    fields: Dict[str, EditableField]


@dataclass(frozen=True)
class StaffFormEdit:
    form_data: Dict[str, Any]
    changes: Dict[str, FieldChange]
    profile_updates: Dict[str, Any]
    stale_meta_keys: FrozenSet[str]
    # The 郵局帳號 digits this edit set; None when it left the account alone or cleared it.
    postal_account: str | None = None


def build_editable_form_spec(definitions: Iterable[FieldDefinition]) -> EditableFormSpec:
    return EditableFormSpec(
        fields={d.field_name: EditableField(d, _route_for(d)) for d in definitions if d.is_active},
    )


def parse_field_value(definition: FieldDefinition, raw: Any, codec: FieldCodec | None = None) -> Any:
    codec = codec or FIELD_CODECS.get(definition.field_type)
    if codec is None:
        raise _invalid(definition, f"的欄位類型 {definition.field_type} 不支援修改")
    if definition.field_type != FieldType.CHECKBOX.value and is_blank(raw):
        if definition.is_required:
            raise _invalid(definition, "為必填欄位，不可清空")
        return codec.cleared_value
    return codec.parse(definition, raw)


def apply_staff_form_edit(
    form_data: Mapping[str, Any] | None,
    spec: EditableFormSpec,
    raw_fields: Mapping[str, Any],
    profile_values: Mapping[str, Any],
) -> StaffFormEdit:
    current: Dict[str, Any] = dict(form_data or {})
    stored_fields: Mapping[str, Any] = current.get("fields") or {}
    written: Dict[str, Any] = {}
    profile_updates: Dict[str, Any] = {}
    changes: Dict[str, FieldChange] = {}
    stale_meta_keys: FrozenSet[str] = frozenset()
    postal_account: str | None = None

    for name, raw in raw_fields.items():
        editable = spec.fields.get(name)
        if editable is None:
            raise ValidationError(f"欄位「{name}」不存在或已停用，無法修改", field=name)
        definition, route = editable.definition, editable.route

        value = parse_field_value(definition, raw, route.codec)
        old = effective_value(route.reads, stored_fields, profile_values)
        if old == value or (is_blank(old) and is_blank(value)):
            continue

        if route.store is Store.PROFILE:
            value = None if is_blank(value) else value
            profile_updates[route.key] = value
        else:
            entry = stored_fields.get(route.key)
            kept = dict(entry) if isinstance(entry, Mapping) else {}
            written[route.key] = {
                **kept,
                "field_id": route.key,
                "field_type": definition.field_type,
                "value": value,
                "required": bool(definition.is_required),
            }
        changes[name] = FieldChange(old=old, new=value)
        stale_meta_keys |= route.stale_meta_keys
        if route is POSTAL_ACCOUNT_ROUTE and not is_blank(value):
            postal_account = value

    form = {**current, "fields": {**stored_fields, **written}} if written else current
    return StaffFormEdit(
        form_data=form,
        changes=changes,
        profile_updates=profile_updates,
        stale_meta_keys=stale_meta_keys,
        postal_account=postal_account,
    )


class ReassignmentOutcome(enum.Enum):
    REASSIGNED = "reassigned"
    ALREADY_ASSIGNED = "already_assigned"
    KEPT_REVIEWED = "kept_reviewed"
    UNASSIGNED_NO_ACCOUNT = "unassigned_no_account"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ProfessorFacts:
    """What decides whether an advisor 人事編號 edit moves the reviewing professor."""

    has_professor_stage: bool
    is_professor_actionable: bool
    current_professor_id: int | None
    current_professor_reviewed: bool
    matched_professor_id: int | None


@dataclass(frozen=True)
class ProfessorReassignment:
    outcome: ReassignmentOutcome
    from_professor_id: int | None
    to_professor_id: int | None

    @property
    def changes_assignment(self) -> bool:
        return self.from_professor_id != self.to_professor_id


def advisor_nycu_id_changed(old: Any, new: Any) -> bool:
    def normalized(value: Any) -> str:
        return str(value or "").strip().upper()

    return normalized(old) != normalized(new)


def decide_professor_reassignment(facts: ProfessorFacts) -> ProfessorReassignment:
    current = facts.current_professor_id

    def outcome(kind: ReassignmentOutcome, to: int | None = current) -> ProfessorReassignment:
        return ProfessorReassignment(outcome=kind, from_professor_id=current, to_professor_id=to)

    if not (facts.has_professor_stage and facts.is_professor_actionable):
        return outcome(ReassignmentOutcome.NOT_APPLICABLE)
    if current is not None and facts.current_professor_reviewed:
        return outcome(ReassignmentOutcome.KEPT_REVIEWED)
    if facts.matched_professor_id is None:
        # Nobody holds that 人事編號 yet: backfill_professor_assignments hands the
        # row to the advisor on their first login.
        return outcome(ReassignmentOutcome.UNASSIGNED_NO_ACCOUNT, to=None)
    if facts.matched_professor_id == current:
        return outcome(ReassignmentOutcome.ALREADY_ASSIGNED)
    return outcome(ReassignmentOutcome.REASSIGNED, to=facts.matched_professor_id)


class RosterAccountAction(enum.Enum):
    SYNCED = "synced"
    # Synced on a 人為移除 row, which the exported Excel does not list: no re-export is due.
    SYNCED_REMOVED = "synced_removed"
    KEPT_LOCKED = "kept_locked"


ROSTER_ACCOUNT_CLAUSES: Dict[RosterAccountAction, str] = {
    RosterAccountAction.SYNCED: "；已同步更新 {count} 份造冊的郵局帳號，請至造冊管理重新匯出 Excel",
    RosterAccountAction.KEPT_LOCKED: "；{count} 份已鎖定的造冊（{rosters}）未變更，如需更正請解鎖後重新產生",
}
ROSTER_ACCOUNT_AUDIT_KEYS: Dict[RosterAccountAction, str] = {
    RosterAccountAction.SYNCED: "roster_items_updated",
    RosterAccountAction.SYNCED_REMOVED: "removed_roster_items_updated",
    RosterAccountAction.KEPT_LOCKED: "locked_rosters_unchanged",
}
LISTED_ROSTER_CODES = 3


@dataclass(frozen=True)
class RosterItemRef:
    roster_id: int
    roster_code: str
    item_id: int


@dataclass(frozen=True)
class RosterAccountSync:
    """What an application account edit did to the 造冊 items that snapshot that account."""

    items: Dict[RosterAccountAction, Tuple[RosterItemRef, ...]] = field(default_factory=dict)

    @property
    def message_clause(self) -> str:
        return "".join(
            clause.format(count=len(_roster_codes(refs)), rosters=_listed_codes(refs))
            for action, clause in ROSTER_ACCOUNT_CLAUSES.items()
            if (refs := self.items.get(action))
        )

    def audit_meta(self) -> Dict[str, Any]:
        return {
            ROSTER_ACCOUNT_AUDIT_KEYS[action]: [vars(ref) for ref in refs]
            for action, refs in self.items.items()
            if refs
        }


def _roster_codes(refs: Iterable[RosterItemRef]) -> Tuple[str, ...]:
    return tuple(dict.fromkeys(ref.roster_code for ref in refs))


def _listed_codes(refs: Iterable[RosterItemRef]) -> str:
    codes = _roster_codes(refs)
    listed = "、".join(codes[:LISTED_ROSTER_CODES])
    return listed + "…" if len(codes) > LISTED_ROSTER_CODES else listed


FORM_EDIT_SAVED_MESSAGE = "表單內容已更新"
REASSIGNMENT_MESSAGES: Dict[ReassignmentOutcome, str] = {
    ReassignmentOutcome.REASSIGNED: FORM_EDIT_SAVED_MESSAGE + "，審核教授已改派為 {professor_name}",
    ReassignmentOutcome.ALREADY_ASSIGNED: FORM_EDIT_SAVED_MESSAGE,
    ReassignmentOutcome.KEPT_REVIEWED: FORM_EDIT_SAVED_MESSAGE + "；原審核教授已完成審核，未改派",
    ReassignmentOutcome.UNASSIGNED_NO_ACCOUNT: FORM_EDIT_SAVED_MESSAGE
    + "；查無此人事編號的教授帳號，該教授登入後會自動指派",
    ReassignmentOutcome.NOT_APPLICABLE: FORM_EDIT_SAVED_MESSAGE,
}


@dataclass(frozen=True)
class AppliedStaffFormEdit:
    changes: Dict[str, FieldChange]
    profile_fields_updated: Tuple[str, ...] = ()
    cleared_meta: Dict[str, Any] = field(default_factory=dict)
    professor_reassignment: ProfessorReassignment | None = None
    new_professor_name: str | None = None
    roster_sync: RosterAccountSync = field(default_factory=RosterAccountSync)

    @property
    def message(self) -> str:
        if not self.changes:
            return "表單內容沒有變更"
        if self.professor_reassignment is None:
            saved = FORM_EDIT_SAVED_MESSAGE
        else:
            template = REASSIGNMENT_MESSAGES[self.professor_reassignment.outcome]
            saved = template.format(professor_name=self.new_professor_name or "")
        return saved + self.roster_sync.message_clause

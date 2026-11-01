"""Staff (admin / 學院) corrections to a submitted application form.

Pure: no DB access. Takes the stored ``submitted_form_data``, the scholarship's
form-config field definitions and the raw values from the request, and returns a
new form-data dict plus the per-field changes. The input is never mutated.
"""

import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Dict, FrozenSet, Iterable, Mapping

from app.core.exceptions import ValidationError
from app.core.regex_validator import RegexValidationError, safe_regex_match
from app.models.application_field import FieldType
from app.schemas.application_field import ApplicationFieldResponse

FieldDefinition = ApplicationFieldResponse

ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class FieldChange:
    old: Any
    new: Any


@dataclass(frozen=True)
class EditableFormSpec:
    """Which fields staff may edit (by field_name) and which are profile-owned."""

    definitions: Dict[str, FieldDefinition]
    locked: FrozenSet[str]


@dataclass(frozen=True)
class StaffFormEdit:
    form_data: Dict[str, Any]
    changes: Dict[str, FieldChange]


def _label(definition: FieldDefinition) -> str:
    return definition.field_label or definition.field_name


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _invalid(definition: FieldDefinition, reason: str) -> ValidationError:
    return ValidationError(f"「{_label(definition)}」{reason}", field=definition.field_name)


def _full_match(definition: FieldDefinition, pattern: str, value: str) -> bool:
    # Same semantics as the HTML pattern attribute the student form uses: the
    # whole value must match, not just a prefix.
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
    allowed = {str(option.get("value")) for option in definition.field_options or [] if isinstance(option, dict)}
    if not isinstance(raw, str) or raw not in allowed:
        raise _invalid(definition, "的值不在可選選項中")
    return raw


def _parse_checkbox(definition: FieldDefinition, raw: Any) -> bool:
    if not isinstance(raw, bool):
        raise _invalid(definition, "必須是勾選或未勾選")
    return raw


@dataclass(frozen=True)
class FieldCodec:
    """How one field_type turns a raw request value into its stored value."""

    parse: Callable[[FieldDefinition, Any], Any]
    blank: Any  # stored when a non-required field is cleared


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


def build_editable_form_spec(definitions: Iterable[FieldDefinition], profile_owned: FrozenSet[str]) -> EditableFormSpec:
    """Active form-config fields minus the UserProfile-owned built-ins."""
    definitions = list(definitions)
    locked = frozenset(profile_owned) | {
        d.field_name for d in definitions if d.field_name in profile_owned or d.fixed_key in profile_owned
    }
    editable = {d.field_name: d for d in definitions if d.is_active and d.field_name not in locked}
    return EditableFormSpec(definitions=editable, locked=locked)


def parse_field_value(definition: FieldDefinition, raw: Any) -> Any:
    codec = FIELD_CODECS.get(definition.field_type)
    if codec is None:
        raise _invalid(definition, f"的欄位類型 {definition.field_type} 不支援修改")
    if definition.field_type != FieldType.CHECKBOX.value and _is_blank(raw):
        if definition.is_required:
            raise _invalid(definition, "為必填欄位，不可清空")
        return codec.blank
    return codec.parse(definition, raw)


def apply_staff_form_edit(
    form_data: Mapping[str, Any] | None, spec: EditableFormSpec, raw_fields: Mapping[str, Any]
) -> StaffFormEdit:
    """Merge `raw_fields` into a copy of `form_data`.

    Untouched fields and ``documents`` are carried over as-is. A value equal to
    the stored one is not a change; when nothing changes the input comes back.
    """
    current: Dict[str, Any] = dict(form_data or {})
    stored_fields: Mapping[str, Any] = current.get("fields") or {}
    written: Dict[str, Any] = {}
    changes: Dict[str, FieldChange] = {}

    for name, raw in raw_fields.items():
        if name in spec.locked:
            raise ValidationError(f"「{name}」屬於學生個人資料（郵局帳號／指導教授），不可在此修改", field=name)
        definition = spec.definitions.get(name)
        if definition is None:
            raise ValidationError(f"欄位「{name}」不存在或已停用，無法修改", field=name)

        value = parse_field_value(definition, raw)
        entry = stored_fields.get(name)
        old = entry.get("value") if isinstance(entry, Mapping) else entry
        if old == value or (_is_blank(old) and _is_blank(value)):
            continue

        kept = dict(entry) if isinstance(entry, Mapping) else {}
        written[name] = {
            **kept,
            "field_id": name,
            "field_type": definition.field_type,
            "value": value,
            "required": bool(definition.is_required),
        }
        changes[name] = FieldChange(old=old, new=value)

    if not changes:
        return StaffFormEdit(form_data=current, changes={})
    return StaffFormEdit(form_data={**current, "fields": {**stored_fields, **written}}, changes=changes)

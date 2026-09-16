"""Per-configuration (per academic year) sub-type display names.

``scholarship_sub_type_configs.name`` is the year-agnostic base label of a
sub-type (e.g. 教育部博士生獎學金 (指導教授配合款每月 $5000 元)). Admins can
override what a given year shows through ``ScholarshipConfiguration.sub_type_labels``::

    {"moe_1w": {"name": "115學年度教育部博士生獎學金 (...)", "name_en": "AY115 MOE ..."},
     "nstc":   {"name": "115學年度國科會博士生獎學金"}}

Every screen that renders a sub-type name for a specific period (student
wizard, professor/college review, application detail, distribution grid,
exports) must resolve it through this module so the override is applied
consistently. Period-less surfaces (rule editor, global translation maps)
keep the base name.
"""

from typing import Any, Dict, Iterable, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scholarship import ScholarshipConfiguration, ScholarshipSubTypeConfig

MAX_LABEL_LENGTH = 200
YEARLY_SEMESTER_ALIASES = {None, "", "yearly", "annual"}

# {sub_type_code: {"zh": ..., "en": ...}}
SubTypeLabelMap = Dict[str, Dict[str, str]]
# {sub_type_code: {"name": ..., "name_en": ...}} — the stored override shape
SubTypeLabelOverrides = Dict[str, Dict[str, str]]


def normalize_sub_type_labels(raw: Any) -> Optional[SubTypeLabelOverrides]:
    """Validate an admin-supplied ``sub_type_labels`` payload.

    Returns a new dict with lowercase/stripped codes and stripped names, or
    ``None`` when nothing is configured. Entries whose ``name`` is blank are
    dropped (the UI sends empty inputs to mean "use the base label").

    Raises ``ValueError`` with a user-facing message on a malformed payload.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("子類型顯示名稱格式錯誤：必須是物件")

    normalized: SubTypeLabelOverrides = {}
    for code, entry in raw.items():
        if not isinstance(code, str) or not code.strip():
            raise ValueError("子類型顯示名稱格式錯誤：子類型代碼不可為空")
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise ValueError(f"子類型顯示名稱格式錯誤：{code} 必須是物件")

        name = _clean_label(entry.get("name"), f"{code} 的名稱")
        name_en = _clean_label(entry.get("name_en"), f"{code} 的英文名稱")
        if not name:
            if name_en:
                raise ValueError(f"子類型顯示名稱格式錯誤：{code} 需先填寫中文名稱")
            continue

        cleaned = {"name": name}
        if name_en:
            cleaned["name_en"] = name_en
        normalized[code.lower().strip()] = cleaned

    return normalized or None


def _clean_label(value: Any, what: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"子類型顯示名稱格式錯誤：{what} 必須是文字")
    stripped = value.strip()
    if len(stripped) > MAX_LABEL_LENGTH:
        raise ValueError(f"子類型顯示名稱過長：{what} 不可超過 {MAX_LABEL_LENGTH} 字")
    return stripped


def base_sub_type_labels(
    sub_type_configs: Iterable[ScholarshipSubTypeConfig], *, include_inactive: bool = False
) -> SubTypeLabelMap:
    """Base (year-agnostic) labels from ``ScholarshipSubTypeConfig`` rows."""
    labels: SubTypeLabelMap = {}
    for config in sub_type_configs:
        if not include_inactive and not config.is_active:
            continue
        labels[config.sub_type_code] = {"zh": config.name, "en": config.name_en or config.name}
    return labels


def merge_sub_type_labels(base: SubTypeLabelMap, overrides: Optional[SubTypeLabelOverrides]) -> SubTypeLabelMap:
    """Return a new label map with per-configuration overrides applied.

    An override with only a Chinese ``name`` also replaces the English label
    (falling back to the base English wording would mix two different years'
    labels on one screen).
    """
    merged: SubTypeLabelMap = {code: dict(entry) for code, entry in base.items()}
    for code, entry in (overrides or {}).items():
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        name_en = (entry.get("name_en") or "").strip() or name
        merged[code] = {"zh": name, "en": name_en}
    return merged


def resolve_sub_type_labels(
    sub_type_configs: Iterable[ScholarshipSubTypeConfig],
    configuration: Optional[ScholarshipConfiguration],
    *,
    include_inactive: bool = False,
) -> SubTypeLabelMap:
    """Labels for one configuration's period: base names + that config's overrides."""
    overrides = configuration.sub_type_labels if configuration is not None else None
    return merge_sub_type_labels(base_sub_type_labels(sub_type_configs, include_inactive=include_inactive), overrides)


def configuration_semester_condition(semester: Optional[str]):
    """SQL condition matching ``ScholarshipConfiguration.semester`` for a period.

    Year-based scholarships are stored as NULL (or the legacy ``"yearly"``);
    callers pass ``None``/``"yearly"``/``"annual"`` interchangeably for them.
    """
    if semester in YEARLY_SEMESTER_ALIASES:
        return or_(
            ScholarshipConfiguration.semester.is_(None),
            ScholarshipConfiguration.semester == "yearly",
        )
    return ScholarshipConfiguration.semester == semester


async def load_configuration_for_period(
    db: AsyncSession,
    scholarship_type_id: int,
    academic_year: int,
    semester: Optional[str],
) -> Optional[ScholarshipConfiguration]:
    """The configuration governing (scholarship type, academic year, semester).

    When several exist the newest (highest id) wins, matching
    ``ManualDistributionService._load_config``.
    """
    stmt = (
        select(ScholarshipConfiguration)
        .where(
            ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
            ScholarshipConfiguration.academic_year == academic_year,
            configuration_semester_condition(semester),
        )
        .order_by(ScholarshipConfiguration.id.desc())
    )
    return (await db.execute(stmt)).scalars().first()


async def load_sub_type_labels(
    db: AsyncSession,
    scholarship_type_id: int,
    academic_year: int,
    semester: Optional[str],
    *,
    include_inactive: bool = False,
) -> SubTypeLabelMap:
    """Resolved labels for a period, loading both the sub-type rows and the configuration."""
    stmt = (
        select(ScholarshipSubTypeConfig)
        .where(ScholarshipSubTypeConfig.scholarship_type_id == scholarship_type_id)
        .order_by(ScholarshipSubTypeConfig.display_order)
    )
    sub_type_configs = (await db.execute(stmt)).scalars().all()
    configuration = await load_configuration_for_period(db, scholarship_type_id, academic_year, semester)
    return resolve_sub_type_labels(sub_type_configs, configuration, include_inactive=include_inactive)


def zh_labels(labels: SubTypeLabelMap) -> Dict[str, str]:
    """Flatten a label map to ``{code: zh_name}`` for Chinese-only consumers."""
    return {code: entry["zh"] for code, entry in labels.items()}

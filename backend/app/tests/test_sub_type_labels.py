"""Per-configuration (per academic year) sub-type display names.

Covers ``app/services/sub_type_labels.py`` — payload validation, the merge of
``ScholarshipConfiguration.sub_type_labels`` over the base
``scholarship_sub_type_configs.name`` — and the two reviewer/student-facing
consumers in ``ApplicationService``.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.enums import Semester
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipSubTypeConfig,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService
from app.services.sub_type_labels import (
    load_sub_type_labels,
    merge_sub_type_labels,
    normalize_sub_type_labels,
    resolve_sub_type_labels,
)

BASE = {
    "nstc": {"zh": "國科會博士生獎學金", "en": "NSTC PHD Scholarship"},
    "moe_1w": {"zh": "教育部博士生獎學金", "en": "MOE PHD Scholarship"},
}


class TestNormalizeSubTypeLabels:
    def test_none_and_empty_become_none(self):
        assert normalize_sub_type_labels(None) is None
        assert normalize_sub_type_labels({}) is None

    def test_codes_and_names_are_normalized(self):
        result = normalize_sub_type_labels({" MOE_1w ": {"name": " 115學年度教育部 ", "name_en": " AY115 MOE "}})
        assert result == {"moe_1w": {"name": "115學年度教育部", "name_en": "AY115 MOE"}}

    def test_blank_name_drops_the_entry(self):
        """The UI sends empty inputs for 'use the base label'."""
        result = normalize_sub_type_labels({"nstc": {"name": "  "}, "moe_1w": {"name": "X"}})
        assert result == {"moe_1w": {"name": "X"}}

    def test_only_all_blank_entries_becomes_none(self):
        assert normalize_sub_type_labels({"nstc": {"name": ""}, "moe_1w": None}) is None

    def test_english_without_chinese_is_rejected(self):
        with pytest.raises(ValueError, match="需先填寫中文名稱"):
            normalize_sub_type_labels({"nstc": {"name": "", "name_en": "NSTC"}})

    @pytest.mark.parametrize("raw", [[], "nstc", 1])
    def test_non_object_payload_is_rejected(self, raw):
        with pytest.raises(ValueError, match="必須是物件"):
            normalize_sub_type_labels(raw)

    def test_non_object_entry_is_rejected(self):
        with pytest.raises(ValueError, match="nstc 必須是物件"):
            normalize_sub_type_labels({"nstc": "國科會"})

    def test_non_string_name_is_rejected(self):
        with pytest.raises(ValueError, match="必須是文字"):
            normalize_sub_type_labels({"nstc": {"name": 123}})

    def test_over_long_name_is_rejected(self):
        with pytest.raises(ValueError, match="不可超過 200 字"):
            normalize_sub_type_labels({"nstc": {"name": "x" * 201}})

    def test_input_is_not_mutated(self):
        raw = {"NSTC": {"name": " 國科會 "}}
        normalize_sub_type_labels(raw)
        assert raw == {"NSTC": {"name": " 國科會 "}}


class TestMergeSubTypeLabels:
    def test_no_overrides_returns_equal_copy(self):
        merged = merge_sub_type_labels(BASE, None)
        assert merged == BASE
        assert merged is not BASE
        assert merged["nstc"] is not BASE["nstc"]

    def test_override_replaces_both_languages(self):
        merged = merge_sub_type_labels(BASE, {"moe_1w": {"name": "115學年度教育部", "name_en": "AY115 MOE"}})
        assert merged["moe_1w"] == {"zh": "115學年度教育部", "en": "AY115 MOE"}
        assert merged["nstc"] == BASE["nstc"]

    def test_chinese_only_override_also_drives_english(self):
        """Falling back to the base English wording would mix two years' labels."""
        merged = merge_sub_type_labels(BASE, {"moe_1w": {"name": "115學年度教育部"}})
        assert merged["moe_1w"] == {"zh": "115學年度教育部", "en": "115學年度教育部"}

    def test_blank_or_malformed_override_is_ignored(self):
        merged = merge_sub_type_labels(BASE, {"moe_1w": {"name": "  "}, "nstc": "oops"})
        assert merged == BASE

    def test_override_for_unknown_code_is_added(self):
        merged = merge_sub_type_labels(BASE, {"moe_2w": {"name": "教育部兩萬"}})
        assert merged["moe_2w"] == {"zh": "教育部兩萬", "en": "教育部兩萬"}


def _sub_type_config(scholarship_type_id: int, code: str, *, active: bool = True) -> ScholarshipSubTypeConfig:
    return ScholarshipSubTypeConfig(
        scholarship_type_id=scholarship_type_id,
        sub_type_code=code,
        name=BASE[code]["zh"],
        name_en=BASE[code]["en"],
        display_order=list(BASE).index(code),
        is_active=active,
    )


class TestResolveSubTypeLabels:
    def test_inactive_rows_hidden_unless_requested(self):
        configs = [_sub_type_config(1, "nstc"), _sub_type_config(1, "moe_1w", active=False)]
        assert set(resolve_sub_type_labels(configs, None)) == {"nstc"}
        assert set(resolve_sub_type_labels(configs, None, include_inactive=True)) == {"nstc", "moe_1w"}

    def test_configuration_override_applied(self):
        configs = [_sub_type_config(1, "nstc"), _sub_type_config(1, "moe_1w")]
        configuration = ScholarshipConfiguration(sub_type_labels={"moe_1w": {"name": "115學年度教育部"}})
        labels = resolve_sub_type_labels(configs, configuration)
        assert labels["moe_1w"]["zh"] == "115學年度教育部"
        assert labels["nstc"] == BASE["nstc"]


async def _phd(db: AsyncSession) -> ScholarshipType:
    scholarship = ScholarshipType(
        code="phd_labels_test",
        name="博士生獎學金",
        sub_type_selection_mode=SubTypeSelectionMode.multiple,
        status="active",
    )
    db.add(scholarship)
    await db.flush()
    db.add(_sub_type_config(scholarship.id, "nstc"))
    db.add(_sub_type_config(scholarship.id, "moe_1w"))
    await db.flush()
    await db.refresh(scholarship, attribute_names=["sub_type_configs"])
    return scholarship


async def _configuration(
    db: AsyncSession, scholarship: ScholarshipType, *, academic_year: int, code: str, labels=None
) -> ScholarshipConfiguration:
    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=academic_year,
        semester=None,
        config_name=f"博士生獎學金 {academic_year}學年",
        config_code=code,
        amount=40000,
        is_active=True,
        sub_type_labels=labels,
    )
    db.add(config)
    await db.flush()
    return config


@pytest.mark.asyncio
class TestLoadSubTypeLabels:
    async def test_each_year_resolves_its_own_wording(self, db: AsyncSession):
        scholarship = await _phd(db)
        await _configuration(db, scholarship, academic_year=114, code="phd_114_lbl")
        await _configuration(
            db,
            scholarship,
            academic_year=115,
            code="phd_115_lbl",
            labels={"moe_1w": {"name": "115學年度教育部", "name_en": "AY115 MOE"}},
        )

        year_114 = await load_sub_type_labels(db, scholarship.id, 114, "yearly")
        year_115 = await load_sub_type_labels(db, scholarship.id, 115, None)

        assert year_114["moe_1w"] == BASE["moe_1w"]
        assert year_115["moe_1w"] == {"zh": "115學年度教育部", "en": "AY115 MOE"}
        assert year_115["nstc"] == BASE["nstc"]

    async def test_missing_configuration_falls_back_to_base(self, db: AsyncSession):
        scholarship = await _phd(db)
        assert await load_sub_type_labels(db, scholarship.id, 120, None) == BASE

    async def test_semester_configuration_not_matched_for_yearly_lookup(self, db: AsyncSession):
        scholarship = await _phd(db)
        semester_config = await _configuration(db, scholarship, academic_year=115, code="phd_115_1")
        semester_config.semester = Semester.first
        semester_config.sub_type_labels = {"nstc": {"name": "上學期國科會"}}
        await db.flush()

        assert (await load_sub_type_labels(db, scholarship.id, 115, None))["nstc"] == BASE["nstc"]
        assert (await load_sub_type_labels(db, scholarship.id, 115, "first"))["nstc"]["zh"] == "上學期國科會"


async def _professor(db: AsyncSession) -> User:
    prof = User(
        nycu_id="prof_labels",
        name="教授",
        email="prof_labels@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.professor,
    )
    db.add(prof)
    await db.flush()
    return prof


async def _application(
    db: AsyncSession,
    scholarship: ScholarshipType,
    *,
    academic_year: int,
    configuration_id=None,
) -> Application:
    student = User(
        nycu_id=f"stu_labels_{academic_year}",
        name="王小明",
        email=f"stu_labels_{academic_year}@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    await db.flush()
    application = Application(
        app_id=f"APP-{academic_year}-0-09998",
        user_id=student.id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=configuration_id,
        academic_year=academic_year,
        semester=None,
        status=ApplicationStatus.submitted,
        sub_type_selection_mode=SubTypeSelectionMode.multiple,
        scholarship_subtype_list=["nstc", "moe_1w"],
        student_data={"std_academyno": "C"},
    )
    db.add(application)
    await db.flush()
    return application


@pytest.mark.asyncio
class TestApplicationServiceUsesYearLabels:
    async def test_available_sub_types_use_applied_configuration_wording(self, db: AsyncSession):
        """The professor review heading shows the applied-for year's label."""
        scholarship = await _phd(db)
        config = await _configuration(
            db,
            scholarship,
            academic_year=115,
            code="phd_115_avail",
            labels={"moe_1w": {"name": "115學年度教育部", "name_en": "AY115 MOE"}},
        )
        prof = await _professor(db)
        application = await _application(db, scholarship, academic_year=115, configuration_id=config.id)

        result = await ApplicationService(db).get_application_available_sub_types(application.id, prof)

        by_code = {row["value"]: row for row in result}
        assert by_code["moe_1w"]["label"] == "115學年度教育部"
        assert by_code["moe_1w"]["label_en"] == "AY115 MOE"
        assert by_code["nstc"]["label"] == BASE["nstc"]["zh"]

    async def test_available_sub_types_fall_back_to_period_when_config_id_missing(self, db: AsyncSession):
        scholarship = await _phd(db)
        await _configuration(
            db, scholarship, academic_year=115, code="phd_115_period", labels={"nstc": {"name": "115國科會"}}
        )
        prof = await _professor(db)
        application = await _application(db, scholarship, academic_year=115, configuration_id=None)

        result = await ApplicationService(db).get_application_available_sub_types(application.id, prof)

        assert {row["value"]: row["label"] for row in result} == {"nstc": "115國科會", "moe_1w": BASE["moe_1w"]["zh"]}

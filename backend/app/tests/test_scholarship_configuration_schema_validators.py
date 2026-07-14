"""
Pydantic validator tests for `app/schemas/scholarship_configuration.py`.

These validators run when admins POST a new configuration — they reject
malformed payloads BEFORE the configuration_service touches the DB. They
mirror (but don't duplicate) the model-level `validate_quota_config`
guarantees, but enforce them at request-input boundary.

Bugs cause:
- `validate_total_quota` bypass: admin enables quota limit without
  setting a total → downstream allocator divides by None → 500
- `validate_quotas` overflow bypass: matrix sum > total saved as-is →
  CRITICAL budget overrun on payment day
- `validate_renewal_*_review` bypass: review dates set without the
  feature flag → workflows fire at unexpected times
- `validate_effective_dates`: end ≤ start → config never effective,
  silent UX bug
- `validate_configurations` (bulk): duplicate config_codes →
  UniqueViolation during transaction rollback, partial write loss
- `validate_import_data`: missing required fields → KeyError mid-import,
  half the rows succeed and half don't
- `WhitelistBatch*Request`: empty list → no-op masquerades as success
  on the admin UI

12 validators across 6 schemas (22 cases). No DB, pure Pydantic.
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.models.enums import Semester
from app.schemas.scholarship_configuration import (
    ScholarshipConfigurationBase,
    ScholarshipConfigurationBulkCreate,
    ScholarshipConfigurationCreate,
    ScholarshipConfigurationImport,
    WhitelistBatchAddRequest,
    WhitelistBatchRemoveRequest,
)


def _base_payload(**overrides) -> dict:
    """A valid minimal payload for ScholarshipConfigurationBase."""
    payload = {
        "academic_year": 113,
        "semester": Semester.first,
        "config_name": "Test Config",
        "config_code": "TEST-113-1",
        "amount": 10000,
    }
    payload.update(overrides)
    return payload


# ─── ScholarshipConfigurationBase: validate_total_quota ──────────────


def test_total_quota_required_when_quota_limit_enabled():
    """SECURITY-ADJACENT: enabling has_quota_limit without a total_quota
    would leave the allocator without a cap → unlimited approvals."""
    with pytest.raises(ValidationError) as exc:
        ScholarshipConfigurationBase(**_base_payload(has_quota_limit=True, total_quota=None))
    assert "總配額" in str(exc.value)


def test_total_quota_optional_when_quota_limit_disabled():
    """has_quota_limit=False → total_quota=None is fine."""
    cfg = ScholarshipConfigurationBase(**_base_payload(has_quota_limit=False, total_quota=None))
    assert cfg.total_quota is None


def test_total_quota_field_constraint_ge_zero():
    """Field constraint: total_quota ≥ 0. Negative quotas would break
    allocator math."""
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_base_payload(has_quota_limit=False, total_quota=-1))


# ─── ScholarshipConfigurationBase: validate_quotas ───────────────────


def test_quotas_required_when_college_quota_enabled():
    with pytest.raises(ValidationError) as exc:
        ScholarshipConfigurationBase(**_base_payload(has_college_quota=True, quotas=None))
    assert "配額配置不能為空" in str(exc.value)


def test_quotas_matrix_sum_must_not_exceed_total():
    """CRITICAL: matrix sum > total_quota → reject at input boundary.
    Otherwise admin saves an over-allocated config that causes budget
    overrun on payment day."""
    with pytest.raises(ValidationError) as exc:
        ScholarshipConfigurationBase(
            **_base_payload(
                has_quota_limit=True,
                total_quota=10,
                has_college_quota=True,
                quotas={"nstc": {"EE": 8, "EN": 5}},  # sum=13 > 10
            )
        )
    assert "超過總配額" in str(exc.value)


def test_quotas_matrix_sum_within_total_accepted():
    cfg = ScholarshipConfigurationBase(
        **_base_payload(
            has_quota_limit=True,
            total_quota=20,
            has_college_quota=True,
            quotas={"nstc": {"EE": 8, "EN": 5}, "moe_1w": {"EE": 3}},  # sum=16 ≤ 20
        )
    )
    assert cfg.quotas == {"nstc": {"EE": 8, "EN": 5}, "moe_1w": {"EE": 3}}


# ─── validate_renewal_professor_review ───────────────────────────────


def test_renewal_professor_review_dates_rejected_without_feature_flag():
    """Setting renewal review end-date without renewal_requires_professor_review
    → reject. Otherwise the dates are saved but ignored by runtime — silent UX bug."""
    end = datetime.now(timezone.utc) + timedelta(days=10)
    with pytest.raises(ValidationError) as exc:
        ScholarshipConfigurationBase(
            **_base_payload(
                renewal_requires_professor_review=False,
                renewal_professor_review_end=end,
            )
        )
    assert "續領教授審查時間" in str(exc.value)


def test_renewal_professor_review_dates_accepted_with_feature_flag():
    start = datetime.now(timezone.utc)
    end = datetime.now(timezone.utc) + timedelta(days=10)
    cfg = ScholarshipConfigurationBase(
        **_base_payload(
            renewal_requires_professor_review=True,
            renewal_professor_review_start=start,
            renewal_professor_review_end=end,
        )
    )
    assert cfg.renewal_professor_review_end == end


def test_renewal_professor_review_flag_independent_of_general_flag():
    """Pin the split: the general requires_professor_recommendation flag no
    longer gates renewal review dates — only the renewal flag does."""
    end = datetime.now(timezone.utc) + timedelta(days=10)
    with pytest.raises(ValidationError) as exc:
        ScholarshipConfigurationBase(
            **_base_payload(
                requires_professor_recommendation=True,  # general flag alone is not enough
                renewal_requires_professor_review=False,
                renewal_professor_review_end=end,
            )
        )
    assert "續領教授審查時間" in str(exc.value)


# ─── validate_renewal_college_review ─────────────────────────────────


def test_renewal_college_review_dates_rejected_without_feature_flag():
    """Same pattern for college review — pin the parallel gate so a
    refactor that consolidates them doesn't silently drop one."""
    end = datetime.now(timezone.utc) + timedelta(days=10)
    with pytest.raises(ValidationError) as exc:
        ScholarshipConfigurationBase(
            **_base_payload(
                renewal_requires_college_review=False,
                renewal_college_review_end=end,
            )
        )
    assert "續領學院審查時間" in str(exc.value)


def test_renewal_college_review_dates_accepted_with_feature_flag():
    start = datetime.now(timezone.utc)
    end = datetime.now(timezone.utc) + timedelta(days=10)
    cfg = ScholarshipConfigurationBase(
        **_base_payload(
            renewal_requires_college_review=True,
            renewal_college_review_start=start,
            renewal_college_review_end=end,
        )
    )
    assert cfg.renewal_college_review_end == end


# ─── validate_effective_dates ────────────────────────────────────────


def test_effective_end_must_be_after_start():
    """end ≤ start → reject. An end-before-start config would never be
    is_effective → silent UX bug."""
    start = datetime(2024, 6, 1, tzinfo=timezone.utc)
    end = datetime(2024, 5, 1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError) as exc:
        ScholarshipConfigurationBase(
            **_base_payload(
                effective_start_date=start,
                effective_end_date=end,
            )
        )
    assert "結束日期必須晚於開始日期" in str(exc.value)


def test_effective_dates_equal_also_rejected():
    """Pin: == is also rejected (strict >, not ≥). A 0-duration window
    is meaningless."""
    same = datetime(2024, 6, 1, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_base_payload(effective_start_date=same, effective_end_date=same))


def test_effective_end_alone_is_allowed():
    """start=None + end set → no comparison → accepted (the field
    validator only kicks in when both are present)."""
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)
    cfg = ScholarshipConfigurationBase(**_base_payload(effective_start_date=None, effective_end_date=end))
    assert cfg.effective_end_date == end


# ─── Field-level constraints ─────────────────────────────────────────


def test_academic_year_must_be_positive():
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_base_payload(academic_year=0))


def test_amount_must_be_positive():
    """gt=0 means 0 is also rejected — pin so a 'free' scholarship can't
    be created with this schema."""
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_base_payload(amount=0))


def test_config_code_max_length_enforced():
    """config_code is stored as String(50) in the DB — pin the
    schema-level cap so an over-length string is rejected before DB."""
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_base_payload(config_code="x" * 51))


# ─── ScholarshipConfigurationBulkCreate.validate_configurations ──────


def _bulk_entry(**overrides) -> dict:
    """A valid minimal entry for the bulk-create configurations list."""
    payload = _base_payload()
    payload["scholarship_type_id"] = 1
    payload.update(overrides)
    return payload


def test_bulk_create_rejects_empty_list():
    with pytest.raises(ValidationError) as exc:
        ScholarshipConfigurationBulkCreate(configurations=[])
    assert "至少需要一個配置" in str(exc.value)


def test_bulk_create_rejects_duplicate_config_codes():
    """CRITICAL: pre-validate duplicates so the bulk INSERT doesn't hit
    UniqueViolation mid-transaction and leave a partial-write state."""
    cfg_a = ScholarshipConfigurationCreate(**_bulk_entry(config_code="DUP-CODE"))
    cfg_b = ScholarshipConfigurationCreate(**_bulk_entry(config_code="DUP-CODE", config_name="Other"))
    with pytest.raises(ValidationError) as exc:
        ScholarshipConfigurationBulkCreate(configurations=[cfg_a, cfg_b])
    assert "配置代碼重複" in str(exc.value)


def test_bulk_create_accepts_unique_config_codes():
    cfg_a = ScholarshipConfigurationCreate(**_bulk_entry(config_code="UNIQUE-A"))
    cfg_b = ScholarshipConfigurationCreate(**_bulk_entry(config_code="UNIQUE-B"))
    bulk = ScholarshipConfigurationBulkCreate(configurations=[cfg_a, cfg_b])
    assert len(bulk.configurations) == 2


# ─── ScholarshipConfigurationImport.validate_import_data ─────────────


def test_import_rejects_empty_data():
    with pytest.raises(ValidationError) as exc:
        ScholarshipConfigurationImport(configurations=[])
    assert "匯入資料不能為空" in str(exc.value)


def test_import_rejects_missing_required_fields_with_index():
    """Pin: error includes the 1-based index of the bad row — admin UI
    relies on this to highlight the broken config."""
    with pytest.raises(ValidationError) as exc:
        ScholarshipConfigurationImport(
            configurations=[
                {"config_code": "OK", "config_name": "OK", "scholarship_type_id": 1},
                {"config_code": "BAD"},  # row 2 missing config_name + scholarship_type_id
            ]
        )
    msg = str(exc.value)
    assert "配置 2" in msg  # 1-based index
    assert "config_name" in msg or "scholarship_type_id" in msg


# ─── WhitelistBatchAddRequest.validate_students ──────────────────────


def test_whitelist_add_rejects_empty_list():
    with pytest.raises(ValidationError) as exc:
        WhitelistBatchAddRequest(students=[])
    assert "學生列表不能為空" in str(exc.value)


def test_whitelist_add_rejects_entries_missing_required_keys():
    """Pin: each student entry must have nycu_id + sub_type. Otherwise
    the admin's CSV-paste leaves placeholder rows that get persisted as
    junk whitelist entries."""
    with pytest.raises(ValidationError) as exc:
        WhitelistBatchAddRequest(students=[{"nycu_id": "0856001"}])  # missing sub_type
    assert "nycu_id 和 sub_type" in str(exc.value)


def test_whitelist_add_accepts_valid_payload():
    req = WhitelistBatchAddRequest(
        students=[
            {"nycu_id": "0856001", "sub_type": "nstc"},
            {"nycu_id": "0856002", "sub_type": "moe_1w"},
        ]
    )
    assert len(req.students) == 2


# ─── WhitelistBatchRemoveRequest.validate_nycu_ids ───────────────────


def test_whitelist_remove_rejects_empty_list():
    with pytest.raises(ValidationError) as exc:
        WhitelistBatchRemoveRequest(nycu_ids=[])
    assert "學號列表不能為空" in str(exc.value)


def test_whitelist_remove_accepts_optional_sub_type():
    """sub_type=None means 'remove from all sub-types' — pin so this
    sentinel path remains accessible."""
    req = WhitelistBatchRemoveRequest(nycu_ids=["0856001"], sub_type=None)
    assert req.sub_type is None
    assert req.nycu_ids == ["0856001"]


# ─── SharedQuotaSource + new config fields ───────────────────────────


def test_shared_quota_source_round_trips_on_base():
    """A shared_quota_sources link is parsed into SharedQuotaSource models
    and project_numbers flattens to {sub_type: code}."""
    cfg = ScholarshipConfigurationBase(
        **_base_payload(
            project_numbers={"nstc": "114R000001", "moe_1w": "114C000002"},
            shared_quota_sources=[
                {"source_config_code": "phd_113", "sub_types": ["nstc"]},
                {"source_config_code": "phd_112", "sub_types": ["nstc", "moe_1w"]},
            ],
        )
    )
    assert cfg.project_numbers == {"nstc": "114R000001", "moe_1w": "114C000002"}
    assert len(cfg.shared_quota_sources) == 2
    assert cfg.shared_quota_sources[0].source_config_code == "phd_113"
    assert cfg.shared_quota_sources[0].sub_types == ["nstc"]
    assert cfg.shared_quota_sources[1].sub_types == ["nstc", "moe_1w"]


def test_shared_quota_source_requires_source_config_code():
    """A link entry missing source_config_code is rejected at the schema boundary."""
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_base_payload(shared_quota_sources=[{"sub_types": ["nstc"]}]))


def test_new_fields_default_to_none():
    """Both new fields are optional and default to None when omitted."""
    cfg = ScholarshipConfigurationBase(**_base_payload())
    assert cfg.shared_quota_sources is None
    assert cfg.project_numbers is None

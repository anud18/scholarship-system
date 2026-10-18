"""
Tests for ManualDistributionService helper methods.

Covers the admin UI enhancement features:
- _compute_term_count: Replace grade display with raw term count
- _get_renewal_sub_type: Map renewal applications to Chinese sub-type names
- _sub_type_to_chinese: Sub-type code -> display name mapping
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

from app.models.application import Application
from app.services.manual_distribution_service import ManualDistributionService


class TestComputeTermCount:
    """Test _compute_term_count method."""

    def test_returns_integer_from_trm_termcount(self):
        """Given student_data with trm_termcount, returns that integer."""
        service = ManualDistributionService(db=Mock())
        result = service._compute_term_count({"trm_termcount": 5})
        assert result == 5

    def test_returns_integer_when_value_is_string(self):
        """Converts string numbers to integer."""
        service = ManualDistributionService(db=Mock())
        result = service._compute_term_count({"trm_termcount": "3"})
        assert result == 3

    def test_returns_none_when_missing(self):
        """Returns None when trm_termcount key absent."""
        service = ManualDistributionService(db=Mock())
        result = service._compute_term_count({})
        assert result is None

    def test_returns_none_when_non_numeric(self):
        """Returns None when value cannot be parsed as integer."""
        service = ManualDistributionService(db=Mock())
        result = service._compute_term_count({"trm_termcount": "abc"})
        assert result is None

    def test_returns_none_when_explicit_none(self):
        """Returns None when value is explicitly None."""
        service = ManualDistributionService(db=Mock())
        result = service._compute_term_count({"trm_termcount": None})
        assert result is None

    def test_falls_back_to_std_termcount_when_term_lookup_failed(self):
        """A snapshot with only std_* (SIS term lookup timed out) still shows 年級."""
        service = ManualDistributionService(db=Mock())
        assert service._compute_term_count({"std_termcount": 4}) == 4

    def test_term_row_count_wins_over_std_termcount(self):
        service = ManualDistributionService(db=Mock())
        assert service._compute_term_count({"trm_termcount": 5, "std_termcount": 4}) == 5


class TestSubTypeToChinese:
    """Test _sub_type_to_chinese static method."""

    def test_nstc_maps_to_chinese(self):
        assert ManualDistributionService._sub_type_to_chinese("nstc") == "國科會"

    def test_moe_1w_maps_to_chinese(self):
        assert ManualDistributionService._sub_type_to_chinese("moe_1w") == "教育部"

    def test_moe_2w_maps_to_chinese(self):
        assert ManualDistributionService._sub_type_to_chinese("moe_2w") == "教育部"

    def test_unknown_returns_raw_code(self):
        """Unknown codes fall back to the raw string."""
        assert ManualDistributionService._sub_type_to_chinese("custom_xyz") == "custom_xyz"


class TestGetRenewalSubType:
    """Test _get_renewal_sub_type method."""

    def test_returns_none_for_non_renewal(self):
        """Non-renewal applications return None."""
        service = ManualDistributionService(db=Mock())
        app = Mock(spec=Application)
        app.is_renewal = False
        app.sub_scholarship_type = "nstc"
        assert service._get_renewal_sub_type(app) is None

    def test_returns_chinese_for_renewal_nstc(self):
        """Renewal with nstc sub-type returns 國科會."""
        service = ManualDistributionService(db=Mock())
        app = Mock(spec=Application)
        app.is_renewal = True
        app.sub_scholarship_type = "nstc"
        assert service._get_renewal_sub_type(app) == "國科會"

    def test_returns_chinese_for_renewal_moe_1w(self):
        """Renewal with moe_1w sub-type returns 教育部."""
        service = ManualDistributionService(db=Mock())
        app = Mock(spec=Application)
        app.is_renewal = True
        app.sub_scholarship_type = "moe_1w"
        assert service._get_renewal_sub_type(app) == "教育部"

    def test_returns_none_when_sub_type_is_general(self):
        """General (no specific) sub-type returns None."""
        service = ManualDistributionService(db=Mock())
        app = Mock(spec=Application)
        app.is_renewal = True
        app.sub_scholarship_type = "general"
        assert service._get_renewal_sub_type(app) is None

    def test_returns_none_when_sub_type_is_empty(self):
        """Empty sub_scholarship_type returns None."""
        service = ManualDistributionService(db=Mock())
        app = Mock(spec=Application)
        app.is_renewal = True
        app.sub_scholarship_type = ""
        assert service._get_renewal_sub_type(app) is None


# ─── 學院/系所/學期數 on the distribution grid: API 1 (std_*) first ───


def _grid_app(app_id, student_data):
    return SimpleNamespace(
        id=app_id,
        deleted_at=None,
        student_data=student_data,
        scholarship_subtype_list=["nstc"],
        quota_allocation_status=None,
        cancelled_from_status=None,
        cancelled_from_quota_status=None,
        revoke_reason=None,
        suspend_reason=None,
        is_renewal=False,
        renewal_year=None,
        previous_application_id=None,
        academic_year=114,
        sub_scholarship_type="nstc",
        scholarship_configuration=None,
    )


async def _grid_rows(monkeypatch, apps, department_names):
    items = [
        SimpleNamespace(
            id=10 + i,
            rank_position=i + 1,
            allocated_sub_type=None,
            allocation_config_id=None,
            is_allocated=False,
            status="ranked",
            college_rejected=False,
            is_supplementary=False,
            application=app,
        )
        for i, app in enumerate(apps)
    ]
    calls = []

    def _execute(stmt, *a, **k):
        calls.append(stmt)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [SimpleNamespace(id=1)] if len(calls) == 1 else items
        return result

    db = MagicMock()
    db.execute = AsyncMock(side_effect=_execute)
    names_loader = AsyncMock(return_value=department_names)
    monkeypatch.setattr("app.services.manual_distribution_service.load_department_names", names_loader)
    svc = ManualDistributionService(db)
    svc._batch_load_rejected_map = AsyncMock(return_value={})
    svc._batch_load_review_items = AsyncMock(return_value={})
    svc._bulk_system_received_months = AsyncMock(return_value={})
    svc._bulk_imported_received_months = AsyncMock(return_value={})
    rows = await svc.get_students_for_distribution(2, 114, "yearly")
    names_loader.assert_awaited_once()  # once per request, never per row
    return {row["application_id"]: row for row in rows}


async def test_grid_term_lookup_failed_snapshot_is_not_blank(monkeypatch):
    """Only std_* in the snapshot (SIS term lookup timed out) → 學院/系所/學期數 still filled."""
    std_only = {"std_cname": "王某", "std_academyno": "E", "std_depno": "1511", "std_termcount": 4}
    rows = await _grid_rows(monkeypatch, [_grid_app(1, std_only)], {"1511": "電機工程學系"})

    assert rows[1]["college_code"] == "E"
    assert rows[1]["college_name"] == "電機學院"
    assert rows[1]["department_name"] == "電機工程學系"
    assert rows[1]["term_count"] == 4


async def test_grid_transferred_student_shows_api_1_unit_and_unknown_code_falls_back(monkeypatch):
    transferred = {
        "std_academyno": "E",
        "std_depno": "1511",
        "trm_academyno": "C",
        "trm_academyname": "資訊學院",
        "trm_depno": "1550",
        "trm_depname": "資訊工程學系",
        "trm_termcount": 3,
    }
    unknown = {"std_academyno": "ZZ", "std_depno": "9999", "trm_academyname": "舊學院", "trm_depname": "舊系"}
    rows = await _grid_rows(
        monkeypatch,
        [_grid_app(1, transferred), _grid_app(2, unknown)],
        {"1511": "電機工程學系", "1550": "資訊工程學系"},
    )

    assert (rows[1]["college_name"], rows[1]["department_name"]) == ("電機學院", "電機工程學系")
    assert (rows[2]["college_name"], rows[2]["department_name"]) == ("舊學院", "舊系")

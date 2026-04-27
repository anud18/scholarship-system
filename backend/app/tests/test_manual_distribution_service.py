"""
Tests for ManualDistributionService helper methods.

Covers the admin UI enhancement features:
- _compute_term_count: Replace grade display with raw term count
- _get_renewal_sub_type: Map renewal applications to Chinese sub-type names
- _sub_type_to_chinese: Sub-type code -> display name mapping
"""

from unittest.mock import Mock

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

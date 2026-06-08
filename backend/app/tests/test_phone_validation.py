"""Unit tests for Taiwan mobile validation used by the contact_phone field."""

from app.utils.phone_validation import (
    TAIWAN_MOBILE_MESSAGE,
    extract_contact_phone,
    is_valid_taiwan_mobile,
)


class TestIsValidTaiwanMobile:
    def test_accepts_valid_mobile(self):
        assert is_valid_taiwan_mobile("0912345678") is True

    def test_rejects_landline_with_dashes(self):
        # Previously accepted by the old pattern; now mobile-only.
        assert is_valid_taiwan_mobile("0912-345-678") is False

    def test_rejects_landline_with_area_code(self):
        assert is_valid_taiwan_mobile("02-12345678") is False

    def test_rejects_too_short(self):
        assert is_valid_taiwan_mobile("091234567") is False

    def test_rejects_too_long(self):
        assert is_valid_taiwan_mobile("09123456789") is False

    def test_rejects_non_09_prefix(self):
        assert is_valid_taiwan_mobile("0812345678") is False

    def test_rejects_non_digits(self):
        assert is_valid_taiwan_mobile("09abcd5678") is False

    def test_rejects_whitespace(self):
        assert is_valid_taiwan_mobile(" 0912345678") is False
        assert is_valid_taiwan_mobile("0912345678 ") is False

    def test_rejects_none_and_empty(self):
        assert is_valid_taiwan_mobile(None) is False
        assert is_valid_taiwan_mobile("") is False

    def test_message_is_the_requested_text(self):
        assert TAIWAN_MOBILE_MESSAGE == "請輸入本人有效的台灣手機 (09xxxxxx)"


class TestExtractContactPhone:
    def test_extracts_value_from_mapping(self):
        fields = {
            "contact_phone": {
                "field_id": "contact_phone",
                "field_type": "text",
                "value": "0912345678",
                "required": True,
            }
        }
        assert extract_contact_phone(fields) == "0912345678"

    def test_absent_field_returns_none(self):
        assert extract_contact_phone({"bank_account": {"value": "123"}}) is None

    def test_none_or_empty_fields_returns_none(self):
        assert extract_contact_phone(None) is None
        assert extract_contact_phone({}) is None

    def test_reads_value_attribute_from_object(self):
        class _Field:
            value = "0987654321"

        assert extract_contact_phone({"contact_phone": _Field()}) == "0987654321"

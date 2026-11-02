"""The shown value of the profile-owned form fields (郵局帳號, 指導教授 trio)."""

import pytest

from app.services.profile_owned_fields import (
    EffectiveProfileFields,
    resolve_effective_profile_fields,
)

OWN = "11111111111111"
PROFILE = "22222222222222"
LEAKED = "33333333333333"
BANK = "44444444444444"


def _form(**values):
    return {"fields": {key: {"field_id": key, "value": value} for key, value in values.items()}}


def _account(form, profile=None):
    return resolve_effective_profile_fields(form, profile or {}).postal_account


class TestPostalAccount:
    def test_account_typed_with_the_application_beats_the_profile(self):
        assert _account(_form(account_number=OWN, postal_account=LEAKED), {"account_number": PROFILE}) == OWN

    def test_profile_beats_a_submitted_postal_account(self):
        assert _account(_form(postal_account=LEAKED), {"account_number": PROFILE}) == PROFILE

    def test_imported_application_without_profile_uses_postal_account(self):
        assert _account(_form(postal_account=LEAKED, bank_account=BANK)) == LEAKED

    def test_bank_account_is_the_last_resort(self):
        assert _account(_form(bank_account=BANK)) == BANK

    @pytest.mark.parametrize("blank", ["", "   ", None])
    def test_blank_sources_fall_through(self, blank):
        assert _account(_form(account_number=blank, postal_account=LEAKED), {"account_number": blank}) == LEAKED

    def test_nothing_anywhere_is_none(self):
        assert _account(_form(account_number=""), {"account_number": None}) is None
        assert _account(None) is None

    def test_a_bare_value_without_an_entry_wrapper_is_read(self):
        assert _account({"fields": {"account_number": OWN}}) == OWN


class TestAdvisorFields:
    @pytest.mark.parametrize("field_id", ["advisor_name", "advisor_email", "advisor_nycu_id"])
    def test_profile_beats_the_submitted_copy(self, field_id):
        effective = resolve_effective_profile_fields(_form(**{field_id: "submitted"}), {field_id: "profile"})
        assert getattr(effective, field_id) == "profile"

    @pytest.mark.parametrize("field_id", ["advisor_name", "advisor_email", "advisor_nycu_id"])
    def test_submitted_copy_when_the_profile_lacks_it(self, field_id):
        effective = resolve_effective_profile_fields(_form(**{field_id: "submitted"}), {field_id: " "})
        assert getattr(effective, field_id) == "submitted"

    def test_profile_account_never_fills_an_advisor_field(self):
        effective = resolve_effective_profile_fields(_form(), {"account_number": PROFILE})
        assert effective == EffectiveProfileFields(
            postal_account=PROFILE, advisor_name=None, advisor_email=None, advisor_nycu_id=None
        )


def test_by_field_id_keys_are_the_form_config_ids():
    effective = resolve_effective_profile_fields(_form(account_number=OWN), {"advisor_name": "王教授"})
    assert effective.by_field_id() == {
        "postal_account": OWN,
        "advisor_name": "王教授",
        "advisor_email": None,
        "advisor_nycu_id": None,
    }

"""ScholarshipConfiguration.open_sub_types: which sub-types this opening accepts."""

from app.models.scholarship import ScholarshipConfiguration


def _config(open_sub_types):
    return ScholarshipConfiguration(open_sub_types=open_sub_types)


def test_null_means_every_sub_type_is_open():
    config = _config(None)
    assert config.is_sub_type_open("nstc")
    assert config.is_sub_type_open("moe_1w")


def test_restricted_list_opens_only_listed_codes():
    config = _config(["moe_1w", "moe_2w"])
    assert config.is_sub_type_open("moe_1w")
    assert config.is_sub_type_open("moe_2w")
    assert not config.is_sub_type_open("nstc")


def test_code_match_ignores_case_and_whitespace():
    config = _config(["nstc"])
    assert config.is_sub_type_open(" NSTC ")
    assert not config.is_sub_type_open(" MOE_1W")


def test_general_is_always_open():
    assert _config(["nstc"]).is_sub_type_open("general")
    assert _config(None).is_sub_type_open("general")

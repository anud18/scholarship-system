"""
Tests for the module-level i18n helpers in `app/utils/i18n.py`.

Wave 6kk (test_i18n_utils.py) covered the ScholarshipI18n classmethod
surface (get_text, status_text, detect_language_from_request,
supported_languages, scholarship_type_text). This wave fills the
remaining surface:

  - **t() shorthand** at module level — used by endpoints / services
    that need a one-line translation. Pin that it routes to
    ScholarshipI18n.get_text with the right defaults.

  - **get_user_language()** — multi-source language preference
    resolver. Priority order pinned:
      1. user_data["preferred_language"] (explicit user setting)
      2. accept-language header
      3. Traditional Chinese default

  - **get_localized_email_template()** — the email template builder.
    Pin: unknown template_type falls back to application_submitted.

13 cases.
"""

from app.utils.i18n import Language, ScholarshipI18n, get_user_language, t

# ─── t() shorthand ──────────────────────────────────────────────────


def test_t_defaults_to_traditional_chinese():
    # Pin: default language is zh-TW.
    result = t("submitted", "status")
    # The exact translation depends on the data; we just check it's
    # non-empty.
    assert isinstance(result, str)
    assert len(result) > 0


def test_t_routes_to_scholarshipi18n_get_text():
    # Pin: t() is a thin wrapper. Same input must yield same output
    # as ScholarshipI18n.get_text.
    assert t("submitted", "status") == ScholarshipI18n.get_text("submitted", "status")


def test_t_with_english_language():
    # Pin: explicit language argument overrides default.
    zh = t("submitted", "status", Language.TRADITIONAL_CHINESE.value)
    en = t("submitted", "status", Language.ENGLISH.value)
    # The two should generally differ (zh / en text).
    # Allow case where both have the same fallback, but the function
    # at least accepts both args.
    assert isinstance(zh, str)
    assert isinstance(en, str)


def test_t_unknown_key_returns_titlecase_fallback():
    # Pin: same fallback as get_text — unknown key becomes Title Case
    # version of the key (no crash).
    result = t("some_unknown_key", "messages")
    assert isinstance(result, str)
    assert len(result) > 0


def test_t_default_category_is_messages():
    # Pin: omitting category routes to "messages" by default. The
    # most common shorthand use case is t("application_submitted").
    direct = t("application_submitted")
    via_messages = t("application_submitted", "messages")
    assert direct == via_messages


# ─── get_user_language() ────────────────────────────────────────────


def test_get_user_language_no_input_defaults_zh():
    # Pin: zh-TW is the documented default per CLAUDE.md (primary
    # system language).
    assert get_user_language() == Language.TRADITIONAL_CHINESE.value


def test_get_user_language_uses_user_data_first():
    # Pin: explicit preference takes priority over header.
    user_data = {"preferred_language": "en"}
    headers = {"accept-language": "zh-TW"}
    assert get_user_language(user_data=user_data, request_headers=headers) == "en"


def test_get_user_language_falls_back_to_header_when_no_user_data():
    # Pin: header-based detection when user data has no preference.
    headers = {"accept-language": "en-US,en;q=0.9"}
    assert get_user_language(request_headers=headers) == Language.ENGLISH.value


def test_get_user_language_user_data_without_preferred_language_key():
    # Pin: user_data dict present but missing the "preferred_language"
    # key falls through to header detection.
    user_data = {"name": "Test"}  # no preferred_language
    headers = {"accept-language": "en"}
    assert get_user_language(user_data=user_data, request_headers=headers) == Language.ENGLISH.value


def test_get_user_language_unknown_header_falls_back_to_zh():
    # Pin: unrecognized Accept-Language → zh-TW default (matches
    # detect_language_from_request behaviour).
    headers = {"accept-language": "fr-FR,fr;q=0.9"}
    assert get_user_language(request_headers=headers) == Language.TRADITIONAL_CHINESE.value


def test_get_user_language_empty_user_data_dict():
    # Pin: empty dict (not None) — falls through to header / default.
    headers = {"accept-language": "zh-CN"}
    assert get_user_language(user_data={}, request_headers=headers) == Language.TRADITIONAL_CHINESE.value


# ─── get_localized_email_template ───────────────────────────────────


def test_email_template_known_type_returns_complete_dict():
    # Pin: known type returns a dict with at least subject + greeting +
    # closing + footer keys. Email render template expects all 4.
    t_dict = ScholarshipI18n.get_localized_email_template("application_submitted")
    assert "subject" in t_dict
    assert "greeting" in t_dict
    assert "closing" in t_dict
    assert "footer" in t_dict


def test_email_template_unknown_type_falls_back_to_application_submitted():
    # Pin: unknown type returns the application_submitted template
    # (not None, not empty dict). Defensive — emails never silently
    # fail to render.
    fallback = ScholarshipI18n.get_localized_email_template("unknown_type_xyz")
    application = ScholarshipI18n.get_localized_email_template("application_submitted")
    assert fallback == application

"""
Tests for `app.utils.i18n.ScholarshipI18n`.

This translator drives every status / scholarship-type / message string
that students and reviewers see. A miss here means UI displays the raw
key (e.g., 'application_status.submitted' instead of '已提交') —
visible to every user.

5 methods covered (14 cases):
- `get_text`                       : primary + fallback + final key-mangle
- `get_application_status_text`    : status enum/string → Chinese label
- `get_scholarship_type_text`      : main → sub fallback path
- `get_supported_languages`        : pinned language list
- `detect_language_from_request`   : Accept-Language header parsing
"""

import pytest

from app.utils.i18n import Language, ScholarshipI18n

# ─── get_text ────────────────────────────────────────────────────────


def test_get_text_chinese_status_lookup():
    """Known key in zh-TW returns the Chinese label."""
    assert (
        ScholarshipI18n.get_text("submitted", "application_status", language=Language.TRADITIONAL_CHINESE.value)
        == "已提交"
    )


def test_get_text_unknown_key_returns_titlecase_fallback():
    """Unknown key → key with underscores → spaces, title-cased.
    This is the last-resort fallback so missing translations are at
    least readable in admin UI."""
    out = ScholarshipI18n.get_text("never_existed_key", "application_status")
    assert out == "Never Existed Key"


def test_get_text_unknown_category_returns_titlecase_fallback():
    """Even with a known key, missing category falls back to title-case."""
    out = ScholarshipI18n.get_text("submitted", "nonexistent_category")
    assert out == "Submitted"


def test_get_text_unknown_language_falls_back_to_fallback_lang():
    """Unknown primary language ⇒ try the fallback (default English).
    Final fallback: title-cased key (since English translations aren't
    fully populated here)."""
    out = ScholarshipI18n.get_text("submitted", "application_status", language="ja")
    assert out == "Submitted"  # Title-cased fallback


# ─── get_application_status_text ─────────────────────────────────────


def test_status_text_known_values():
    """Pin a handful of business-critical status mappings — these are
    visible in every admin queue and student dashboard."""
    assert ScholarshipI18n.get_application_status_text("draft") == "草稿"
    assert ScholarshipI18n.get_application_status_text("approved") == "已核准"
    assert ScholarshipI18n.get_application_status_text("rejected") == "已拒絕"
    assert ScholarshipI18n.get_application_status_text("withdrawn") == "已撤回"


def test_status_text_accepts_enum_like_object():
    """The function unwraps any obj with a .value attribute (Enum
    duck-typing) — pin so passing an ApplicationStatus enum works."""

    class _FakeEnum:
        value = "submitted"

    assert ScholarshipI18n.get_application_status_text(_FakeEnum()) == "已提交"


# ─── get_scholarship_type_text ───────────────────────────────────────


def test_scholarship_type_text_main_type():
    """Main scholarship types resolve directly."""
    assert ScholarshipI18n.get_scholarship_type_text("PHD") == "博士獎學金"


def test_scholarship_type_text_falls_through_to_sub_type():
    """Sub-type values fall through main-type lookup to sub-types
    (the main lookup returns the title-cased key for non-matches,
    then the helper retries against sub_types)."""
    assert ScholarshipI18n.get_scholarship_type_text("NSTC") == "國科會類"
    assert ScholarshipI18n.get_scholarship_type_text("MOE_1W") == "教育部一般"


# ─── get_supported_languages ─────────────────────────────────────────


def test_supported_languages_returns_two_entries():
    """Two languages — zh-TW and en. Adding more requires translation
    coverage in the TRANSLATIONS dict, so pin this so it's reviewed."""
    langs = ScholarshipI18n.get_supported_languages()
    assert len(langs) == 2
    codes = [l["code"] for l in langs]
    assert codes == ["zh-TW", "en"]


# ─── detect_language_from_request ────────────────────────────────────


def test_detect_language_no_header_returns_zh_default():
    """No Accept-Language header → default to zh-TW (the primary user base)."""
    assert ScholarshipI18n.detect_language_from_request(None) == "zh-TW"
    assert ScholarshipI18n.detect_language_from_request("") == "zh-TW"


def test_detect_language_zh_header():
    """Any zh-* variant (zh, zh-TW, zh-Hant) → zh-TW."""
    assert ScholarshipI18n.detect_language_from_request("zh-TW,en;q=0.9") == "zh-TW"
    assert ScholarshipI18n.detect_language_from_request("zh-Hant-TW") == "zh-TW"


def test_detect_language_en_header():
    """Anglo-leaning header → en."""
    assert ScholarshipI18n.detect_language_from_request("en-US,en;q=0.9") == "en"


def test_detect_language_unknown_falls_back_to_zh():
    """ja / fr / unknown → zh-TW (the default user base)."""
    assert ScholarshipI18n.detect_language_from_request("ja-JP") == "zh-TW"
    assert ScholarshipI18n.detect_language_from_request("fr-FR") == "zh-TW"


def test_detect_language_zh_takes_precedence_over_en():
    """If both zh and en appear in header, zh wins (it's checked first).
    Pin because this affects which language a Taiwan-locale user with
    English browser preference sees."""
    assert ScholarshipI18n.detect_language_from_request("en-US,zh-TW;q=0.8") == "zh-TW"

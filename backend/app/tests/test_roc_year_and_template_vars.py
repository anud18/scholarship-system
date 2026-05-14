"""
Tests for pure helpers on two endpoint files:

  - **taiwan_to_western_year / western_to_taiwan_year**
    (scholarship_configurations.py): bidirectional ROC↔Gregorian
    year converters used when the admin UI emits 民國年 (e.g., 114)
    but the API stores Gregorian (e.g., 2025). Critical because:
      * Wrong by 1911 → academic years off by ~2 millennia in DB,
        wrong by 11 → no overlap with any real-world data
      * Round-trip must be exact (taiwan→western→taiwan == id)

  - **extract_template_variables(subject, body)**
    (email_management.py): pulls `{variable}` placeholders out of
    email template strings. The admin email template editor uses
    this list to show "missing variable" warnings and to validate
    that the rendering context provides every variable. Pin:
      * `{name}` and `{user.email}` extraction
      * Deduplication across subject+body
      * Sorted output (deterministic UI list)
      * No placeholders → empty list
      * Non-`{...}` strings ignored

13 cases.
"""

from app.api.v1.endpoints.email_management import extract_template_variables
from app.api.v1.endpoints.scholarship_configurations import (
    taiwan_to_western_year,
    western_to_taiwan_year,
)

# ─── taiwan_to_western_year ──────────────────────────────────────────


def test_taiwan_to_western_current_year():
    # Pin: ROC year 114 → 2025. This is the current academic year
    # at the time this test wave was written; documents the offset
    # explicitly.
    assert taiwan_to_western_year(114) == 2025


def test_taiwan_to_western_historical():
    # Pin: ROC year 1 = 1912 (Republic founding year).
    assert taiwan_to_western_year(1) == 1912


def test_taiwan_to_western_zero():
    # Pin: ROC year 0 → 1911. Edge case — admin UI might emit 0 if
    # the year field is unfilled; the function shouldn't crash.
    assert taiwan_to_western_year(0) == 1911


# ─── western_to_taiwan_year ──────────────────────────────────────────


def test_western_to_taiwan_current_year():
    # Pin: 2025 → ROC 114. Reverse of the above.
    assert western_to_taiwan_year(2025) == 114


def test_western_to_taiwan_historical():
    # Pin: 1912 → ROC 1.
    assert western_to_taiwan_year(1912) == 1


def test_western_to_taiwan_before_roc_founding():
    # Pin: years before 1911 produce NEGATIVE ROC years. Function
    # does not validate input — caller's responsibility. Pinned
    # so a defensive `max(0, ...)` doesn't get added without
    # explicit review.
    assert western_to_taiwan_year(1900) == -11


def test_roundtrip_is_identity():
    # Pin: round-trip exactness. Any year passed through both
    # converters must equal itself — this is the contract every
    # call site relies on.
    for year in [1, 100, 114, 200, 1000]:
        assert western_to_taiwan_year(taiwan_to_western_year(year)) == year


# ─── extract_template_variables ─────────────────────────────────────


def test_extract_single_variable_from_subject():
    # Pin: `{name}` extracted from subject. Subject-only path.
    out = extract_template_variables("Hello {name}!", "")
    assert out == ["name"]


def test_extract_single_variable_from_body():
    # Pin: `{user}` extracted from body. Body-only path.
    out = extract_template_variables("", "Dear {user}")
    assert out == ["user"]


def test_extract_dedupes_across_subject_and_body():
    # Pin: same variable appearing in both fields appears ONCE in
    # output. Set-union semantics, not list concat.
    out = extract_template_variables("Hi {name}", "Dear {name}")
    assert out == ["name"]


def test_extract_returns_sorted_list():
    # Pin: output is alphabetically sorted. The admin UI displays
    # the variable list verbatim — pin so a refactor to a Set or
    # to insertion-order dict doesn't shuffle the UI.
    out = extract_template_variables("{zulu} {alpha}", "{mike}")
    assert out == ["alpha", "mike", "zulu"]


def test_extract_returns_empty_when_no_placeholders():
    # Pin: zero placeholders → [] (empty list). Caller code
    # iterates this; pin so a refactor doesn't return None.
    out = extract_template_variables("plain subject", "plain body")
    assert out == []


def test_extract_word_pattern_only():
    # Pin: regex is `\{(\w+)\}` — \w means [A-Za-z0-9_]. Dotted
    # paths like {user.email} or {a-b} are NOT extracted. The
    # template renderer does not support dot-path expansion, so
    # this is the documented contract.
    out = extract_template_variables("", "{user.email} {plain}")
    assert out == ["plain"]


def test_extract_handles_multiple_occurrences():
    # Pin: multiple occurrences of same variable → single entry
    # (set semantics). Also pins regex finds all matches, not
    # just first.
    out = extract_template_variables(
        "{name} hello {name}",
        "{name} bye {other}",
    )
    assert out == ["name", "other"]

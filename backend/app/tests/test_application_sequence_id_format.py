"""
Tests for `ApplicationSequence.get_semester_code` and
`ApplicationSequence.format_app_id` — the canonical application ID
formatter documented in CLAUDE.md §6.

Every Application row in the system gets its `app_id` from
`format_app_id`, and downstream systems (notification emails, audit
log queries, admin search UI, PDF exports) all parse the format
`APP-{academic_year}-{semester_code}-{sequence:05d}`.

Bugs cause:
- Wrong semester_code in app_id → admin search by semester filter
  returns wrong applications
- Wrong zero-padding → string sort order breaks
- Format-string drift → email templates render literal `{academic_year}`
- Unknown semester silently mapped to wrong code → applications
  attributed to wrong academic period

2 static helpers (11 cases). Pure, no DB.
"""

from app.models.application_sequence import ApplicationSequence

# ─── get_semester_code ───────────────────────────────────────────────


def test_semester_code_first_maps_to_1():
    """Pin: 'first' → '1'. CLAUDE.md §6 documents this exact mapping."""
    assert ApplicationSequence.get_semester_code("first") == "1"


def test_semester_code_second_maps_to_2():
    """Pin: 'second' → '2'."""
    assert ApplicationSequence.get_semester_code("second") == "2"


def test_semester_code_yearly_maps_to_0():
    """Pin: 'yearly' → '0'. Yearly scholarships use the special
    semester_code 0 (no semester partition in the ID)."""
    assert ApplicationSequence.get_semester_code("yearly") == "0"


def test_semester_code_unknown_defaults_to_yearly():
    """Pin: unknown semester strings → '0' (yearly default).
    Defensive against accidental enum-rename or None passed by
    over-zealous caller.

    Note: this is the LEAST surprising default for the format string —
    a yearly-style app_id is parseable, whereas missing the semester
    section entirely would corrupt the format."""
    assert ApplicationSequence.get_semester_code("unknown_value") == "0"
    assert ApplicationSequence.get_semester_code("") == "0"


def test_semester_code_returns_string_not_int():
    """Pin: return type is str (not int). The format_app_id formatter
    interpolates it directly; an int would still f-string but would
    break callers that expect a string."""
    result = ApplicationSequence.get_semester_code("first")
    assert isinstance(result, str)


# ─── format_app_id ───────────────────────────────────────────────────


def test_format_app_id_canonical_first_semester():
    """Pin: APP-113-1-00001 — CLAUDE.md §6 first example.
    Five-digit zero-padded sequence."""
    assert ApplicationSequence.format_app_id(113, "first", 1) == "APP-113-1-00001"


def test_format_app_id_second_semester_larger_sequence():
    """Pin: APP-113-2-00125 — CLAUDE.md §6 second example.
    Confirms five-digit padding maintained for >100 sequence."""
    assert ApplicationSequence.format_app_id(113, "second", 125) == "APP-113-2-00125"


def test_format_app_id_yearly():
    """Pin: APP-114-0-00001 — CLAUDE.md §6 third example."""
    assert ApplicationSequence.format_app_id(114, "yearly", 1) == "APP-114-0-00001"


def test_format_app_id_zero_padding_5_digits():
    """Pin: 5-digit zero-padding even for sequence >= 10000. The system
    is unlikely to exceed 99999 in one semester but pin the format
    explicitly so a refactor to {sequence:04d} surfaces here."""
    assert ApplicationSequence.format_app_id(113, "first", 12345) == "APP-113-1-12345"


def test_format_app_id_unknown_semester_uses_yearly_code():
    """Pin: unknown semester string flows through get_semester_code's
    default → '0'. So format_app_id with bad semester produces a
    yearly-style ID rather than an empty/broken section."""
    assert ApplicationSequence.format_app_id(113, "bogus", 1) == "APP-113-0-00001"


def test_format_app_id_preserves_prefix_APP():
    """Pin: prefix is literal 'APP-'. Email templates and audit-log
    queries grep for this prefix to detect application IDs in free text."""
    result = ApplicationSequence.format_app_id(113, "first", 1)
    assert result.startswith("APP-")

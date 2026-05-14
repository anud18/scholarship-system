"""
Tests for the 4 roster-related enums in `app.models.payment_roster`.

These enums drive:
- Roster generation scheduling (cycle: monthly/semi-yearly/yearly)
- Roster lifecycle state machine (status: draft → processing →
  completed → locked, or failed)
- Trigger source attribution (manual / scheduled / dry_run)
- Student eligibility verification outcome

Bugs cause:
- Wrong cycle value → APScheduler picks the wrong cron template
- Wrong status value → roster lifecycle state machine deadlocks
- Wrong verification status → ineligible students included on roster
  OR eligible students excluded

Note: these enums deviate from the system-wide lowercase-member-name
convention (CLAUDE.md §4) — member names are UPPERCASE but values are
lowercase. Pin the contract so a 'fix' doesn't accidentally rename
either side.

4 enums (10 cases). Pure, no DB.
"""

from app.models.payment_roster import (
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)

# ─── RosterCycle (drives schedule cron template) ─────────────────────


def test_roster_cycle_values():
    """Pin: 3 cycle values matching the scheduler's cron-template lookup."""
    assert RosterCycle.MONTHLY.value == "monthly"
    assert RosterCycle.SEMI_YEARLY.value == "semi_yearly"
    assert RosterCycle.YEARLY.value == "yearly"
    assert len(list(RosterCycle)) == 3


def test_roster_cycle_member_names_uppercase():
    """Pin: member names are UPPERCASE (deviation from system-wide
    lowercase convention). Pin to prevent a 'fix' from renaming
    these and breaking the entire roster scheduler import chain."""
    assert RosterCycle.MONTHLY.name == "MONTHLY"
    assert RosterCycle.SEMI_YEARLY.name == "SEMI_YEARLY"


# ─── RosterStatus (lifecycle state machine) ──────────────────────────


def test_roster_status_values():
    """Pin: 5 status values forming the lifecycle:
    draft → processing → completed → locked (success path)
    or → failed (failure path)."""
    assert RosterStatus.DRAFT.value == "draft"
    assert RosterStatus.PROCESSING.value == "processing"
    assert RosterStatus.COMPLETED.value == "completed"
    assert RosterStatus.LOCKED.value == "locked"
    assert RosterStatus.FAILED.value == "failed"
    assert len(list(RosterStatus)) == 5


def test_roster_status_locked_distinct_from_completed():
    """Pin: LOCKED is its own state, NOT completed-locked. Once locked,
    the roster becomes read-only — distinct semantics from completed
    (which can still be edited by an admin before lock)."""
    assert RosterStatus.LOCKED.value != RosterStatus.COMPLETED.value
    assert RosterStatus.LOCKED.value == "locked"


# ─── RosterTriggerType (manual vs scheduled vs dry-run) ──────────────


def test_roster_trigger_type_values():
    """Pin: 3 trigger types. CRITICAL: 'dry_run' must NOT match
    'manual' or 'scheduled' — the roster-execution path branches on
    this to decide whether to write to the DB or just preview."""
    assert RosterTriggerType.MANUAL.value == "manual"
    assert RosterTriggerType.SCHEDULED.value == "scheduled"
    assert RosterTriggerType.DRY_RUN.value == "dry_run"
    assert len(list(RosterTriggerType)) == 3


def test_roster_trigger_type_dry_run_uses_underscore():
    """Pin: dry_run with underscore (not dash). The cron job + admin UI
    serialize this string into URL paths AND audit logs — a refactor
    to 'dry-run' would silently break both."""
    assert RosterTriggerType.DRY_RUN.value == "dry_run"
    assert "-" not in RosterTriggerType.DRY_RUN.value


# ─── StudentVerificationStatus ───────────────────────────────────────


def test_student_verification_status_values():
    """Pin: 6 verification outcomes covering both happy paths (verified,
    graduated, withdrawn) and API failure modes (api_error, not_found,
    suspended).

    SECURITY-RELEVANT: getting these wrong means a graduated/withdrawn
    student stays on the active roster, OR a verified student is
    silently excluded. Compliance auditors track these strings."""
    assert StudentVerificationStatus.VERIFIED.value == "verified"
    assert StudentVerificationStatus.GRADUATED.value == "graduated"
    assert StudentVerificationStatus.SUSPENDED.value == "suspended"
    assert StudentVerificationStatus.WITHDRAWN.value == "withdrawn"
    assert StudentVerificationStatus.API_ERROR.value == "api_error"
    assert StudentVerificationStatus.NOT_FOUND.value == "not_found"
    assert len(list(StudentVerificationStatus)) == 6


def test_student_verification_status_api_error_distinct_from_not_found():
    """Pin: 'api_error' and 'not_found' are SEMANTICALLY DIFFERENT —
    api_error means upstream NYCU portal is down (retry later);
    not_found means the student record doesn't exist (skip permanently).
    A regression collapsing these to one value would cause infinite
    retries on missing students."""
    assert StudentVerificationStatus.API_ERROR.value != StudentVerificationStatus.NOT_FOUND.value


# ─── Cross-enum invariant ────────────────────────────────────────────


def test_all_roster_enum_values_are_lowercase():
    """Pin: despite member names being UPPERCASE, the .value strings
    are all lowercase per the DB column convention."""
    for enum_cls in (RosterCycle, RosterStatus, RosterTriggerType, StudentVerificationStatus):
        for member in enum_cls:
            assert (
                member.value == member.value.lower()
            ), f"{enum_cls.__name__}.{member.name} value '{member.value}' is not lowercase"

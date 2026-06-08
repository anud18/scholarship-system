"""
Tests for the remaining model enums:
- ScholarshipStatus (scholarship.py): active/inactive/draft
- FieldType (application_field.py): 8 form field types
- RosterScheduleStatus (roster_schedule.py): scheduler lifecycle
- RosterAuditAction (roster_audit.py): 15 audit actions (includes
  dry_run distinct from schedule_run/manual_run)
- RosterAuditLevel (roster_audit.py): info/warning/error/critical

Bugs cause:
- ScholarshipStatus.draft vs inactive collision → drafts shown as
  active in admin UI
- FieldType rename → form-builder UI orphans fields
- RosterScheduleStatus rename → scheduler can't resume after restart
- RosterAuditAction collision → wrong action attributed in compliance
  audit (e.g., dry_run shown as schedule_run → false compliance violation)

5 enums (10 cases). Pure, no DB.
"""

from app.models.application_field import FieldType
from app.models.roster_audit import RosterAuditAction, RosterAuditLevel
from app.models.roster_schedule import RosterScheduleStatus
from app.models.scholarship import ScholarshipStatus

# ─── ScholarshipStatus ───────────────────────────────────────────────


def test_scholarship_status_values():
    """Pin: 3 lifecycle values. active = displayed to students,
    inactive = admin-hidden, draft = WIP not yet published."""
    assert ScholarshipStatus.active.value == "active"
    assert ScholarshipStatus.inactive.value == "inactive"
    assert ScholarshipStatus.draft.value == "draft"
    assert len(list(ScholarshipStatus)) == 3


def test_scholarship_status_draft_distinct_from_inactive():
    """Pin: draft vs inactive — draft is unpublished WIP (admin sees
    in editor), inactive is published-then-archived (admin sees in
    'archived' tab). A collision would hide WIP work from admins."""
    assert ScholarshipStatus.draft.value != ScholarshipStatus.inactive.value


# ─── FieldType (form builder) ────────────────────────────────────────


def test_field_type_values():
    """Pin: 8 form-field types covering text input, structured input,
    and selection widgets. Member names are UPPERCASE here (deviation
    from system convention)."""
    assert FieldType.TEXT.value == "text"
    assert FieldType.TEXTAREA.value == "textarea"
    assert FieldType.NUMBER.value == "number"
    assert FieldType.EMAIL.value == "email"
    assert FieldType.DATE.value == "date"
    assert FieldType.SELECT.value == "select"
    assert FieldType.CHECKBOX.value == "checkbox"
    assert FieldType.RADIO.value == "radio"
    assert len(list(FieldType)) == 8


def test_field_type_text_vs_textarea_distinct():
    """Pin: TEXT and TEXTAREA distinct. The form renderer chooses
    <input> vs <textarea> based on this — collapsing them would lose
    multi-line UX for descriptions."""
    assert FieldType.TEXT.value != FieldType.TEXTAREA.value


# ─── RosterScheduleStatus ────────────────────────────────────────────


def test_roster_schedule_status_values():
    """Pin: 4 status values. CRITICAL: 'paused' and 'disabled' are
    distinct — paused is temporary (resumable), disabled is admin-
    decommissioned (requires re-enable workflow)."""
    assert RosterScheduleStatus.ACTIVE.value == "active"
    assert RosterScheduleStatus.PAUSED.value == "paused"
    assert RosterScheduleStatus.DISABLED.value == "disabled"
    assert RosterScheduleStatus.ERROR.value == "error"
    assert len(list(RosterScheduleStatus)) == 4


# ─── RosterAuditAction (compliance audit) ────────────────────────────


def test_roster_audit_action_values():
    """Pin: 16 audit action strings. CRITICAL: these are stored in
    compliance audit logs. A rename would orphan historical rows from
    their action category in the admin audit dashboard.

    `RosterAuditAction` is a NATIVE PostgreSQL enum (`rosterauditaction`). If
    this fails because you ADDED a value, you MUST also add an
    `ALTER TYPE rosterauditaction ADD VALUE` Alembic migration (see
    add_item_restore_audit_001.py) — otherwise inserting the new action 500s on
    PostgreSQL (InvalidTextRepresentation); SQLite tests don't catch it."""
    assert RosterAuditAction.CREATE.value == "create"
    assert RosterAuditAction.UPDATE.value == "update"
    assert RosterAuditAction.DELETE.value == "delete"
    assert RosterAuditAction.LOCK.value == "lock"
    assert RosterAuditAction.UNLOCK.value == "unlock"
    assert RosterAuditAction.EXPORT.value == "export"
    assert RosterAuditAction.DOWNLOAD.value == "download"
    assert RosterAuditAction.STUDENT_VERIFY.value == "student_verify"
    assert RosterAuditAction.SCHEDULE_RUN.value == "schedule_run"
    assert RosterAuditAction.MANUAL_RUN.value == "manual_run"
    assert RosterAuditAction.DRY_RUN.value == "dry_run"
    assert RosterAuditAction.STATUS_CHANGE.value == "status_change"
    assert RosterAuditAction.ITEM_ADD.value == "item_add"
    assert RosterAuditAction.ITEM_REMOVE.value == "item_remove"
    assert RosterAuditAction.ITEM_UPDATE.value == "item_update"
    assert RosterAuditAction.ITEM_RESTORE.value == "item_restore"
    assert len(list(RosterAuditAction)) == 16


def test_roster_audit_action_run_types_distinct():
    """Pin: schedule_run, manual_run, and dry_run are 3 distinct values
    — compliance audit filters by these to attribute who ran a roster
    job. A collision would misattribute scheduled jobs to admins."""
    run_values = {
        RosterAuditAction.SCHEDULE_RUN.value,
        RosterAuditAction.MANUAL_RUN.value,
        RosterAuditAction.DRY_RUN.value,
    }
    assert len(run_values) == 3


# ─── RosterAuditLevel ────────────────────────────────────────────────


def test_roster_audit_level_values():
    """Pin: 4 severity levels — info/warning/error/critical. Admin
    alert dashboard filters by these to surface critical issues.

    The RosterAuditLog.is_error() method (covered in wave 6a19)
    returns True for ERROR + CRITICAL — both pinned here."""
    assert RosterAuditLevel.INFO.value == "info"
    assert RosterAuditLevel.WARNING.value == "warning"
    assert RosterAuditLevel.ERROR.value == "error"
    assert RosterAuditLevel.CRITICAL.value == "critical"
    assert len(list(RosterAuditLevel)) == 4


# ─── Cross-enum lowercase invariant ──────────────────────────────────


def test_all_misc_enum_values_lowercase():
    """Pin: per CLAUDE.md §4, all enum values lowercase. UPPERCASE-
    name + lowercase-value pattern is the system convention; any value
    typo'd as uppercase would cause SQLAlchemy LookupError."""
    for enum_cls in (
        ScholarshipStatus,
        FieldType,
        RosterScheduleStatus,
        RosterAuditAction,
        RosterAuditLevel,
    ):
        for member in enum_cls:
            assert (
                member.value == member.value.lower()
            ), f"{enum_cls.__name__}.{member.name} value '{member.value}' is not lowercase"

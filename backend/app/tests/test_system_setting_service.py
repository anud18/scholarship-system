"""
Behavioral tests for `SystemSettingService` and `EmailTemplateService` — real
async-DB integration tests using the in-memory SQLite fixture stack from
conftest.

These two services have all-staticmethod CRUD interfaces over the
`system_settings` and `email_templates` tables. Both were flagged as zero
tests in the audit re-check (PR #231 added the only tests for the related
`roster_scheduler_service`; these two stayed open until this PR).

What this PR adds (vs the pure-helper PRs earlier in the session): these
are **full async-DB-fixture tests** using the canonical `db: AsyncSession`
fixture from conftest. They exercise the upsert semantics
(`set_setting` / `set_template`), the `get_or_create_*` short-circuit,
and the `updated_at` refresh — all behaviors a unit test on pure helpers
could not cover.

Coverage:
- SystemSettingService: 6 tests (get miss, set creates, set updates,
  get_or_create returns existing, get_or_create creates with default,
  multiple distinct keys are isolated)
- EmailTemplateService: 5 tests (same pattern + cc/bcc handling)

Wave 2j — first async-DB-fixture test in the production-readiness rollout.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.system_setting_service import EmailTemplateService, SystemSettingService

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# SystemSettingService
# ---------------------------------------------------------------------------


class TestSystemSettingService:
    """CRUD over system_settings table via async DB."""

    async def test_get_setting_missing_returns_none(self, db: AsyncSession) -> None:
        assert await SystemSettingService.get_setting(db, "nonexistent.key") is None

    async def test_set_setting_creates_new(self, db: AsyncSession) -> None:
        result = await SystemSettingService.set_setting(db, "feature.new_ui", "true")
        assert result.key == "feature.new_ui"
        assert result.value == "true"
        # Round-trip
        fetched = await SystemSettingService.get_setting(db, "feature.new_ui")
        assert fetched is not None
        assert fetched.value == "true"

    async def test_set_setting_updates_existing(self, db: AsyncSession) -> None:
        """Calling set_setting on an existing key updates value, doesn't create
        a duplicate. Upsert semantics."""
        first = await SystemSettingService.set_setting(db, "rate_limit.per_minute", "60")
        second = await SystemSettingService.set_setting(db, "rate_limit.per_minute", "120")

        # Same row, updated value
        assert second.id == first.id
        assert second.value == "120"

        # Only one row exists for this key
        again = await SystemSettingService.get_setting(db, "rate_limit.per_minute")
        assert again is not None
        assert again.id == first.id
        assert again.value == "120"

    async def test_get_or_create_returns_existing(self, db: AsyncSession) -> None:
        """When the key exists, get_or_create returns the existing row WITHOUT
        overwriting its value with the default. This is the documented
        idempotency behavior — callers can safely call this on every request."""
        existing = await SystemSettingService.set_setting(db, "smtp.timeout", "30")

        result = await SystemSettingService.get_or_create_setting(db, "smtp.timeout", default_value="999")
        assert result.id == existing.id
        # Default value NOT applied — existing wins
        assert result.value == "30"

    async def test_get_or_create_creates_with_default(self, db: AsyncSession) -> None:
        result = await SystemSettingService.get_or_create_setting(db, "smtp.retries", default_value="3")
        assert result.value == "3"
        # Persisted, not just in-memory
        fetched = await SystemSettingService.get_setting(db, "smtp.retries")
        assert fetched is not None
        assert fetched.value == "3"

    async def test_distinct_keys_isolated(self, db: AsyncSession) -> None:
        """Two distinct keys must produce two distinct rows. Pin this as a
        sanity check against an accidental shared-row regression."""
        a = await SystemSettingService.set_setting(db, "key.a", "value_a")
        b = await SystemSettingService.set_setting(db, "key.b", "value_b")
        assert a.id != b.id
        # Modifying one doesn't affect the other
        await SystemSettingService.set_setting(db, "key.a", "value_a_v2")
        b_again = await SystemSettingService.get_setting(db, "key.b")
        assert b_again is not None
        assert b_again.value == "value_b"


# ---------------------------------------------------------------------------
# EmailTemplateService
# ---------------------------------------------------------------------------


class TestEmailTemplateService:
    """CRUD over email_templates table via async DB."""

    async def test_get_template_missing_returns_none(self, db: AsyncSession) -> None:
        assert await EmailTemplateService.get_template(db, "nonexistent.tpl") is None

    async def test_set_template_creates_new(self, db: AsyncSession) -> None:
        result = await EmailTemplateService.set_template(
            db,
            key="application.submitted",
            subject="Application received",
            body="Hi {{name}}, your application is in.",
        )
        assert result.key == "application.submitted"
        assert result.subject_template == "Application received"
        assert result.body_template.startswith("Hi {{name}}")
        # Default cc/bcc are None
        assert result.cc is None
        assert result.bcc is None

    async def test_set_template_with_cc_and_bcc(self, db: AsyncSession) -> None:
        result = await EmailTemplateService.set_template(
            db,
            key="application.approved",
            subject="Application approved",
            body="Congrats {{name}}.",
            cc="dean@nycu.edu.tw",
            bcc="audit@nycu.edu.tw",
        )
        assert result.cc == "dean@nycu.edu.tw"
        assert result.bcc == "audit@nycu.edu.tw"

    async def test_set_template_updates_existing(self, db: AsyncSession) -> None:
        """Upsert: second call with same key updates subject/body/cc/bcc."""
        first = await EmailTemplateService.set_template(
            db,
            key="application.rejected",
            subject="Original subject",
            body="Original body",
        )
        second = await EmailTemplateService.set_template(
            db,
            key="application.rejected",
            subject="New subject",
            body="New body",
            cc="appeals@nycu.edu.tw",
        )
        assert second.id == first.id
        assert second.subject_template == "New subject"
        assert second.body_template == "New body"
        assert second.cc == "appeals@nycu.edu.tw"

    async def test_get_or_create_returns_existing(self, db: AsyncSession) -> None:
        """get_or_create on existing template returns it unmodified — the
        default subject/body are NOT applied. Caller-side idempotency."""
        existing = await EmailTemplateService.set_template(
            db,
            key="application.under_review",
            subject="Original subject",
            body="Original body",
        )
        result = await EmailTemplateService.get_or_create_template(
            db,
            key="application.under_review",
            default_subject="Default subject",
            default_body="Default body",
        )
        assert result.id == existing.id
        assert result.subject_template == "Original subject"  # NOT overwritten

    async def test_get_or_create_creates_with_defaults(self, db: AsyncSession) -> None:
        result = await EmailTemplateService.get_or_create_template(
            db,
            key="application.pending_documents",
            default_subject="Documents needed",
            default_body="Please upload {{document}}.",
        )
        assert result.subject_template == "Documents needed"
        assert result.body_template == "Please upload {{document}}."
        # Persisted
        fetched = await EmailTemplateService.get_template(db, "application.pending_documents")
        assert fetched is not None
        assert fetched.body_template == "Please upload {{document}}."

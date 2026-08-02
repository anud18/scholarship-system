"""Tests for the third email trigger point: 學院送出排名 → 寄信給學院.

The college finalizes ("送出") its ranking and the reviewers of that college get
a confirmation. Unlike the other two trigger points this one is ranking-scoped,
so the recipient query binds ``{college_code}`` rather than ``{application_id}``.

Contract pinned here:
- The trigger emits the ``college_review_submitted`` event with a context that
  carries every placeholder the seeded rule and templates reference.
- The seeded condition_query survives the read-only SQL guard and resolves to
  exactly the college users of the ranking's own college.
- The template key maps to the React template and the 學院 email category.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed_scholarship_configs import (
    COLLEGE_RANKING_SUBMITTED_BODY,
    COLLEGE_RANKING_SUBMITTED_CONDITION_QUERY,
    COLLEGE_RANKING_SUBMITTED_SUBJECT,
    COLLEGE_RANKING_SUBMITTED_TEMPLATE_KEY,
)
from app.models.email_management import EmailAutomationRule, EmailCategory, TriggerEvent
from app.models.user import User, UserRole, UserType
from app.services.email_automation_service import email_automation_service

RANKING_DATA = {
    "ranking_id": 42,
    "college_code": "C",
    "college_name": "資訊學院",
    "ranking_name": "114-1 博士生獎學金排名",
    "scholarship_type": "博士生獎學金",
    "scholarship_type_id": 7,
    "sub_type_code": "nstc",
    "academic_year": "114",
    "semester": "first",
    "total_applications": "12",
    "finalized_by": "學院承辦人",
    "finalized_at": "2026-08-03 10:00",
}


async def _seed_user(
    db: AsyncSession,
    *,
    nycu_id: str,
    role: UserRole,
    college_code: str | None,
    email: str | None = "unset",
) -> User:
    user = User(
        nycu_id=nycu_id,
        name=nycu_id,
        email=f"{nycu_id}@u.edu" if email == "unset" else email,
        user_type=UserType.employee if role != UserRole.student else UserType.student,
        role=role,
        college_code=college_code,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest.mark.asyncio
async def test_trigger_emits_college_review_submitted_with_full_context(db: AsyncSession, monkeypatch):
    captured = {}

    async def _capture(_db, trigger_event, context):
        captured["event"] = trigger_event
        captured["context"] = context

    monkeypatch.setattr(email_automation_service, "process_trigger", _capture)

    await email_automation_service.trigger_college_ranking_submitted(db=db, ranking_data=RANKING_DATA)

    assert captured["event"] == "college_review_submitted"
    context = captured["context"]
    assert context["ranking_id"] == 42
    assert context["college_code"] == "C"
    assert context["college_name"] == "資訊學院"
    assert context["scholarship_name"] == "博士生獎學金"  # alias used by the templates
    assert context["system_url"]


@pytest.mark.asyncio
async def test_seeded_templates_render_against_the_trigger_context(db: AsyncSession, monkeypatch):
    """Every {placeholder} in the seeded subject/body must exist in the context.

    _schedule_automated_email calls ``.format(**context)`` on both, so a missing
    key is a KeyError at send time rather than a bad-looking email.
    """
    captured = {}

    async def _capture(_db, trigger_event, context):
        captured["context"] = context

    monkeypatch.setattr(email_automation_service, "process_trigger", _capture)
    await email_automation_service.trigger_college_ranking_submitted(db=db, ranking_data=RANKING_DATA)

    context = captured["context"]
    subject = COLLEGE_RANKING_SUBMITTED_SUBJECT.format(**context)
    body = COLLEGE_RANKING_SUBMITTED_BODY.format(**context)

    assert "博士生獎學金" in subject
    assert "資訊學院" in body
    assert "nstc" in body


@pytest.mark.asyncio
async def test_condition_query_resolves_only_that_colleges_reviewers(db: AsyncSession):
    target = await _seed_user(db, nycu_id="col_c1", role=UserRole.college, college_code="C")
    also_target = await _seed_user(db, nycu_id="col_c2", role=UserRole.college, college_code="C")
    await _seed_user(db, nycu_id="col_e1", role=UserRole.college, college_code="E")  # other college
    await _seed_user(db, nycu_id="prof_c", role=UserRole.professor, college_code="C")  # wrong role
    await _seed_user(db, nycu_id="col_noemail", role=UserRole.college, college_code="C", email=None)

    rule = EmailAutomationRule(
        name="學院排名送出通知",
        trigger_event=TriggerEvent.college_review_submitted,
        template_key=COLLEGE_RANKING_SUBMITTED_TEMPLATE_KEY,
        condition_query=COLLEGE_RANKING_SUBMITTED_CONDITION_QUERY,
        delay_hours=0,
        is_active=True,
    )

    recipients = await email_automation_service._get_recipients(db, rule, {"college_code": "C"})

    assert sorted(r["email"] for r in recipients) == sorted([target.email, also_target.email])


@pytest.mark.asyncio
async def test_global_admin_ranking_resolves_to_no_recipients(db: AsyncSession):
    """A ranking with college_code NULL must not fan out to every college."""
    await _seed_user(db, nycu_id="col_any", role=UserRole.college, college_code="C")

    rule = EmailAutomationRule(
        name="學院排名送出通知",
        trigger_event=TriggerEvent.college_review_submitted,
        template_key=COLLEGE_RANKING_SUBMITTED_TEMPLATE_KEY,
        condition_query=COLLEGE_RANKING_SUBMITTED_CONDITION_QUERY,
        delay_hours=0,
        is_active=True,
    )

    recipients = await email_automation_service._get_recipients(db, rule, {"college_code": None})

    assert recipients == []


def test_template_key_maps_to_react_template_and_college_category():
    assert (
        email_automation_service._get_react_email_template_name(COLLEGE_RANKING_SUBMITTED_TEMPLATE_KEY)
        == "college-ranking-submitted"
    )
    assert (
        email_automation_service._get_email_category_from_template_key(COLLEGE_RANKING_SUBMITTED_TEMPLATE_KEY)
        == EmailCategory.review_college
    )

"""Endpoint pin: GET /distribution-diff + POST /reconcile enforce admin, wrap the
service in ApiResponse, and map service errors to HTTP 400/403. Called as
functions with a sync session to avoid the async/sync test-DB split and Redis."""

import contextlib

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import payment_rosters as ep
from app.models.payment_roster import RosterStatus  # noqa: F401  (kept for clarity / future use)
from app.models.user import User, UserRole, UserType
from app.schemas.payment_roster import ReconcileRequest
from app.tests.test_roster_distribution_reconcile_service import (
    _admin,
    _application,
    _config,
    _ranking,
    _ranking_item,
    _roster,
    _scholarship,
    _student,
)


def _build_scenario(db_sync):
    """admin + a roster with NO item for app_b, where app_b is allocated in the
    distribution → app_b is a to_add candidate."""
    admin = _admin(db_sync, nycu_id="ep_admin")
    sch = _scholarship(db_sync, code="ep_sch")
    config = _config(db_sync, sch)
    ub = _student(db_sync, "ep_b")
    app_b = _application(db_sync, ub, sch, config, app_id="APP-EP-B", std_code="333B")
    ranking = _ranking(db_sync, sch)
    _ranking_item(db_sync, ranking, app_b, rank=1)
    roster = _roster(db_sync, config, admin, code="ROSTER-EP-1")
    db_sync.commit()
    return admin, roster, app_b


def _nonadmin(db_sync):
    u = User(
        nycu_id="ep_student_u",
        email="ep_student_u@nycu.edu.tw",
        name="S",
        role=UserRole.student,
        user_type=UserType.student,
    )
    db_sync.add(u)
    db_sync.flush()
    return u


@contextlib.contextmanager
def _passthrough_lock(*args, **kwargs):
    yield "test-token"


def test_distribution_diff_endpoint_returns_apiresponse(db_sync):
    admin, roster, app_b = _build_scenario(db_sync)
    resp = ep.get_distribution_diff(roster_id=roster.id, db=db_sync, current_user=admin)
    assert resp["success"] is True
    add_ids = [e["application_id"] for e in resp["data"]["to_add"]]
    assert app_b.id in add_ids


def test_distribution_diff_endpoint_requires_admin(db_sync):
    admin, roster, app_b = _build_scenario(db_sync)
    student = _nonadmin(db_sync)
    with pytest.raises(HTTPException) as exc:
        ep.get_distribution_diff(roster_id=roster.id, db=db_sync, current_user=student)
    assert exc.value.status_code == 403


def test_reconcile_endpoint_adds_member(db_sync, monkeypatch):
    monkeypatch.setattr(ep, "with_lock_sync", _passthrough_lock)
    admin, roster, app_b = _build_scenario(db_sync)
    req = ReconcileRequest(add_application_ids=[app_b.id], remove_item_ids=[], reason="sync")
    resp = ep.reconcile_roster_endpoint(roster_id=roster.id, request=req, db=db_sync, current_user=admin)
    assert resp["success"] is True
    assert len(resp["data"]["added"]) == 1
    assert resp["data"]["excel_stale"] is True


def test_reconcile_endpoint_maps_value_error_to_400(db_sync, monkeypatch):
    monkeypatch.setattr(ep, "with_lock_sync", _passthrough_lock)
    admin, roster, app_b = _build_scenario(db_sync)
    req = ReconcileRequest(add_application_ids=[999999], remove_item_ids=[], reason=None)
    with pytest.raises(HTTPException) as exc:
        ep.reconcile_roster_endpoint(roster_id=roster.id, request=req, db=db_sync, current_user=admin)
    assert exc.value.status_code == 400

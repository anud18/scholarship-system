"""Endpoint pin: POST /payment-rosters/{roster_id}/regenerate enforces admin,
wraps the service in the {success,message,data} shape, and maps service errors
to HTTP 400/404. Called as functions with a sync session to avoid the
async/sync test-DB split and Redis.

The route also fills a pre-existing hole: the frontend already shipped a
`regenerateRoster()` client pointing at this path with no backend behind it.
"""

import contextlib

import pytest
from fastapi import HTTPException
from unittest.mock import patch

from app.api.v1.endpoints import payment_rosters as ep
from app.api.v1.endpoints.payment_rosters import _build_regeneration_message
from app.models.payment_roster import PaymentRosterItem, RosterStatus, StudentVerificationStatus
from app.schemas.payment_roster import RegenerateRosterRequest
from app.tests.test_roster_regeneration_service import (
    EXPORT_TARGET,
    _admin,
    _allocate,
    _application,
    _config,
    _generate,
    _ranking,
    _student,
)
from app.models.scholarship import ScholarshipType


@contextlib.contextmanager
def _passthrough_lock(*args, **kwargs):
    yield "test-token"


def _build_scenario(db_sync):
    admin = _admin(db_sync)
    sch = ScholarshipType(code="ep_regen", name="EpRegen", description="x")
    db_sync.add(sch)
    db_sync.flush()
    config = _config(db_sync, sch, code="EPREGEN-115")
    ranking = _ranking(db_sync, sch)
    app = _application(db_sync, _student(db_sync, "ep_regen_a"), sch, config, app_id="APP-EPR-A", std_code="115A")
    _allocate(db_sync, ranking, app, config)
    db_sync.commit()

    roster = _generate(db_sync, sch, admin)
    db_sync.commit()
    return admin, roster


def test_regenerate_endpoint_returns_api_response(db_sync, monkeypatch):
    monkeypatch.setattr(ep, "with_lock_sync", _passthrough_lock)
    admin, roster = _build_scenario(db_sync)

    with patch(EXPORT_TARGET):
        resp = ep.regenerate_roster_endpoint(roster_id=roster.id, request=None, db=db_sync, current_user=admin)

    assert resp["success"] is True
    assert resp["data"]["roster_id"] == roster.id
    assert resp["data"]["rebuilt_items"] == 1
    assert resp["data"]["preserved_exclusions"] == 0
    assert resp["data"]["status"] == RosterStatus.COMPLETED.value
    assert resp["data"]["excel_stale"] is False


def test_regenerate_endpoint_verification_override_is_per_run_not_sticky(db_sync, monkeypatch):
    """「同時重新驗證學籍」is a one-off. It must NOT be written back to the roster —
    otherwise ticking it once latches slow SIS verification on forever and
    unticking it next time would silently do nothing."""
    monkeypatch.setattr(ep, "with_lock_sync", _passthrough_lock)
    admin, roster = _build_scenario(db_sync)
    assert roster.student_verification_enabled is False

    req = RegenerateRosterRequest(student_verification_enabled=True)
    with patch(EXPORT_TARGET), patch("app.services.roster_service.StudentVerificationService") as svs:
        # Return the ENUM member, not the "verified" string — _create_roster_item
        # compares against StudentVerificationStatus.VERIFIED, so a string would
        # silently exclude the student and mask what this test is asserting.
        svs.return_value.verify_student.return_value = {
            "status": StudentVerificationStatus.VERIFIED,
            "student_info": {},
        }
        resp = ep.regenerate_roster_endpoint(roster_id=roster.id, request=req, db=db_sync, current_user=admin)

    assert resp["success"] is True
    # The override took effect for this run...
    assert svs.return_value.verify_student.called
    assert resp["data"]["newly_excluded"] == 0
    # ...but the roster's own setting is untouched, so the next run is fast again.
    assert roster.student_verification_enabled is False


def test_regenerate_endpoint_requires_admin(db_sync, monkeypatch):
    monkeypatch.setattr(ep, "with_lock_sync", _passthrough_lock)
    _admin_user, roster = _build_scenario(db_sync)
    student = _student(db_sync, "ep_regen_outsider")

    with pytest.raises(HTTPException) as exc:
        ep.regenerate_roster_endpoint(roster_id=roster.id, request=None, db=db_sync, current_user=student)
    assert exc.value.status_code == 403


def test_regenerate_endpoint_maps_missing_roster_to_404(db_sync, monkeypatch):
    monkeypatch.setattr(ep, "with_lock_sync", _passthrough_lock)
    admin, _roster = _build_scenario(db_sync)

    with pytest.raises(HTTPException) as exc:
        ep.regenerate_roster_endpoint(roster_id=999999, request=None, db=db_sync, current_user=admin)
    assert exc.value.status_code == 404


def test_regenerate_endpoint_maps_locked_roster_to_400(db_sync, monkeypatch):
    """A locked roster must fail loudly with an actionable message, and its
    items must survive the refused call."""
    monkeypatch.setattr(ep, "with_lock_sync", _passthrough_lock)
    admin, roster = _build_scenario(db_sync)
    roster.status = RosterStatus.LOCKED
    db_sync.commit()

    with pytest.raises(HTTPException) as exc:
        ep.regenerate_roster_endpoint(roster_id=roster.id, request=None, db=db_sync, current_user=admin)
    assert exc.value.status_code == 400
    assert "解鎖" in exc.value.detail
    assert db_sync.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster.id).count() == 1


def test_regenerate_endpoint_maps_lock_busy_to_409(db_sync, monkeypatch):
    admin, roster = _build_scenario(db_sync)

    @contextlib.contextmanager
    def _busy(*args, **kwargs):
        raise ep.LockBusy("roster:regenerate:1")
        yield  # pragma: no cover

    monkeypatch.setattr(ep, "with_lock_sync", _busy)
    with pytest.raises(HTTPException) as exc:
        ep.regenerate_roster_endpoint(roster_id=roster.id, request=None, db=db_sync, current_user=admin)
    assert exc.value.status_code == 409


def test_build_regeneration_message_names_every_way_a_student_leaves():
    assert _build_regeneration_message(5, 0, 0, 0, 0) == "已重新生成造冊：5 筆明細"

    preserved = _build_regeneration_message(5, 2, 0, 0, 0)
    assert "保留 2 筆人為排除" in preserved

    newly_excluded = _build_regeneration_message(5, 0, 3, 0, 0)
    assert "3 筆先前納入的明細依當下資料改為排除" in newly_excluded

    dropped = _build_regeneration_message(5, 0, 0, 4, 0)
    assert "4 位先前納入的學生已不在分發名單中" in dropped

    failed = _build_regeneration_message(4, 0, 0, 0, 1)
    assert "1 筆申請資料不全" in failed

    everything = _build_regeneration_message(4, 2, 3, 4, 1)
    assert "保留 2 筆人為排除" in everything
    assert "3 筆先前納入的明細依當下資料改為排除" in everything
    assert "4 位先前納入的學生已不在分發名單中" in everything
    assert "1 筆申請資料不全" in everything

"""
HTTP-layer tests for "several draft rankings, finalize keeps one"
(app/api/v1/endpoints/college_review/ranking_management.py).

A college may keep several DRAFT rankings per scope (scholarship type, sub-type,
academic year, semester, college). 確認排名 (finalize) deletes the scope's other
drafts and no new ranking can be created while the finalized (or a distributed)
ranking exists; 解除鎖定 re-allows it. 同步申請名單 (POST /rankings/{id}/sync)
adds pending applications and removes stale ones, append-only once distributed.

Authentication is simulated by overriding `get_current_user` with real DB-backed
users, so require_college and assert_can_manage_ranking run unmodified. SQLite
does not enforce foreign keys, so deletions are checked with explicit row counts.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models.application import ApplicationStatus
from app.models.audit_log import AuditAction, AuditLog
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.user import UserRole
from app.tests.ranking_scope_helpers import (
    SEMESTER,
    SUB_TYPE,
    YEAR,
    add_application,
    add_payment_roster,
    count_items,
    count_rankings,
    final_positions,
    first_item,
    insert_ranking,
    item_positions,
    make_config,
    make_expired_config,
    make_scholarship,
    make_user,
    ranking_exists,
)

RANKINGS_URL = "/api/v1/college-review/rankings"

# Ways a ranking becomes "settled" (distribution state that must never be deleted).
SETTLED_BY_DISTRIBUTION = ["distribution_executed", "allocated_item", "revoked_item", "rejected_item"]
# ...plus a payment roster referencing it, which also blocks deletion.
UNDELETABLE = SETTLED_BY_DISTRIBUTION + ["roster"]


@pytest_asyncio.fixture
async def login():
    """Authenticate the test client as a given User via dependency override."""
    from app.core.security import get_current_user
    from app.main import app

    def _login(user) -> None:
        async def _override():
            return user

        app.dependency_overrides[get_current_user] = _override

    yield _login
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def users(db):
    return {
        "eng": await make_user(db, "md_eng1", college_code="ENG"),
        "eng2": await make_user(db, "md_eng2", college_code="ENG"),
        "sci": await make_user(db, "md_sci1", college_code="SCI"),
        "admin": await make_user(db, "md_admin", role=UserRole.admin),
    }


@pytest_asyncio.fixture
async def scholarship(db):
    return await make_scholarship(db, "multi_draft_scholarship")


def _payload(scholarship_id: int, **overrides) -> dict:
    return {
        "scholarship_type_id": scholarship_id,
        "sub_type_code": SUB_TYPE,
        "academic_year": YEAR,
        "semester": SEMESTER,
        **overrides,
    }


async def _create(client, scholarship_id: int, **overrides) -> int:
    response = await client.post(RANKINGS_URL, json=_payload(scholarship_id, **overrides))
    assert response.status_code == 200, response.text
    return response.json()["data"]["id"]


async def _detail(client, ranking_id: int) -> dict:
    response = await client.get(f"{RANKINGS_URL}/{ranking_id}")
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _reverse_order(client, db, ranking_id: int) -> None:
    """PUT /rankings/{id}/order with the ranking's current order reversed."""
    items = (
        (await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.ranking_id == ranking_id)))
        .scalars()
        .all()
    )
    last = len(items) + 1
    new_order = [{"item_id": item.id, "position": last - item.rank_position} for item in items]
    response = await client.put(f"{RANKINGS_URL}/{ranking_id}/order", json=new_order)
    assert response.status_code == 200, response.text


async def _is_finalized(db, ranking_id: int) -> bool:
    return bool(await db.scalar(select(CollegeRanking.is_finalized).where(CollegeRanking.id == ranking_id)))


async def _settle(db, ranking_id: int, how: str, *, created_by: int, scholarship_id: int) -> None:
    """Give a ranking (with at least one item) the state that protects it from deletion."""
    if how == "distribution_executed":
        ranking = await db.get(CollegeRanking, ranking_id)
        ranking.distribution_executed = True
    elif how == "allocated_item":
        item = await first_item(db, ranking_id)
        item.is_allocated = True
        item.allocated_sub_type = SUB_TYPE
        item.status = "allocated"
    elif how == "revoked_item":
        # 撤銷/停發 clears is_allocated but keeps the slot for 復發.
        item = await first_item(db, ranking_id)
        item.allocated_sub_type = SUB_TYPE
    elif how == "rejected_item":
        # manual distribution finalize() marks unallocated items rejected.
        item = await first_item(db, ranking_id)
        item.status = "rejected"
    elif how == "roster":
        config = await make_config(db, scholarship_id, code=f"roster_cfg_{ranking_id}", academic_year=100)
        await add_payment_roster(db, ranking_id=ranking_id, config_id=config.id, created_by=created_by)
    else:  # pragma: no cover - guards a typo in a parametrize list
        raise AssertionError(f"unknown settle mode {how}")
    await db.commit()


async def _audit_rows(db, action: str):
    result = await db.execute(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id))
    return list(result.scalars().all())


@pytest.mark.api
class TestCreateAlwaysAddsADraft:
    """POST /rankings always creates a NEW draft unless the scope is locked or distributed."""

    async def test_second_create_returns_a_new_draft(self, client, login, db, users, scholarship):
        await add_application(db, scholarship.id, "a1")
        login(users["eng"])

        first = await client.post(RANKINGS_URL, json=_payload(scholarship.id))
        second = await client.post(RANKINGS_URL, json=_payload(scholarship.id, ranking_name="B 版本"))
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text

        first_body, second_body = first.json(), second.json()
        assert first_body["message"] == second_body["message"] == "Ranking created successfully"
        first_data, second_data = first_body["data"], second_body["data"]
        assert first_data["id"] != second_data["id"]
        assert second_data["ranking_name"] == "B 版本"
        for data in (first_data, second_data):
            assert data["is_finalized"] is False
            assert data["total_applications"] == 1
            assert "reused" not in data
            assert "added_application_count" not in data

        assert await count_rankings(db, "ENG") == 2
        assert await count_items(db, first_data["id"]) == 1
        assert await count_items(db, second_data["id"]) == 1

    async def test_every_reviewer_of_the_college_sees_all_drafts_in_id_order(
        self, client, login, db, users, scholarship
    ):
        login(users["eng"])
        first_id = await _create(client, scholarship.id)
        login(users["eng2"])
        second_id = await _create(client, scholarship.id)

        for reviewer in ("eng", "eng2"):
            login(users[reviewer])
            listing = await client.get(RANKINGS_URL, params={"academic_year": YEAR, "semester": SEMESTER})
            assert listing.status_code == 200, listing.text
            rows = listing.json()["data"]
            assert [row["id"] for row in rows] == [first_id, second_id]
            assert {row["college_code"] for row in rows} == {"ENG"}

        login(users["sci"])
        listing = await client.get(RANKINGS_URL)
        assert listing.json()["data"] == []

    async def test_create_409_while_scope_holds_a_finalized_ranking(self, client, login, db, users, scholarship):
        await insert_ranking(db, scholarship.id, created_by=users["eng"].id, is_finalized=True, name="已確認版")

        login(users["eng"])
        response = await client.post(RANKINGS_URL, json=_payload(scholarship.id))
        assert response.status_code == 409, response.text
        detail = response.json()["message"]
        assert "已確認版" in detail
        assert "解除鎖定" in detail
        assert await count_rankings(db, "ENG") == 1

    @pytest.mark.parametrize("how", ["distribution_executed", "allocated_item", "revoked_item"])
    async def test_create_409_while_scope_holds_a_distributed_ranking(self, client, login, db, users, scholarship, how):
        application = await add_application(db, scholarship.id, "a1")
        ranking = await insert_ranking(
            db, scholarship.id, created_by=users["eng"].id, application_ids=[application.id], name="分發版"
        )
        await _settle(db, ranking.id, how, created_by=users["eng"].id, scholarship_id=scholarship.id)

        login(users["eng"])
        response = await client.post(RANKINGS_URL, json=_payload(scholarship.id))
        assert response.status_code == 409, response.text
        detail = response.json()["message"]
        assert "分發版" in detail
        assert "已執行分發" in detail
        assert await count_rankings(db, "ENG") == 1

    async def test_finalized_ranking_blocks_only_its_own_scope(self, client, login, db, users, scholarship):
        await insert_ranking(db, scholarship.id, created_by=users["eng"].id, is_finalized=True)

        login(users["eng"])
        await _create(client, scholarship.id, sub_type_code="moe_1w")
        await _create(client, scholarship.id, semester="second")
        await _create(client, scholarship.id, academic_year=YEAR - 1)
        blocked = await client.post(RANKINGS_URL, json=_payload(scholarship.id))
        assert blocked.status_code == 409, blocked.text

        login(users["sci"])
        await _create(client, scholarship.id)

        assert await count_rankings(db, "ENG") == 4
        assert await count_rankings(db, "SCI") == 1

    async def test_create_allowed_again_after_unfinalize(self, client, login, db, users, scholarship):
        login(users["eng"])
        ranking_id = await _create(client, scholarship.id)
        assert (await client.post(f"{RANKINGS_URL}/{ranking_id}/finalize")).status_code == 200

        blocked = await client.post(RANKINGS_URL, json=_payload(scholarship.id))
        assert blocked.status_code == 409, blocked.text

        assert (await client.post(f"{RANKINGS_URL}/{ranking_id}/unfinalize")).status_code == 200
        new_id = await _create(client, scholarship.id)
        assert new_id != ranking_id
        assert await count_rankings(db, "ENG") == 2

    @pytest.mark.parametrize("stored, requested", [(None, "yearly"), ("yearly", None)])
    async def test_null_and_legacy_yearly_semester_are_one_scope(
        self, client, login, db, users, scholarship, stored, requested
    ):
        await insert_ranking(
            db, scholarship.id, created_by=users["eng"].id, sub_type_code="default", semester=stored, is_finalized=True
        )

        login(users["eng"])
        response = await client.post(
            RANKINGS_URL, json=_payload(scholarship.id, sub_type_code="default", semester=requested)
        )
        assert response.status_code == 409, response.text


@pytest.mark.api
class TestFinalizeKeepsOneRanking:
    """POST /rankings/{id}/finalize deletes the scope's other drafts (and only those)."""

    async def test_finalize_deletes_same_scope_drafts_and_their_items(self, client, login, db, users, scholarship):
        eng_id = users["eng"].id
        apps = [await add_application(db, scholarship.id, f"a{n}", order=n) for n in (1, 2)]
        sci_app = await add_application(db, scholarship.id, "s1", college_code="SCI")

        login(users["eng"])
        draft_ids = [await _create(client, scholarship.id) for _ in range(3)]
        doomed = [draft_ids[0], draft_ids[2]]
        target = draft_ids[1]

        # Rankings of other scopes must survive untouched.
        other_scopes = [
            await insert_ranking(
                db, scholarship.id, created_by=users["sci"].id, college_code="SCI", application_ids=[sci_app.id]
            ),
            await insert_ranking(
                db, scholarship.id, created_by=eng_id, sub_type_code="moe_1w", application_ids=[apps[0].id]
            ),
            await insert_ranking(
                db, scholarship.id, created_by=eng_id, semester="second", application_ids=[apps[0].id]
            ),
            await insert_ranking(
                db, scholarship.id, created_by=eng_id, academic_year=YEAR - 1, application_ids=[apps[0].id]
            ),
            await insert_ranking(
                db, scholarship.id, created_by=users["admin"].id, college_code=None, application_ids=[apps[0].id]
            ),
        ]
        other_ids = [ranking.id for ranking in other_scopes]

        response = await client.post(f"{RANKINGS_URL}/{target}/finalize")
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["is_finalized"] is True
        assert data["deleted_ranking_ids"] == doomed
        assert data["deleted_ranking_count"] == 2

        for ranking_id in doomed:
            assert not await ranking_exists(db, ranking_id)
            assert await count_items(db, ranking_id) == 0
        assert await _is_finalized(db, target)
        assert await count_items(db, target) == 2
        for ranking_id in other_ids:
            assert await ranking_exists(db, ranking_id)
            assert await count_items(db, ranking_id) == 1
            assert not await _is_finalized(db, ranking_id)

        listing = await client.get(RANKINGS_URL)
        assert {row["id"] for row in listing.json()["data"]} == {target, *other_ids[1:4]}

    async def test_finalize_audits_every_deleted_draft_with_its_order(self, client, login, db, users, scholarship):
        # A deleted draft's order must stay reconstructable (G8 #970).
        apps = [await add_application(db, scholarship.id, f"a{n}", order=n) for n in (1, 2)]

        login(users["eng"])
        draft_ids = [await _create(client, scholarship.id) for _ in range(3)]
        doomed = [draft_ids[0], draft_ids[2]]
        target = draft_ids[1]
        await _reverse_order(client, db, draft_ids[2])
        expected_orders = [
            {str(apps[0].id): 1, str(apps[1].id): 2},
            {str(apps[0].id): 2, str(apps[1].id): 1},
        ]

        response = await client.post(f"{RANKINGS_URL}/{target}/finalize")
        assert response.status_code == 200, response.text

        deletions = await _audit_rows(db, AuditAction.delete_ranking.value)
        assert [row.resource_id for row in deletions] == [str(ranking_id) for ranking_id in doomed]
        for row, expected_order in zip(deletions, expected_orders):
            assert row.resource_type == "ranking"
            assert f"superseded when ranking {target} was finalized" in row.description
            assert row.old_values["rank_positions"] == expected_order
            assert row.old_values["total_applications"] == 2
        [finalize_row] = await _audit_rows(db, AuditAction.finalize_ranking.value)
        assert finalize_row.resource_id == str(target)
        assert finalize_row.new_values["deleted_ranking_ids"] == doomed

    @pytest.mark.parametrize("how", UNDELETABLE)
    async def test_finalize_409_when_a_sibling_cannot_be_deleted(self, client, login, db, users, scholarship, how):
        application = await add_application(db, scholarship.id, "a1")
        sibling = await insert_ranking(
            db, scholarship.id, created_by=users["eng"].id, application_ids=[application.id], name="已分發排名"
        )
        target = await insert_ranking(db, scholarship.id, created_by=users["eng"].id, application_ids=[application.id])
        sibling_id, target_id = sibling.id, target.id
        await _settle(db, sibling_id, how, created_by=users["eng"].id, scholarship_id=scholarship.id)

        login(users["eng"])
        response = await client.post(f"{RANKINGS_URL}/{target_id}/finalize")
        assert response.status_code == 409, response.text
        detail = response.json()["message"]
        assert "已分發排名" in detail
        assert "已執行分發或已用於造冊" in detail

        # Nothing deleted, the target stays a draft and no finalize was audited.
        assert await ranking_exists(db, sibling_id)
        assert await count_items(db, sibling_id) == 1
        assert await count_items(db, target_id) == 1
        assert not await _is_finalized(db, target_id)
        assert await _audit_rows(db, AuditAction.finalize_ranking.value) == []

    async def test_finalize_409_while_another_ranking_of_the_scope_is_finalized(
        self, client, login, db, users, scholarship
    ):
        locked = await insert_ranking(db, scholarship.id, created_by=users["eng"].id, is_finalized=True, name="鎖定版")
        draft = await insert_ranking(db, scholarship.id, created_by=users["eng"].id)
        locked_id, draft_id = locked.id, draft.id

        login(users["eng"])
        response = await client.post(f"{RANKINGS_URL}/{draft_id}/finalize")
        assert response.status_code == 409, response.text
        assert "鎖定版" in response.json()["message"]
        assert await ranking_exists(db, draft_id)
        assert not await _is_finalized(db, draft_id)
        assert await _is_finalized(db, locked_id)

    async def test_finalize_mirrors_the_confirmed_order_into_final_ranking_position(
        self, client, login, db, users, scholarship
    ):
        apps = [await add_application(db, scholarship.id, f"a{n}", order=n) for n in (1, 2)]
        app_ids = [application.id for application in apps]

        login(users["eng"])
        reordered_id = await _create(client, scholarship.id)
        confirmed_id = await _create(client, scholarship.id)
        assert await item_positions(db, confirmed_id) == [(app_ids[0], 1), (app_ids[1], 2)]

        # Reordering the other draft writes ITS order into final_ranking_position.
        await _reverse_order(client, db, reordered_id)
        assert await final_positions(db, app_ids) == {app_ids[0]: 2, app_ids[1]: 1}

        response = await client.post(f"{RANKINGS_URL}/{confirmed_id}/finalize")
        assert response.status_code == 200, response.text
        assert response.json()["data"]["deleted_ranking_ids"] == [reordered_id]
        assert await final_positions(db, app_ids) == {app_ids[0]: 1, app_ids[1]: 2}

    async def test_finalize_race_on_the_partial_unique_index_returns_409(
        self, client, login, db, users, scholarship, monkeypatch
    ):
        # A concurrent finalize of another draft committed after this request read
        # the scope: the sibling scan sees nothing, the flush trips the partial
        # unique index and the endpoint must answer 409, not 500.
        from app.services.college_review_service import CollegeReviewService

        application = await add_application(db, scholarship.id, "a1")
        locked = await insert_ranking(db, scholarship.id, created_by=users["eng"].id, is_finalized=True)
        draft = await insert_ranking(db, scholarship.id, created_by=users["eng"].id, application_ids=[application.id])
        locked_id, draft_id = locked.id, draft.id

        async def scope_looks_empty(self, *args, **kwargs):
            return []

        monkeypatch.setattr(CollegeReviewService, "list_scope_rankings", scope_looks_empty)

        login(users["eng"])
        response = await client.post(f"{RANKINGS_URL}/{draft_id}/finalize")
        assert response.status_code == 409, response.text
        assert response.json()["message"] == "此學年度／學期已有其他鎖定的排名，請重新整理後再試"

        # The endpoint rolled back: both rows unchanged.
        assert not await _is_finalized(db, draft_id)
        assert await _is_finalized(db, locked_id)
        assert await count_items(db, draft_id) == 1


@pytest.mark.api
class TestRankingDiffAndSync:
    """GET /rankings/{id} pending/stale counts and POST /rankings/{id}/sync."""

    async def test_counts_and_sync_cover_new_withdrawn_deleted_and_moved_applications(
        self, client, login, db, users, scholarship
    ):
        keep = await add_application(db, scholarship.id, "keep", order=0)
        withdrawn = await add_application(db, scholarship.id, "withdrawn", order=1)
        soft_deleted = await add_application(db, scholarship.id, "deleted", order=2)
        moved_sub_type = await add_application(db, scholarship.id, "moved_sub", order=3)
        moved_college = await add_application(db, scholarship.id, "moved_college", order=4)
        moved_term = await add_application(db, scholarship.id, "moved_term", order=5)
        parked = await add_application(db, scholarship.id, "parked", order=6)
        revoked = await add_application(db, scholarship.id, "revoked", order=7)

        login(users["eng"])
        ranking_id = await _create(client, scholarship.id)
        assert await count_items(db, ranking_id) == 8

        withdrawn.status = ApplicationStatus.withdrawn
        soft_deleted.deleted_at = datetime.now(timezone.utc)
        moved_sub_type.sub_scholarship_type = "moe_1w"
        moved_college.student_data = {**moved_college.student_data, "std_academyno": "SCI"}
        moved_term.semester = "second"
        # Reversible states keep their item (and rank): 補件中 and 撤銷 awaiting 復發.
        parked.status = ApplicationStatus.pending_documents
        revoked.status = ApplicationStatus.cancelled
        revoked.quota_allocation_status = "revoked"
        await db.commit()
        late = await add_application(db, scholarship.id, "late", order=8)

        detail = await _detail(client, ranking_id)
        assert detail["pending_application_count"] == 1
        assert detail["stale_application_count"] == 5

        synced = await client.post(f"{RANKINGS_URL}/{ranking_id}/sync")
        assert synced.status_code == 200, synced.text
        body = synced.json()
        assert body["message"] == "已加入 1 位新申請者、移除 5 筆已不符合的申請"
        assert body["data"] == {
            "id": ranking_id,
            "added_application_count": 1,
            "removed_application_count": 5,
            "total_applications": 4,
        }
        assert await item_positions(db, ranking_id) == [(keep.id, 1), (parked.id, 2), (revoked.id, 3), (late.id, 4)]
        assert await db.scalar(select(CollegeRanking.total_applications).where(CollegeRanking.id == ranking_id)) == 4

        detail = await _detail(client, ranking_id)
        assert detail["pending_application_count"] == 0
        assert detail["stale_application_count"] == 0

        again = await client.post(f"{RANKINGS_URL}/{ranking_id}/sync")
        assert again.status_code == 200, again.text
        assert again.json()["message"] == "排名已與申請名單一致"
        assert again.json()["data"]["added_application_count"] == 0
        assert again.json()["data"]["removed_application_count"] == 0

        # Every sync is audited with what changed (G8 #970).
        sync_rows = [
            row for row in await _audit_rows(db, AuditAction.update.value) if row.resource_id == str(ranking_id)
        ]
        assert [row.description for row in sync_rows] == [
            "ranking synced with application list (+1 / -5)",
            "ranking synced with application list (+0 / -0)",
        ]
        assert sync_rows[0].resource_type == "college_ranking"
        created_order = [keep, withdrawn, soft_deleted, moved_sub_type, moved_college, moved_term, parked, revoked]
        assert sync_rows[0].old_values["rank_positions"] == {
            str(app.id): position for position, app in enumerate(created_order, 1)
        }
        assert sync_rows[1].old_values["rank_positions"] == {
            str(keep.id): 1,
            str(parked.id): 2,
            str(revoked.id): 3,
            str(late.id): 4,
        }
        assert sync_rows[0].new_values["added_application_ids"] == [late.id]
        assert sync_rows[0].new_values["removed_application_ids"] == [
            withdrawn.id,
            soft_deleted.id,
            moved_sub_type.id,
            moved_college.id,
            moved_term.id,
        ]

    async def test_sync_inserts_new_renewals_after_the_last_renewal(self, client, login, db, users, scholarship):
        renewal = await add_application(db, scholarship.id, "r1", is_renewal=True, order=0)
        first_new = await add_application(db, scholarship.id, "n1", order=1)
        second_new = await add_application(db, scholarship.id, "n2", order=2)

        login(users["eng"])
        ranking_id = await _create(client, scholarship.id)
        assert await item_positions(db, ranking_id) == [(renewal.id, 1), (first_new.id, 2), (second_new.id, 3)]

        late_new = await add_application(db, scholarship.id, "n3", order=3)
        late_renewal = await add_application(db, scholarship.id, "r2", is_renewal=True, order=4)

        synced = await client.post(f"{RANKINGS_URL}/{ranking_id}/sync")
        assert synced.status_code == 200, synced.text
        assert synced.json()["data"]["added_application_count"] == 2
        assert await item_positions(db, ranking_id) == [
            (renewal.id, 1),
            (late_renewal.id, 2),
            (first_new.id, 3),
            (second_new.id, 4),
            (late_new.id, 5),
        ]
        # New and moved items mirror their position (same as a manual reorder).
        positions = await final_positions(db, [late_renewal.id, first_new.id, second_new.id, late_new.id])
        assert positions == {late_renewal.id: 2, first_new.id: 3, second_new.id: 4, late_new.id: 5}

    async def test_sync_puts_a_new_renewal_first_when_the_ranking_has_none(self, client, login, db, users, scholarship):
        first_new = await add_application(db, scholarship.id, "n1", order=1)
        second_new = await add_application(db, scholarship.id, "n2", order=2)

        login(users["eng"])
        ranking_id = await _create(client, scholarship.id)
        renewal = await add_application(db, scholarship.id, "r1", is_renewal=True, order=3)

        synced = await client.post(f"{RANKINGS_URL}/{ranking_id}/sync")
        assert synced.status_code == 200, synced.text
        assert await item_positions(db, ranking_id) == [(renewal.id, 1), (first_new.id, 2), (second_new.id, 3)]

    @pytest.mark.parametrize("how", ["distribution_executed", "allocated_item"])
    async def test_sync_of_a_distributed_unlocked_ranking_is_append_only(
        self, client, login, db, users, scholarship, how
    ):
        apps = [await add_application(db, scholarship.id, f"a{n}", order=n) for n in (1, 2, 3)]

        login(users["eng"])
        ranking_id = await _create(client, scholarship.id)
        await _settle(db, ranking_id, how, created_by=users["eng"].id, scholarship_id=scholarship.id)
        # A gap in the positions must survive: nothing is renumbered.
        last_item = (
            await db.execute(
                select(CollegeRankingItem).where(
                    CollegeRankingItem.ranking_id == ranking_id,
                    CollegeRankingItem.application_id == apps[2].id,
                )
            )
        ).scalar_one()
        last_item.rank_position = 5
        apps[0].status = ApplicationStatus.withdrawn
        await db.commit()
        supplementary = await add_application(db, scholarship.id, "late", order=9)

        detail = await _detail(client, ranking_id)
        assert detail["pending_application_count"] == 1
        assert detail["stale_application_count"] == 0

        synced = await client.post(f"{RANKINGS_URL}/{ranking_id}/sync")
        assert synced.status_code == 200, synced.text
        data = synced.json()["data"]
        assert data["added_application_count"] == 1
        assert data["removed_application_count"] == 0
        assert data["total_applications"] == 4
        assert await item_positions(db, ranking_id) == [
            (apps[0].id, 1),
            (apps[1].id, 2),
            (apps[2].id, 5),
            (supplementary.id, 6),
        ]
        assert (await final_positions(db, [supplementary.id]))[supplementary.id] == 6

    async def test_sync_409_while_finalized(self, client, login, db, users, scholarship):
        await add_application(db, scholarship.id, "a1")

        login(users["eng"])
        ranking_id = await _create(client, scholarship.id)
        assert (await client.post(f"{RANKINGS_URL}/{ranking_id}/finalize")).status_code == 200
        await add_application(db, scholarship.id, "late", order=5)

        response = await client.post(f"{RANKINGS_URL}/{ranking_id}/sync")
        assert response.status_code == 409, response.text
        assert "解除鎖定" in response.json()["message"]
        assert await count_items(db, ranking_id) == 1

    async def test_finalized_ranking_still_reports_pending_and_stale_counts(
        self, client, login, db, users, scholarship
    ):
        # Not distributed yet: the reminder tells the college to unlock and sync.
        await add_application(db, scholarship.id, "a1")
        withdrawn = await add_application(db, scholarship.id, "a2", order=1)

        login(users["eng"])
        ranking_id = await _create(client, scholarship.id)
        assert (await client.post(f"{RANKINGS_URL}/{ranking_id}/finalize")).status_code == 200
        withdrawn.status = ApplicationStatus.withdrawn
        await db.commit()
        await add_application(db, scholarship.id, "late", order=5)

        detail = await _detail(client, ranking_id)
        assert detail["is_finalized"] is True
        assert detail["pending_application_count"] == 1
        assert detail["stale_application_count"] == 1

    async def test_finalized_and_distributed_ranking_reports_no_changes(self, client, login, db, users, scholarship):
        await add_application(db, scholarship.id, "a1")
        withdrawn = await add_application(db, scholarship.id, "a2", order=1)

        login(users["eng"])
        ranking_id = await _create(client, scholarship.id)
        assert (await client.post(f"{RANKINGS_URL}/{ranking_id}/finalize")).status_code == 200
        await _settle(
            db, ranking_id, "distribution_executed", created_by=users["eng"].id, scholarship_id=scholarship.id
        )
        withdrawn.status = ApplicationStatus.withdrawn
        await db.commit()
        await add_application(db, scholarship.id, "late", order=5)

        detail = await _detail(client, ranking_id)
        assert detail["pending_application_count"] == 0
        assert detail["stale_application_count"] == 0

    async def test_counts_ignore_other_colleges_applications(self, client, login, db, users, scholarship):
        await add_application(db, scholarship.id, "a1")

        login(users["eng"])
        ranking_id = await _create(client, scholarship.id)
        await add_application(db, scholarship.id, "s1", college_code="SCI")

        detail = await _detail(client, ranking_id)
        assert detail["pending_application_count"] == 0
        assert detail["stale_application_count"] == 0


@pytest.mark.api
class TestDeleteGuards:
    """DELETE /rankings/{id} removes drafts (and their items) only."""

    async def test_delete_draft_removes_its_items_and_audits_its_order(self, client, login, db, users, scholarship):
        apps = [await add_application(db, scholarship.id, f"a{n}", order=n) for n in (1, 2)]

        login(users["eng"])
        doomed_id = await _create(client, scholarship.id, ranking_name="草稿 A")
        kept_id = await _create(client, scholarship.id)

        response = await client.delete(f"{RANKINGS_URL}/{doomed_id}")
        assert response.status_code == 200, response.text
        assert "草稿 A" in response.json()["message"]

        assert not await ranking_exists(db, doomed_id)
        assert await count_items(db, doomed_id) == 0
        assert await count_items(db, kept_id) == 2

        [row] = await _audit_rows(db, AuditAction.delete_ranking.value)
        assert row.resource_id == str(doomed_id)
        assert row.old_values["rank_positions"] == {str(apps[0].id): 1, str(apps[1].id): 2}

    @pytest.mark.parametrize("how", UNDELETABLE)
    async def test_delete_409_when_distributed_or_used_by_a_roster(self, client, login, db, users, scholarship, how):
        application = await add_application(db, scholarship.id, "a1")
        ranking = await insert_ranking(db, scholarship.id, created_by=users["eng"].id, application_ids=[application.id])
        ranking_id = ranking.id
        await _settle(db, ranking_id, how, created_by=users["eng"].id, scholarship_id=scholarship.id)

        login(users["eng"])
        response = await client.delete(f"{RANKINGS_URL}/{ranking_id}")
        assert response.status_code == 409, response.text
        assert response.json()["message"] == "此排名已執行分發或已用於造冊，無法刪除"
        assert await ranking_exists(db, ranking_id)
        assert await count_items(db, ranking_id) == 1

    async def test_delete_blocked_after_deadline_for_college(self, client, login, db, users, scholarship):
        # Create is deadline-gated, so delete must be too: a post-deadline delete
        # would leave the college without the ranking it can no longer recreate.
        ranking = await insert_ranking(db, scholarship.id, created_by=users["eng"].id)
        await make_expired_config(db, scholarship.id, code="md_delete_deadline")

        login(users["eng"])
        response = await client.delete(f"{RANKINGS_URL}/{ranking.id}")
        assert response.status_code == 403
        assert await count_rankings(db, "ENG") == 1


class TestFinalizedRankingIndex:
    """uq_college_rankings_finalized_per_college: drafts are free, ONE finalized per scope."""

    async def test_database_accepts_several_drafts_next_to_a_finalized_ranking(self, db, users, scholarship):
        for _ in range(3):
            await insert_ranking(db, scholarship.id, created_by=users["eng"].id)
        await insert_ranking(db, scholarship.id, created_by=users["eng"].id, is_finalized=True)
        assert await count_rankings(db, "ENG") == 4

    async def test_database_accepts_finalized_rankings_of_other_scopes(self, db, users, scholarship):
        for college_code in ("ENG", "SCI", None):
            await insert_ranking(
                db, scholarship.id, created_by=users["eng"].id, college_code=college_code, is_finalized=True
            )
        await insert_ranking(db, scholarship.id, created_by=users["eng"].id, sub_type_code="moe_1w", is_finalized=True)
        assert await db.scalar(select(func.count()).select_from(CollegeRanking)) == 4

    @pytest.mark.parametrize(
        "first, second",
        [
            ({"semester": SEMESTER, "college_code": "ENG"}, {"semester": SEMESTER, "college_code": "ENG"}),
            # Yearly rankings store NULL; a legacy "yearly" must still collide.
            ({"semester": None, "college_code": "ENG"}, {"semester": "yearly", "college_code": "ENG"}),
            # Admin global rankings store NULL college_code; "" is the same scope.
            ({"semester": SEMESTER, "college_code": None}, {"semester": SEMESTER, "college_code": ""}),
        ],
    )
    async def test_database_rejects_a_second_finalized_ranking_in_one_scope(
        self, db, users, scholarship, first, second
    ):
        scholarship_id, creator_id = scholarship.id, users["eng"].id
        await insert_ranking(db, scholarship_id, created_by=creator_id, is_finalized=True, **first)

        db.add(
            CollegeRanking(
                scholarship_type_id=scholarship_id,
                sub_type_code=SUB_TYPE,
                academic_year=YEAR,
                created_by=creator_id,
                is_finalized=True,
                ranking_status="finalized",
                **second,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

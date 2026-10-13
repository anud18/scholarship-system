"""
DB-backed tests for the ranking-scope rules of CollegeReviewService:
create_ranking / compute_ranking_diff / sync_ranking / finalize_ranking /
delete_ranking and the "settled" predicate.

Covers what the HTTP layer cannot reach: admin global rankings (require_college
rejects admins at the endpoint), the scope derived from the target row when an
admin acts on a college's ranking, and the full stale/exempt status matrix.
SQLite does not enforce foreign keys, so deletions are asserted with row counts.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.application import ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.user import UserRole
from app.services.college_review_service import (
    CollegeReviewService,
    DeletedRankingInfo,
    RankingModificationError,
    RankingNotFoundError,
    RankingScopeConflictError,
)
from app.tests.ranking_scope_helpers import (
    SEMESTER,
    SUB_TYPE,
    YEAR,
    add_application,
    add_payment_roster,
    count_items,
    final_positions,
    first_item,
    insert_ranking,
    item_positions,
    make_config,
    make_scholarship,
    make_user,
    ranking_exists,
)


@pytest_asyncio.fixture
async def users(db):
    return {
        "eng": await make_user(db, "scope_eng", college_code="ENG"),
        "sci": await make_user(db, "scope_sci", college_code="SCI"),
        "admin": await make_user(db, "scope_admin", role=UserRole.admin),
    }


@pytest_asyncio.fixture
async def scholarship(db):
    return await make_scholarship(db, "scope_service_scholarship")


@pytest.fixture
def service(db):
    return CollegeReviewService(db)


async def _create(service, db, scholarship_id: int, creator_id: int, **overrides) -> int:
    """create_ranking for the default scope; returns the committed ranking id."""
    params = {"sub_type_code": SUB_TYPE, "academic_year": YEAR, "semester": SEMESTER, **overrides}
    ranking = await service.create_ranking(scholarship_type_id=scholarship_id, creator_id=creator_id, **params)
    ranking_id = ranking.id
    await db.commit()
    return ranking_id


class TestCreateRanking:
    async def test_always_inserts_a_new_draft_of_the_creators_college(self, service, db, users, scholarship):
        application = await add_application(db, scholarship.id, "a1")
        await add_application(db, scholarship.id, "s1", college_code="SCI")

        first_id = await _create(service, db, scholarship.id, users["eng"].id)
        second_id = await _create(service, db, scholarship.id, users["eng"].id, ranking_name="第二版")

        assert first_id != second_id
        second = await db.get(CollegeRanking, second_id)
        assert second.college_code == "ENG"
        assert second.ranking_name == "第二版"
        assert not second.is_finalized
        for ranking_id in (first_id, second_id):
            assert await item_positions(db, ranking_id) == [(application.id, 1)]

    async def test_refuses_while_the_scope_is_locked_and_allows_again_after_unlocking(
        self, service, db, users, scholarship
    ):
        ranking_id = await _create(service, db, scholarship.id, users["eng"].id, ranking_name="正式排名")
        await service.finalize_ranking(ranking_id, users["eng"].id)
        await db.commit()

        with pytest.raises(RankingScopeConflictError) as exc:
            await service.create_ranking(scholarship.id, SUB_TYPE, YEAR, SEMESTER, users["eng"].id)
        assert "正式排名" in str(exc.value)

        await service.unfinalize_ranking(ranking_id)
        await db.commit()
        assert await _create(service, db, scholarship.id, users["eng"].id) != ranking_id

    async def test_unlocked_but_distributed_ranking_still_blocks_create(self, service, db, users, scholarship):
        # Unlocking a distributed ranking (the 補充匯入 window) re-allows syncing it,
        # not a competing draft next to it.
        ranking_id = await _create(service, db, scholarship.id, users["eng"].id)
        ranking = await db.get(CollegeRanking, ranking_id)
        ranking.distribution_executed = True
        await db.commit()

        with pytest.raises(RankingScopeConflictError) as exc:
            await service.create_ranking(scholarship.id, SUB_TYPE, YEAR, SEMESTER, users["eng"].id)
        assert "同步申請名單" in str(exc.value)

    async def test_admin_creates_global_drafts_with_null_college(self, service, db, users, scholarship):
        eng_app = await add_application(db, scholarship.id, "a1")
        sci_app = await add_application(db, scholarship.id, "s1", college_code="SCI", order=1)

        global_id = await _create(service, db, scholarship.id, users["admin"].id)

        ranking = await db.get(CollegeRanking, global_id)
        assert ranking.college_code is None
        # A global ranking spans every college's applications.
        assert {app_id for app_id, _pos in await item_positions(db, global_id)} == {eng_app.id, sci_app.id}


class TestFinalizeScope:
    async def test_admin_global_finalize_collapses_global_drafts_only(self, service, db, users, scholarship):
        await add_application(db, scholarship.id, "a1")
        global_ids = [await _create(service, db, scholarship.id, users["admin"].id) for _ in range(2)]
        # A legacy global draft stored with college_code '' is the same scope as NULL.
        legacy_global = await insert_ranking(db, scholarship.id, created_by=users["admin"].id, college_code="")
        eng_id = await _create(service, db, scholarship.id, users["eng"].id)

        result = await service.finalize_ranking(global_ids[1], users["admin"].id)
        await db.commit()

        assert [deleted.id for deleted in result.deleted_rankings] == [global_ids[0], legacy_global.id]
        assert not await ranking_exists(db, global_ids[0])
        assert not await ranking_exists(db, legacy_global.id)
        assert await ranking_exists(db, eng_id)
        assert await count_items(db, eng_id) == 1

    async def test_admin_finalizing_a_college_ranking_uses_that_rankings_scope(self, service, db, users, scholarship):
        await add_application(db, scholarship.id, "a1")
        await add_application(db, scholarship.id, "s1", college_code="SCI", order=1)
        eng_ids = [await _create(service, db, scholarship.id, users["eng"].id) for _ in range(2)]
        sci_id = await _create(service, db, scholarship.id, users["sci"].id)
        global_id = await _create(service, db, scholarship.id, users["admin"].id)

        result = await service.finalize_ranking(eng_ids[1], users["admin"].id)
        await db.commit()

        assert result.ranking.id == eng_ids[1]
        assert result.ranking.finalized_by == users["admin"].id
        assert [deleted.id for deleted in result.deleted_rankings] == [eng_ids[0]]
        for ranking_id in (sci_id, global_id):
            assert await ranking_exists(db, ranking_id)

    async def test_legacy_yearly_semester_draft_is_a_sibling_of_a_null_semester_ranking(
        self, service, db, users, scholarship
    ):
        legacy = await insert_ranking(
            db, scholarship.id, created_by=users["eng"].id, sub_type_code="default", semester="yearly"
        )
        ranking_id = await _create(service, db, scholarship.id, users["eng"].id, sub_type_code="default", semester=None)

        result = await service.finalize_ranking(ranking_id, users["eng"].id)
        await db.commit()

        assert [deleted.id for deleted in result.deleted_rankings] == [legacy.id]

    async def test_result_snapshots_the_deleted_drafts_order(self, service, db, users, scholarship):
        apps = [await add_application(db, scholarship.id, f"a{n}", order=n) for n in (1, 2)]
        doomed_id = await _create(service, db, scholarship.id, users["eng"].id, ranking_name="草稿")
        kept_id = await _create(service, db, scholarship.id, users["eng"].id)

        result = await service.finalize_ranking(kept_id, users["eng"].id)
        await db.commit()

        assert result.deleted_rankings == [
            DeletedRankingInfo(
                id=doomed_id,
                ranking_name="草稿",
                total_applications=2,
                rank_positions={str(apps[0].id): 1, str(apps[1].id): 2},
            )
        ]
        assert await count_items(db, doomed_id) == 0

    async def test_applications_only_in_deleted_drafts_lose_the_rank_those_drafts_wrote(
        self, service, db, users, scholarship
    ):
        shared = await add_application(db, scholarship.id, "shared", order=0)
        only_doomed = await add_application(db, scholarship.id, "only_doomed", order=1)
        written_elsewhere = await add_application(db, scholarship.id, "elsewhere", order=2)
        await insert_ranking(
            db,
            scholarship.id,
            created_by=users["eng"].id,
            application_ids=[only_doomed.id, written_elsewhere.id, shared.id],
            name="doomed",
        )
        kept = await insert_ranking(
            db, scholarship.id, created_by=users["eng"].id, application_ids=[shared.id], name="kept"
        )
        shared.final_ranking_position = 3  # the doomed draft's order
        only_doomed.final_ranking_position = 1  # the doomed draft's order
        written_elsewhere.final_ranking_position = 9  # some other ranking's order
        await db.commit()

        await service.finalize_ranking(kept.id, users["eng"].id)
        await db.commit()

        assert await final_positions(db, [shared.id, only_doomed.id, written_elsewhere.id]) == {
            shared.id: 1,
            only_doomed.id: None,
            written_elsewhere.id: 9,
        }

    async def test_deleted_draft_leaves_the_rank_while_another_scope_holds_the_application(
        self, service, db, users, scholarship
    ):
        # The "default" sub-type ranking spans every sub-type, so it holds the same
        # application at the same position: the value may be its own.
        both = await add_application(db, scholarship.id, "both", order=0)
        other = await add_application(db, scholarship.id, "other", order=1)
        await insert_ranking(db, scholarship.id, created_by=users["eng"].id, application_ids=[both.id], name="doomed")
        kept = await insert_ranking(
            db, scholarship.id, created_by=users["eng"].id, application_ids=[other.id], name="kept"
        )
        await insert_ranking(
            db,
            scholarship.id,
            created_by=users["eng"].id,
            sub_type_code="default",
            application_ids=[both.id],
            name="default scope",
        )
        both.final_ranking_position = 1
        await db.commit()

        await service.finalize_ranking(kept.id, users["eng"].id)
        await db.commit()

        assert await final_positions(db, [both.id, other.id]) == {both.id: 1, other.id: 1}

    async def test_roster_referenced_sibling_blocks_finalize_until_the_roster_is_gone(
        self, service, db, users, scholarship
    ):
        await add_application(db, scholarship.id, "a1")
        used_id = await _create(service, db, scholarship.id, users["eng"].id)
        draft_id = await _create(service, db, scholarship.id, users["eng"].id)
        config = await make_config(db, scholarship.id, code="scope_roster_cfg", academic_year=100)
        roster = await add_payment_roster(db, ranking_id=used_id, config_id=config.id, created_by=users["eng"].id)

        with pytest.raises(RankingScopeConflictError):
            await service.finalize_ranking(draft_id, users["eng"].id)
        assert await service._load_roster_referenced_ids([used_id, draft_id]) == {used_id}

        await db.delete(roster)
        await db.commit()
        result = await service.finalize_ranking(draft_id, users["eng"].id)
        assert [deleted.id for deleted in result.deleted_rankings] == [used_id]

    async def test_missing_ranking_raises_not_found(self, service):
        with pytest.raises(RankingNotFoundError):
            await service.finalize_ranking(999999, 1)


class TestDeleteRanking:
    async def test_missing_ranking_raises_not_found(self, service):
        with pytest.raises(RankingNotFoundError):
            await service.delete_ranking(999999)

    async def test_finalized_ranking_must_be_unlocked_first(self, service, db, users, scholarship):
        ranking = await insert_ranking(db, scholarship.id, created_by=users["eng"].id, is_finalized=True)

        with pytest.raises(RankingModificationError, match="unfinalize it first"):
            await service.delete_ranking(ranking.id)

    async def test_settled_ranking_is_never_deleted(self, service, db, users, scholarship):
        application = await add_application(db, scholarship.id, "a1")
        ranking = await insert_ranking(db, scholarship.id, created_by=users["eng"].id, application_ids=[application.id])
        item = await first_item(db, ranking.id)
        item.backup_position = 1  # a 備取 slot is distribution state too
        await db.commit()

        with pytest.raises(RankingScopeConflictError):
            await service.delete_ranking(ranking.id)
        assert await count_items(db, ranking.id) == 1

    async def test_draft_is_deleted_with_its_items(self, service, db, users, scholarship):
        application = await add_application(db, scholarship.id, "a1")
        ranking = await insert_ranking(
            db, scholarship.id, created_by=users["eng"].id, application_ids=[application.id], name="試排"
        )
        ranking_id = ranking.id

        deleted = await service.delete_ranking(ranking_id)
        await db.commit()

        assert deleted == DeletedRankingInfo(
            id=ranking_id, ranking_name="試排", total_applications=1, rank_positions={str(application.id): 1}
        )
        assert not await ranking_exists(db, ranking_id)
        assert await count_items(db, ranking_id) == 0


class TestSettledPredicate:
    """_load_settled_ids: the SQL pre-filter must not drop any row the Python predicate keeps."""

    @pytest.mark.parametrize(
        "column, value, settled",
        [
            ("is_allocated", True, True),
            ("allocated_sub_type", SUB_TYPE, True),
            ("allocation_config_id", "config", True),
            ("backup_position", 2, True),
            ("backup_allocations", [{"sub_type": SUB_TYPE, "backup_position": 1}], True),
            ("backup_allocations", [], False),
            ("status", "allocated", True),
            ("status", "rejected", True),
            ("status", "waitlisted", True),
            ("status", "ranked", False),
            # A college "N" (college_rejected) is a ranking decision, not distribution.
            ("college_rejected", True, False),
        ],
    )
    async def test_item_columns(self, service, db, users, scholarship, column, value, settled):
        application = await add_application(db, scholarship.id, "a1")
        ranking = await insert_ranking(db, scholarship.id, created_by=users["eng"].id, application_ids=[application.id])
        if value == "config":
            value = (await make_config(db, scholarship.id, code="settled_cfg", academic_year=100)).id
        item = await first_item(db, ranking.id)
        setattr(item, column, value)
        await db.commit()

        assert await service._load_settled_ids([ranking.id]) == ({ranking.id} if settled else set())

    async def test_distribution_executed_without_items(self, service, db, users, scholarship):
        ranking = await insert_ranking(db, scholarship.id, created_by=users["eng"].id)
        other = await insert_ranking(db, scholarship.id, created_by=users["eng"].id)
        ranking.distribution_executed = True
        await db.commit()

        assert await service._load_settled_ids([ranking.id, other.id, None]) == {ranking.id}
        assert await service._load_settled_ids([]) == set()


class TestRankingDiff:
    @pytest.mark.parametrize(
        "status, quota_allocation_status, soft_deleted, stale",
        [
            (ApplicationStatus.approved, None, False, False),
            # Reversible: staff move it back / the student resubmits / 復發.
            (ApplicationStatus.pending_documents, None, False, False),
            (ApplicationStatus.returned, None, False, False),
            (ApplicationStatus.manual_excluded, None, False, False),
            (ApplicationStatus.cancelled, "revoked", False, False),
            (ApplicationStatus.cancelled, "suspended", False, False),
            # Gone for good.
            (ApplicationStatus.cancelled, None, False, True),
            (ApplicationStatus.cancelled_by_challenge, None, False, True),
            (ApplicationStatus.withdrawn, None, False, True),
            (ApplicationStatus.draft, None, False, True),  # withdraw resets the application to draft
            (ApplicationStatus.deleted, None, False, True),
            (ApplicationStatus.approved, None, True, True),
            # Soft deletion beats an otherwise reversible status.
            (ApplicationStatus.pending_documents, None, True, True),
        ],
    )
    async def test_stale_status_matrix(
        self, service, db, users, scholarship, status, quota_allocation_status, soft_deleted, stale
    ):
        application = await add_application(db, scholarship.id, "a1")
        ranking_id = await _create(service, db, scholarship.id, users["eng"].id)

        application.status = status
        application.quota_allocation_status = quota_allocation_status
        if soft_deleted:
            application.deleted_at = datetime.now(timezone.utc)
        await db.commit()

        diff = await service.compute_ranking_diff(await db.get(CollegeRanking, ranking_id))
        assert diff.stale_application_ids == ([application.id] if stale else [])
        assert diff.pending_application_ids == []

    async def test_pending_applications_are_listed_in_ranking_sort_order(self, service, db, users, scholarship):
        await add_application(db, scholarship.id, "a0", order=0)
        ranking_id = await _create(service, db, scholarship.id, users["eng"].id)
        late = await add_application(db, scholarship.id, "late", order=9)
        early = await add_application(db, scholarship.id, "early", order=3)
        renewal = await add_application(db, scholarship.id, "renewal", is_renewal=True, order=20)

        diff = await service.compute_ranking_diff(await db.get(CollegeRanking, ranking_id))
        # Renewals first, then by submission time.
        assert diff.pending_application_ids == [renewal.id, early.id, late.id]
        assert diff.stale_application_ids == []

    async def test_default_sub_type_ranking_spans_every_sub_type(self, service, db, users, scholarship):
        application = await add_application(db, scholarship.id, "a1")
        ranking_id = await _create(service, db, scholarship.id, users["eng"].id, sub_type_code="default")
        application.sub_scholarship_type = "moe_1w"
        await db.commit()
        other = await add_application(db, scholarship.id, "a2", sub_type="moe_2w", order=1)

        diff = await service.compute_ranking_diff(await db.get(CollegeRanking, ranking_id))
        assert diff.stale_application_ids == []
        assert diff.pending_application_ids == [other.id]


class TestSyncRanking:
    async def test_missing_ranking_raises_not_found(self, service):
        with pytest.raises(RankingNotFoundError):
            await service.sync_ranking(999999)

    async def test_finalized_ranking_is_refused(self, service, db, users, scholarship):
        ranking = await insert_ranking(db, scholarship.id, created_by=users["eng"].id, is_finalized=True)

        with pytest.raises(RankingModificationError, match="解除鎖定"):
            await service.sync_ranking(ranking.id)

    async def test_sync_leaves_nothing_for_the_next_diff(self, service, db, users, scholarship):
        # Pending and stale come from ONE eligibility query, so a sync never
        # flip-flops: the very next diff is empty.
        kept = await add_application(db, scholarship.id, "kept", order=0)
        gone = await add_application(db, scholarship.id, "gone", order=1)
        ranking_id = await _create(service, db, scholarship.id, users["eng"].id)
        gone.status = ApplicationStatus.withdrawn
        await db.commit()
        new = await add_application(db, scholarship.id, "new", order=2)

        result = await service.sync_ranking(ranking_id)
        await db.commit()

        assert result.added_application_ids == [new.id]
        assert result.removed_application_ids == [gone.id]
        assert result.ranking.total_applications == 2
        assert await item_positions(db, ranking_id) == [(kept.id, 1), (new.id, 2)]
        diff = await service.compute_ranking_diff(await db.get(CollegeRanking, ranking_id))
        assert not diff.has_changes

    async def test_removed_application_loses_only_the_rank_this_ranking_wrote(self, service, db, users, scholarship):
        kept = await add_application(db, scholarship.id, "kept", order=0)
        gone = await add_application(db, scholarship.id, "gone", order=1)
        overwritten = await add_application(db, scholarship.id, "overwritten", order=2)
        ranking = await insert_ranking(
            db, scholarship.id, created_by=users["eng"].id, application_ids=[kept.id, gone.id, overwritten.id]
        )
        gone.final_ranking_position = 2  # mirrored from this ranking
        overwritten.final_ranking_position = 7  # another draft reordered it since
        gone.status = ApplicationStatus.withdrawn
        overwritten.status = ApplicationStatus.withdrawn
        await db.commit()

        result = await service.sync_ranking(ranking.id)
        await db.commit()

        assert result.removed_application_ids == [gone.id, overwritten.id]
        assert result.previous_rank_positions == {str(kept.id): 1, str(gone.id): 2, str(overwritten.id): 3}
        assert await final_positions(db, [kept.id, gone.id, overwritten.id]) == {
            kept.id: None,  # never mirrored, and its position did not move
            gone.id: None,
            overwritten.id: 7,
        }

    async def test_removed_application_keeps_the_rank_while_another_scope_holds_it(
        self, service, db, users, scholarship
    ):
        # An admin global ranking (college_code NULL) holds the same application at
        # the same position, so the value may be its own.
        gone = await add_application(db, scholarship.id, "gone", order=0)
        ranking = await insert_ranking(db, scholarship.id, created_by=users["eng"].id, application_ids=[gone.id])
        await insert_ranking(
            db,
            scholarship.id,
            created_by=users["admin"].id,
            college_code=None,
            application_ids=[gone.id],
            name="global",
        )
        gone.final_ranking_position = 1
        gone.status = ApplicationStatus.withdrawn
        await db.commit()

        result = await service.sync_ranking(ranking.id)
        await db.commit()

        assert result.removed_application_ids == [gone.id]
        assert await final_positions(db, [gone.id]) == {gone.id: 1}

    async def test_new_applicants_go_before_college_rejected_rows(self, service, db, users, scholarship):
        ranked = await add_application(db, scholarship.id, "ranked", order=0)
        rejected = await add_application(db, scholarship.id, "rejected", order=1)
        ranking = await insert_ranking(
            db, scholarship.id, created_by=users["eng"].id, application_ids=[ranked.id, rejected.id]
        )
        rejected_item = (
            await db.execute(
                select(CollegeRankingItem).where(
                    CollegeRankingItem.ranking_id == ranking.id, CollegeRankingItem.application_id == rejected.id
                )
            )
        ).scalar_one()
        rejected_item.college_rejected = True  # 'N' in the Excel import, parked at the end
        await db.commit()
        new = await add_application(db, scholarship.id, "new", order=2)
        renewal = await add_application(db, scholarship.id, "renewal", order=3, is_renewal=True)

        await service.sync_ranking(ranking.id)
        await db.commit()

        assert await item_positions(db, ranking.id) == [
            (renewal.id, 1),
            (ranked.id, 2),
            (new.id, 3),
            (rejected.id, 4),
        ]

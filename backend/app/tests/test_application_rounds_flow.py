"""DB-backed tests for 多梯次申請 (additional application rounds).

- the review-phase filter shows a later-round application only inside its round's
  review window (falling back to the general window for a NULL round window);
- college rankings keep 續領 → 第一梯次 → 第二梯次 on create, sync, reorder and Excel import;
- the admin PUT /application-rounds endpoint validates rounds and refuses to drop a
  round that already holds applications.

SQLite in-memory (conftest) — application_round / round rows are real rows.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.application import Application, ApplicationStatus
from app.models.application_round import ScholarshipApplicationRound
from app.models.college_review import CollegeRankingItem
from app.models.scholarship import ScholarshipConfiguration
from app.models.user import UserRole
from app.services.college_review_service import CollegeReviewService, InvalidRankingDataError
from app.services.review_phase_filter import apply_renewal_phase_filter
from app.tests.ranking_scope_helpers import (
    SEMESTER,
    SUB_TYPE,
    YEAR,
    add_application,
    insert_ranking,
    item_positions,
    make_config,
    make_scholarship,
    make_user,
)

NOW = datetime.now(timezone.utc)
CLOSED = (NOW - timedelta(days=40), NOW - timedelta(days=30))
OPEN = (NOW - timedelta(days=1), NOW + timedelta(days=5))
LATER = (NOW + timedelta(days=10), NOW + timedelta(days=20))

ROUNDS_URL = "/api/v1/scholarship-configurations/configurations/{id}/application-rounds"
RANKINGS_URL = "/api/v1/college-review/rankings"


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
async def scholarship(db):
    scholarship = await make_scholarship(db, "multi_round_scholarship")
    scholarship.sub_type_list = ["nstc", "moe_1w"]
    await db.commit()
    return scholarship


@pytest_asyncio.fixture
async def college_user(db):
    return await make_user(db, "mr_eng", college_code="ENG")


async def _add_round(db, config_id: int, number: int = 2, window=OPEN, **fields) -> ScholarshipApplicationRound:
    row = ScholarshipApplicationRound(
        configuration_id=config_id,
        round_number=number,
        application_start_date=window[0],
        application_end_date=window[1],
        open_sub_types=fields.pop("open_sub_types", [SUB_TYPE]),
        **fields,
    )
    db.add(row)
    await db.commit()
    return row


async def _pending(db, scholarship_id: int, key: str, config_id: int, **kwargs) -> Application:
    return await add_application(
        db, scholarship_id, key, configuration_id=config_id, status=ApplicationStatus.under_review, **kwargs
    )


async def _visible_ids(db, role: str) -> set:
    stmt = select(Application).where(Application.status == ApplicationStatus.under_review.value)
    result = await db.execute(apply_renewal_phase_filter(stmt, role=role))
    return {app.id for app in result.scalars().all()}


class TestReviewPhaseFilter:
    async def test_second_round_uses_its_own_college_window(self, db, scholarship):
        config = await make_config(db, scholarship.id, code="mr_phase_1")
        config.college_review_start, config.college_review_end = CLOSED
        await db.commit()
        await _add_round(db, config.id, college_review_start=OPEN[0], college_review_end=OPEN[1])

        first = await _pending(db, scholarship.id, "p1", config.id)
        second = await _pending(db, scholarship.id, "p2", config.id, application_round=2)

        visible = await _visible_ids(db, "college")
        assert second.id in visible
        assert first.id not in visible

    async def test_null_round_window_falls_back_to_general(self, db, scholarship):
        config = await make_config(db, scholarship.id, code="mr_phase_2")
        config.professor_review_start, config.professor_review_end = OPEN
        await db.commit()
        await _add_round(db, config.id)

        first = await _pending(db, scholarship.id, "q1", config.id)
        second = await _pending(db, scholarship.id, "q2", config.id, application_round=2)

        assert {first.id, second.id} <= await _visible_ids(db, "professor")

    async def test_closed_round_window_hides_only_that_round(self, db, scholarship):
        config = await make_config(db, scholarship.id, code="mr_phase_3")
        config.college_review_start, config.college_review_end = OPEN
        await db.commit()
        await _add_round(db, config.id, college_review_start=LATER[0], college_review_end=LATER[1])

        first = await _pending(db, scholarship.id, "r1", config.id)
        second = await _pending(db, scholarship.id, "r2", config.id, application_round=2)

        visible = await _visible_ids(db, "college")
        assert first.id in visible
        assert second.id not in visible


class TestRankingOrder:
    async def test_create_ranks_later_rounds_last(self, db, scholarship, college_user):
        await make_config(db, scholarship.id, code="mr_rank_1")
        second = await add_application(db, scholarship.id, "c2", application_round=2, order=0)
        first = await add_application(db, scholarship.id, "c1", order=5)
        renewal = await add_application(db, scholarship.id, "c0", is_renewal=True, order=9)

        service = CollegeReviewService(db)
        ranking = await service.create_ranking(
            scholarship_type_id=scholarship.id,
            sub_type_code=SUB_TYPE,
            academic_year=YEAR,
            semester=SEMESTER,
            creator_id=college_user.id,
        )
        await db.commit()

        assert [app_id for app_id, _pos in await item_positions(db, ranking.id)] == [renewal.id, first.id, second.id]

    async def test_sync_slots_new_first_round_before_second_round(self, db, scholarship, college_user):
        await make_config(db, scholarship.id, code="mr_rank_2")
        renewal = await add_application(db, scholarship.id, "s0", is_renewal=True)
        first = await add_application(db, scholarship.id, "s1")
        second = await add_application(db, scholarship.id, "s2", application_round=2)
        rejected = await add_application(db, scholarship.id, "sx")
        ranking = await insert_ranking(
            db,
            scholarship.id,
            created_by=college_user.id,
            application_ids=[renewal.id, first.id, second.id, rejected.id],
        )
        rejected_item = (
            await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.application_id == rejected.id))
        ).scalar_one()
        rejected_item.college_rejected = True
        await db.commit()

        late_first = await add_application(db, scholarship.id, "s3", order=30)
        late_second = await add_application(db, scholarship.id, "s4", application_round=2, order=31)
        late_renewal = await add_application(db, scholarship.id, "s5", is_renewal=True, order=32)

        result = await CollegeReviewService(db).sync_ranking(ranking.id)
        await db.commit()

        assert set(result.added_application_ids) == {late_first.id, late_second.id, late_renewal.id}
        assert [app_id for app_id, _pos in await item_positions(db, ranking.id)] == [
            renewal.id,
            late_renewal.id,
            first.id,
            late_first.id,
            second.id,
            late_second.id,
            rejected.id,
        ]

    async def test_update_order_rejects_second_round_above_first(self, db, scholarship, college_user):
        await make_config(db, scholarship.id, code="mr_rank_3")
        first_a = await add_application(db, scholarship.id, "u1")
        first_b = await add_application(db, scholarship.id, "u2")
        second = await add_application(db, scholarship.id, "u3", application_round=2)
        ranking = await insert_ranking(
            db, scholarship.id, created_by=college_user.id, application_ids=[first_a.id, first_b.id, second.id]
        )
        # ids read up front: the rollback below expires every loaded row
        ranking_id, first_a_id, first_b_id, second_id = ranking.id, first_a.id, first_b.id, second.id
        items = {
            item.application_id: item.id
            for item in (
                await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.ranking_id == ranking.id))
            ).scalars()
        }
        service = CollegeReviewService(db)

        with pytest.raises(InvalidRankingDataError, match="第二梯次申請學生的排名必須在第一梯次之後"):
            await service.update_ranking_order(
                ranking_id,
                [
                    {"item_id": items[second_id], "position": 1},
                    {"item_id": items[first_a_id], "position": 2},
                    {"item_id": items[first_b_id], "position": 3},
                ],
            )
        await db.rollback()

        # Reordering inside the first round is fine
        await service.update_ranking_order(
            ranking_id,
            [
                {"item_id": items[first_b_id], "position": 1},
                {"item_id": items[first_a_id], "position": 2},
                {"item_id": items[second_id], "position": 3},
            ],
        )
        await db.commit()
        assert [app_id for app_id, _pos in await item_positions(db, ranking_id)] == [first_b_id, first_a_id, second_id]

    async def test_college_rejected_rows_are_exempt(self, db, scholarship, college_user):
        await make_config(db, scholarship.id, code="mr_rank_4")
        first = await add_application(db, scholarship.id, "v1")
        second = await add_application(db, scholarship.id, "v2", application_round=2)
        rejected_first = await add_application(db, scholarship.id, "v3")
        # Stored order is invalid (second round on top); the request below fixes it while the
        # rejected first-round row stays parked behind the second round.
        ranking = await insert_ranking(
            db, scholarship.id, created_by=college_user.id, application_ids=[second.id, first.id, rejected_first.id]
        )
        items = {
            item.application_id: item
            for item in (
                await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.ranking_id == ranking.id))
            ).scalars()
        }
        items[rejected_first.id].college_rejected = True
        await db.commit()

        await CollegeReviewService(db).update_ranking_order(
            ranking.id,
            [
                {"item_id": items[first.id].id, "position": 1},
                {"item_id": items[second.id].id, "position": 2},
                {"item_id": items[rejected_first.id].id, "position": 3},
            ],
        )

    async def test_excel_import_rejects_second_round_above_first(self, client, db, login, scholarship, college_user):
        await make_config(db, scholarship.id, code="mr_rank_5")
        first = await add_application(db, scholarship.id, "w1")
        second = await add_application(db, scholarship.id, "w2", application_round=2)
        ranking = await insert_ranking(
            db, scholarship.id, created_by=college_user.id, application_ids=[first.id, second.id]
        )
        login(college_user)

        bad = [
            {"student_id": "w1", "student_name": "Student w1", "rank_position": 2},
            {"student_id": "w2", "student_name": "Student w2", "rank_position": 1},
        ]
        response = await client.post(f"{RANKINGS_URL}/{ranking.id}/import-excel", json=bad)
        assert response.status_code == 422, response.text
        assert "第二梯次申請學生的排名必須在第一梯次之後" in response.text

        # 'N' on the first-round student parks it at the end — allowed
        ok = [
            {"student_id": "w1", "student_name": "Student w1", "rank_position": "N"},
            {"student_id": "w2", "student_name": "Student w2", "rank_position": 1},
        ]
        response = await client.post(f"{RANKINGS_URL}/{ranking.id}/import-excel", json=ok)
        assert response.status_code == 200, response.text

        detail = await client.get(f"{RANKINGS_URL}/{ranking.id}")
        assert detail.status_code == 200, detail.text
        rounds = {
            item["application"]["app_id"]: item["application"]["application_round"]
            for item in detail.json()["data"]["items"]
        }
        assert rounds == {"APP-w1": 1, "APP-w2": 2}


class TestApplicationRoundsEndpoint:
    @pytest_asyncio.fixture
    async def admin(self, db):
        return await make_user(db, "mr_super", role=UserRole.super_admin)

    @pytest_asyncio.fixture
    async def config(self, db, scholarship):
        config = await make_config(db, scholarship.id, code="mr_endpoint")
        config.application_start_date, config.application_end_date = CLOSED
        await db.commit()
        return config

    @staticmethod
    def _round(number=2, window=OPEN, sub_types=("nstc", "moe_1w"), **extra):
        return {
            "round_number": number,
            "application_start_date": window[0].isoformat(),
            "application_end_date": window[1].isoformat(),
            "open_sub_types": list(sub_types),
            **extra,
        }

    async def test_create_update_and_clear_rounds(self, client, db, login, admin, config):
        login(admin)
        url = ROUNDS_URL.format(id=config.id)

        response = await client.put(url, json={"rounds": [self._round(), self._round(3, LATER, ("nstc",))]})
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert [r["round_number"] for r in data["rounds"]] == [2, 3]
        assert data["current_application_round"] == 2
        assert data["available_sub_types"] == ["nstc", "moe_1w"]

        response = await client.put(url, json={"rounds": [self._round(sub_types=("moe_1w",))]})
        assert response.status_code == 200, response.text
        assert [(r["round_number"], r["open_sub_types"]) for r in response.json()["data"]["rounds"]] == [
            (2, ["moe_1w"])
        ]

        listing = await client.get(url)
        assert listing.status_code == 200
        assert listing.json()["data"]["first_round"]["round_number"] == 1

        config_detail = await client.get(f"/api/v1/scholarship-configurations/configurations/{config.id}")
        assert config_detail.status_code == 200, config_detail.text
        assert [r["round_number"] for r in config_detail.json()["data"]["application_rounds"]] == [2]

        response = await client.put(url, json={"rounds": []})
        assert response.status_code == 200, response.text
        assert response.json()["data"]["rounds"] == []

    async def test_rejects_unknown_sub_type(self, client, login, admin, config):
        login(admin)
        response = await client.put(ROUNDS_URL.format(id=config.id), json={"rounds": [self._round(sub_types=("xyz",))]})
        assert response.status_code == 400
        assert "xyz" in response.text

    async def test_rejects_round_before_first_round_ends(self, client, db, login, admin, config):
        config.application_end_date = NOW + timedelta(days=2)
        await db.commit()
        login(admin)
        response = await client.put(ROUNDS_URL.format(id=config.id), json={"rounds": [self._round()]})
        assert response.status_code == 400
        assert "第一梯次" in response.text

    async def test_requires_first_round_window(self, client, db, login, admin, config):
        config.application_start_date = None
        config.application_end_date = None
        await db.commit()
        login(admin)
        response = await client.put(ROUNDS_URL.format(id=config.id), json={"rounds": [self._round()]})
        assert response.status_code == 400

    async def test_cannot_remove_round_with_applications(self, client, db, login, admin, config, scholarship):
        await _add_round(db, config.id)
        await add_application(db, scholarship.id, "e1", application_round=2, configuration_id=config.id)
        login(admin)
        response = await client.put(ROUNDS_URL.format(id=config.id), json={"rounds": []})
        assert response.status_code == 409
        assert "第二梯次（1 件）" in response.text
        remaining = (
            (
                await db.execute(
                    select(ScholarshipApplicationRound).where(ScholarshipApplicationRound.configuration_id == config.id)
                )
            )
            .scalars()
            .all()
        )
        assert [r.round_number for r in remaining] == [2]

    async def test_non_admin_is_refused(self, client, login, college_user, config):
        login(college_user)
        response = await client.put(ROUNDS_URL.format(id=config.id), json={"rounds": []})
        assert response.status_code == 403

    async def test_ranking_deadline_extends_to_last_round(self, db, scholarship, college_user, config):
        config.college_review_end = NOW - timedelta(days=1)
        await db.commit()
        service = CollegeReviewService(db)
        with pytest.raises(Exception, match="已過排名截止時間"):
            await service.assert_ranking_within_deadline(scholarship.id, YEAR, SEMESTER, college_user)

        await _add_round(db, config.id, college_review_start=OPEN[0], college_review_end=OPEN[1])
        await db.refresh(config, attribute_names=["application_rounds"])
        await service.assert_ranking_within_deadline(scholarship.id, YEAR, SEMESTER, college_user)


async def test_round_rows_cascade_with_configuration(db, scholarship):
    config = await make_config(db, scholarship.id, code="mr_cascade")
    await _add_round(db, config.id)
    loaded = (
        await db.execute(
            select(ScholarshipConfiguration)
            .where(ScholarshipConfiguration.id == config.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert [r.round_number for r in loaded.application_rounds] == [2]
    await db.delete(loaded)
    await db.commit()
    assert (await db.execute(select(ScholarshipApplicationRound))).scalars().all() == []

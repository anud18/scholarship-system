"""Pin: 預設分發 plans against the admin's SCREEN, not the saved distribution.

`auto_allocate_preview` used to build its quota tracker purely from persisted
`CollegeRankingItem.is_allocated` rows. An admin who unticked a saved allocation
saw a free slot on screen that the algorithm could not see: it produced no
suggestion for it, and the grid reported 「名額已用盡」 while showing headroom.

These cover the `staged` overlay that fixes it — the caller's on-screen
allocations for every row it renders:

- an unticked row (staged null) releases its slot HERE AND NOW,
- a hand-ticked row (staged non-null) is charged for its slot and is never
  re-suggested, whether or not it was ever saved,
- another college's unsaved ticks still consume the shared pool,
- omitting the overlay keeps the old saved-state behaviour.

The conftest provides `db` as the async session (AsyncSession).
"""

import pytest
import pytest_asyncio

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.services.manual_distribution_service import ManualDistributionService

SCHOLARSHIP_TYPE_ID = 1
ACADEMIC_YEAR = 114
SEMESTER = "first"


# ---------------------------------------------------------------------------
# Fixtures — one college with ONE nstc slot and two ranked candidates, so every
# assertion below is about who holds that single slot.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_user(db):
    from app.models.user import User, UserRole, UserType

    u = User(
        nycu_id="admin_staged_preview",
        email="admin_staged_preview@nycu.edu.tw",
        name="Admin Staged Preview",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def config_one_slot_per_college(db):
    """One nstc slot for college C, one for college D."""
    from app.models.scholarship import ScholarshipConfiguration

    cfg = ScholarshipConfiguration(
        scholarship_type_id=SCHOLARSHIP_TYPE_ID,
        config_code="STAGED-114",
        config_name="Staged overlay 114",
        academic_year=ACADEMIC_YEAR,
        semester=SEMESTER,
        amount=50000,
        has_college_quota=True,
        quotas={"nstc": {"C": 1, "D": 1}},
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@pytest_asyncio.fixture
async def ranking(db, admin_user):
    r = CollegeRanking(
        scholarship_type_id=SCHOLARSHIP_TYPE_ID,
        sub_type_code="nstc",
        academic_year=ACADEMIC_YEAR,
        semester=SEMESTER,
        ranking_name="Staged overlay ranking",
        is_finalized=True,
        ranking_status="finalized",
        created_by=admin_user.id,
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def _make_candidate(db, ranking, admin_user, *, app_id, college, rank, allocated_config_id=None):
    """A ranked applicant for nstc; `allocated_config_id` marks a SAVED allocation.

    Each candidate gets its own user: applications are unique per
    (user, scholarship_type, year, semester).
    """
    from app.models.enums import ReviewStage
    from app.models.scholarship import SubTypeSelectionMode
    from app.models.user import User, UserRole, UserType

    student = User(
        nycu_id=f"student_{app_id}",
        email=f"{app_id}@nycu.edu.tw",
        name=app_id,
        role=UserRole.student,
        user_type=UserType.student,
    )
    db.add(student)
    await db.commit()
    await db.refresh(student)

    app = Application(
        user_id=student.id,
        app_id=app_id,
        scholarship_type_id=SCHOLARSHIP_TYPE_ID,
        academic_year=ACADEMIC_YEAR,
        semester=SEMESTER,
        status=ApplicationStatus.submitted,
        review_stage=ReviewStage.student_draft,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=["nstc"],
        student_data={"std_academyno": college, "std_cname": app_id},
        quota_allocation_status=None,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)

    item = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=app.id,
        rank_position=rank,
        is_allocated=allocated_config_id is not None,
        allocated_sub_type="nstc" if allocated_config_id is not None else None,
        allocation_config_id=allocated_config_id,
        status="allocated" if allocated_config_id is not None else "ranked",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return app, item


@pytest_asyncio.fixture
async def college_c(db, ranking, admin_user, config_one_slot_per_college):
    """Rank 1 holds the college's only SAVED nstc slot; rank 2 is waiting."""
    _, first = await _make_candidate(
        db,
        ranking,
        admin_user,
        app_id="APP-STAGED-C1",
        college="C",
        rank=1,
        allocated_config_id=config_one_slot_per_college.id,
    )
    _, second = await _make_candidate(db, ranking, admin_user, app_id="APP-STAGED-C2", college="C", rank=2)
    return first, second


def _staged(*rows):
    """Build an overlay: (item_id, sub_type or None) pairs."""
    return [
        {
            "ranking_item_id": item_id,
            "sub_type_code": sub_type,
            "allocation_config_id": config_id,
        }
        for item_id, sub_type, config_id in rows
    ]


async def _preview(db, staged=None, college_code=None):
    svc = ManualDistributionService(db)
    suggestions = await svc.auto_allocate_preview(
        scholarship_type_id=SCHOLARSHIP_TYPE_ID,
        academic_year=ACADEMIC_YEAR,
        semester=SEMESTER,
        college_code=college_code,
        staged=staged,
    )
    return {s["ranking_item_id"]: s for s in suggestions}


# ---------------------------------------------------------------------------
# The core fix
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_without_an_overlay_the_saved_allocation_still_holds_the_slot(db, college_c):
    """Baseline: nothing staged, so the saved winner keeps the only slot."""
    first, second = college_c

    by_item = await _preview(db)

    assert first.id not in by_item, "a saved allocation is not re-planned for"
    assert by_item[second.id]["sub_type_code"] is None
    assert by_item[second.id]["reason"] == "quota_full"


@pytest.mark.asyncio
async def test_unticking_a_saved_allocation_releases_the_slot_immediately(db, college_c, config_one_slot_per_college):
    """The heart of it: the admin unticks rank 1 WITHOUT saving.

    The screen now shows a free slot, so the run must hand one out — to rank 1
    again, because releasing a slot does not forfeit your place in the ranking.
    """
    first, second = college_c

    by_item = await _preview(db, staged=_staged((first.id, None, None), (second.id, None, None)))

    assert by_item[first.id]["sub_type_code"] == "nstc"
    assert by_item[first.id]["allocation_config_id"] == config_one_slot_per_college.id
    assert by_item[second.id]["reason"] == "quota_full", "the college still only has one slot"


@pytest.mark.asyncio
async def test_a_hand_ticked_row_takes_the_released_slot_and_is_left_alone(db, college_c, config_one_slot_per_college):
    """Admin unticks rank 1 and ticks rank 2 instead — both unsaved.

    Rank 2 is decided, so it is not re-planned for; its unsaved tick is charged
    against the college's only slot, which is why rank 1 now reads quota_full.
    Reading the database instead would give rank 1 the slot AND leave rank 2
    ticked — two winners for one slot.
    """
    first, second = college_c

    by_item = await _preview(
        db,
        staged=_staged((first.id, None, None), (second.id, "nstc", config_one_slot_per_college.id)),
    )

    assert second.id not in by_item, "a hand-ticked row is decided; never re-suggested"
    assert by_item[first.id]["sub_type_code"] is None
    assert by_item[first.id]["reason"] == "quota_full"


@pytest.mark.asyncio
async def test_re_staging_the_saved_allocation_is_a_no_op(db, college_c, config_one_slot_per_college):
    """The overlay a freshly-loaded screen sends: staged == saved.

    Charging both the saved row and its overlay twin would bill one slot twice,
    turning a merely-full college into an over-drawn one.
    """
    first, second = college_c

    by_item = await _preview(
        db,
        staged=_staged((first.id, "nstc", config_one_slot_per_college.id), (second.id, None, None)),
    )

    assert first.id not in by_item
    assert by_item[second.id]["reason"] == "quota_full"


@pytest.mark.asyncio
async def test_a_variant_spelling_in_the_overlay_still_charges_the_slot(db, college_c, config_one_slot_per_college):
    """Sub-types are free-form strings; " NSTC " must hit the same quota cell."""
    first, second = college_c

    by_item = await _preview(
        db,
        staged=_staged((first.id, " NSTC ", config_one_slot_per_college.id), (second.id, None, None)),
    )

    assert by_item[second.id]["reason"] == "quota_full", "an uncanonical spelling must not free the slot"


# ---------------------------------------------------------------------------
# The pool is shared: one college's unsaved work constrains another's run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_another_colleges_unsaved_tick_consumes_the_shared_pool(
    db, ranking, admin_user, college_c, config_one_slot_per_college
):
    """A single-college run still sees every college's staged state.

    College D's slot is staged by hand; the run for college C must not be
    disturbed by it, but the charge must land — otherwise pressing 預設分發 per
    college in turn over-draws a pool that is counted globally.
    """
    first, second = college_c
    _, d_item = await _make_candidate(db, ranking, admin_user, app_id="APP-STAGED-D1", college="D", rank=1)

    by_item = await _preview(
        db,
        college_code="C",
        staged=_staged(
            (first.id, None, None),
            (second.id, None, None),
            (d_item.id, "nstc", config_one_slot_per_college.id),
        ),
    )

    assert d_item.id not in by_item, "a single-college run only plans for that college"
    assert by_item[first.id]["sub_type_code"] == "nstc", "college C's own slot is untouched by D"


@pytest.mark.asyncio
async def test_a_row_missing_from_the_overlay_falls_back_to_its_saved_state(
    db, ranking, admin_user, college_c, config_one_slot_per_college
):
    """The caller never rendered college D, so D's saved allocation still counts."""
    first, second = college_c
    _, d_item = await _make_candidate(
        db,
        ranking,
        admin_user,
        app_id="APP-STAGED-D2",
        college="D",
        rank=1,
        allocated_config_id=config_one_slot_per_college.id,
    )

    by_item = await _preview(db, college_code="D", staged=_staged((first.id, None, None), (second.id, None, None)))

    assert d_item.id not in by_item, "still allocated in the database, so still decided"


# ---------------------------------------------------------------------------
# Malformed / degenerate overlays
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_same_row_staged_twice_is_rejected(db, college_c, config_one_slot_per_college):
    """`allocate` raises on a duplicated ranking item; so must the preview.

    A dict build would let the last entry win, so the row's slot vanishes from
    the tracker while the screen still shows it taken — and the run hands that
    slot to somebody else.
    """
    first, second = college_c

    with pytest.raises(ValueError, match=f"Duplicate ranking item: {first.id}"):
        await _preview(
            db,
            staged=_staged(
                (first.id, "nstc", config_one_slot_per_college.id),
                (first.id, None, None),
                (second.id, None, None),
            ),
        )


@pytest.mark.asyncio
async def test_an_empty_overlay_means_an_empty_screen_not_a_cleared_one(db, college_c):
    """`staged=[]` says "I render no rows", so the saved state still stands.

    This is why the grid must send an explicit null per row when the admin
    presses 清空 — an empty list would silently restore the very distribution
    they just cleared.
    """
    first, second = college_c

    by_item = await _preview(db, staged=[])

    assert first.id not in by_item, "the saved allocation still holds its slot"
    assert by_item[second.id]["reason"] == "quota_full"

"""
Test cases for College Review Service

Tests critical functionality including:
- Ranking operations with concurrent access protection
- Ranking scope rules (several drafts, finalize keeps one) at the statement level
- Error handling and validation
- Permission checks and data integrity

DB-backed coverage of the scope rules lives in test_college_ranking_scope_service.py.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.services.college_ranking_scope import _has_allocation_state
from app.services.college_review_service import (
    RANKING_SCOPE_LOCK_NAMESPACE,
    CollegeReviewError,
    CollegeReviewService,
    InvalidRankingDataError,
    RankingDiff,
    RankingModificationError,
    RankingNotFoundError,
    RankingScopeConflictError,
    ReviewPermissionError,
)


def _where_sql(stmt) -> str:
    """A statement's WHERE rendered with literal binds (asserts the exact predicate)."""
    return str(stmt.whereclause.compile(compile_kwargs={"literal_binds": True}))


def _scope_sql(semester, college_code) -> str:
    conditions = CollegeReviewService._scope_conditions(2, "default", 114, semester, college_code)
    return " AND ".join(str(c.compile(compile_kwargs={"literal_binds": True})) for c in conditions)


def _mock_result(scalar=None, rows=()):
    """One db.execute() result serving scalar_one_or_none / scalars().all() / all()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    result.scalars.return_value.all.return_value = list(rows)
    result.all.return_value = list(rows)
    return result


class TestCollegeReviewService:
    """Test suite for CollegeReviewService"""

    @pytest.fixture
    def service(self):
        """Create service instance with a mock database session."""
        db = MagicMock()
        db.execute = AsyncMock()
        db.get = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.commit = AsyncMock()
        return CollegeReviewService(db)

    @pytest.fixture
    def sample_ranking(self):
        """Sample ranking for testing"""
        return CollegeRanking(
            id=1,
            scholarship_type_id=1,
            sub_type_code="phd_research",
            academic_year=113,
            semester="FIRST",
            created_by=2001,
            is_finalized=False,
            ranking_status="draft",
        )

    async def test_finalize_locks_the_target_then_only_its_own_scope(self, service):
        """finalize re-reads the target FOR UPDATE, then row-locks the siblings of the
        TARGET's scope only: same college (equality — another college's ranking must
        never be touched, issue #1034), same yearly-normalised semester, target excluded."""
        target = CollegeRanking(
            id=6,
            scholarship_type_id=2,
            sub_type_code="default",
            academic_year=114,
            semester=None,
            college_code="E",
            is_finalized=False,
            ranking_status="draft",
        )
        service.db.get = AsyncMock(return_value=target)
        captured = []

        def _record(stmt, *args, **kwargs):
            captured.append(stmt)
            # 1st: target FOR UPDATE; 2nd: siblings (none); 3rd: item rows to mirror (none).
            return _mock_result(scalar=target if len(captured) == 1 else None)

        service.db.execute = AsyncMock(side_effect=_record)

        result = await service.finalize_ranking(ranking_id=6, finalizer_id=99)

        assert result.ranking is target
        assert result.deleted_rankings == []
        assert target.is_finalized is True
        assert target.ranking_status == "finalized"
        assert target.finalized_by == 99
        service.db.flush.assert_called_once()

        assert len(captured) == 3, f"expected target lock, sibling scan, item rows; got {len(captured)}"
        target_lock, sibling_scan = captured[0], captured[1]
        assert target_lock._for_update_arg is not None
        assert "college_rankings.id = 6" in _where_sql(target_lock)

        assert sibling_scan._for_update_arg is not None, "siblings must be row-locked before they are deleted"
        where_sql = _where_sql(sibling_scan)
        assert "college_rankings.college_code = 'E'" in where_sql
        assert "college_code !=" not in where_sql
        assert "created_by" not in where_sql
        assert "college_rankings.semester IS NULL OR college_rankings.semester = 'yearly'" in where_sql
        assert "college_rankings.id != 6" in where_sql

    async def test_finalize_already_finalized_ranking(self, service):
        """Test finalizing an already finalized ranking"""
        finalized_ranking = CollegeRanking(id=1, is_finalized=True, ranking_status="finalized")

        service.db.get = AsyncMock(return_value=finalized_ranking)
        service.db.execute = AsyncMock(return_value=_mock_result(scalar=finalized_ranking))

        with pytest.raises(RankingModificationError):
            await service.finalize_ranking(ranking_id=1, finalizer_id=2001)

    async def test_finalize_missing_ranking(self, service):
        service.db.get = AsyncMock(return_value=None)

        with pytest.raises(RankingNotFoundError):
            await service.finalize_ranking(ranking_id=404, finalizer_id=2001)
        service.db.execute.assert_not_called()

    async def test_finalize_ranking_deleted_by_a_concurrent_finalize(self, service, sample_ranking):
        """The plain get still sees the draft, but the FOR UPDATE re-read (after the
        scope lock) finds it gone: a sibling's finalize deleted it meanwhile."""
        service.db.get = AsyncMock(return_value=sample_ranking)
        service.db.execute = AsyncMock(return_value=_mock_result(scalar=None))

        with pytest.raises(RankingNotFoundError):
            await service.finalize_ranking(ranking_id=1, finalizer_id=2001)
        service.db.flush.assert_not_called()

    async def test_update_ranking_order_validation(self, service, sample_ranking):
        """Test ranking order update with validation"""
        sample_ranking.items = [
            CollegeRankingItem(id=1, application_id=101, rank_position=1),
            CollegeRankingItem(id=2, application_id=102, rank_position=2),
        ]

        result = MagicMock()
        result.scalar_one_or_none.return_value = sample_ranking
        service.db.execute = AsyncMock(return_value=result)

        new_order = [{"item_id": 1, "position": 2}, {"item_id": 2, "position": 1}]

        ranking = await service.update_ranking_order(ranking_id=1, new_order=new_order)

        assert ranking is not None
        service.db.flush.assert_called_once()
        service.db.refresh.assert_called_once()

    async def test_update_ranking_duplicate_positions(self, service, sample_ranking):
        """Test ranking order update with duplicate positions"""
        new_order = [
            {"item_id": 1, "position": 1},
            {"item_id": 2, "position": 1},  # Duplicate position
        ]

        result = MagicMock()
        result.scalar_one_or_none.return_value = sample_ranking
        service.db.execute = AsyncMock(return_value=result)

        with pytest.raises(InvalidRankingDataError):
            await service.update_ranking_order(ranking_id=1, new_order=new_order)

    async def test_create_ranking_scope_lookup_is_scoped_by_college(self, service):
        """Regression (issue #1034): the scope lookup behind create_ranking's 409 guard
        must be scoped by the creator's college_code (equality), otherwise one college's
        locked ranking would block — or a sibling scan would reach — other colleges."""
        captured = []

        def _record(stmt, *args, **kwargs):
            captured.append(stmt)
            # 1st query is the creator lookup → a college reviewer; nothing else exists.
            return _mock_result(scalar=SimpleNamespace(college_code="E") if len(captured) == 1 else None)

        service.db.execute = AsyncMock(side_effect=_record)

        await service.create_ranking(
            scholarship_type_id=2,
            sub_type_code="default",
            academic_year=114,
            semester="yearly",
            creator_id=52,
        )

        scope_queries = [
            stmt
            for stmt in captured
            if getattr(stmt, "whereclause", None) is not None
            and "college_rankings.sub_type_code" in str(stmt.whereclause)
        ]
        assert scope_queries, "expected a scope lookup on the college_rankings key"
        where_sql = _where_sql(scope_queries[0])
        assert "college_code = 'E'" in where_sql, f"scope must be the creator's college; got: {where_sql}"
        assert "college_code !=" not in where_sql, f"scope must use equality, not !=; got: {where_sql}"
        assert "created_by" not in where_sql, (
            "scope must NOT be per creator (every reviewer of the college shares its rankings); "
            f"got WHERE: {where_sql}"
        )
        # No ranking in scope ⇒ a new draft of the creator's college is inserted.
        [added] = [call.args[0] for call in service.db.add.call_args_list if isinstance(call.args[0], CollegeRanking)]
        assert added.college_code == "E"
        assert added.semester is None

    async def test_create_ranking_refuses_while_scope_holds_a_finalized_ranking(self, service):
        locked = CollegeRanking(
            id=7,
            scholarship_type_id=2,
            sub_type_code="default",
            academic_year=114,
            semester=None,
            college_code="E",
            ranking_name="114 學年度排名",
            is_finalized=True,
            ranking_status="finalized",
        )
        calls = []

        def _record(stmt, *args, **kwargs):
            calls.append(stmt)
            if len(calls) == 1:
                return _mock_result(scalar=SimpleNamespace(college_code="E"))
            return _mock_result(rows=[locked])  # the scope lookup

        service.db.execute = AsyncMock(side_effect=_record)

        with pytest.raises(RankingScopeConflictError) as exc:
            await service.create_ranking(
                scholarship_type_id=2,
                sub_type_code="default",
                academic_year=114,
                semester="yearly",
                creator_id=52,
            )
        assert "114 學年度排名" in str(exc.value)
        assert "解除鎖定" in str(exc.value)
        service.db.add.assert_not_called()
        # creator lookup + scope lookup only — no application query, no insert
        assert len(calls) == 2

    def test_scope_conditions_match_the_college_by_equality(self):
        where_sql = _scope_sql("first", "E")
        assert "college_rankings.college_code = 'E'" in where_sql
        assert "college_rankings.semester = 'first'" in where_sql
        assert "college_rankings.scholarship_type_id = 2" in where_sql
        assert "college_rankings.sub_type_code = 'default'" in where_sql
        assert "college_rankings.academic_year = 114" in where_sql

    @pytest.mark.parametrize("college_code", [None, ""])
    def test_scope_conditions_admin_global_ranking_matches_null_or_empty_college(self, college_code):
        # Mirrors the index's COALESCE(college_code, ''): NULL and '' are one scope.
        where_sql = _scope_sql("first", college_code)
        assert "college_rankings.college_code IS NULL OR college_rankings.college_code = ''" in where_sql

    @pytest.mark.parametrize("semester", [None, "yearly", "Semester.yearly"])
    def test_scope_conditions_yearly_matches_null_or_legacy_spelling(self, semester):
        # Mirrors the index's COALESCE(semester, 'yearly').
        where_sql = _scope_sql(semester, "E")
        assert "college_rankings.semester IS NULL OR college_rankings.semester = 'yearly'" in where_sql

    @pytest.mark.parametrize(
        "semester, college_code, scope_key",
        [
            ("yearly", "E", "2:nstc:114:yearly:E"),
            (None, None, "2:nstc:114:yearly:"),
            ("first", "E", "2:nstc:114:first:E"),
        ],
    )
    async def test_lock_ranking_scope_takes_a_postgres_advisory_lock(self, semester, college_code, scope_key):
        db = MagicMock()
        db.get_bind = MagicMock(return_value=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")))
        db.execute = AsyncMock()

        await CollegeReviewService(db)._lock_ranking_scope(2, "nstc", 114, semester, college_code)

        db.execute.assert_awaited_once()
        statement, params = db.execute.await_args.args
        assert "pg_advisory_xact_lock(:namespace, hashtext(:scope_key))" in str(statement)
        assert params == {"namespace": RANKING_SCOPE_LOCK_NAMESPACE, "scope_key": scope_key}
        # pg_advisory_xact_lock(int4, int4): the namespace must fit a signed int4.
        assert -(2**31) <= RANKING_SCOPE_LOCK_NAMESPACE < 2**31

    @pytest.mark.parametrize("dialect_name", ["sqlite", None])
    async def test_lock_ranking_scope_is_skipped_off_postgres(self, dialect_name):
        db = MagicMock()
        db.get_bind = MagicMock(return_value=SimpleNamespace(dialect=SimpleNamespace(name=dialect_name)))
        db.execute = AsyncMock()

        await CollegeReviewService(db)._lock_ranking_scope(2, "nstc", 114, "first", "E")

        db.execute.assert_not_called()

    def test_exception_hierarchy(self):
        """Test that custom exceptions inherit properly"""
        assert issubclass(RankingNotFoundError, CollegeReviewError)
        assert issubclass(RankingModificationError, CollegeReviewError)
        assert issubclass(InvalidRankingDataError, CollegeReviewError)
        assert issubclass(ReviewPermissionError, CollegeReviewError)
        assert issubclass(RankingScopeConflictError, CollegeReviewError)
        assert issubclass(CollegeReviewError, Exception)


def _item(**overrides):
    """A ranking-item column row as _load_settled_ids reads it (no allocation state)."""
    columns = {
        "is_allocated": False,
        "allocated_sub_type": None,
        "allocation_config_id": None,
        "backup_position": None,
        "backup_allocations": None,
        "status": "ranked",
    }
    return SimpleNamespace(**{**columns, **overrides})


class TestRankingScopePredicates:
    """Pure helpers behind the 'settled ranking' rule and the sync reminder."""

    @pytest.mark.parametrize(
        "overrides",
        [
            {"is_allocated": True},
            # 撤銷/停發 clear is_allocated but keep the slot for 復發.
            {"allocated_sub_type": "nstc"},
            {"allocation_config_id": 3},
            {"backup_position": 1},
            {"backup_allocations": [{"sub_type": "nstc", "backup_position": 1}]},
            {"status": "allocated"},
            {"status": "rejected"},
            {"status": "waitlisted"},
        ],
    )
    def test_item_with_distribution_state_is_settled(self, overrides):
        assert _has_allocation_state(_item(**overrides)) is True

    @pytest.mark.parametrize(
        "overrides",
        [{}, {"status": None}, {"backup_allocations": []}, {"backup_allocations": {}}, {"is_allocated": None}],
    )
    def test_plain_ranked_item_is_not_settled(self, overrides):
        assert _has_allocation_state(_item(**overrides)) is False

    def test_ranking_diff_has_changes(self):
        assert RankingDiff(pending_application_ids=[], stale_application_ids=[]).has_changes is False
        assert RankingDiff(pending_application_ids=[1], stale_application_ids=[]).has_changes is True
        assert RankingDiff(pending_application_ids=[], stale_application_ids=[2]).has_changes is True


class TestAssertCanManageRanking:
    """assert_can_manage_ranking: a college's reviewers (or admins) may act on that
    college's ranking; other colleges may not. Keeps the ranking write/read-by-id
    endpoints consistent with the college-scoped create/list (issue #1034)."""

    @staticmethod
    def _user(*, is_admin=False, is_super_admin=False, college_code=None):
        u = MagicMock()
        u.is_admin.return_value = is_admin
        u.is_super_admin.return_value = is_super_admin
        u.college_code = college_code
        return u

    @staticmethod
    def _ranking(college_code):
        r = MagicMock()
        r.college_code = college_code
        return r

    def _assert(self):
        from app.api.v1.endpoints.college_review._helpers import assert_can_manage_ranking

        return assert_can_manage_ranking

    def test_admin_can_manage_any(self):
        self._assert()(self._ranking("E"), self._user(is_admin=True, college_code=None))

    def test_super_admin_can_manage_any(self):
        self._assert()(self._ranking(None), self._user(is_super_admin=True, college_code=None))

    def test_same_college_reviewer_allowed(self):
        # Second reviewer of college E (not the creator) may manage E's ranking.
        self._assert()(self._ranking("E"), self._user(college_code="E"))

    def test_different_college_reviewer_forbidden(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._assert()(self._ranking("E"), self._user(college_code="B"))
        assert exc.value.status_code == 403

    def test_college_user_cannot_manage_global_null_ranking(self):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._assert()(self._ranking(None), self._user(college_code="E"))
        assert exc.value.status_code == 403

    def test_null_college_user_does_not_match_null_ranking(self):
        # Guard against NULL == NULL accidentally granting access.
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._assert()(self._ranking(None), self._user(college_code=None))
        assert exc.value.status_code == 403

    def test_empty_string_college_codes_are_not_a_match(self):
        # "" is not a valid college; two empty-coded actors must not share access
        # (aligns with the defensive strip-and-reject in export/supplementary-import).
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            self._assert()(self._ranking(""), self._user(college_code=""))
        assert exc.value.status_code == 403


# Integration tests that would require database setup
class TestCollegeReviewServiceIntegration:
    """Integration tests for CollegeReviewService with real database operations"""

    @pytest.mark.integration
    async def test_full_review_workflow(self, db):
        """Test complete review workflow from creation to finalization"""
        # Placeholder — full DB-backed workflow test not yet implemented
        pass

    @pytest.mark.integration
    async def test_concurrent_ranking_modifications(self, db):
        """Test concurrent access protection in real database scenario"""
        # Placeholder — concurrent access test not yet implemented
        pass

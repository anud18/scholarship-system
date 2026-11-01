"""Unit tests for 多梯次申請 (additional application rounds): pure model / schema / helper logic.

The configuration's own application window is 第一梯次 (every sub-type); later rounds
come from ScholarshipApplicationRound rows. Rankings keep 續領 → 第一梯次 → 第二梯次.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError
from app.models.application import Application
from app.models.application_round import ScholarshipApplicationRound
from app.models.enums import ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration
from app.schemas.application_round import ApplicationRoundsUpdate
from app.services.application_builder import validate_sub_types_open_in_round
from app.services.application_round_rules import ApplicationRoundRuleError, validate_rounds_against_config
from app.services.application_service import ApplicationService
from app.services.ranking_groups import (
    RENEWAL_ORDER_ERROR,
    find_group_order_violation,
    ranking_group,
    round_label,
)
from app.services.scholarship_service import ScholarshipService

NOW = datetime.now(timezone.utc)
PAST = (NOW - timedelta(days=30), NOW - timedelta(days=20))
OPEN = (NOW - timedelta(days=1), NOW + timedelta(days=5))
FUTURE = (NOW + timedelta(days=20), NOW + timedelta(days=30))


def _round(number: int, window, sub_types=("nstc",), **review) -> ScholarshipApplicationRound:
    return ScholarshipApplicationRound(
        round_number=number,
        application_start_date=window[0],
        application_end_date=window[1],
        open_sub_types=list(sub_types),
        **review,
    )


def _config(first_window=PAST, rounds=(), **fields) -> ScholarshipConfiguration:
    config = ScholarshipConfiguration(
        academic_year=114,
        config_name="phd 114",
        config_code="phd_114_unit",
        amount=10000,
        application_start_date=first_window[0] if first_window else None,
        application_end_date=first_window[1] if first_window else None,
        **fields,
    )
    config.application_rounds = list(rounds)
    return config


def _app(*, is_renewal=False, application_round=1):
    return SimpleNamespace(is_renewal=is_renewal, application_round=application_round)


class TestCurrentApplicationRound:
    def test_single_round_configuration_behaves_as_before(self):
        assert _config(first_window=OPEN).current_application_round == 1
        assert _config(first_window=OPEN).open_sub_types_for_round(1) is None
        assert _config(first_window=PAST).current_application_round is None
        assert _config(first_window=PAST).is_general_application_period is False
        assert _config(first_window=PAST).is_application_period is False

    def test_second_round_open_after_first_closed(self):
        config = _config(first_window=PAST, rounds=[_round(2, OPEN, ("nstc", "moe_1w"))])
        assert config.current_application_round == 2
        assert config.is_general_application_period is True
        assert config.is_application_period is True
        assert config.current_application_type == "general"
        assert config.open_sub_types_for_round(2) == ["nstc", "moe_1w"]

    def test_no_round_open_between_windows(self):
        config = _config(first_window=PAST, rounds=[_round(2, FUTURE)])
        assert config.current_application_round is None
        assert config.is_application_period is False

    def test_first_round_wins_when_windows_overlap(self):
        config = _config(first_window=OPEN, rounds=[_round(2, OPEN)])
        assert config.current_application_round == 1

    def test_rounds_are_matched_by_number_not_list_order(self):
        config = _config(rounds=[_round(3, FUTURE, ("moe_1w",)), _round(2, OPEN, ("nstc",))])
        assert [r.round_number for r in config.extra_application_rounds] == [2, 3]
        assert config.current_application_round == 2
        assert config.open_sub_types_for_round(3) == ["moe_1w"]
        assert config.open_sub_types_for_round(1) is None


class TestReviewWindows:
    def test_round_window_overrides_general_window(self):
        general = (NOW - timedelta(days=40), NOW - timedelta(days=10))
        round_window = (NOW - timedelta(days=2), NOW + timedelta(days=2))
        config = _config(
            rounds=[_round(2, OPEN, college_review_start=round_window[0], college_review_end=round_window[1])],
            college_review_start=general[0],
            college_review_end=general[1],
            professor_review_start=general[0],
            professor_review_end=general[1],
        )
        assert config.review_window_for("college", False, 1) == general
        assert config.review_window_for("college", False, 2) == round_window
        # A NULL round window falls back to the general one
        assert config.review_window_for("professor", False, 2) == general
        assert config.professor_review_end_for(False, 2) == general[1]

    def test_renewals_ignore_rounds(self):
        renewal = (NOW - timedelta(days=3), NOW + timedelta(days=3))
        config = _config(
            rounds=[_round(2, OPEN, college_review_start=NOW, college_review_end=NOW + timedelta(days=9))],
            renewal_college_review_start=renewal[0],
            renewal_college_review_end=renewal[1],
        )
        assert config.review_window_for("college", True, 2) == renewal

    def test_effective_college_review_end_is_latest_round(self):
        later = NOW + timedelta(days=60)
        config = _config(
            rounds=[_round(2, OPEN, college_review_start=NOW, college_review_end=later)],
            college_review_end=NOW + timedelta(days=1),
        )
        assert config.effective_college_review_end == later
        assert _config(college_review_end=None).effective_college_review_end is None

    def test_unknown_role_raises(self):
        with pytest.raises(ValueError):
            _config().review_window_for("dean", False, 1)


class TestRankingGroups:
    def test_groups(self):
        assert ranking_group(_app(is_renewal=True, application_round=2)) == 0
        assert ranking_group(_app()) == 1
        assert ranking_group(_app(application_round=2)) == 2
        assert ranking_group(_app(application_round=None)) == 1
        assert ranking_group(None) == 1

    def test_round_label(self):
        assert round_label(1) == "第一梯次"
        assert round_label(2) == "第二梯次"
        assert round_label(12) == "第12梯次"

    def test_valid_orders(self):
        assert find_group_order_violation([]) is None
        order = [_app(is_renewal=True), _app(), _app(), _app(application_round=2), _app(application_round=3)]
        assert find_group_order_violation(order) is None

    def test_renewal_after_new_application(self):
        assert find_group_order_violation([_app(), _app(is_renewal=True)]) == RENEWAL_ORDER_ERROR

    def test_second_round_above_first_round(self):
        message = find_group_order_violation([_app(application_round=2), _app()])
        assert message == "第二梯次申請學生的排名必須在第一梯次之後"

    def test_violation_found_past_the_neighbour(self):
        order = [_app(), _app(application_round=3), _app(application_round=2)]
        assert find_group_order_violation(order) == "第三梯次申請學生的排名必須在第二梯次之後"


class TestRoundSchemas:
    @staticmethod
    def _payload(number=2, window=OPEN, sub_types=("NSTC", " moe_1w ", "nstc"), **extra):
        return {
            "round_number": number,
            "application_start_date": window[0].isoformat(),
            "application_end_date": window[1].isoformat(),
            "open_sub_types": list(sub_types),
            **extra,
        }

    def test_normalizes_sub_types(self):
        update = ApplicationRoundsUpdate(rounds=[self._payload()])
        assert update.rounds[0].open_sub_types == ["nstc", "moe_1w"]

    def test_empty_list_is_allowed(self):
        assert ApplicationRoundsUpdate(rounds=[]).rounds == []

    @pytest.mark.parametrize(
        "rounds",
        [
            [{"round_number": 1}],
            [{"round_number": 3}],
            [{"round_number": 2}, {"round_number": 4}],
            [{"open_sub_types": []}],
            [{"open_sub_types": ["  "]}],
            [{"window": (OPEN[1], OPEN[0])}],
            [{"college_review_start": NOW.isoformat()}],
            [{"college_review_start": NOW.isoformat(), "college_review_end": (NOW - timedelta(days=1)).isoformat()}],
            [{"round_number": 2, "window": OPEN}, {"round_number": 3, "window": OPEN}],
        ],
    )
    def test_rejects_invalid_rounds(self, rounds):
        payload = []
        for overrides in rounds:
            overrides = dict(overrides)
            window = overrides.pop("window", OPEN)
            number = overrides.pop("round_number", 2)
            sub_types = overrides.pop("open_sub_types", ("nstc",))
            payload.append(self._payload(number, window, sub_types, **overrides))
        with pytest.raises(PydanticValidationError):
            ApplicationRoundsUpdate(rounds=payload)

    def test_accepts_consecutive_ordered_rounds(self):
        update = ApplicationRoundsUpdate(rounds=[self._payload(3, FUTURE), self._payload(2, OPEN)])
        assert sorted(r.round_number for r in update.rounds) == [2, 3]


class TestSubTypeGate:
    def test_first_round_accepts_everything(self):
        config = _config(rounds=[_round(2, OPEN, ("nstc",))])
        validate_sub_types_open_in_round(config, 1, ["moe_1w"])

    def test_later_round_rejects_closed_sub_type(self):
        config = _config(rounds=[_round(2, OPEN, ("nstc",))])
        validate_sub_types_open_in_round(config, 2, ["NSTC"])
        with pytest.raises(ValidationError, match="第二梯次僅開放申請：nstc；不可申請：moe_1w"):
            validate_sub_types_open_in_round(config, 2, ["nstc", "moe_1w"])

    def test_missing_config_is_a_no_op(self):
        validate_sub_types_open_in_round(None, 2, ["moe_1w"])


class TestFirstSubmitRoundAssignment:
    @staticmethod
    def _draft(config, *, status=ApplicationStatus.draft, sub_types=("nstc",), is_renewal=False, round_number=1):
        application = Application(
            status=status,
            is_renewal=is_renewal,
            application_round=round_number,
            scholarship_subtype_list=list(sub_types),
            sub_scholarship_type=sub_types[0] if sub_types else "general",
        )
        application.scholarship_configuration = config
        return application

    def test_draft_joins_open_round(self):
        config = _config(rounds=[_round(2, OPEN, ("nstc",))])
        application = self._draft(config)
        ApplicationService._assign_application_round_on_first_submit(application)
        assert application.application_round == 2

    def test_draft_with_closed_sub_type_is_rejected(self):
        config = _config(rounds=[_round(2, OPEN, ("nstc",))])
        with pytest.raises(ValidationError):
            ApplicationService._assign_application_round_on_first_submit(self._draft(config, sub_types=("moe_1w",)))

    def test_returned_later_round_application_is_rechecked(self):
        # Security review: a returned 第二梯次 application must not switch to a closed sub-type
        config = _config(rounds=[_round(2, OPEN, ("nstc",))])
        application = self._draft(config, status=ApplicationStatus.returned, sub_types=("moe_1w",), round_number=2)
        with pytest.raises(ValidationError):
            ApplicationService._assign_application_round_on_first_submit(application)
        assert application.application_round == 2

    def test_draft_edit_checks_the_round_it_would_join(self):
        config = _config(rounds=[_round(2, OPEN, ("nstc",))])
        draft = self._draft(config)
        with pytest.raises(ValidationError):
            ApplicationService._check_sub_types_against_round(draft, config, ["moe_1w"])
        ApplicationService._check_sub_types_against_round(draft, config, ["nstc"])

    def test_returned_application_keeps_its_round(self):
        config = _config(rounds=[_round(2, OPEN, ("nstc",))])
        application = self._draft(config, status=ApplicationStatus.returned, sub_types=("moe_1w",))
        ApplicationService._assign_application_round_on_first_submit(application)
        assert application.application_round == 1

    def test_renewal_is_untouched(self):
        config = _config(rounds=[_round(2, OPEN, ("nstc",))])
        application = self._draft(config, is_renewal=True, sub_types=("moe_1w",))
        ApplicationService._assign_application_round_on_first_submit(application)
        assert application.application_round == 1

    def test_draft_outside_every_window_is_refused(self):
        from app.core.exceptions import ApplicationPeriodClosedError

        config = _config(first_window=PAST, rounds=[_round(2, FUTURE, ("nstc",))])
        application = self._draft(config, round_number=1, sub_types=("moe_1w",))
        with pytest.raises(ApplicationPeriodClosedError):
            ApplicationService._assign_application_round_on_first_submit(application)

    def test_configuration_without_windows_is_not_period_gated(self):
        application = self._draft(_config(first_window=None), round_number=1)
        ApplicationService._assign_application_round_on_first_submit(application)
        assert application.application_round == 1


class TestStudentSubTypeRestriction:
    SUBTYPES = [{"value": "nstc"}, {"value": "moe_1w"}]
    INFO = {"nstc": {"eligible": True}, "moe_1w": {"eligible": True}}

    def test_no_restriction_in_first_round(self):
        subtypes, info = ScholarshipService._restrict_subtypes_to_round(self.SUBTYPES, self.INFO, None)
        assert subtypes == self.SUBTYPES
        assert info == self.INFO

    def test_closed_sub_types_are_hidden_and_flagged(self):
        subtypes, info = ScholarshipService._restrict_subtypes_to_round(self.SUBTYPES, self.INFO, ["nstc"])
        assert subtypes == [{"value": "nstc"}]
        assert info["nstc"] == {"eligible": True}
        assert info["moe_1w"] == {"eligible": False, "closed_in_round": True}
        # inputs are not mutated
        assert self.INFO["moe_1w"] == {"eligible": True}

    def test_ineligible_sub_type_keeps_its_own_reason(self):
        info_in = {"nstc": {"eligible": True}, "moe_1w": {"eligible": False, "failed_rules": [{"rule_name": "年級"}]}}
        _subtypes, info = ScholarshipService._restrict_subtypes_to_round([{"value": "nstc"}], info_in, ["nstc"])
        assert info["moe_1w"]["closed_in_round"] is False
        assert info["moe_1w"]["failed_rules"] == [{"rule_name": "年級"}]

    def test_round_fields(self):
        config = _config(rounds=[_round(2, OPEN, ("nstc",)), _round(3, FUTURE, ("moe_1w",))])
        fields = ScholarshipService._application_round_fields(config)
        assert fields["current_application_round"] == 2
        assert fields["current_round_application_end_date"] == OPEN[1]
        assert fields["open_sub_types"] == ["nstc"]
        assert [r["round_number"] for r in fields["application_rounds"]] == [2, 3]
        assert [r["is_open"] for r in fields["application_rounds"]] == [True, False]

    def test_round_fields_when_closed(self):
        fields = ScholarshipService._application_round_fields(_config(first_window=PAST))
        assert fields["current_application_round"] is None
        assert fields["current_round_application_end_date"] is None
        assert fields["open_sub_types"] is None


class TestRoundRules:
    """application_round_rules: shared by the rounds endpoint and the config update."""

    SUB_TYPES = ["nstc", "moe_1w"]

    @staticmethod
    def _cfg(**fields):
        return _config(first_window=PAST, **fields)

    def test_valid_round(self):
        validate_rounds_against_config(self._cfg(), [_round(2, OPEN)], self.SUB_TYPES)

    def test_needs_first_round(self):
        with pytest.raises(ApplicationRoundRuleError, match="一般申請期間"):
            validate_rounds_against_config(_config(first_window=None), [_round(2, OPEN)], [])

    def test_round_before_first_round_ends(self):
        with pytest.raises(ApplicationRoundRuleError, match="不可早於第一梯次"):
            validate_rounds_against_config(_config(first_window=OPEN), [_round(2, OPEN)], ["nstc"])

    def test_unknown_sub_type(self):
        with pytest.raises(ApplicationRoundRuleError, match="xyz"):
            validate_rounds_against_config(self._cfg(), [_round(2, OPEN, ("xyz",))], self.SUB_TYPES)

    def test_fallback_review_window_closed_before_round_ends(self):
        # Code review: a round without its own window falls back to round 1's, long closed
        config = self._cfg(requires_college_review=True, college_review_end=PAST[1])
        with pytest.raises(ApplicationRoundRuleError, match="學院審查期間"):
            validate_rounds_against_config(config, [_round(2, OPEN)], self.SUB_TYPES)

    def test_own_review_window_fixes_it(self):
        config = self._cfg(requires_college_review=True, college_review_end=PAST[1])
        validate_rounds_against_config(
            config, [_round(2, OPEN, college_review_start=OPEN[0], college_review_end=FUTURE[1])], self.SUB_TYPES
        )

    def test_review_not_required_is_not_checked(self):
        config = self._cfg(requires_professor_recommendation=False, professor_review_end=PAST[1])
        validate_rounds_against_config(config, [_round(2, OPEN)], self.SUB_TYPES)

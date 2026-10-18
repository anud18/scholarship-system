"""Rules a configuration's later 申請梯次 must satisfy (多梯次申請).

Checked when the admin saves the rounds AND when the configuration itself is edited,
because a round depends on the configuration's own fields: round 1's window, the
scholarship's sub-types and the general review windows a round falls back to.
"""

from typing import Iterable, List, Optional

from app.models.application_round import as_utc
from app.services.ranking_groups import round_label

_REVIEW_ROLES = (
    ("professor", "教授", "requires_professor_recommendation"),
    ("college", "學院", "requires_college_review"),
)


class ApplicationRoundRuleError(ValueError):
    """A round conflicts with its configuration (surfaced as HTTP 400).

    ``message`` is written for the admin (zh-TW) and is safe to return as-is.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _open_codes(application_round) -> List[str]:
    codes = getattr(application_round, "open_sub_type_codes", None)
    if codes is None:
        codes = application_round.open_sub_types or []
    return [str(code).lower().strip() for code in codes]


def _check_review_windows(config, application_round) -> None:
    """A required review must still be open when the round's applications come in.

    A round without its own window falls back to the configuration's general one,
    which usually closed with round 1 — that would leave the round unreviewable.
    """
    for role, role_name, required_flag in _REVIEW_ROLES:
        if not getattr(config, required_flag, False):
            continue
        end: Optional[object] = getattr(application_round, f"{role}_review_end", None) or getattr(
            config, f"{role}_review_end", None
        )
        if end is not None and as_utc(end) < as_utc(application_round.application_end_date):
            raise ApplicationRoundRuleError(
                f"{round_label(application_round.round_number)}的{role_name}審查期間在申請截止前就已結束，"
                f"請為該梯次設定{role_name}審查期間"
            )


def validate_rounds_against_config(config, rounds: Iterable, sub_type_list: Optional[List[str]] = None) -> None:
    """Raise ApplicationRoundRuleError when ``rounds`` do not fit ``config``.

    ``rounds`` are ApplicationRoundInput payloads or ScholarshipApplicationRound rows.
    ``sub_type_list`` defaults to the configuration's scholarship type's list.
    """
    rounds = sorted(rounds, key=lambda r: r.round_number)
    if not rounds:
        return
    if not config.application_start_date or not config.application_end_date:
        raise ApplicationRoundRuleError("請先設定一般申請期間（第一梯次）再新增其他梯次")
    first_extra = rounds[0]
    if as_utc(first_extra.application_start_date) < as_utc(config.application_end_date):
        raise ApplicationRoundRuleError(
            f"{round_label(first_extra.round_number)}的申請期間不可早於第一梯次（一般申請）結束"
        )

    if sub_type_list is None:
        sub_type_list = config.scholarship_type.sub_type_list if config.scholarship_type else []
    allowed = {code.lower().strip() for code in (sub_type_list or []) if code}
    for application_round in rounds:
        unknown = [code for code in _open_codes(application_round) if code not in allowed]
        if unknown:
            raise ApplicationRoundRuleError(
                f"{round_label(application_round.round_number)}包含此獎學金沒有的子類別：{'、'.join(unknown)}"
            )
        _check_review_windows(config, application_round)

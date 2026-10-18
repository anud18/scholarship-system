"""Schemas for 多梯次申請 (additional application rounds) administration."""

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

# The configuration's own application window is round 1; extra rounds start at 2.
FIRST_EXTRA_ROUND = 2
MAX_EXTRA_ROUNDS = 10


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class ApplicationRoundInput(BaseModel):
    """One later 申請梯次 as the administrator sets it."""

    round_number: int = Field(..., ge=FIRST_EXTRA_ROUND, description="2 = 第二梯次, 3 = 第三梯次 ...")
    application_start_date: datetime
    application_end_date: datetime
    open_sub_types: List[str] = Field(..., min_length=1, description="開放申請的子類別代碼")
    professor_review_start: Optional[datetime] = None
    professor_review_end: Optional[datetime] = None
    college_review_start: Optional[datetime] = None
    college_review_end: Optional[datetime] = None

    @field_validator("open_sub_types")
    @classmethod
    def normalize_sub_types(cls, value: List[str]) -> List[str]:
        normalized = [code.lower().strip() for code in value if code and code.strip()]
        if not normalized:
            raise ValueError("至少需開放一個子類別")
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def check_windows(self) -> "ApplicationRoundInput":
        if _utc(self.application_end_date) <= _utc(self.application_start_date):
            raise ValueError(f"第 {self.round_number} 梯次的申請截止時間必須晚於開始時間")
        for label, start, end in (
            ("教授審查", self.professor_review_start, self.professor_review_end),
            ("學院審查", self.college_review_start, self.college_review_end),
        ):
            if (start is None) != (end is None):
                raise ValueError(f"第 {self.round_number} 梯次的{label}期間需同時設定開始與結束時間")
            if start is not None and _utc(end) <= _utc(start):
                raise ValueError(f"第 {self.round_number} 梯次的{label}結束時間必須晚於開始時間")
        return self


class ApplicationRoundsUpdate(BaseModel):
    """The full list of later rounds of a configuration (replaces the current set)."""

    rounds: List[ApplicationRoundInput] = Field(default_factory=list, max_length=MAX_EXTRA_ROUNDS)

    @model_validator(mode="after")
    def check_sequence(self) -> "ApplicationRoundsUpdate":
        ordered = sorted(self.rounds, key=lambda r: r.round_number)
        expected = list(range(FIRST_EXTRA_ROUND, FIRST_EXTRA_ROUND + len(ordered)))
        if [r.round_number for r in ordered] != expected:
            raise ValueError("梯次編號需從 2 開始連續編號")
        for previous, current in zip(ordered, ordered[1:]):
            if _utc(current.application_start_date) < _utc(previous.application_end_date):
                raise ValueError(f"第 {current.round_number} 梯次的申請期間不可早於第 {previous.round_number} 梯次結束")
        return self

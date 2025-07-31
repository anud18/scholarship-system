"""
Shared enums for the scholarship system
"""

import enum


class Semester(enum.Enum):
    """Semester enum"""
    FIRST = "first"
    SECOND = "second"


class SubTypeSelectionMode(enum.Enum):
    """Sub-type selection mode enum"""
    SINGLE = "single"          # 僅能選擇一個子項目
    MULTIPLE = "multiple"      # 可自由多選
    HIERARCHICAL = "hierarchical"  # 需依序選取：A → AB → ABC


class CycleType(enum.Enum):
    """Application cycle type enum"""
    SEMESTER = "semester"
    YEARLY = "yearly" 
"""
Shared enums for the scholarship system
"""

import enum


class Semester(enum.Enum):
    """Semester enum"""

    first = "first"
    second = "second"
    annual = "annual"  # 全年


class SubTypeSelectionMode(enum.Enum):
    """Sub-type selection mode enum"""

    single = "single"  # 僅能選擇一個子項目
    multiple = "multiple"  # 可自由多選
    hierarchical = "hierarchical"  # 需依序選取：A → AB → ABC


class ApplicationCycle(enum.Enum):
    """Application cycle/period type enum"""

    semester = "semester"
    yearly = "yearly"


class QuotaManagementMode(enum.Enum):
    """Quota management mode enum"""

    none = "none"  # 無配額限制
    simple = "simple"  # 簡單總配額
    college_based = "college_based"  # 學院分配配額
    matrix_based = "matrix_based"  # 矩陣配額管理 (子類型×學院)

"""
Shared enums for the scholarship system
"""

import enum


class Semester(enum.Enum):
    """Semester enum"""
    FIRST = "FIRST"
    SECOND = "SECOND"


class SubTypeSelectionMode(enum.Enum):
    """Sub-type selection mode enum"""
    SINGLE = "single"          # 僅能選擇一個子項目
    MULTIPLE = "multiple"      # 可自由多選
    HIERARCHICAL = "hierarchical"  # 需依序選取：A → AB → ABC


class ApplicationCycle(enum.Enum):
    """Application cycle/period type enum"""
    SEMESTER = "semester"
    YEARLY = "yearly"


class QuotaManagementMode(enum.Enum):
    """Quota management mode enum"""
    NONE = "none"                    # 無配額限制
    SIMPLE = "simple"                # 簡單總配額
    COLLEGE_BASED = "college_based"  # 學院分配配額
    MATRIX_BASED = "matrix_based"    # 矩陣配額管理 (子類型×學院)
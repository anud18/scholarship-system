"""Funding-agency (補助機關) grouping of scholarship sub-type codes.

Several reports collapse sub-types that share a funding source into one
column/label — e.g. 教育部 covers both ``moe_1w`` and ``moe_2w`` (they differ
only in the advisor's matching contribution). Sub-types not listed here have no
agency grouping; callers fall back to the sub-type's own configured name.
"""

from typing import Dict, Optional

SUB_TYPE_AGENCY_LABELS: Dict[str, str] = {
    "nstc": "國科會",
    "moe_1w": "教育部",
    "moe_2w": "教育部",
}


def sub_type_agency_label(sub_type_code: str) -> Optional[str]:
    """Return the funding-agency label for a sub-type code, or None if ungrouped."""
    return SUB_TYPE_AGENCY_LABELS.get((sub_type_code or "").lower().strip())

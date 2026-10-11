"""Scholarship sub-type display names for the exports."""

from typing import Any, Dict


def sub_type_labels_of(scholarship_type: Any) -> Dict[str, str]:
    """sub_type_code → 中文名稱 from the scholarship's sub_type_configs (must be
    eager-loaded); empty for None or a scholarship without configs."""
    labels: Dict[str, str] = {}
    for cfg in getattr(scholarship_type, "sub_type_configs", None) or []:
        if cfg.sub_type_code and cfg.name:
            labels[cfg.sub_type_code] = cfg.name
    return labels

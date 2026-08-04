"""Pure structural validation for the quota matrix {sub_type: {college_code: int}}.

Shared by the create and update scholarship-configuration endpoints so the rules
cannot drift between write paths. Returns a list of human-readable (zh) error
strings; an empty list means the matrix is structurally valid.
"""

from typing import Any, Iterable, List

MAX_CELL_QUOTA = 1000


def validate_quota_matrix(
    quotas: Any,
    allowed_sub_types: Iterable[str],
    allowed_college_codes: Iterable[str],
) -> List[str]:
    errors: List[str] = []
    allowed_sub = set(allowed_sub_types)
    allowed_col = set(allowed_college_codes)

    if not isinstance(quotas, dict):
        return ["配額格式錯誤：必須為物件 {子類型: {學院代碼: 數量}}"]

    for sub_type, row in quotas.items():
        if sub_type not in allowed_sub:
            errors.append(f"未知的子類型：{sub_type}")
            continue
        if not isinstance(row, dict):
            errors.append(f"子類型 {sub_type} 的配額格式錯誤：必須為 {{學院代碼: 數量}}")
            continue
        for college, value in row.items():
            if college not in allowed_col:
                errors.append(f"未知的學院代碼：{college}（子類型 {sub_type}）")
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"配額必須為整數：{sub_type}/{college} = {value!r}")
            elif value < 0 or value > MAX_CELL_QUOTA:
                errors.append(f"配額需介於 0 與 {MAX_CELL_QUOTA} 之間：{sub_type}/{college} = {value}")

    return errors

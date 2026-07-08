"""Shared application-construction helpers.

Single source of truth for logic used by BOTH the student self-submission
path (ApplicationService) and the batch import path (BatchImportService).
Any submitted-application field rule that must stay identical across the
two paths belongs here — that is the module's only admission criterion.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.exceptions import ValidationError
from app.models.enums import ApplicationStatus, ReviewStage
from app.utils.i18n import ScholarshipI18n

logger = logging.getLogger(__name__)

# Mirrors FORCED_FIRST_PREFERENCE in
# frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx:
# the manual preference-ordering UI is hidden; MOE (moe_1w) is always the
# first preference when selected alongside other sub-types.
FORCED_FIRST_PREFERENCE = "moe_1w"


def derive_sub_scholarship_type(scholarship_subtype_list: Optional[List[str]]) -> str:
    """Derive the denormalized scalar `sub_scholarship_type` from the selected
    sub-type list: first entry wins, normalized to lowercase; empty → "general".
    """
    if scholarship_subtype_list:
        return scholarship_subtype_list[0].lower()
    return "general"


def validate_sub_type_for_submission(scholarship, sub_scholarship_type: Optional[str]) -> None:
    """Reject the synthetic "general" category on submission for scholarships
    that define real sub-types, and arbitrary sub-types for scholarships that
    define none. Comparison is case-insensitive.
    """
    if scholarship is None:
        return
    real_sub_types = [st.lower() for st in (scholarship.sub_type_list or []) if st and st.lower() != "general"]
    normalized = (sub_scholarship_type or "general").lower()
    if real_sub_types:
        if normalized not in real_sub_types:
            raise ValidationError("此獎學金需選擇申請類別（" + "、".join(real_sub_types) + "），不可使用通用類別")
    elif normalized != "general":
        raise ValidationError("此獎學金不提供申請類別選擇，不可指定子類別")


def order_sub_type_preferences(sub_types: List[str]) -> List[str]:
    """Order a selected sub-type list the way the student wizard does:
    FORCED_FIRST_PREFERENCE (moe_1w) leads when present; the rest keep
    their given order. Returns a new list.
    """
    if FORCED_FIRST_PREFERENCE in sub_types:
        return [FORCED_FIRST_PREFERENCE] + [st for st in sub_types if st != FORCED_FIRST_PREFERENCE]
    return list(sub_types)


def build_submitted_application_values(scholarship, config) -> Dict[str, Any]:
    """Field values every application must carry the moment it is submitted,
    regardless of which path created it.
    """
    return {
        "status": ApplicationStatus.submitted.value,
        "status_name": ScholarshipI18n.get_application_status_text(ApplicationStatus.submitted.value),
        "review_stage": ReviewStage.student_submitted.value,
        "submitted_at": datetime.now(timezone.utc),
        "amount": config.amount,
        "scholarship_name": config.config_name or scholarship.name,
    }

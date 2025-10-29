"""
Scholarship Eligibility Plugins

This package contains scholarship-specific business logic plugins
that can be used for special eligibility checking and alternate promotion rules.
"""

from app.services.plugins.phd_eligibility_plugin import (
    check_phd_alternate_eligibility,
    check_phd_eligibility,
    is_phd_scholarship,
)

__all__ = [
    "check_phd_eligibility",
    "check_phd_alternate_eligibility",
    "is_phd_scholarship",
]

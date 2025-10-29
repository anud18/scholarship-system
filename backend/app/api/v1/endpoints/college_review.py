"""
College Review API Router

This is the entry point that imports the aggregated router from the college_review package.
The actual implementation is organized in the college_review/ subdirectory:
- application_review.py: Application review endpoints
- ranking_management.py: Ranking management endpoints
- distribution.py: Quota distribution endpoints
- utilities.py: Statistics and utility endpoints
- _helpers.py: Shared helper functions
"""

from app.api.v1.endpoints.college_review import router

__all__ = ["router"]

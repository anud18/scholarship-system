"""Professor (教授) access scoping for applications.

Single source of truth for "may this professor read this application?": a
professor sees exactly the applications assigned to them through
``Application.professor_id``. ``ApplicationService._get_application_model``
(``GET /applications/{id}``) and the file proxy (``endpoints/files.py``) both
call this, so every document the professor's detail dialog lists is also
previewable.

Deliberately NOT ``User.can_access_student_data``: that walks the lazy
``professor_relationships`` collection, which raises MissingGreenlet under an
AsyncSession (issue #1130).
"""

from app.models.application import Application
from app.models.user import User


def professor_user_may_access(user: User, application: Application) -> bool:
    """True when ``application`` is assigned to ``user``; False if unassigned."""
    return application.professor_id is not None and application.professor_id == user.id

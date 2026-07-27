"""
HTTP-layer tests for the unified review endpoints (app/api/v1/endpoints/reviews.py).

Focus (issue #1081 follow-up): authorization scoping, review-flow policy,
input validation, and the {success, message, data} response envelope.

These tests exercise the real FastAPI app over ASGI with the in-memory SQLite
database from conftest. Authentication is simulated by overriding the
`get_current_user` dependency with real DB-backed User rows so that all
role-scoping logic downstream of authentication runs unmodified.
"""

import pytest
import pytest_asyncio
from sqlalchemy import delete as sa_delete

from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipSubTypeConfig, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType

REVIEWS_PREFIX = "/api/v1/reviews"


def _submit_url(application_id: int) -> str:
    return f"{REVIEWS_PREFIX}/applications/{application_id}/review"


@pytest_asyncio.fixture
async def login():
    """Return a function that authenticates the test client as a given User.

    Overrides the get_current_user dependency (auth layer) while leaving every
    downstream role/permission check intact.
    """
    from app.core.security import get_current_user
    from app.main import app

    def _login(user: User) -> None:
        async def _override():
            return user

        app.dependency_overrides[get_current_user] = _override

    yield _login
    from app.core.security import get_current_user as _gcu
    from app.main import app as _app

    _app.dependency_overrides.pop(_gcu, None)


@pytest_asyncio.fixture
async def review_users(db):
    """Real DB users covering every role involved in the review flow."""
    users = {
        "student": User(
            nycu_id="rev_student",
            name="Review Student",
            email="rev_student@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        ),
        "other_student": User(
            nycu_id="rev_student2",
            name="Other Student",
            email="rev_student2@test.edu",
            user_type=UserType.student,
            role=UserRole.student,
        ),
        "professor": User(
            nycu_id="rev_prof",
            name="Review Professor",
            email="rev_prof@test.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        ),
        "unrelated_professor": User(
            nycu_id="rev_prof2",
            name="Unrelated Professor",
            email="rev_prof2@test.edu",
            user_type=UserType.employee,
            role=UserRole.professor,
        ),
        "college": User(
            nycu_id="rev_college",
            name="College Reviewer",
            email="rev_college@test.edu",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code="ENG",
        ),
        "admin": User(
            nycu_id="rev_admin",
            name="Review Admin",
            email="rev_admin@test.edu",
            user_type=UserType.employee,
            role=UserRole.admin,
        ),
    }
    for user in users.values():
        db.add(user)
    await db.commit()
    for user in users.values():
        await db.refresh(user)
    return users


@pytest_asyncio.fixture
async def review_scholarship(db) -> ScholarshipType:
    scholarship = ScholarshipType(
        code="rev_phd_scholarship",
        name="Review Test Scholarship",
        description="Scholarship used by review endpoint tests",
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)

    # Active sub-type configs are what the review form actually renders, and
    # the submit-time coverage check is scoped to them. Without these rows the
    # dialogs would fall back to a single synthetic "default" item, so the
    # multi-sub-type behaviour under test would not be reachable.
    for order, (code, name) in enumerate((("nstc", "國科會"), ("moe_1w", "教育部一萬")), start=1):
        db.add(
            ScholarshipSubTypeConfig(
                scholarship_type_id=scholarship.id,
                sub_type_code=code,
                name=name,
                display_order=order,
                is_active=True,
            )
        )
    await db.commit()
    return scholarship


@pytest_asyncio.fixture
async def review_application(db, review_users, review_scholarship) -> Application:
    """Application owned by `student` with two reviewable sub-types."""
    application = Application(
        app_id="APP-114-1-00001",
        user_id=review_users["student"].id,
        professor_id=review_users["professor"].id,
        scholarship_type_id=review_scholarship.id,
        sub_type_selection_mode=SubTypeSelectionMode.multiple,
        status=ApplicationStatus.under_review.value,
        academic_year=114,
        semester="first",
        scholarship_subtype_list=["nstc", "moe_1w"],
        student_data={"std_stdcode": "310460031", "std_cname": "Review Student"},
        submitted_form_data={},
        agree_terms=True,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


def _approve_items(*codes):
    return {"items": [{"sub_type_code": code, "recommendation": "approve", "comments": None} for code in codes]}


def _reject_items(*codes):
    return {
        "items": [{"sub_type_code": code, "recommendation": "reject", "comments": f"rejected {code}"} for code in codes]
    }


@pytest.mark.api
class TestReviewsAuthorization:
    """Authorization scoping for the unified review endpoints."""

    async def test_submit_review_unauthenticated_401(self, client, review_application):
        response = await client.post(_submit_url(review_application.id), json=_approve_items("nstc"))
        assert response.status_code == 401
        assert response.json()["success"] is False

    async def test_get_application_reviews_unauthenticated_401(self, client, review_application):
        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/reviews")
        assert response.status_code == 401

    async def test_student_cannot_submit_review(self, client, login, review_users, review_application):
        login(review_users["student"])
        response = await client.post(_submit_url(review_application.id), json=_approve_items("nstc"))
        assert response.status_code == 403

    async def test_student_cannot_create_review_via_reviews_endpoint(
        self, client, login, review_users, review_application
    ):
        """POST /reviews has no explicit role gate; the student is stopped by the
        reviewable-subtypes filter (unknown role -> empty list -> 403)."""
        login(review_users["student"])
        payload = {"application_id": review_application.id, **_approve_items("nstc")}
        response = await client.post(f"{REVIEWS_PREFIX}/reviews", json=payload)
        assert response.status_code == 403

    async def test_student_cannot_read_application_reviews(self, client, login, review_users, review_application):
        # Enforced rule (#1081): students may not read the full reviews list for
        # any application (they use review-status for their own progress).
        login(review_users["other_student"])
        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/reviews")
        assert response.status_code == 403

    async def test_owning_student_cannot_read_application_reviews(
        self, client, login, review_users, review_application
    ):
        # Enforced rule (#1081): even the owning student is denied the full
        # reviews list — students only get review-status.
        login(review_users["student"])
        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/reviews")
        assert response.status_code == 403

    async def test_assigned_professor_can_read_application_reviews(
        self, client, login, review_users, review_application
    ):
        # Enforced rule (#1081): the application's assigned professor may read
        # its reviews.
        login(review_users["professor"])
        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/reviews")
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_unrelated_professor_cannot_read_application_reviews(
        self, client, login, review_users, review_application
    ):
        # Enforced rule (#1081): a professor who is not the assigned advisor may
        # not read another application's reviews.
        login(review_users["unrelated_professor"])
        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/reviews")
        assert response.status_code == 403

    async def test_college_can_read_application_reviews(self, client, login, review_users, review_application):
        login(review_users["college"])
        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/reviews")
        assert response.status_code == 200

    async def test_student_cannot_read_other_application_review_status(
        self, client, login, review_users, review_application
    ):
        # Enforced rule (#1081): a student may query review-status ONLY for their
        # own application; another student's application is denied.
        login(review_users["other_student"])
        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/review-status")
        assert response.status_code == 403

    async def test_owning_student_can_read_own_review_status(self, client, login, review_users, review_application):
        # Enforced rule (#1081): the owning student CAN read their own
        # review-status (progress display).
        login(review_users["student"])
        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/review-status")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert "decision_reason" in body["data"]

    async def test_student_cannot_read_single_review(self, client, login, review_users, review_application):
        # First create a review as the assigned professor.
        login(review_users["professor"])
        created = await client.post(
            f"{REVIEWS_PREFIX}/reviews",
            json={"application_id": review_application.id, **_approve_items("nstc", "moe_1w")},
        )
        assert created.status_code == 201
        review_id = created.json()["data"]["id"]

        # Enforced rule (#1081): GET /reviews/{id} denies students.
        login(review_users["other_student"])
        response = await client.get(f"{REVIEWS_PREFIX}/reviews/{review_id}")
        assert response.status_code == 403

    async def test_unrelated_professor_cannot_read_single_review(self, client, login, review_users, review_application):
        login(review_users["professor"])
        created = await client.post(
            f"{REVIEWS_PREFIX}/reviews",
            json={"application_id": review_application.id, **_approve_items("nstc", "moe_1w")},
        )
        assert created.status_code == 201
        review_id = created.json()["data"]["id"]

        # Enforced rule (#1081): a professor who neither authored the review nor
        # advises the application is denied.
        login(review_users["unrelated_professor"])
        response = await client.get(f"{REVIEWS_PREFIX}/reviews/{review_id}")
        assert response.status_code == 403

    async def test_admin_can_read_single_review(self, client, login, review_users, review_application):
        login(review_users["professor"])
        created = await client.post(
            f"{REVIEWS_PREFIX}/reviews",
            json={"application_id": review_application.id, **_approve_items("nstc", "moe_1w")},
        )
        assert created.status_code == 201
        review_id = created.json()["data"]["id"]

        login(review_users["admin"])
        response = await client.get(f"{REVIEWS_PREFIX}/reviews/{review_id}")
        assert response.status_code == 200
        assert response.json()["data"]["reviewer_name"] == "Review Professor"

    async def test_unrelated_professor_cannot_submit_review(self, client, login, review_users, review_application):
        # Enforced rule (#1081): the multi-role route POST /applications/{id}/review
        # verifies the professor is the application's assigned advisor. An
        # unrelated professor is denied.
        login(review_users["unrelated_professor"])
        response = await client.post(_submit_url(review_application.id), json=_approve_items("nstc"))
        assert response.status_code == 403

    async def test_assigned_professor_can_submit_review(self, client, login, review_users, review_application):
        # Enforced rule (#1081): the assigned professor CAN still submit.
        # Must cover every applied sub-type — a partial submission is a 422.
        login(review_users["professor"])
        response = await client.post(_submit_url(review_application.id), json=_approve_items("nstc", "moe_1w"))
        assert response.status_code == 200
        assert response.json()["success"] is True

    async def test_unrelated_professor_cannot_create_review_via_reviews_endpoint(
        self, client, login, review_users, review_application
    ):
        # Enforced rule (#1081): POST /reviews also verifies the advisor
        # relationship for professors.
        login(review_users["unrelated_professor"])
        payload = {"application_id": review_application.id, **_approve_items("nstc")}
        response = await client.post(f"{REVIEWS_PREFIX}/reviews", json=payload)
        assert response.status_code == 403

    async def test_professor_submit_nonexistent_application_403(self, client, login, review_users):
        # Current behavior: the submit route never 404s on a missing
        # application — get_reviewable_subtypes returns [] and the sub-type
        # check yields 403 instead.
        login(review_users["professor"])
        response = await client.post(_submit_url(999999), json=_approve_items("nstc"))
        assert response.status_code == 403

    async def test_college_cannot_review_professor_rejected_subtype(
        self, client, login, review_users, review_application
    ):
        login(review_users["professor"])
        rejected = await client.post(_submit_url(review_application.id), json=_reject_items("nstc", "moe_1w"))
        assert rejected.status_code == 200

        login(review_users["college"])
        response = await client.post(_submit_url(review_application.id), json=_approve_items("nstc"))
        assert response.status_code == 403

    async def test_admin_reviewable_subtypes_empty_after_professor_reject(
        self, client, login, review_users, review_application
    ):
        login(review_users["professor"])
        rejected = await client.post(_submit_url(review_application.id), json=_reject_items("nstc", "moe_1w"))
        assert rejected.status_code == 200

        login(review_users["admin"])
        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/reviewable-subtypes")
        assert response.status_code == 200
        assert response.json()["data"]["reviewable_subtypes"] == []


@pytest.mark.api
class TestReviewsPolicy:
    """Review-flow policy: professor full-reject is terminal for the professor."""

    async def test_professor_full_reject_sets_application_rejected(
        self, client, login, db, review_users, review_application
    ):
        login(review_users["professor"])
        response = await client.post(_submit_url(review_application.id), json=_reject_items("nstc", "moe_1w"))
        assert response.status_code == 200
        assert response.json()["data"]["recommendation"] == "reject"

        await db.refresh(review_application)
        assert review_application.status == ApplicationStatus.rejected

    async def test_professor_cannot_rereview_after_full_reject(self, client, login, review_users, review_application):
        # Review-Flow Policy (#1081): a professor full-reject is terminal — the
        # second professor review on this unified multi-role route must now be
        # rejected with 403 (mirrors the /professor/applications/{id}/review
        # route). Previously get_reviewable_subtypes returned ALL sub-types for
        # professors, letting them silently overwrite a terminal reject.
        login(review_users["professor"])
        first = await client.post(_submit_url(review_application.id), json=_reject_items("nstc", "moe_1w"))
        assert first.status_code == 200

        second = await client.post(_submit_url(review_application.id), json=_approve_items("nstc", "moe_1w"))
        assert second.status_code == 403
        assert second.json()["success"] is False

    async def test_review_status_overall_rejected_after_full_reject(
        self, client, login, review_users, review_application
    ):
        login(review_users["professor"])
        rejected = await client.post(_submit_url(review_application.id), json=_reject_items("nstc", "moe_1w"))
        assert rejected.status_code == 200

        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/review-status")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["overall_status"] == "rejected"
        assert set(data["subtype_statuses"].keys()) == {"nstc", "moe_1w"}


@pytest.mark.api
class TestReviewSubmissionCoverage:
    """A submission must decide EXACTLY the reviewer's currently-reviewable sub-types.

    A reviewer's items are deleted and recreated on every submit, so a payload
    that omits a sub-type would silently destroy that sub-type's earlier verdict
    — and would leave the application unable to reach a final status. The
    submission is rejected instead of being partially applied.
    """

    async def test_partial_submission_is_rejected(self, client, login, review_users, review_application):
        # review_application applies for ["nstc", "moe_1w"]; deciding only nstc
        # used to be accepted (and, for a reject, terminally rejected the app).
        login(review_users["professor"])
        response = await client.post(_submit_url(review_application.id), json=_approve_items("nstc"))
        assert response.status_code == 422
        assert "moe_1w" in response.json()["message"]

    async def test_partial_reject_does_not_reject_the_application(
        self, db, client, login, review_users, review_application
    ):
        """The dangerous case: a lone reject must not slip through as "all rejected"."""
        login(review_users["professor"])
        payload = {"items": [{"sub_type_code": "nstc", "recommendation": "reject", "comments": "not eligible"}]}
        response = await client.post(_submit_url(review_application.id), json=payload)
        assert response.status_code == 422

        await db.refresh(review_application)
        status_value = getattr(review_application.status, "value", review_application.status)
        assert status_value != ApplicationStatus.rejected.value

    async def test_full_submission_is_accepted(self, client, login, review_users, review_application):
        login(review_users["professor"])
        response = await client.post(_submit_url(review_application.id), json=_approve_items("nstc", "moe_1w"))
        assert response.status_code == 200

    async def test_duplicate_subtype_is_rejected(self, client, login, review_users, review_application):
        login(review_users["professor"])
        response = await client.post(_submit_url(review_application.id), json=_approve_items("nstc", "nstc", "moe_1w"))
        assert response.status_code == 422

    async def test_subtype_without_active_config_does_not_block_submission(
        self, db, client, login, review_users, review_application
    ):
        """Coverage must not demand a sub-type the review form cannot render.

        Sub-types are quotas-driven, so a student can hold one that has no
        ``ScholarshipSubTypeConfig`` row (or whose row was deactivated
        mid-cycle). Those never appear in the form, so requiring them would
        make the application permanently unsubmittable.
        """
        review_application.scholarship_subtype_list = ["nstc", "moe_1w", "moe_2w"]
        db.add(review_application)
        await db.commit()

        login(review_users["professor"])
        response = await client.post(_submit_url(review_application.id), json=_approve_items("nstc", "moe_1w"))
        assert response.status_code == 200, response.text

    async def test_submission_allowed_when_no_subtype_has_an_active_config(
        self, db, client, login, review_users, review_application
    ):
        """With nothing renderable the dialogs submit a synthetic "default" item."""
        await db.execute(sa_delete(ScholarshipSubTypeConfig))
        await db.commit()

        login(review_users["professor"])
        response = await client.post(_submit_url(review_application.id), json=_approve_items("default"))
        assert response.status_code == 200, response.text

    async def test_professor_update_path_also_requires_full_coverage(
        self, db, client, login, review_users, review_application
    ):
        """PUT /professor/.../review/{id} is the path the UI takes on RE-review.

        It replaces the reviewer's items wholesale, so an incomplete payload
        deleted the verdicts it omitted — caught by an end-to-end Playwright
        run after the POST path was already guarded.
        """
        login(review_users["professor"])
        created = await client.post(
            _submit_url(review_application.id),
            json={
                "items": [
                    {"sub_type_code": "nstc", "recommendation": "approve"},
                    {"sub_type_code": "moe_1w", "recommendation": "reject", "comments": "not eligible"},
                ]
            },
        )
        assert created.status_code == 200
        review_id = created.json()["data"]["id"]

        partial = await client.put(
            f"/api/v1/professor/applications/{review_application.id}/review/{review_id}",
            json={"items": [{"sub_type_code": "nstc", "recommendation": "approve"}]},
        )
        assert partial.status_code == 422

        # The omitted sub-type's verdict must still be on record.
        stored = await client.get(_submit_url(review_application.id))
        assert stored.status_code == 200
        assert sorted(item["sub_type_code"] for item in stored.json()["data"]["items"]) == ["moe_1w", "nstc"]

    async def test_college_must_cover_subtypes_professor_left_open(
        self, client, login, review_users, review_application
    ):
        """College's required set is its own reviewable set, not the full applied list."""
        login(review_users["professor"])
        prof = await client.post(_submit_url(review_application.id), json=_approve_items("nstc", "moe_1w"))
        assert prof.status_code == 200

        login(review_users["college"])
        partial = await client.post(_submit_url(review_application.id), json=_approve_items("nstc"))
        assert partial.status_code == 422

        full = await client.post(_submit_url(review_application.id), json=_approve_items("nstc", "moe_1w"))
        assert full.status_code == 200


class TestReviewsValidation:
    """Input validation and not-found handling."""

    async def test_submit_review_empty_items_422(self, client, login, review_users, review_application):
        login(review_users["professor"])
        response = await client.post(_submit_url(review_application.id), json={"items": []})
        assert response.status_code == 422
        assert response.json()["success"] is False

    async def test_submit_review_invalid_recommendation_422(self, client, login, review_users, review_application):
        login(review_users["professor"])
        payload = {"items": [{"sub_type_code": "nstc", "recommendation": "maybe"}]}
        response = await client.post(_submit_url(review_application.id), json=payload)
        assert response.status_code == 422

    async def test_submit_review_missing_body_422(self, client, login, review_users, review_application):
        login(review_users["professor"])
        response = await client.post(_submit_url(review_application.id), json={})
        assert response.status_code == 422

    async def test_reject_without_comments_400(self, client, login, review_users, review_application):
        login(review_users["professor"])
        # Covers every applied sub-type so the submission clears the coverage
        # check and actually reaches the reject-needs-comments validation.
        payload = {
            "items": [
                {"sub_type_code": "nstc", "recommendation": "reject", "comments": None},
                {"sub_type_code": "moe_1w", "recommendation": "approve", "comments": None},
            ]
        }
        response = await client.post(_submit_url(review_application.id), json=payload)
        assert response.status_code == 400

    async def test_submit_review_unknown_subtype_403(self, client, login, review_users, review_application):
        login(review_users["professor"])
        response = await client.post(_submit_url(review_application.id), json=_approve_items("not_a_subtype"))
        assert response.status_code == 403

    async def test_submit_review_invalid_application_id_400(self, client, login, review_users):
        login(review_users["professor"])
        response = await client.post(_submit_url(0), json=_approve_items("nstc"))
        assert response.status_code == 400

    async def test_create_review_nonexistent_application_404(self, client, login, review_users):
        login(review_users["professor"])
        payload = {"application_id": 999999, **_approve_items("nstc")}
        response = await client.post(f"{REVIEWS_PREFIX}/reviews", json=payload)
        assert response.status_code == 404

    async def test_get_review_not_found_404(self, client, login, review_users):
        login(review_users["admin"])
        response = await client.get(f"{REVIEWS_PREFIX}/reviews/999999")
        assert response.status_code == 404

    async def test_get_application_reviews_not_found_404(self, client, login, review_users):
        login(review_users["admin"])
        response = await client.get(f"{REVIEWS_PREFIX}/applications/999999/reviews")
        assert response.status_code == 404

    async def test_reviewable_subtypes_not_found_404(self, client, login, review_users):
        login(review_users["professor"])
        response = await client.get(f"{REVIEWS_PREFIX}/applications/999999/reviewable-subtypes")
        assert response.status_code == 404


@pytest.mark.api
class TestReviewsEnvelopeAndFlow:
    """Happy-path behavior and the {success, message, data} envelope."""

    async def test_professor_submit_review_envelope(self, client, login, review_users, review_application):
        login(review_users["professor"])
        response = await client.post(_submit_url(review_application.id), json=_approve_items("nstc", "moe_1w"))
        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) >= {"success", "message", "data"}
        assert body["success"] is True
        data = body["data"]
        assert data["application_id"] == review_application.id
        assert data["reviewer_id"] == review_users["professor"].id
        assert data["recommendation"] == "approve"
        assert {item["sub_type_code"] for item in data["items"]} == {"nstc", "moe_1w"}

    async def test_create_review_endpoint_201_envelope(self, client, login, review_users, review_application):
        login(review_users["professor"])
        payload = {"application_id": review_application.id, **_approve_items("nstc", "moe_1w")}
        response = await client.post(f"{REVIEWS_PREFIX}/reviews", json=payload)
        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["reviewer_role"] in ("professor", "UserRole.professor")
        assert len(body["data"]["items"]) == 2

    async def test_subtype_code_is_normalized(self, client, login, review_users, review_application):
        login(review_users["professor"])
        payload = {
            "items": [
                {"sub_type_code": " NSTC ", "recommendation": "approve"},
                {"sub_type_code": "moe_1w", "recommendation": "approve"},
            ]
        }
        response = await client.post(_submit_url(review_application.id), json=payload)
        assert response.status_code == 200
        items = response.json()["data"]["items"]
        # Padded/upper-cased code is normalised before it is stored, and the
        # coverage check matches on the normalised form.
        assert sorted(item["sub_type_code"] for item in items) == ["moe_1w", "nstc"]

    async def test_get_own_review_returns_null_when_absent(self, client, login, review_users, review_application):
        login(review_users["professor"])
        response = await client.get(_submit_url(review_application.id))
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["data"] is None

    async def test_get_own_review_after_submit(self, client, login, review_users, review_application):
        login(review_users["professor"])
        submitted = await client.post(_submit_url(review_application.id), json=_approve_items("nstc", "moe_1w"))
        assert submitted.status_code == 200

        response = await client.get(_submit_url(review_application.id))
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["reviewer_id"] == review_users["professor"].id
        assert sorted(item["sub_type_code"] for item in data["items"]) == ["moe_1w", "nstc"]

    async def test_reviewable_subtypes_professor_sees_all(self, client, login, review_users, review_application):
        login(review_users["professor"])
        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/reviewable-subtypes")
        assert response.status_code == 200
        data = response.json()["data"]
        assert sorted(data["reviewable_subtypes"]) == ["moe_1w", "nstc"]
        assert sorted(data["all_subtypes"]) == ["moe_1w", "nstc"]

    async def test_application_reviews_list_after_submit(self, client, login, review_users, review_application):
        login(review_users["professor"])
        submitted = await client.post(_submit_url(review_application.id), json=_approve_items("nstc", "moe_1w"))
        assert submitted.status_code == 200

        response = await client.get(f"{REVIEWS_PREFIX}/applications/{review_application.id}/reviews")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert isinstance(body["data"], list)
        assert len(body["data"]) == 1
        assert body["data"][0]["reviewer_name"] == "Review Professor"

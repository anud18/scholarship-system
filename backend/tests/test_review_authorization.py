"""
測試審查授權邏輯

驗證修正後的授權規則：
- College 可以審查：未被拒絕的 OR 被自己拒絕的（可覆蓋修改）
- College 不能審查：被 professor 拒絕的
- Admin 可以審查：未被拒絕的 OR 被自己拒絕的（可覆蓋修改）
- Admin 不能審查：被 professor 或 college 拒絕的
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application, ApplicationStatus
from app.models.enums import Semester
from app.models.scholarship import SubTypeSelectionMode
from app.models.user import User, UserRole
from app.services.review_service import ReviewService


@pytest_asyncio.fixture
async def test_application(db_session: AsyncSession) -> Application:
    """建立測試申請"""
    # 建立學生
    student = User(
        nycu_id="test_student",
        email="student@test.com",
        name="Test Student",
        role=UserRole.student.value,
    )
    db_session.add(student)
    await db_session.flush()

    # 建立申請
    application = Application(
        app_id="APP-114-1-00001",
        user_id=student.id,
        scholarship_type_id=1,
        scholarship_subtype_list=["nstc", "moe_1w", "moe_2w"],
        sub_type_selection_mode=SubTypeSelectionMode.multiple.value,
        academic_year=114,
        semester=Semester.first.value,
        status=ApplicationStatus.submitted.value,
        student_data={"std_stdcode": "test001", "std_cname": "測試學生"},
    )
    db_session.add(application)
    await db_session.commit()
    await db_session.refresh(application)

    return application


@pytest_asyncio.fixture
async def professor_user(db_session: AsyncSession) -> User:
    """建立 professor 測試帳號"""
    user = User(
        nycu_id="test_professor",
        email="professor@test.com",
        name="Test Professor",
        role=UserRole.professor.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def college_user(db_session: AsyncSession) -> User:
    """建立 college 測試帳號"""
    user = User(
        nycu_id="test_college",
        email="college@test.com",
        name="Test College",
        role=UserRole.college.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """建立 admin 測試帳號"""
    user = User(
        nycu_id="test_admin",
        email="admin@test.com",
        name="Test Admin",
        role=UserRole.admin.value,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_college_can_review_unrejectted_items(
    db_session: AsyncSession, test_application: Application, college_user: User
):
    """測試：College 可以審查尚未被拒絕的項目"""
    review_service = ReviewService(db_session)

    # 取得可審查的子項目
    reviewable = await review_service.get_reviewable_subtypes(test_application.id, college_user.role)

    # 應該可以審查所有未被拒絕的子項目
    assert "nstc" in reviewable
    assert "moe_1w" in reviewable
    assert "moe_2w" in reviewable


@pytest.mark.asyncio
async def test_college_can_override_own_rejection(
    db_session: AsyncSession, test_application: Application, college_user: User
):
    """測試：College 可以覆蓋修改自己已拒絕的項目"""
    review_service = ReviewService(db_session)

    # College 第一次審查：拒絕 'nstc'
    await review_service.create_review(
        application_id=test_application.id,
        reviewer_id=college_user.id,
        items=[{"sub_type_code": "nstc", "recommendation": "reject", "comments": "不符合要求"}],
    )

    # College 第二次查詢：應該仍然可以看到 'nstc'（可覆蓋修改）
    reviewable = await review_service.get_reviewable_subtypes(test_application.id, college_user.role)

    assert "nstc" in reviewable, "College should be able to override own rejection"


@pytest.mark.asyncio
async def test_college_cannot_review_professor_rejection(
    db_session: AsyncSession, test_application: Application, professor_user: User, college_user: User
):
    """測試：College 不能審查 professor 已拒絕的項目"""
    review_service = ReviewService(db_session)

    # Professor 審查：拒絕 'nstc'
    await review_service.create_review(
        application_id=test_application.id,
        reviewer_id=professor_user.id,
        items=[{"sub_type_code": "nstc", "recommendation": "reject", "comments": "研究計畫不符合"}],
    )

    # College 查詢：不應該看到 'nstc'
    reviewable = await review_service.get_reviewable_subtypes(test_application.id, college_user.role)

    assert "nstc" not in reviewable, "College should NOT be able to review professor-rejected items"
    assert "moe_1w" in reviewable, "College should still see other unrejectted items"


@pytest.mark.asyncio
async def test_admin_can_review_unrejectted_items(
    db_session: AsyncSession, test_application: Application, admin_user: User
):
    """測試：Admin 可以審查尚未被拒絕的項目"""
    review_service = ReviewService(db_session)

    reviewable = await review_service.get_reviewable_subtypes(test_application.id, admin_user.role)

    assert "nstc" in reviewable
    assert "moe_1w" in reviewable
    assert "moe_2w" in reviewable


@pytest.mark.asyncio
async def test_admin_can_override_own_rejection(
    db_session: AsyncSession, test_application: Application, admin_user: User
):
    """測試：Admin 可以覆蓋修改自己已拒絕的項目"""
    review_service = ReviewService(db_session)

    # Admin 第一次審查：拒絕 'nstc'
    await review_service.create_review(
        application_id=test_application.id,
        reviewer_id=admin_user.id,
        items=[{"sub_type_code": "nstc", "recommendation": "reject", "comments": "不符合政策"}],
    )

    # Admin 第二次查詢：應該仍然可以看到 'nstc'
    reviewable = await review_service.get_reviewable_subtypes(test_application.id, admin_user.role)

    assert "nstc" in reviewable, "Admin should be able to override own rejection"


@pytest.mark.asyncio
async def test_admin_cannot_review_professor_rejection(
    db_session: AsyncSession, test_application: Application, professor_user: User, admin_user: User
):
    """測試：Admin 不能審查 professor 已拒絕的項目"""
    review_service = ReviewService(db_session)

    # Professor 審查：拒絕 'moe_1w'
    await review_service.create_review(
        application_id=test_application.id,
        reviewer_id=professor_user.id,
        items=[{"sub_type_code": "moe_1w", "recommendation": "reject", "comments": "不符合"}],
    )

    # Admin 查詢：不應該看到 'moe_1w'
    reviewable = await review_service.get_reviewable_subtypes(test_application.id, admin_user.role)

    assert "moe_1w" not in reviewable, "Admin should NOT be able to review professor-rejected items"


@pytest.mark.asyncio
async def test_admin_cannot_review_college_rejection(
    db_session: AsyncSession, test_application: Application, college_user: User, admin_user: User
):
    """測試：Admin 不能審查 college 已拒絕的項目"""
    review_service = ReviewService(db_session)

    # College 審查：拒絕 'moe_2w'
    await review_service.create_review(
        application_id=test_application.id,
        reviewer_id=college_user.id,
        items=[{"sub_type_code": "moe_2w", "recommendation": "reject", "comments": "不符合"}],
    )

    # Admin 查詢：不應該看到 'moe_2w'
    reviewable = await review_service.get_reviewable_subtypes(test_application.id, admin_user.role)

    assert "moe_2w" not in reviewable, "Admin should NOT be able to review college-rejected items"


@pytest.mark.asyncio
async def test_professor_can_review_all_items(
    db_session: AsyncSession, test_application: Application, professor_user: User, college_user: User
):
    """測試：Professor 可以審查所有項目（不受其他角色拒絕影響）"""
    review_service = ReviewService(db_session)

    # College 先審查：拒絕 'nstc'
    await review_service.create_review(
        application_id=test_application.id,
        reviewer_id=college_user.id,
        items=[{"sub_type_code": "nstc", "recommendation": "reject", "comments": "不符合"}],
    )

    # Professor 查詢：應該仍然可以看到所有項目
    reviewable = await review_service.get_reviewable_subtypes(test_application.id, professor_user.role)

    assert "nstc" in reviewable, "Professor should review all items regardless of other rejections"
    assert "moe_1w" in reviewable
    assert "moe_2w" in reviewable


@pytest.mark.asyncio
async def test_complex_scenario_multiple_rejections(
    db_session: AsyncSession,
    test_application: Application,
    professor_user: User,
    college_user: User,
    admin_user: User,
):
    """測試：複雜場景 - 多個審查者拒絕不同項目"""
    review_service = ReviewService(db_session)

    # Professor 拒絕 'nstc'
    await review_service.create_review(
        application_id=test_application.id,
        reviewer_id=professor_user.id,
        items=[{"sub_type_code": "nstc", "recommendation": "reject", "comments": "Professor reject"}],
    )

    # College 拒絕 'moe_1w'
    await review_service.create_review(
        application_id=test_application.id,
        reviewer_id=college_user.id,
        items=[{"sub_type_code": "moe_1w", "recommendation": "reject", "comments": "College reject"}],
    )

    # 驗證 College 可見項目
    college_reviewable = await review_service.get_reviewable_subtypes(test_application.id, college_user.role)
    assert "nstc" not in college_reviewable  # Professor 拒絕 → 不可見
    assert "moe_1w" in college_reviewable  # 自己拒絕 → 可覆蓋
    assert "moe_2w" in college_reviewable  # 未被拒絕 → 可見

    # 驗證 Admin 可見項目
    admin_reviewable = await review_service.get_reviewable_subtypes(test_application.id, admin_user.role)
    assert "nstc" not in admin_reviewable  # Professor 拒絕 → 不可見
    assert "moe_1w" not in admin_reviewable  # College 拒絕 → 不可見
    assert "moe_2w" in admin_reviewable  # 未被拒絕 → 可見

    # 驗證 Professor 仍可見所有項目
    professor_reviewable = await review_service.get_reviewable_subtypes(test_application.id, professor_user.role)
    assert len(professor_reviewable) == 3  # Professor 可見所有

"""
Regression tests for UserProfileService.delete_bank_document — issue #55.

The original delete path silently:
  1. Left bank_document_object_name set (orphan DB pointer)
  2. Failed to remove the MinIO object (it tried os.remove on a local-FS
     path that never exists after the MinIO migration)

These tests pin down the symmetric "clear both columns + remove from MinIO"
behavior so the fix doesn't regress.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole, UserType
from app.models.user_profile import UserProfile
from app.services.user_profile_service import UserProfileService


@pytest.mark.asyncio
async def test_delete_bank_document_clears_both_columns_and_removes_minio_object(db: AsyncSession):
    """Happy path: both columns cleared + MinIO object removed."""
    user = User(
        nycu_id="stu_bankdoc_a",
        name="Test PhD A",
        email="stu_bankdoc_a@university.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    object_name = f"user-profiles/{user.id}/bank-documents/abc.pdf"
    profile = UserProfile(
        user_id=user.id,
        bank_document_photo_url=f"/api/v1/user-profiles/files/bank_documents/abc.pdf",
        bank_document_object_name=object_name,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    service = UserProfileService(db)
    with patch("app.services.user_profile_service.minio_service") as mock_minio:
        mock_minio.delete_file = MagicMock(return_value=True)
        result = await service.delete_bank_document(user.id)

    assert result is True
    mock_minio.delete_file.assert_called_once_with(object_name)

    await db.refresh(profile)
    assert profile.bank_document_photo_url is None
    assert profile.bank_document_object_name is None


@pytest.mark.asyncio
async def test_delete_bank_document_no_document_returns_false(db: AsyncSession):
    """No document set → returns False, never touches MinIO."""
    user = User(
        nycu_id="stu_bankdoc_b",
        name="Test PhD B",
        email="stu_bankdoc_b@university.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    profile = UserProfile(user_id=user.id)
    db.add(profile)
    await db.commit()

    service = UserProfileService(db)
    with patch("app.services.user_profile_service.minio_service") as mock_minio:
        result = await service.delete_bank_document(user.id)

    assert result is False
    mock_minio.delete_file.assert_not_called()


@pytest.mark.asyncio
async def test_delete_bank_document_minio_failure_still_clears_db(db: AsyncSession):
    """MinIO delete failure must not block DB cleanup — DB consistency wins."""
    user = User(
        nycu_id="stu_bankdoc_c",
        name="Test PhD C",
        email="stu_bankdoc_c@university.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    object_name = f"user-profiles/{user.id}/bank-documents/x.pdf"
    profile = UserProfile(
        user_id=user.id,
        bank_document_photo_url=f"/api/v1/user-profiles/files/bank_documents/x.pdf",
        bank_document_object_name=object_name,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    service = UserProfileService(db)
    with patch("app.services.user_profile_service.minio_service") as mock_minio:
        mock_minio.delete_file = MagicMock(return_value=False)  # simulate MinIO failure
        result = await service.delete_bank_document(user.id)

    assert result is True
    await db.refresh(profile)
    assert profile.bank_document_photo_url is None
    assert profile.bank_document_object_name is None

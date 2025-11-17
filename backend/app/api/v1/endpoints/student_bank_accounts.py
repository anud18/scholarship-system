"""
Student Bank Account API Endpoints

Allows students to check their verified bank account information.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, get_current_user
from app.db.deps import get_db
from app.models.student_bank_account import StudentBankAccount
from app.models.user import User
from app.schemas.student_bank_account import StudentBankAccountResponse, VerifiedAccountCheckResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/my-verified-account")
async def get_my_verified_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current user's verified bank account (student only)

    Returns the student's currently active verified bank account if available.
    This helps students see their verification status when filling out new applications.
    """
    try:
        # Query for active verified account
        stmt = (
            select(StudentBankAccount)
            .where(
                StudentBankAccount.user_id == current_user.id,
                StudentBankAccount.is_active == True,
                StudentBankAccount.verification_status == "verified",
            )
            .order_by(StudentBankAccount.verified_at.desc())
        )

        result = await db.execute(stmt)
        verified_account = result.scalar_one_or_none()

        if verified_account:
            # Generate file access token and URL for passbook cover
            passbook_cover_url = None
            if verified_account.passbook_cover_object_name:
                token_data = {"sub": str(current_user.id)}
                access_token = create_access_token(token_data)
                # Use generic file endpoint for passbook covers
                passbook_cover_url = (
                    f"{settings.base_url}{settings.api_v1_str}/files/passbook/"
                    f"{verified_account.id}?token={access_token}"
                )

            account_response = StudentBankAccountResponse.model_validate(verified_account)
            # Add passbook_cover_url to response if available
            account_dict = account_response.model_dump()
            account_dict["passbook_cover_url"] = passbook_cover_url

            return {
                "success": True,
                "message": "您的郵局帳號已通過驗證",
                "data": VerifiedAccountCheckResponse(
                    has_verified_account=True,
                    account=account_dict,
                    message=f"您的郵局帳號 {verified_account.account_number} (戶名: {verified_account.account_holder}) 已於 {verified_account.verified_at.strftime('%Y-%m-%d')} 通過驗證，您可以在申請時使用此帳號，無需重新驗證。",
                ),
            }
        else:
            return {
                "success": True,
                "message": "尚未有已驗證的郵局帳號",
                "data": VerifiedAccountCheckResponse(
                    has_verified_account=False,
                    account=None,
                    message="您尚未有已驗證的郵局帳號。當您首次提交申請並經過管理員審核通過後，您的帳號將被記錄為已驗證狀態。",
                ),
            }

    except Exception as e:
        logger.error(f"Error getting verified account for user {current_user.id}: {str(e)}")
        return {
            "success": False,
            "message": "查詢已驗證帳號時發生錯誤",
            "data": None,
        }

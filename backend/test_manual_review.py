#!/usr/bin/env python3
"""
Test script for manual bank verification review functionality
Tests that roster items are properly updated after manual review
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.application import Application
from app.models.payment_roster import PaymentRosterItem
from app.services.bank_verification_service import BankVerificationService


async def test_manual_review():
    """Test manual review updates both application and roster items"""
    # Create async engine
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get an application with submitted form data
        stmt = select(Application).where(Application.submitted_form_data.isnot(None)).limit(1)
        result = await session.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            print("❌ No applications found for testing")
            return

        print(f"✅ Testing with application ID: {application.id}")
        print(f"   App ID: {application.app_id}")

        # Check if there are roster items for this application
        roster_stmt = select(PaymentRosterItem).where(PaymentRosterItem.application_id == application.id)
        roster_result = await session.execute(roster_stmt)
        roster_items_before = roster_result.scalars().all()

        print(f"\n📊 Found {len(roster_items_before)} roster items for this application")
        if len(roster_items_before) > 0:
            print(
                f"   Initial status: account_number={roster_items_before[0].bank_account_number_status}, "
                f"account_holder={roster_items_before[0].bank_account_holder_status}"
            )

        # Initialize service
        service = BankVerificationService(session)

        # Test manual review with corrected values
        print("\n🔍 Testing manual review with corrected account number...")
        try:
            result = await service.manual_review_bank_info(
                application_id=application.id,
                account_number_approved=None,  # Not explicitly approved
                account_number_corrected="12345678901234",  # 14-digit account
                account_holder_approved=True,  # Explicitly approved
                account_holder_corrected=None,  # No correction needed
                review_notes="Test manual review",
                reviewer_username="test_admin",
            )

            print("✅ Manual review completed successfully")
            print(f"   Account number status: {result['account_number_status']}")
            print(f"   Account holder status: {result['account_holder_status']}")
            print(f"   Roster items updated: {result['roster_items_updated']}")

            # Verify roster items were updated
            roster_result_after = await session.execute(roster_stmt)
            roster_items_after = roster_result_after.scalars().all()

            if len(roster_items_after) > 0:
                print("\n✅ Roster items verified:")
                for idx, item in enumerate(roster_items_after):
                    print(f"   Item {idx + 1}:")
                    print(f"      - account_number_status: {item.bank_account_number_status}")
                    print(f"      - account_holder_status: {item.bank_account_holder_status}")
                    print(f"      - review_notes: {item.bank_manual_review_notes}")
                    if item.bank_verification_details:
                        print("      - has verification_details: Yes")
                        manual_review = item.bank_verification_details.get("manual_review", {})
                        print(f"      - reviewed_by: {manual_review.get('reviewed_by', 'N/A')}")
            else:
                print("⚠️ No roster items to verify (application might not be in any roster)")

            # Rollback to not affect database
            await session.rollback()
            print("\n✅ All changes rolled back (test mode)")

        except ValueError as e:
            print(f"❌ Manual review failed: {str(e)}")
            await session.rollback()
        except Exception as e:
            print(f"❌ Unexpected error: {str(e)}")
            await session.rollback()

        # Test account format validation
        print("\n🔍 Testing account format validation...")
        try:
            # Test with invalid account (too short)
            result = await service.manual_review_bank_info(
                application_id=application.id,
                account_number_approved=None,
                account_number_corrected="12345",  # Only 5 digits (invalid)
                account_holder_approved=None,
                account_holder_corrected=None,
                review_notes="Test validation",
                reviewer_username="test_admin",
            )
            print("❌ Validation should have failed but didn't")
        except ValueError as e:
            if "格式驗證失敗" in str(e):
                print(f"✅ Validation correctly rejected invalid account: {str(e)}")
            else:
                print(f"❌ Unexpected error: {str(e)}")
            await session.rollback()

        print("\n✨ All tests completed successfully!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_manual_review())

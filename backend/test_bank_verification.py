#!/usr/bin/env python3
"""
Quick test script for bank verification functionality
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.application import Application
from app.services.bank_verification_service import BankVerificationService


async def test_bank_verification():
    """Test bank verification with real database"""
    # Create async engine
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get first application with bank account info
        stmt = select(Application).where(Application.submitted_form_data.isnot(None)).limit(1)
        result = await session.execute(stmt)
        application = result.scalar_one_or_none()

        if not application:
            print("❌ No applications found for testing")
            return

        print(f"✅ Testing with application ID: {application.id}")
        print(f"   App ID: {application.app_id}")

        # Initialize service
        service = BankVerificationService(session)

        # Test extracting bank fields
        print("\n📋 Extracting bank fields...")
        bank_fields = service.extract_bank_fields_from_application(application)
        print(f"   Account Number: {bank_fields.get('account_number', 'N/A')}")
        print(f"   Account Holder: {bank_fields.get('account_holder', 'N/A')}")

        # Test similarity calculation
        print("\n🔍 Testing similarity calculation...")
        test_cases = [
            ("12345678", "12345678", "Exact match"),
            ("王小明", "王小名", "Similar names"),
            ("12345678", "", "One empty"),
            ("", "", "Both empty"),
        ]

        for val1, val2, description in test_cases:
            similarity = service.calculate_similarity(val1, val2)
            print(f"   {description}: {val1} vs {val2} = {similarity:.2%}")

        print("\n✨ All tests completed successfully!")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(test_bank_verification())

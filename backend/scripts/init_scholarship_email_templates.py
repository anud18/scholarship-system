#!/usr/bin/env python3
"""
Initialize default email templates for all scholarships
"""

import asyncio
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.scholarship import ScholarshipType  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402
from app.services.scholarship_email_template_service import ScholarshipEmailTemplateService  # noqa: E402


async def initialize_scholarship_email_templates():
    """Initialize default email templates for all scholarships"""
    print("🚀 Starting scholarship email template initialization...")

    async with AsyncSessionLocal() as db:
        # Get all scholarships
        scholarship_stmt = select(ScholarshipType).order_by(ScholarshipType.id)
        scholarship_result = await db.execute(scholarship_stmt)
        scholarships = list(scholarship_result.scalars().all())

        print(f"📊 Found {len(scholarships)} scholarships:")
        for scholarship in scholarships:
            print(f"   - {scholarship.name} (ID: {scholarship.id})")

        # Get a super admin user to perform the operations
        admin_stmt = select(User).where(User.role == UserRole.super_admin).limit(1)
        admin_result = await db.execute(admin_stmt)
        admin_user = admin_result.scalar_one_or_none()

        if not admin_user:
            print("❌ No super admin user found. Creating a temporary admin user...")
            # For initialization purposes, we'll create a mock admin user
            admin_user = User(
                id=0,
                nycu_id="system",
                name="System Admin",
                email="system@admin.local",
                role=UserRole.super_admin,
            )

        print(f"👤 Using admin user: {admin_user.name} ({admin_user.role})")

        # Initialize templates for each scholarship
        total_created = 0
        for scholarship in scholarships:
            print(f"\n📧 Processing {scholarship.name}...")

            try:
                # Check if templates already exist
                existing_templates = await ScholarshipEmailTemplateService.get_scholarship_templates(
                    db, scholarship.id, admin_user
                )

                if existing_templates:
                    print(f"   ⚠️  Found {len(existing_templates)} existing templates, skipping...")
                    continue

                # Create default templates based on scholarship configuration
                created_templates = await ScholarshipEmailTemplateService.bulk_create_default_templates(
                    db, scholarship.id, admin_user
                )

                print(f"   ✅ Created {len(created_templates)} email templates:")
                for template in created_templates:
                    print(f"      - {template.email_template_key} (priority: {template.priority})")

                total_created += len(created_templates)

            except Exception as e:
                print(f"   ❌ Failed to create templates for {scholarship.name}: {e}")
                continue

        print("\n🎉 Initialization complete!")
        print(f"   📈 Total templates created: {total_created}")
        print(f"   🏆 Processed {len(scholarships)} scholarships")


async def show_template_summary():
    """Show a summary of all scholarship email templates"""
    print("\n📋 Email Template Summary:")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        # Get all scholarships
        scholarship_stmt = select(ScholarshipType).order_by(ScholarshipType.id)
        scholarship_result = await db.execute(scholarship_stmt)
        scholarships = list(scholarship_result.scalars().all())

        # Create a mock admin user for querying
        admin_user = User(
            id=0,
            nycu_id="system",
            name="System Query",
            email="system@query.local",
            role=UserRole.super_admin,
        )

        for scholarship in scholarships:
            try:
                templates = await ScholarshipEmailTemplateService.get_scholarship_templates(
                    db, scholarship.id, admin_user
                )

                print(f"\n🎓 {scholarship.name} (ID: {scholarship.id})")
                print(f"   📧 Templates: {len(templates)}")

                if templates:
                    for template in templates:
                        status = "✅ Enabled" if template.is_enabled else "❌ Disabled"
                        custom = "🎨 Custom" if (template.custom_subject or template.custom_body) else "📄 Default"
                        print(
                            f"      - {template.email_template_key}: {status} {custom} (Priority: {template.priority})"
                        )
                else:
                    print("      No templates configured")

            except Exception as e:
                print(f"   ❌ Error loading templates: {e}")


async def main():
    """Main entry point"""
    print("🔧 Scholarship Email Template Initialization Tool")
    print("=" * 50)

    if len(sys.argv) > 1 and sys.argv[1] == "--summary":
        await show_template_summary()
    else:
        await initialize_scholarship_email_templates()
        await show_template_summary()


if __name__ == "__main__":
    asyncio.run(main())

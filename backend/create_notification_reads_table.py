#!/usr/bin/env python3
"""
Database migration script to create notification_reads table
Run this script to add per-user read status tracking for notifications
"""

import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# Import models to ensure they're registered
from app.models.notification import NotificationRead
from app.models.user import User, UserType, EmployeeStatus
from app.db.base import Base
from app.core.config import settings

async def create_notification_reads_table():
    """Create the notification_reads table"""
    
    # Create async engine
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=True,
        pool_pre_ping=True
    )
    
    try:
        # Create tables
        async with engine.begin() as conn:
            # Create notification_reads table
            await conn.run_sync(Base.metadata.create_all)
            
        print("✅ notification_reads table created successfully!")
        
        # Test the new functionality
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            # Check if table exists and has correct structure
            result = await session.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = 'notification_reads'
                ORDER BY ordinal_position;
            """))
            
            columns = result.fetchall()
            print("\n📋 Table structure:")
            for col in columns:
                print(f"  - {col[0]}: {col[1]} ({'NULL' if col[2] == 'YES' else 'NOT NULL'})")
            
            # Check constraints
            constraint_result = await session.execute(text("""
                SELECT constraint_name, constraint_type
                FROM information_schema.table_constraints 
                WHERE table_name = 'notification_reads';
            """))
            
            constraints = constraint_result.fetchall()
            print(f"\n🔒 Constraints: {len(constraints)} found")
            for constraint in constraints:
                print(f"  - {constraint[0]}: {constraint[1]}")
                
    except Exception as e:
        print(f"❌ Error creating table: {e}")
        raise
    finally:
        await engine.dispose()

async def test_notification_service():
    """Test the new notification service functionality"""
    from app.db.session import AsyncSessionLocal
    from app.services.notification_service import NotificationService
    from app.models.user import User, UserRole
    from app.models.notification import Notification
    from sqlalchemy import select
    
    print("\n🧪 Testing notification service...")
    
    async with AsyncSessionLocal() as session:
        try:
            service = NotificationService(session)
            
            # Find or create a test user
            result = await session.execute(select(User).where(User.nycu_id == "test_user"))
            test_user = result.scalar_one_or_none()
            
            if not test_user:
                # Create test user
                test_user = User(
                    nycu_id="test_user",
                    name="Test User",
                    email="test@example.com",
                    user_type=UserType.STUDENT,
                    status=EmployeeStatus.在學,
                    dept_code="5802",
                    dept_name="校務資訊組",
                    role=UserRole.STUDENT,
                    comment="Test user for notification system"
                )
                session.add(test_user)
                await session.commit()
                await session.refresh(test_user)
                print(f"✅ Created test user: {test_user.nycu_id}")
            
            # Create a system announcement
            system_announcement = await service.createSystemAnnouncement(
                title="測試系統公告",
                title_en="Test System Announcement",
                message="這是一個測試系統公告，測試按用戶已讀狀態功能。",
                message_en="This is a test system announcement to test per-user read status functionality.",
                notification_type="info",
                priority="normal"
            )
            print(f"✅ Created system announcement: {system_announcement.id}")
            
            # Test getting user notifications
            notifications = await service.getUserNotifications(test_user.id, limit=10)
            print(f"✅ Retrieved {len(notifications)} notifications for user")
            
            # Test unread count
            unread_count = await service.getUnreadNotificationCount(test_user.id)
            print(f"✅ Unread count: {unread_count}")
            
            # Test marking as read
            if notifications:
                success = await service.markNotificationAsRead(notifications[0]["id"], test_user.id)
                print(f"✅ Marked notification as read: {success}")
                
                # Check unread count again
                new_unread_count = await service.getUnreadNotificationCount(test_user.id)
                print(f"✅ New unread count: {new_unread_count}")
            
            # Test mark all as read
            marked_count = await service.markAllNotificationsAsRead(test_user.id)
            print(f"✅ Marked {marked_count} notifications as read")
            
            final_unread_count = await service.getUnreadNotificationCount(test_user.id)
            print(f"✅ Final unread count: {final_unread_count}")
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            await session.rollback()
            raise

if __name__ == "__main__":
    print("🚀 Starting notification_reads table creation...")
    asyncio.run(create_notification_reads_table())
    
    print("\n🧪 Running functionality tests...")
    asyncio.run(test_notification_service())
    
    print("\n✅ Migration completed successfully!")
    print("\n📝 Next steps:")
    print("1. Restart your FastAPI server")
    print("2. Test the notification system in the frontend")
    print("3. Verify that system announcements have per-user read status") 
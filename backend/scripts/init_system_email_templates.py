#!/usr/bin/env python3
"""
Initialize default system email templates
"""

import asyncio
import os
import sys

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.system_setting import EmailTemplate, SendingType  # noqa: E402


async def initialize_system_email_templates():
    """Initialize default system email templates"""
    print("🚀 Starting system email template initialization...")

    async with AsyncSessionLocal() as db:
        # Check if templates already exist
        stmt = select(EmailTemplate)
        result = await db.execute(stmt)
        existing_templates = list(result.scalars().all())

        if existing_templates:
            print(f"📊 Found {len(existing_templates)} existing templates, skipping initialization")
            return

        # Define default email templates
        default_templates = [
            # Single sending type templates
            {
                "key": "application_submitted_student",
                "subject_template": "申請確認通知 - {scholarship_name}",
                "body_template": """親愛的 {student_name} 同學：

您好！

感謝您申請 {scholarship_name}。我們已收到您的申請資料，申請編號為：{application_id}

申請詳情：
- 申請時間：{submission_date}
- 獎學金名稱：{scholarship_name}
- 申請學期：{semester}
- 獎學金金額：{scholarship_amount}

我們會儘快處理您的申請。如有任何問題，歡迎隨時與各學院系所獎學金承辦人聯繫。

祝學業順利！

國立陽明交通大學
獎學金管理系統""",
                "sending_type": SendingType.single,
                "recipient_options": [{"label": "申請學生", "value": "student"}],
            },
            {
                "key": "application_submitted_admin",
                "subject_template": "新申請通知 - {student_name}",
                "body_template": """管理員您好：

有新的獎學金申請需要處理：

申請人資訊：
- 學生姓名：{student_name}
- 學生學號：{student_id}
- 申請時間：{submission_date}
- 申請編號：{application_id}
- 獎學金名稱：{scholarship_name}

請至管理系統查看詳細資料：{admin_portal_url}

獎學金管理系統""",
                "sending_type": SendingType.single,
                "recipient_options": [{"label": "管理員", "value": "admin"}],
            },
            {
                "key": "professor_review_notification",
                "subject_template": "審查通知 - {student_name} 的 {scholarship_name} 申請",
                "body_template": """{professor_name} 教授您好：

您的指導學生 {student_name}（學號：{student_id}）申請了 {scholarship_name}，需要您進行審查。

審查截止日期：{review_deadline}

請點擊以下連結進行審查：
{review_url}

如有任何問題，歡迎隨時與各學院系所獎學金承辦人聯繫。

國立陽明交通大學
獎學金管理系統""",
                "sending_type": SendingType.single,
                "recipient_options": [{"label": "指導教授", "value": "professor"}],
            },
            {
                "key": "professor_review_submitted_admin",
                "subject_template": "教授審查結果通知 - {student_name}",
                "body_template": """管理員您好：

{professor_name} 教授已完成對 {student_name}（學號：{student_id}）的 {scholarship_name} 申請審查。

審查結果：{review_result}

請至管理系統查看詳細審查資料。

獎學金管理系統""",
                "sending_type": SendingType.single,
                "recipient_options": [{"label": "管理員", "value": "admin"}],
            },
            # Bulk sending type templates
            {
                "key": "scholarship_announcement",
                "subject_template": "獎學金公告 - {scholarship_name}",
                "body_template": """各位同學：

{scholarship_name} 現正開放申請！

申請期間：{application_period}
申請資格：{eligibility_criteria}
獎學金金額：{scholarship_amount}

申請方式：
請至獎學金管理系統線上申請

如有任何問題，請聯繫承辦人員。

國立陽明交通大學
獎學金管理系統""",
                "sending_type": SendingType.bulk,
                "recipient_options": [
                    {"label": "全體學生", "value": "all_students"},
                    {"label": "特定科系學生", "value": "department_students"},
                    {"label": "特定年級學生", "value": "grade_students"},
                ],
                "max_recipients": 500,
            },
            {
                "key": "application_deadline_reminder",
                "subject_template": "申請截止提醒 - {scholarship_name}",
                "body_template": """各位同學：

提醒您 {scholarship_name} 即將截止申請！

申請截止時間：{application_deadline}
剩餘時間：{remaining_time}

尚未申請的同學請把握時間完成申請手續。

獎學金管理系統""",
                "sending_type": SendingType.bulk,
                "recipient_options": [
                    {"label": "尚未申請的學生", "value": "non_applicants"},
                    {"label": "申請未完成的學生", "value": "incomplete_applicants"},
                ],
                "max_recipients": 1000,
            },
        ]

        print(f"📧 Creating {len(default_templates)} default email templates...")

        # Create templates
        for template_data in default_templates:
            template = EmailTemplate(**template_data)
            db.add(template)
            print(f"   ✅ Created template: {template_data['key']} ({template_data['sending_type'].value})")

        await db.commit()

        print("✅ System email templates initialized successfully!")
        print("\n📋 Created templates:")
        print("   Single sending templates:")
        print("   - application_submitted_student: 學生申請確認通知")
        print("   - application_submitted_admin: 管理員新申請通知")
        print("   - professor_review_notification: 教授審查通知")
        print("   - professor_review_submitted_admin: 教授審查結果通知")
        print("\n   Bulk sending templates:")
        print("   - scholarship_announcement: 獎學金公告")
        print("   - application_deadline_reminder: 申請截止提醒")


if __name__ == "__main__":
    asyncio.run(initialize_system_email_templates())

"""cleanup_application_fields

Revision ID: 5b7fb81203ac
Revises: 06e8a66d9437
Create Date: 2025-10-23 10:03:08.457507

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5b7fb81203ac"
down_revision: Union[str, None] = "06e8a66d9437"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    清理 application_fields 中不應存在的欄位配置

    刪除舊的 dept_code 欄位，確保只保留正確的動態欄位配置
    """
    # 刪除舊的 dept_code 欄位配置（所有 scholarship_type）
    op.execute(
        """
        DELETE FROM application_fields
        WHERE field_name = 'dept_code'
    """
    )
    print("  ✓ Deleted dept_code field configurations")

    # 確保 phd 獎學金有正確的 master_school_info 欄位
    op.execute(
        """
        INSERT INTO application_fields (
            scholarship_type, field_name, field_label, field_label_en,
            field_type, is_required, placeholder, placeholder_en,
            max_length, display_order, is_active, help_text, help_text_en
        ) VALUES (
            'phd', 'master_school_info', '碩士畢業學校學院系所',
            'Master''s Degree School/College/Department',
            'text', true, '例如：國立陽明交通大學 資訊學院 資訊工程學系',
            'e.g., NYCU College of Computer Science, Department of Computer Science',
            200, 1, true, '請填寫完整的畢業學校、學院、系所名稱',
            'Please provide complete school, college, and department names'
        )
        ON CONFLICT (scholarship_type, field_name) DO NOTHING
    """
    )
    print("  ✓ Ensured master_school_info field exists for phd scholarship")

    # 確保 direct_phd 獎學金有正確的欄位
    op.execute(
        """
        INSERT INTO application_fields (
            scholarship_type, field_name, field_label, field_label_en,
            field_type, is_required, placeholder, placeholder_en,
            max_length, display_order, is_active, help_text, help_text_en
        ) VALUES (
            'direct_phd', 'advisors', '多位指導教授資訊',
            'Multiple Advisors Information',
            'text', true, '請輸入所有指導教授的姓名（如有多位請以逗號分隔）',
            'Please enter all advisor names (separate with commas if multiple)',
            200, 1, true, '請填寫所有指導教授的姓名',
            'Please provide all advisor names'
        )
        ON CONFLICT (scholarship_type, field_name) DO NOTHING
    """
    )

    op.execute(
        """
        INSERT INTO application_fields (
            scholarship_type, field_name, field_label, field_label_en,
            field_type, is_required, placeholder, placeholder_en,
            max_length, display_order, is_active, help_text, help_text_en
        ) VALUES (
            'direct_phd', 'research_topic_zh', '研究題目（中文）',
            'Research Topic (Chinese)',
            'text', true, '請輸入研究題目（中文）',
            'Please enter research topic (in Chinese)',
            200, 2, true, '請填寫您的研究題目',
            'Please provide your research topic'
        )
        ON CONFLICT (scholarship_type, field_name) DO NOTHING
    """
    )
    print("  ✓ Ensured direct_phd scholarship fields exist")

    print("  ✅ Application fields cleaned up successfully")


def downgrade() -> None:
    """
    恢復舊的 dept_code 欄位配置（不建議）
    """
    print("  ⚠️  Cannot restore old dept_code configurations")
    pass

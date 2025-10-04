"""clear_whitelist_data_change_to_nycu_id

白名單系統重構：
- 將白名單從存儲 user_id (數字) 改為存儲 nycu_id (學號字串)
- 清空現有白名單數據（因為格式不兼容，無法轉換）
- 更新註釋說明新的數據格式

白名單新格式：{"general": ["0856001", "0856002"], "nstc": ["0856003"]}

Revision ID: e5ce4830cc3d
Revises: 475a5cc5a601
Create Date: 2025-10-04 04:36:01.293531

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5ce4830cc3d"
down_revision: Union[str, None] = "475a5cc5a601"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    清空所有白名單數據，因為數據格式從 user_id (數字) 改為 nycu_id (學號字串)

    注意：會先備份現有白名單數據到 scholarship_configurations_whitelist_backup 表格
    """
    # Step 1: Create backup table with existing whitelist data
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS scholarship_configurations_whitelist_backup AS
        SELECT
            id,
            scholarship_type_id,
            academic_year,
            semester,
            whitelist_student_ids,
            updated_at,
            NOW() as backup_created_at
        FROM scholarship_configurations
        WHERE whitelist_student_ids IS NOT NULL
        AND whitelist_student_ids::text != '{}'
    """
    )

    # Step 2: Clear all whitelist data in scholarship_configurations
    op.execute(
        "UPDATE scholarship_configurations SET whitelist_student_ids = '{}' WHERE whitelist_student_ids IS NOT NULL"
    )

    # Add comment to document the new format
    op.execute(
        """
        COMMENT ON COLUMN scholarship_configurations.whitelist_student_ids IS
        '白名單學號列表，依子獎學金區分。格式: {"general": ["0856001", "0856002"], "nstc": ["0856003"]}'
        """
    )


def downgrade() -> None:
    """
    無法自動還原，因為數據格式不兼容

    如需還原，可手動從 scholarship_configurations_whitelist_backup 表格恢復數據
    """
    # Cannot automatically restore due to format incompatibility
    # Manual restoration from backup table may be possible if needed
    op.execute(
        """
        COMMENT ON TABLE scholarship_configurations_whitelist_backup IS
        '白名單備份表格 - 包含從 user_id 改為 nycu_id 之前的數據'
    """
    )
    pass

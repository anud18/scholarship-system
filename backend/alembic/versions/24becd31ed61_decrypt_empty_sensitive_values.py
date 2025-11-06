"""decrypt_empty_sensitive_values

修復已加密的空值：
- 找出所有 is_sensitive=True 且 allow_empty=True 的設定
- 嘗試解密這些設定的值
- 如果解密後是空字串，將資料庫值改為空字串（移除加密）
- 這樣使用者可以在 UI 上清楚看到 "(空值)" 而非加密字串

Revision ID: 24becd31ed61
Revises: b450ae0845fa
Create Date: 2025-10-04 19:12:41.986000

"""
import base64
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from cryptography.fernet import Fernet

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "24becd31ed61"
down_revision: Union[str, None] = "b450ae0845fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Decrypt encrypted empty values in system_settings"""
    # Get database connection
    bind = op.get_bind()

    # Get SECRET_KEY from environment to initialize encryption
    import os

    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise ValueError(
            "SECRET_KEY environment variable is required for this migration. "
            "Please set SECRET_KEY before running migrations."
        )

    # Initialize Fernet cipher (same logic as ConfigEncryption class)
    key_material = secret_key.encode()[:32].ljust(32, b"0")
    key = base64.urlsafe_b64encode(hashlib.sha256(key_material).digest())
    fernet = Fernet(key)

    # Query all sensitive settings that allow empty values
    result = bind.execute(
        sa.text(
            """
        SELECT id, key, value, is_sensitive, allow_empty
        FROM system_settings
        WHERE is_sensitive = true AND allow_empty = true
    """
        )
    )

    settings_to_update = []
    for row in result:
        setting_id, setting_key, encrypted_value, is_sensitive, allow_empty = row

        if encrypted_value:  # Only process non-empty values
            try:
                # Try to decrypt the value
                decrypted_value = fernet.decrypt(encrypted_value.encode()).decode()

                # If decrypted value is empty string, mark for update
                if not decrypted_value:
                    settings_to_update.append((setting_id, setting_key))
                    print(f"Found encrypted empty value for: {setting_key} (id={setting_id})")
            except Exception as e:
                # If decryption fails, it might already be an empty string or invalid
                print(f"Could not decrypt {setting_key}: {str(e)}")

    # Update settings with empty strings (unencrypted)
    for setting_id, setting_key in settings_to_update:
        bind.execute(sa.text("UPDATE system_settings SET value = '' WHERE id = :id"), {"id": setting_id})
        print(f"Updated {setting_key} to empty string (unencrypted)")

    if settings_to_update:
        print(f"✅ Fixed {len(settings_to_update)} encrypted empty values")
    else:
        print("ℹ️  No encrypted empty values found")


def downgrade() -> None:
    """
    Downgrade is not implemented as we cannot reverse this change
    (we don't know which empty values were originally encrypted)
    """
    print("⚠️  Downgrade not supported for this migration")
    pass

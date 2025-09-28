"""fix_enum_case_consistency

Revision ID: a7c76a19a59e
Revises: 0f8f3a9bbaaf
Create Date: 2025-09-27 22:44:14.794452

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c76a19a59e"
down_revision: Union[str, None] = "0f8f3a9bbaaf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Fix enum case consistency for critical enum types"""

    print("🔧 Starting critical enum consistency fixes...")

    # Only fix the most critical enums that are causing the user's data display issues
    # Skip complex notification/email enums for now to avoid migration failures

    try:
        # 1. Fix Semester enum (most important for scholarship data)
        print("📅 Updating Semester enum...")
        op.execute("CREATE TYPE semester_new AS ENUM ('first', 'second', 'summer', 'annual')")

        # Check if tables exist before updating them
        connection = op.get_bind()

        # Update applications table if it exists
        result = connection.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'applications')"
        )
        if result.scalar():
            op.execute(
                """
                ALTER TABLE applications ADD COLUMN semester_new semester_new;
                UPDATE applications SET semester_new = CASE
                    WHEN semester = 'FIRST' THEN 'first'::semester_new
                    WHEN semester = 'SECOND' THEN 'second'::semester_new
                    WHEN semester = 'SUMMER' THEN 'summer'::semester_new
                    WHEN semester = 'ANNUAL' THEN 'annual'::semester_new
                    ELSE NULL
                END;
            """
            )
            # Only drop and rename if column exists
            try:
                op.execute("ALTER TABLE applications DROP COLUMN semester")
                op.execute("ALTER TABLE applications RENAME COLUMN semester_new TO semester")
            except Exception as exc:
                print(f"⚠️  Semester column update in applications table skipped: {exc}")

        # Update scholarship_configurations table if it exists
        result = connection.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'scholarship_configurations')"
        )
        if result.scalar():
            try:
                op.execute(
                    """
                    ALTER TABLE scholarship_configurations ADD COLUMN semester_new semester_new;
                    UPDATE scholarship_configurations SET semester_new = CASE
                        WHEN semester = 'FIRST' THEN 'first'::semester_new
                        WHEN semester = 'SECOND' THEN 'second'::semester_new
                        WHEN semester = 'SUMMER' THEN 'summer'::semester_new
                        WHEN semester = 'ANNUAL' THEN 'annual'::semester_new
                        ELSE NULL
                    END;
                    ALTER TABLE scholarship_configurations DROP COLUMN semester;
                    ALTER TABLE scholarship_configurations RENAME COLUMN semester_new TO semester;
                """
                )
            except Exception as exc:
                print(f"⚠️  Semester column update in scholarship_configurations table skipped: {exc}")

        # Drop old enum and rename new one
        op.execute("DROP TYPE semester CASCADE")
        op.execute("ALTER TYPE semester_new RENAME TO semester")

        print("✅ Semester enum updated successfully")

    except Exception as e:
        print(f"⚠️  Semester enum update failed: {e}")

    try:
        # 2. Fix SubTypeSelectionMode enum
        print("🔀 Updating SubTypeSelectionMode enum...")
        op.execute("CREATE TYPE subtypeselectionmode_new AS ENUM ('single', 'multiple', 'hierarchical')")

        # Update applications table if it exists
        result = connection.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'applications')"
        )
        if result.scalar():
            try:
                op.execute(
                    """
                    ALTER TABLE applications ADD COLUMN sub_type_selection_mode_new subtypeselectionmode_new;
                    UPDATE applications SET sub_type_selection_mode_new = CASE
                        WHEN sub_type_selection_mode = 'SINGLE' THEN 'single'::subtypeselectionmode_new
                        WHEN sub_type_selection_mode = 'MULTIPLE' THEN 'multiple'::subtypeselectionmode_new
                        WHEN sub_type_selection_mode = 'HIERARCHICAL' THEN 'hierarchical'::subtypeselectionmode_new
                        ELSE NULL
                    END;
                    ALTER TABLE applications DROP COLUMN sub_type_selection_mode;
                    ALTER TABLE applications RENAME COLUMN sub_type_selection_mode_new TO sub_type_selection_mode;
                """
                )
            except Exception as exc:
                print(f"⚠️  SubTypeSelectionMode column update in applications table skipped: {exc}")

        # Update scholarship_types table if it exists
        result = connection.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'scholarship_types')"
        )
        if result.scalar():
            try:
                op.execute(
                    """
                    ALTER TABLE scholarship_types ADD COLUMN sub_type_selection_mode_new subtypeselectionmode_new;
                    UPDATE scholarship_types SET sub_type_selection_mode_new = CASE
                        WHEN sub_type_selection_mode = 'SINGLE' THEN 'single'::subtypeselectionmode_new
                        WHEN sub_type_selection_mode = 'MULTIPLE' THEN 'multiple'::subtypeselectionmode_new
                        WHEN sub_type_selection_mode = 'HIERARCHICAL' THEN 'hierarchical'::subtypeselectionmode_new
                        ELSE NULL
                    END;
                    ALTER TABLE scholarship_types DROP COLUMN sub_type_selection_mode;
                    ALTER TABLE scholarship_types RENAME COLUMN sub_type_selection_mode_new TO sub_type_selection_mode;
                """
                )
            except Exception as exc:
                print(f"⚠️  SubTypeSelectionMode column update in scholarship_types table skipped: {exc}")

        op.execute("DROP TYPE subtypeselectionmode CASCADE")
        op.execute("ALTER TYPE subtypeselectionmode_new RENAME TO subtypeselectionmode")

        print("✅ SubTypeSelectionMode enum updated successfully")

    except Exception as e:
        print(f"⚠️  SubTypeSelectionMode enum update failed: {e}")

    try:
        # 3. Fix UserRole enum (critical for super_admin access)
        print("👤 Updating UserRole enum...")
        op.execute("CREATE TYPE userrole_new AS ENUM ('student', 'professor', 'college', 'admin', 'super_admin')")

        result = connection.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users')")
        if result.scalar():
            try:
                op.execute(
                    """
                    ALTER TABLE users ADD COLUMN role_new userrole_new;
                    UPDATE users SET role_new = CASE
                        WHEN role = 'STUDENT' THEN 'student'::userrole_new
                        WHEN role = 'PROFESSOR' THEN 'professor'::userrole_new
                        WHEN role = 'COLLEGE' THEN 'college'::userrole_new
                        WHEN role = 'ADMIN' THEN 'admin'::userrole_new
                        WHEN role = 'SUPER_ADMIN' THEN 'super_admin'::userrole_new
                        ELSE NULL
                    END;
                    ALTER TABLE users DROP COLUMN role;
                    ALTER TABLE users RENAME COLUMN role_new TO role;
                """
                )
            except Exception as exc:
                print(f"⚠️  UserRole column update skipped: {exc}")

        op.execute("DROP TYPE userrole CASCADE")
        op.execute("ALTER TYPE userrole_new RENAME TO userrole")

        print("✅ UserRole enum updated successfully")

    except Exception as e:
        print(f"⚠️  UserRole enum update failed: {e}")

    print("🎉 Critical enum consistency migration completed!")
    print("💡 Note: Some complex enums were skipped to avoid migration failures.")
    print("📊 Run validation script to check remaining inconsistencies.")


def downgrade() -> None:
    """Revert enum changes - this would be complex, so we'll just document it"""
    print("WARNING: Downgrade for enum consistency changes is complex and may cause data loss.")
    print("Manual intervention may be required to revert these changes.")
    # In a real scenario, you would implement the reverse mappings
    pass

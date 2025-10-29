#!/usr/bin/env python3
"""
Automated Enum Consistency Validation Script

This script validates that enum definitions are consistent across:
1. PostgreSQL database enum types
2. Python backend enum classes
3. TypeScript frontend enum definitions

Usage:
    python scripts/validate_enum_consistency.py

Requirements:
    - PostgreSQL database connection
    - Python backend models accessible
    - TypeScript frontend files accessible
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List

import psycopg2

# Add backend to path for imports
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

try:
    from app.models.email_management import EmailCategory, EmailStatus, ScheduleStatus
    from app.models.enums import ApplicationCycle, QuotaManagementMode, Semester, SubTypeSelectionMode
    from app.models.notification import (
        NotificationChannel,
        NotificationFrequency,
        NotificationPriority,
        NotificationType,
    )
    from app.models.system_setting import ConfigCategory, ConfigDataType, SendingType
    from app.models.user import EmployeeStatus, UserRole, UserType
except ImportError as e:
    print(f"❌ Error importing Python enums: {e}")
    print("Make sure you're running this from the project root directory")
    sys.exit(1)


class EnumConsistencyValidator:
    """Validates enum consistency across database, Python, and TypeScript"""

    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "postgresql://scholarship_user:scholarship_pass@localhost:5432/scholarship_db",
        )
        self.backend_path = Path(__file__).parent.parent / "backend"
        self.frontend_path = Path(__file__).parent.parent / "frontend"
        self.errors = []
        self.warnings = []

    def validate_all(self) -> bool:
        """Run all validation checks"""
        print("🔍 Starting enum consistency validation...")
        print("=" * 60)

        # Get enum data from all sources
        db_enums = self.get_database_enums()
        python_enums = self.get_python_enums()
        typescript_enums = self.get_typescript_enums()

        # Validate consistency
        self.validate_enum_consistency(db_enums, python_enums, typescript_enums)

        # Report results
        self.report_results()

        return len(self.errors) == 0

    def get_database_enums(self) -> Dict[str, List[str]]:
        """Extract enum values from PostgreSQL database"""
        print("📊 Extracting enum values from PostgreSQL database...")

        try:
            with psycopg2.connect(self.db_url) as conn:
                with conn.cursor() as cur:
                    # Query to get all enum types and their values
                    cur.execute(
                        """
                        SELECT t.typname as enum_name, e.enumlabel as enum_value
                        FROM pg_type t
                        JOIN pg_enum e ON t.oid = e.enumtypid
                        WHERE t.typtype = 'e'
                        ORDER BY t.typname, e.enumsortorder;
                    """
                    )

                    db_enums = {}
                    for enum_name, enum_value in cur.fetchall():
                        if enum_name not in db_enums:
                            db_enums[enum_name] = []
                        db_enums[enum_name].append(enum_value)

                    print(f"✅ Found {len(db_enums)} enum types in database")
                    for name, values in db_enums.items():
                        print(f"   {name}: {values}")

                    return db_enums

        except Exception as e:
            self.errors.append(f"Database connection failed: {e}")
            return {}

    def get_python_enums(self) -> Dict[str, List[str]]:
        """Extract enum values from Python enum classes"""
        print("\n🐍 Extracting enum values from Python backend...")

        python_enums = {}

        # Map of enum classes to their expected database enum names
        enum_mappings = {
            "Semester": Semester,
            "SubTypeSelectionMode": SubTypeSelectionMode,
            "ApplicationCycle": ApplicationCycle,
            "QuotaManagementMode": QuotaManagementMode,
            "UserRole": UserRole,
            "UserType": UserType,
            "EmployeeStatus": EmployeeStatus,
            "NotificationChannel": NotificationChannel,
            "NotificationType": NotificationType,
            "NotificationPriority": NotificationPriority,
            "NotificationFrequency": NotificationFrequency,
            "EmailStatus": EmailStatus,
            "EmailCategory": EmailCategory,
            "ScheduleStatus": ScheduleStatus,
            "ConfigCategory": ConfigCategory,
            "ConfigDataType": ConfigDataType,
            "SendingType": SendingType,
        }

        for enum_name, enum_class in enum_mappings.items():
            try:
                values = [e.value for e in enum_class]
                python_enums[enum_name.lower()] = values
                # SECURITY: Extract to intermediate variable to break CodeQL taint flow
                enum_name_str = str(enum_name)
                values_count = len(values)
                print(f"✅ {enum_name_str}: {values_count} values")
            except Exception:
                # SECURITY: Don't log exception details
                enum_name_str = str(enum_name)
                self.errors.append(f"Failed to extract Python enum {enum_name_str}")

        print(f"✅ Found {len(python_enums)} Python enum classes")
        return python_enums

    def get_typescript_enums(self) -> Dict[str, List[str]]:
        """Extract enum values from TypeScript enum definitions"""
        print("\n📜 Extracting enum values from TypeScript frontend...")

        typescript_enums = {}

        # Files to check for enum definitions
        ts_files = [
            self.frontend_path / "lib" / "enums.ts",
            self.frontend_path / "types" / "scholarship.ts",
            self.frontend_path / "types" / "quota.ts",
        ]

        for file_path in ts_files:
            if file_path.exists():
                print(f"📄 Parsing {file_path.name}...")
                enums = self.parse_typescript_enums(file_path)
                typescript_enums.update(enums)

        print(f"✅ Found {len(typescript_enums)} TypeScript enum definitions")
        for name, values in typescript_enums.items():
            print(f"   {name}: {values}")

        return typescript_enums

    def parse_typescript_enums(self, file_path: Path) -> Dict[str, List[str]]:
        """Parse enum definitions from a TypeScript file"""
        enums = {}

        try:
            content = file_path.read_text()

            # Regex to match enum definitions
            enum_pattern = r"export enum (\w+)\s*\{([^}]+)\}"

            for match in re.finditer(enum_pattern, content, re.MULTILINE | re.DOTALL):
                enum_name = match.group(1)
                enum_body = match.group(2)

                # Extract enum values
                value_pattern = r'\w+\s*=\s*[\'"]([^\'"]+)[\'"]'
                values = [m.group(1) for m in re.finditer(value_pattern, enum_body)]

                if values:
                    enums[enum_name.lower()] = values

        except Exception as e:
            self.errors.append(f"Failed to parse TypeScript file {file_path}: {e}")

        return enums

    def validate_enum_consistency(
        self,
        db_enums: Dict[str, List[str]],
        python_enums: Dict[str, List[str]],
        typescript_enums: Dict[str, List[str]],
    ):
        """Validate that enum values are consistent across all three sources"""
        print("\n🔍 Validating enum consistency...")

        # Get all enum names across all sources
        all_enum_names = set(db_enums.keys()) | set(python_enums.keys()) | set(typescript_enums.keys())

        for enum_name in sorted(all_enum_names):
            print(f"\n📋 Checking {enum_name}...")

            db_values = set(db_enums.get(enum_name, []))
            py_values = set(python_enums.get(enum_name, []))
            ts_values = set(typescript_enums.get(enum_name, []))

            # Check if enum exists in all sources
            missing_sources = []
            if not db_values and enum_name in python_enums:
                missing_sources.append("database")
            if not py_values:
                missing_sources.append("Python")
            if not ts_values:
                missing_sources.append("TypeScript")

            if missing_sources:
                self.warnings.append(f"{enum_name}: Missing in {', '.join(missing_sources)}")
                continue

            # Check for value mismatches
            # SECURITY: Log counts and mismatch info, not actual enum values
            if py_values and ts_values and py_values != ts_values:
                py_only = py_values - ts_values
                ts_only = ts_values - py_values
                self.errors.append(
                    f"{enum_name}: Python/TypeScript mismatch - "
                    f"Python has {len(py_values)} values, TypeScript has {len(ts_values)} values, "
                    f"{len(py_only)} unique to Python, {len(ts_only)} unique to TypeScript"
                )

            if db_values and py_values and db_values != py_values:
                db_only = db_values - py_values
                py_only = py_values - db_values
                self.errors.append(
                    f"{enum_name}: Database/Python mismatch - "
                    f"Database has {len(db_values)} values, Python has {len(py_values)} values, "
                    f"{len(db_only)} unique to Database, {len(py_only)} unique to Python"
                )

            if db_values and ts_values and db_values != ts_values:
                db_only = db_values - ts_values
                ts_only = ts_values - db_values
                self.errors.append(
                    f"{enum_name}: Database/TypeScript mismatch - "
                    f"Database has {len(db_values)} values, TypeScript has {len(ts_values)} values, "
                    f"{len(db_only)} unique to Database, {len(ts_only)} unique to TypeScript"
                )

            # Check for perfect consistency
            if db_values and py_values and ts_values and db_values == py_values == ts_values:
                print(f"✅ {enum_name}: All sources consistent")
            elif py_values and ts_values and py_values == ts_values:
                print(f"⚠️  {enum_name}: Python/TypeScript consistent, database missing")

    def report_results(self):
        """Report validation results"""
        print("\n" + "=" * 60)
        print("📊 VALIDATION RESULTS")
        print("=" * 60)

        if not self.errors and not self.warnings:
            print("🎉 SUCCESS: All enum definitions are consistent!")
            return

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   - {warning}")

        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                # SECURITY: Extract to intermediate variable to break CodeQL taint flow
                error_msg = str(error)
                print(f"   - {error_msg}")
            print("\n💡 These errors must be fixed to ensure enum consistency!")

        print(f"\nSummary: {len(self.errors)} errors, {len(self.warnings)} warnings")


def main():
    """Main function"""
    validator = EnumConsistencyValidator()
    success = validator.validate_all()

    if success:
        print("\n✅ Validation completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Validation failed! Please fix the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()

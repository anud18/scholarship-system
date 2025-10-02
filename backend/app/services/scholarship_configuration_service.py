"""
Scholarship Configuration Service
Handles business logic for dynamic scholarship configurations
"""

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application import Application, ApplicationStatus
from app.models.enums import QuotaManagementMode
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType

func: Any = sa_func


class ScholarshipConfigurationService:
    """Service class for scholarship configuration management"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_active_configurations(
        self, scholarship_type_id: Optional[int] = None
    ) -> List[ScholarshipConfiguration]:
        """Get all active and effective configurations"""
        stmt = (
            select(ScholarshipConfiguration)
            .options(selectinload(ScholarshipConfiguration.scholarship_type))
            .filter(ScholarshipConfiguration.is_active.is_(True))
        )

        if scholarship_type_id:
            stmt = stmt.filter(ScholarshipConfiguration.scholarship_type_id == scholarship_type_id)

        result = await self.db.execute(stmt)
        configurations = result.scalars().all()

        # Filter by effective dates
        effective_configs = []
        for config in configurations:
            if config.is_effective:
                effective_configs.append(config)

        return effective_configs

    async def get_configuration_by_code(self, config_code: str) -> Optional[ScholarshipConfiguration]:
        """Get configuration by its unique code"""
        stmt = select(ScholarshipConfiguration).filter(ScholarshipConfiguration.config_code == config_code)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    def validate_configuration_requirements(
        self, config: ScholarshipConfiguration, application_data: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """Validate if application meets configuration requirements"""
        errors = []

        # Quota validation can be added here if needed

        return len(errors) == 0, errors

    async def check_quota_availability(
        self, config: ScholarshipConfiguration, college_code: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Check if quota is available for application"""
        if config.quota_management_mode == QuotaManagementMode.none:
            return True, {"unlimited": True}

        # Get current approved applications
        stmt = select(func.count(Application.id)).filter(
            and_(
                Application.scholarship_type_id == config.scholarship_type_id,
                Application.status == ApplicationStatus.approved.value,
            )
        )
        result = await self.db.execute(stmt)
        approved_count = result.scalar()

        quota_info = {
            "total_quota": config.total_quota,
            "used_quota": approved_count,
            "available_quota": None,
            "usage_percentage": None,
        }

        # Check total quota
        if config.has_quota_limit and config.total_quota:
            available = config.total_quota - approved_count
            quota_info["available_quota"] = max(0, available)
            quota_info["usage_percentage"] = (approved_count / config.total_quota) * 100

            if available <= 0:
                return False, quota_info

        # Check college-specific quota
        if config.has_college_quota and college_code:
            college_quota = config.get_quota_for_college(college_code)
            if college_quota:
                # Get college-specific approved applications
                # This would need additional tracking in applications table
                college_approved = 0  # Placeholder - would implement college-specific counting

                quota_info["college_quota"] = college_quota
                quota_info["college_used"] = college_approved
                quota_info["college_available"] = max(0, college_quota - college_approved)

                if college_quota - college_approved <= 0:
                    return False, quota_info

        return True, quota_info

    def calculate_application_score(self, config: ScholarshipConfiguration, application_data: Dict[str, Any]) -> float:
        """Calculate application score based on configuration criteria"""
        if not config.scoring_criteria:
            return 0.0

        total_score = 0.0
        total_weight = 0.0

        criteria = config.get_scoring_criteria()

        for criterion_name, criterion_config in criteria.items():
            weight = criterion_config.get("weight", 0.0)
            max_score = criterion_config.get("max_score", 100)

            # Get score for this criterion from application data
            raw_score = application_data.get(f"score_{criterion_name}", 0)
            normalized_score = min(raw_score, max_score)

            weighted_score = normalized_score * weight
            total_score += weighted_score
            total_weight += weight

        # Normalize to 0-100 scale
        if total_weight > 0:
            return (total_score / total_weight) * 100
        return 0.0

    async def apply_auto_screening(
        self, config: ScholarshipConfiguration, applications: List[Application]
    ) -> List[Tuple[Application, bool, str]]:
        """Apply automatic screening rules to applications"""
        if not config.auto_screening_rules:
            return [(app, True, "No screening rules") for app in applications]

        results = []
        screening_rules = config.auto_screening_rules

        for application in applications:
            passed = True
            reason = "Passed all screening rules"

            # Apply each screening rule
            for rule_name, rule_config in screening_rules.items():
                rule_type = rule_config.get("type")
                threshold = rule_config.get("threshold")
                field = rule_config.get("field")

                if rule_type == "minimum_score":
                    score = getattr(application, field, 0) if field else 0
                    if score < threshold:
                        passed = False
                        reason = f"Score too low: {score} < {threshold}"
                        break

                elif rule_type == "maximum_applications":
                    # Check if student has too many applications (using user_id now)
                    stmt = (
                        select(func.count()).select_from(Application).where(Application.user_id == application.user_id)
                    )
                    result = await self.db.execute(stmt)
                    student_app_count = result.scalar() or 0

                    if student_app_count > threshold:
                        passed = False
                        reason = f"Too many applications: {student_app_count} > {threshold}"
                        break

                elif rule_type == "required_field":
                    if not getattr(application, field, None):
                        passed = False
                        reason = f"Missing required field: {field}"
                        break

            results.append((application, passed, reason))

        return results

    # CRUD Operations for ScholarshipConfiguration Management

    async def create_configuration(
        self,
        scholarship_type_id: int,
        config_data: Dict[str, Any],
        created_by_user_id: int,
    ) -> ScholarshipConfiguration:
        """Create a new scholarship configuration"""

        # Validate academic year and semester combination
        academic_year = config_data.get("academic_year")
        semester = config_data.get("semester")

        if not academic_year:
            raise ValueError("Academic year is required")

        # Check if configuration already exists for this period
        stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                ScholarshipConfiguration.academic_year == academic_year,
                ScholarshipConfiguration.semester == semester,
                ScholarshipConfiguration.is_active.is_(True),
            )
        )
        result = await self.db.execute(stmt)
        existing_config = result.scalar_one_or_none()

        if existing_config:
            raise ValueError("Configuration already exists for this academic period")

        # Create new configuration
        new_config = ScholarshipConfiguration(
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
            config_name=config_data["config_name"],
            config_code=config_data["config_code"],
            description=config_data.get("description"),
            description_en=config_data.get("description_en"),
            amount=config_data["amount"],
            currency=config_data.get("currency", "TWD"),
            whitelist_student_ids=config_data.get("whitelist_student_ids", {}),
            renewal_application_start_date=config_data.get("renewal_application_start_date"),
            renewal_application_end_date=config_data.get("renewal_application_end_date"),
            application_start_date=config_data.get("application_start_date"),
            application_end_date=config_data.get("application_end_date"),
            renewal_professor_review_start=config_data.get("renewal_professor_review_start"),
            renewal_professor_review_end=config_data.get("renewal_professor_review_end"),
            renewal_college_review_start=config_data.get("renewal_college_review_start"),
            renewal_college_review_end=config_data.get("renewal_college_review_end"),
            requires_professor_recommendation=config_data.get("requires_professor_recommendation", False),
            professor_review_start=config_data.get("professor_review_start"),
            professor_review_end=config_data.get("professor_review_end"),
            requires_college_review=config_data.get("requires_college_review", False),
            college_review_start=config_data.get("college_review_start"),
            college_review_end=config_data.get("college_review_end"),
            review_deadline=config_data.get("review_deadline"),
            is_active=config_data.get("is_active", True),
            effective_start_date=config_data.get("effective_start_date"),
            effective_end_date=config_data.get("effective_end_date"),
            version=config_data.get("version", "1.0"),
            created_by=created_by_user_id,
        )

        self.db.add(new_config)
        await self.db.commit()
        await self.db.refresh(new_config)

        return new_config

    async def update_configuration(
        self, config_id: int, config_data: Dict[str, Any], updated_by_user_id: int
    ) -> ScholarshipConfiguration:
        """Update an existing scholarship configuration"""

        stmt = select(ScholarshipConfiguration).where(ScholarshipConfiguration.id == config_id)
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            raise ValueError("Configuration not found")

        # Update fields (excluding quota-related fields)
        updatable_fields = [
            "config_name",
            "description",
            "description_en",
            "amount",
            "currency",
            "whitelist_student_ids",
            "renewal_application_start_date",
            "renewal_application_end_date",
            "application_start_date",
            "application_end_date",
            "renewal_professor_review_start",
            "renewal_professor_review_end",
            "renewal_college_review_start",
            "renewal_college_review_end",
            "requires_professor_recommendation",
            "professor_review_start",
            "professor_review_end",
            "requires_college_review",
            "college_review_start",
            "college_review_end",
            "review_deadline",
            "is_active",
            "effective_start_date",
            "effective_end_date",
            "version",
        ]

        for field in updatable_fields:
            if field in config_data:
                setattr(config, field, config_data[field])

        config.updated_by = updated_by_user_id

        await self.db.commit()
        await self.db.refresh(config)

        return config

    async def deactivate_configuration(self, config_id: int, updated_by_user_id: int) -> ScholarshipConfiguration:
        """Deactivate (soft delete) a scholarship configuration"""

        stmt = select(ScholarshipConfiguration).where(ScholarshipConfiguration.id == config_id)
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            raise ValueError("Configuration not found")

        # Check if there are active applications using this configuration
        active_applications_query = select(func.count(Application.id)).where(
            and_(
                Application.config_code == config.config_code,
                Application.scholarship_type_id == config.scholarship_type_id,
                Application.status.not_in(
                    [ApplicationStatus.rejected, ApplicationStatus.withdrawn, ApplicationStatus.cancelled]
                ),
            )
        )

        active_apps_result = await self.db.execute(active_applications_query)
        active_applications_count = active_apps_result.scalar() or 0

        if active_applications_count > 0:
            raise ValueError(
                f"Cannot delete configuration with {active_applications_count} active applications. "
                "Please reject or withdraw all applications first, or use deactivation instead."
            )

        config.is_active = False
        config.updated_by = updated_by_user_id

        await self.db.commit()
        await self.db.refresh(config)

        return config

    async def duplicate_configuration(
        self,
        source_config_id: int,
        target_academic_year: int,
        target_semester: Optional[str],
        new_config_code: str,
        new_config_name: Optional[str],
        created_by_user_id: int,
    ) -> ScholarshipConfiguration:
        """Duplicate a scholarship configuration to a new academic period"""

        stmt = select(ScholarshipConfiguration).where(ScholarshipConfiguration.id == source_config_id)
        result = await self.db.execute(stmt)
        source_config = result.scalar_one_or_none()

        if not source_config:
            raise ValueError("Source configuration not found")

        # Check if target configuration already exists
        stmt = select(ScholarshipConfiguration).where(
            and_(
                ScholarshipConfiguration.scholarship_type_id == source_config.scholarship_type_id,
                ScholarshipConfiguration.academic_year == target_academic_year,
                ScholarshipConfiguration.semester == target_semester,
                ScholarshipConfiguration.is_active.is_(True),
            )
        )
        result = await self.db.execute(stmt)
        existing_target = result.scalar_one_or_none()

        if existing_target:
            raise ValueError("Target configuration already exists for this academic period")

        # Create duplicate configuration
        new_config = ScholarshipConfiguration(
            scholarship_type_id=source_config.scholarship_type_id,
            academic_year=target_academic_year,
            semester=target_semester,
            config_name=new_config_name or f"{source_config.config_name} (複製)",
            config_code=new_config_code,
            description=source_config.description,
            description_en=source_config.description_en,
            amount=source_config.amount,
            currency=source_config.currency,
            whitelist_student_ids=source_config.whitelist_student_ids.copy()
            if source_config.whitelist_student_ids
            else {},
            requires_professor_recommendation=source_config.requires_professor_recommendation,
            requires_college_review=source_config.requires_college_review,
            is_active=True,
            version="1.0",
            created_by=created_by_user_id,
        )

        self.db.add(new_config)
        await self.db.commit()
        await self.db.refresh(new_config)

        return new_config

    async def get_configurations_by_filter(
        self,
        scholarship_type_id: Optional[int] = None,
        academic_year: Optional[int] = None,
        semester: Optional[str] = None,
        is_active: bool = True,
    ) -> List[ScholarshipConfiguration]:
        """Get configurations with filtering options"""

        stmt = select(ScholarshipConfiguration)

        if scholarship_type_id:
            stmt = stmt.where(ScholarshipConfiguration.scholarship_type_id == scholarship_type_id)

        if academic_year:
            stmt = stmt.where(ScholarshipConfiguration.academic_year == academic_year)

        if semester:
            if semester == "first":
                from app.models.enums import Semester

                stmt = stmt.where(ScholarshipConfiguration.semester == Semester.first)
            elif semester == "second":
                from app.models.enums import Semester

                stmt = stmt.where(ScholarshipConfiguration.semester == Semester.second)

        stmt = stmt.where(ScholarshipConfiguration.is_active.is_(is_active))
        stmt = stmt.order_by(
            ScholarshipConfiguration.academic_year.desc(),
            ScholarshipConfiguration.semester.desc(),
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    def validate_configuration_data(self, config_data: Dict[str, Any]) -> List[str]:
        """Validate configuration data and return list of errors"""
        errors = []

        # Required fields validation
        required_fields = ["config_name", "config_code", "academic_year", "amount"]
        for field in required_fields:
            if not config_data.get(field):
                errors.append(f"{field} is required")

        # Academic year validation
        academic_year = config_data.get("academic_year")
        if academic_year and (academic_year < 100 or academic_year > 200):
            errors.append("Academic year should be in Taiwan calendar format (e.g., 113)")

        # Amount validation
        amount = config_data.get("amount")
        if amount and amount <= 0:
            errors.append("Amount must be greater than 0")

        # Date validation
        date_fields = [
            ("renewal_application_start_date", "renewal_application_end_date"),
            ("application_start_date", "application_end_date"),
            ("renewal_professor_review_start", "renewal_professor_review_end"),
            ("renewal_college_review_start", "renewal_college_review_end"),
            ("professor_review_start", "professor_review_end"),
            ("college_review_start", "college_review_end"),
            ("effective_start_date", "effective_end_date"),
        ]

        for start_field, end_field in date_fields:
            start_date = config_data.get(start_field)
            end_date = config_data.get(end_field)

            if start_date and end_date:
                try:
                    from datetime import datetime

                    if isinstance(start_date, str):
                        start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                    else:
                        start_dt = start_date

                    if isinstance(end_date, str):
                        end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                    else:
                        end_dt = end_date

                    if start_dt >= end_dt:
                        errors.append(f"{end_field} must be after {start_field}")
                except (ValueError, TypeError):
                    errors.append(f"Invalid date format for {start_field} or {end_field}")

        return errors

    async def get_configuration_analytics(self, config: ScholarshipConfiguration) -> Dict[str, Any]:
        """Get analytics data for a configuration"""
        # Get applications for this configuration's scholarship type
        stmt = select(Application).where(Application.scholarship_type_id == config.scholarship_type_id)
        result = await self.db.execute(stmt)
        applications = result.scalars().all()

        total_applications = len(applications)

        if total_applications == 0:
            return {
                "total_applications": 0,
                "status_breakdown": {},
                "usage_analytics": {},
                "trends": {},
            }

        # Status breakdown
        status_breakdown = {}
        for status in ApplicationStatus:
            count = len([app for app in applications if app.status == status.value])
            if count > 0:
                status_breakdown[status.value] = count

        # Usage analytics
        approved_count = status_breakdown.get(ApplicationStatus.approved.value, 0)
        usage_analytics = {
            "approval_rate": (approved_count / total_applications) * 100 if total_applications > 0 else 0,
            "quota_usage": None,
            "college_breakdown": {},
        }

        if config.has_quota_limit and config.total_quota:
            usage_analytics["quota_usage"] = {
                "total_quota": config.total_quota,
                "used": approved_count,
                "available": max(0, config.total_quota - approved_count),
                "usage_percentage": (approved_count / config.total_quota) * 100,
            }

        # Time trends (simplified)
        from collections import defaultdict

        monthly_trends = defaultdict(int)

        for app in applications:
            if app.created_at:
                month_key = app.created_at.strftime("%Y-%m")
                monthly_trends[month_key] += 1

        return {
            "total_applications": total_applications,
            "status_breakdown": status_breakdown,
            "usage_analytics": usage_analytics,
            "trends": {"monthly_applications": dict(monthly_trends)},
            "configuration_effectiveness": {
                "is_effective": config.is_effective,
                "validation_status": len(config.validate_quota_config()) == 0,
            },
        }

    async def create_configuration_version(
        self,
        original_config: ScholarshipConfiguration,
        updates: Dict[str, Any],
        user_id: int,
    ) -> ScholarshipConfiguration:
        """Create a new version of configuration with updates"""
        # Export current configuration
        config_data = original_config.export_config()

        # Apply updates
        config_data.update(updates)

        # Increment version
        current_version = original_config.version or "1.0"
        version_parts = current_version.split(".")
        major, minor = int(version_parts[0]), int(version_parts[1])

        # Determine if this is a major or minor version change
        major_changes = [
            "quota_management_mode",
            "has_quota_limit",
            "application_period",
        ]
        is_major_change = any(key in updates for key in major_changes)

        if is_major_change:
            new_version = f"{major + 1}.0"
        else:
            new_version = f"{major}.{minor + 1}"

        # Create new configuration
        new_config = ScholarshipConfiguration(
            **config_data,
            scholarship_type_id=original_config.scholarship_type_id,
            config_code=f"{original_config.config_code}_v{new_version.replace('.', '_')}",
            version=new_version,
            previous_config_id=original_config.id,
            is_active=True,
            created_by=user_id,
            updated_by=user_id,
        )

        # Deactivate original configuration
        original_config.is_active = False
        original_config.updated_by = user_id

        self.db.add(new_config)
        await self.db.commit()
        await self.db.refresh(new_config)

        return new_config

    async def import_configurations(
        self,
        configurations_data: List[Dict[str, Any]],
        user_id: int,
        overwrite_existing: bool = False,
    ) -> Tuple[List[ScholarshipConfiguration], List[str]]:
        """Import configurations from data"""
        imported_configs = []
        errors = []

        for i, config_data in enumerate(configurations_data):
            try:
                config_code = config_data.get("config_code")
                if not config_code:
                    errors.append(f"Configuration {i+1}: Missing config_code")
                    continue

                # Check if exists
                existing = await self.get_configuration_by_code(config_code)
                if existing and not overwrite_existing:
                    errors.append(f"Configuration {i+1}: Code '{config_code}' already exists")
                    continue

                # Validate scholarship type
                scholarship_type_id = config_data.get("scholarship_type_id")
                if not scholarship_type_id:
                    errors.append(f"Configuration {i+1}: Missing scholarship_type_id")
                    continue

                stmt = select(ScholarshipType).where(ScholarshipType.id == scholarship_type_id)
                result = await self.db.execute(stmt)
                scholarship_type = result.scalar_one_or_none()

                if not scholarship_type:
                    errors.append(f"Configuration {i+1}: Scholarship type {scholarship_type_id} not found")
                    continue

                # Create or update configuration
                if existing and overwrite_existing:
                    # Update existing
                    for key, value in config_data.items():
                        if hasattr(existing, key) and key not in [
                            "id",
                            "created_at",
                            "created_by",
                        ]:
                            setattr(existing, key, value)
                    existing.updated_by = user_id
                    imported_configs.append(existing)
                else:
                    # Create new
                    new_config = ScholarshipConfiguration(**config_data, created_by=user_id, updated_by=user_id)

                    # Validate
                    validation_errors = new_config.validate_quota_config()
                    if validation_errors:
                        errors.append(f"Configuration {i+1}: {'; '.join(validation_errors)}")
                        continue

                    self.db.add(new_config)
                    imported_configs.append(new_config)

            except Exception as e:
                errors.append(f"Configuration {i+1}: {str(e)}")

        if imported_configs and not errors:
            await self.db.commit()
            for config in imported_configs:
                await self.db.refresh(config)

        return imported_configs, errors

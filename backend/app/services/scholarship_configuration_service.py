"""
Scholarship Configuration Service
Handles business logic for dynamic scholarship configurations
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func

from app.models.scholarship import ScholarshipType, ScholarshipConfiguration
from app.models.application import Application, ApplicationStatus
from app.models.enums import ApplicationCycle, QuotaManagementMode
from app.models.user import User


class ScholarshipConfigurationService:
    """Service class for scholarship configuration management"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_active_configurations(
        self, 
        scholarship_type_id: Optional[int] = None
    ) -> List[ScholarshipConfiguration]:
        """Get all active and effective configurations"""
        query = self.db.query(ScholarshipConfiguration).filter(
            ScholarshipConfiguration.is_active == True
        )
        
        if scholarship_type_id:
            query = query.filter(ScholarshipConfiguration.scholarship_type_id == scholarship_type_id)
        
        now = datetime.now(timezone.utc)
        configurations = query.all()
        
        # Filter by effective dates
        effective_configs = []
        for config in configurations:
            if config.is_effective:
                effective_configs.append(config)
        
        return effective_configs
    
    def get_configuration_by_code(self, config_code: str) -> Optional[ScholarshipConfiguration]:
        """Get configuration by its unique code"""
        return self.db.query(ScholarshipConfiguration).filter(
            ScholarshipConfiguration.config_code == config_code
        ).first()
    
    def validate_configuration_requirements(
        self, 
        config: ScholarshipConfiguration, 
        application_data: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """Validate if application meets configuration requirements"""
        errors = []
        
        # Check interview requirement
        if config.requires_interview and not application_data.get('interview_scheduled'):
            errors.append("此獎學金需要面試")
        
        # Check recommendation letter requirement
        if config.requires_recommendation_letter and not application_data.get('recommendation_letter'):
            errors.append("此獎學金需要推薦信")
        
        # Check research proposal requirement
        if config.requires_research_proposal and not application_data.get('research_proposal'):
            errors.append("此獎學金需要研究計畫")
        
        # Check special requirements
        if config.special_requirements:
            for requirement_key, requirement_value in config.special_requirements.items():
                if requirement_key not in application_data or application_data[requirement_key] != requirement_value:
                    errors.append(f"不符合特殊要求: {requirement_key}")
        
        # Check eligibility overrides
        if config.eligibility_overrides:
            # This would implement complex eligibility logic
            pass
        
        return len(errors) == 0, errors
    
    def check_quota_availability(
        self, 
        config: ScholarshipConfiguration, 
        college_code: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """Check if quota is available for application"""
        if config.quota_management_mode == QuotaManagementMode.NONE:
            return True, {"unlimited": True}
        
        # Get current approved applications
        approved_count = self.db.query(Application).filter(
            and_(
                Application.scholarship_type_id == config.scholarship_type_id,
                Application.status == ApplicationStatus.APPROVED.value
            )
        ).count()
        
        quota_info = {
            "total_quota": config.total_quota,
            "used_quota": approved_count,
            "available_quota": None,
            "usage_percentage": None
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
    
    def calculate_application_score(
        self, 
        config: ScholarshipConfiguration,
        application_data: Dict[str, Any]
    ) -> float:
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
    
    def apply_auto_screening(
        self, 
        config: ScholarshipConfiguration,
        applications: List[Application]
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
                    student_app_count = self.db.query(Application).filter(
                        Application.user_id == application.user_id
                    ).count()
                    
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
    
    def get_configuration_analytics(
        self, 
        config: ScholarshipConfiguration
    ) -> Dict[str, Any]:
        """Get analytics data for a configuration"""
        # Get applications for this configuration's scholarship type
        applications = self.db.query(Application).filter(
            Application.scholarship_type_id == config.scholarship_type_id
        ).all()
        
        total_applications = len(applications)
        
        if total_applications == 0:
            return {
                "total_applications": 0,
                "status_breakdown": {},
                "usage_analytics": {},
                "trends": {}
            }
        
        # Status breakdown
        status_breakdown = {}
        for status in ApplicationStatus:
            count = len([app for app in applications if app.status == status.value])
            if count > 0:
                status_breakdown[status.value] = count
        
        # Usage analytics
        approved_count = status_breakdown.get(ApplicationStatus.APPROVED.value, 0)
        usage_analytics = {
            "approval_rate": (approved_count / total_applications) * 100 if total_applications > 0 else 0,
            "quota_usage": None,
            "college_breakdown": {}
        }
        
        if config.has_quota_limit and config.total_quota:
            usage_analytics["quota_usage"] = {
                "total_quota": config.total_quota,
                "used": approved_count,
                "available": max(0, config.total_quota - approved_count),
                "usage_percentage": (approved_count / config.total_quota) * 100
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
            "trends": {
                "monthly_applications": dict(monthly_trends)
            },
            "configuration_effectiveness": {
                "is_effective": config.is_effective,
                "validation_status": len(config.validate_quota_config()) == 0
            }
        }
    
    def create_configuration_version(
        self, 
        original_config: ScholarshipConfiguration,
        updates: Dict[str, Any],
        user_id: int
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
        major_changes = ["quota_management_mode", "has_quota_limit", "application_period"]
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
            updated_by=user_id
        )
        
        # Deactivate original configuration
        original_config.is_active = False
        original_config.updated_by = user_id
        
        self.db.add(new_config)
        self.db.commit()
        self.db.refresh(new_config)
        
        return new_config
    
    def import_configurations(
        self, 
        configurations_data: List[Dict[str, Any]],
        user_id: int,
        overwrite_existing: bool = False
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
                existing = self.get_configuration_by_code(config_code)
                if existing and not overwrite_existing:
                    errors.append(f"Configuration {i+1}: Code '{config_code}' already exists")
                    continue
                
                # Validate scholarship type
                scholarship_type_id = config_data.get("scholarship_type_id")
                if not scholarship_type_id:
                    errors.append(f"Configuration {i+1}: Missing scholarship_type_id")
                    continue
                
                scholarship_type = self.db.query(ScholarshipType).filter(
                    ScholarshipType.id == scholarship_type_id
                ).first()
                
                if not scholarship_type:
                    errors.append(f"Configuration {i+1}: Scholarship type {scholarship_type_id} not found")
                    continue
                
                # Create or update configuration
                if existing and overwrite_existing:
                    # Update existing
                    for key, value in config_data.items():
                        if hasattr(existing, key) and key not in ['id', 'created_at', 'created_by']:
                            setattr(existing, key, value)
                    existing.updated_by = user_id
                    imported_configs.append(existing)
                else:
                    # Create new
                    new_config = ScholarshipConfiguration(
                        **config_data,
                        created_by=user_id,
                        updated_by=user_id
                    )
                    
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
            self.db.commit()
            for config in imported_configs:
                self.db.refresh(config)
        
        return imported_configs, errors
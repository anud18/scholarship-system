"""
Automated eligibility verification service for scholarship applications
Performs comprehensive checks based on scholarship rules and student data
"""

from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.scholarship import ScholarshipType, ScholarshipRule
# Student model removed - student data now fetched from external API
# StudentType enum removed - use database lookup instead
from app.models.application import Application, ApplicationStatus, ScholarshipMainType, ScholarshipSubType
from app.models.user import User
from app.services.student_service import StudentService

import logging

logger = logging.getLogger(__name__)


class EligibilityVerificationService:
    """Service for automated eligibility verification"""
    
    def __init__(self, db: Session):
        self.db = db
        self.student_service = StudentService()
    
    def verify_student_eligibility(
        self, 
        student_id: int, 
        scholarship_type_id: int, 
        semester: str
    ) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Comprehensive eligibility verification for a student and scholarship
        
        Returns:
            - bool: Whether student is eligible
            - List[str]: List of failure reasons (empty if eligible)
            - Dict[str, Any]: Verification details and scores
        """
        
        try:
            student = self.db.query(Student).filter(Student.id == student_id).first()
            scholarship_type = self.db.query(ScholarshipType).filter(
                ScholarshipType.id == scholarship_type_id
            ).first()
            
            if not student or not scholarship_type:
                return False, ["Student or scholarship type not found"], {}
            
            verification_results = {
                "student_id": student_id,
                "scholarship_type_id": scholarship_type_id,
                "verification_timestamp": datetime.now(timezone.utc).isoformat(),
                "checks_performed": [],
                "scores": {},
                "warnings": []
            }
            
            failure_reasons = []
            
            # 1. Basic scholarship status check
            if not scholarship_type.is_active:
                failure_reasons.append("Scholarship type is not active")
                verification_results["checks_performed"].append({
                    "check": "scholarship_active",
                    "passed": False,
                    "details": "Scholarship is inactive"
                })
            else:
                verification_results["checks_performed"].append({
                    "check": "scholarship_active",
                    "passed": True,
                    "details": "Scholarship is active"
                })
            
            # 2. Application period check
            in_application_period = scholarship_type.is_application_period
            if not in_application_period:
                failure_reasons.append("Not currently in application period")
                verification_results["checks_performed"].append({
                    "check": "application_period",
                    "passed": False,
                    "details": f"Period: {scholarship_type.application_start_date} to {scholarship_type.application_end_date}"
                })
            else:
                verification_results["checks_performed"].append({
                    "check": "application_period",
                    "passed": True,
                    "details": f"Within application period"
                })
            
            # 3. Whitelist check
            in_whitelist = scholarship_type.is_student_in_whitelist(student_id)
            if not in_whitelist:
                failure_reasons.append("Student not in scholarship whitelist")
                verification_results["checks_performed"].append({
                    "check": "whitelist",
                    "passed": False,
                    "details": "Student not authorized for this scholarship"
                })
            else:
                verification_results["checks_performed"].append({
                    "check": "whitelist",
                    "passed": True,
                    "details": "Student is authorized"
                })
            
            # 4. Duplicate application check
            existing_app = self.db.query(Application).filter(
                and_(
                    Application.student_id == student_id,
                    Application.scholarship_type_id == scholarship_type_id,
                    Application.semester == semester,
                    Application.status.notin_([
                        ApplicationStatus.WITHDRAWN.value,
                        ApplicationStatus.REJECTED.value,
                        ApplicationStatus.CANCELLED.value
                    ])
                )
            ).first()
            
            if existing_app:
                failure_reasons.append(f"Already has an active application ({existing_app.app_id})")
                verification_results["checks_performed"].append({
                    "check": "duplicate_application",
                    "passed": False,
                    "details": f"Existing application: {existing_app.app_id}"
                })
            else:
                verification_results["checks_performed"].append({
                    "check": "duplicate_application",
                    "passed": True,
                    "details": "No conflicting applications found"
                })
            
            # 5. Academic eligibility checks
            academic_eligible, academic_details = self._check_academic_eligibility(
                student, scholarship_type
            )
            verification_results["checks_performed"].extend(academic_details["checks"])
            verification_results["scores"].update(academic_details["scores"])
            
            if not academic_eligible:
                failure_reasons.extend(academic_details["failures"])
            
            # 6. Scholarship-specific rule validation
            rules_passed, rules_details = self._validate_scholarship_rules(
                student, scholarship_type
            )
            verification_results["checks_performed"].extend(rules_details["checks"])
            verification_results["scores"].update(rules_details["scores"])
            
            if not rules_passed:
                failure_reasons.extend(rules_details["failures"])
            
            # 7. Check renewal eligibility if applicable
            renewal_eligible, renewal_details = self._check_renewal_eligibility(
                student_id, scholarship_type_id, semester
            )
            verification_results["checks_performed"].extend(renewal_details["checks"])
            if renewal_details.get("is_renewal_candidate"):
                verification_results["renewal_candidate"] = True
                verification_results["previous_applications"] = renewal_details.get("previous_applications", [])
            
            # 8. Calculate overall eligibility score
            total_checks = len(verification_results["checks_performed"])
            passed_checks = sum(1 for check in verification_results["checks_performed"] if check["passed"])
            eligibility_score = (passed_checks / total_checks * 100) if total_checks > 0 else 0
            
            verification_results["eligibility_score"] = eligibility_score
            verification_results["total_checks"] = total_checks
            verification_results["passed_checks"] = passed_checks
            
            # Overall eligibility determination
            is_eligible = len(failure_reasons) == 0
            
            logger.info(f"Eligibility check for student {student_id}, scholarship {scholarship_type_id}: {'PASS' if is_eligible else 'FAIL'}")
            
            return is_eligible, failure_reasons, verification_results
            
        except Exception as e:
            logger.error(f"Error in eligibility verification: {str(e)}")
            return False, [f"Verification error: {str(e)}"], {}
    
    def _check_academic_eligibility(
        self, 
        student: Student, 
        scholarship_type: ScholarshipType
    ) -> Tuple[bool, Dict[str, Any]]:
        """Check academic eligibility requirements"""
        
        details = {
            "checks": [],
            "scores": {},
            "failures": []
        }
        
        # Use student data directly since academic records are now managed externally
        # For development, we'll use the student data that's available
        if not student:
            details["failures"].append("Missing student data")
            details["checks"].append({
                "check": "student_data",
                "passed": False,
                "details": "Student data not found"
            })
            return False, details
        
        details["checks"].append({
            "check": "student_data",
            "passed": True,
            "details": "Student data found"
        })
        
        # Determine student type
        student_type = self._determine_student_type(student)
        details["scores"]["student_type"] = student_type.value
        
        # Check if student type is eligible for this scholarship
        if scholarship_type.eligible_student_types:
            if student_type.value not in scholarship_type.eligible_student_types:
                details["failures"].append(f"Student type {student_type.value} not eligible")
                details["checks"].append({
                    "check": "student_type_eligibility",
                    "passed": False,
                    "details": f"Required: {scholarship_type.eligible_student_types}, Actual: {student_type.value}"
                })
            else:
                details["checks"].append({
                    "check": "student_type_eligibility",
                    "passed": True,
                    "details": f"Student type {student_type.value} is eligible"
                })
        
        # GPA check
        if scholarship_type.min_gpa and term_record.gpa:
            gpa_eligible = float(term_record.gpa) >= float(scholarship_type.min_gpa)
            details["scores"]["gpa"] = float(term_record.gpa)
            details["scores"]["required_gpa"] = float(scholarship_type.min_gpa)
            
            if not gpa_eligible:
                details["failures"].append(f"GPA {term_record.gpa} below minimum {scholarship_type.min_gpa}")
                details["checks"].append({
                    "check": "gpa_requirement",
                    "passed": False,
                    "details": f"GPA {term_record.gpa} < {scholarship_type.min_gpa}"
                })
            else:
                details["checks"].append({
                    "check": "gpa_requirement",
                    "passed": True,
                    "details": f"GPA {term_record.gpa} meets requirement"
                })
        
        # Ranking check
        if scholarship_type.max_ranking_percent:
            if term_record.placingsrate:
                ranking_eligible = float(term_record.placingsrate) <= float(scholarship_type.max_ranking_percent)
                details["scores"]["class_ranking_percent"] = float(term_record.placingsrate)
                details["scores"]["max_ranking_percent"] = float(scholarship_type.max_ranking_percent)
                
                if not ranking_eligible:
                    details["failures"].append(f"Class ranking {term_record.placingsrate}% exceeds maximum {scholarship_type.max_ranking_percent}%")
                    details["checks"].append({
                        "check": "ranking_requirement",
                        "passed": False,
                        "details": f"Ranking {term_record.placingsrate}% > {scholarship_type.max_ranking_percent}%"
                    })
                else:
                    details["checks"].append({
                        "check": "ranking_requirement",
                        "passed": True,
                        "details": f"Ranking {term_record.placingsrate}% meets requirement"
                    })
        
        # Term count check
        if scholarship_type.max_completed_terms and term_record.completedTerms:
            terms_eligible = term_record.completedTerms <= scholarship_type.max_completed_terms
            details["scores"]["completed_terms"] = term_record.completedTerms
            details["scores"]["max_completed_terms"] = scholarship_type.max_completed_terms
            
            if not terms_eligible:
                details["failures"].append(f"Completed terms {term_record.completedTerms} exceeds maximum {scholarship_type.max_completed_terms}")
                details["checks"].append({
                    "check": "term_count_requirement",
                    "passed": False,
                    "details": f"Terms {term_record.completedTerms} > {scholarship_type.max_completed_terms}"
                })
            else:
                details["checks"].append({
                    "check": "term_count_requirement",
                    "passed": True,
                    "details": f"Terms {term_record.completedTerms} meets requirement"
                })
        
        is_eligible = len(details["failures"]) == 0
        return is_eligible, details
    
    def _validate_scholarship_rules(
        self, 
        student: Student, 
        scholarship_type: ScholarshipType
    ) -> Tuple[bool, Dict[str, Any]]:
        """Validate custom scholarship rules"""
        
        details = {
            "checks": [],
            "scores": {},
            "failures": []
        }
        
        rules = self.db.query(ScholarshipRule).filter(
            and_(
                ScholarshipRule.scholarship_type_id == scholarship_type.id,
                ScholarshipRule.is_active == True
            )
        ).order_by(ScholarshipRule.priority.desc()).all()
        
        if not rules:
            details["checks"].append({
                "check": "custom_rules",
                "passed": True,
                "details": "No custom rules defined"
            })
            return True, details
        
        # Process rules using student data directly
        rule_scores = []
        
        for rule in rules:
            try:
                # Get the value to check based on rule's condition field
                value_to_check = self._get_student_value_for_rule(student, rule.condition_field)
                
                if value_to_check is None:
                    if rule.is_required:
                        details["failures"].append(f"Required field {rule.condition_field} is missing")
                        details["checks"].append({
                            "check": f"rule_{rule.rule_name}",
                            "passed": False,
                            "details": f"Missing required field: {rule.condition_field}"
                        })
                    continue
                
                # Validate the rule
                rule_passed = rule.validate(value_to_check)
                rule_score = float(rule.weight) if rule_passed else 0
                rule_scores.append(rule_score)
                
                details["scores"][f"rule_{rule.rule_name}"] = rule_score
                details["checks"].append({
                    "check": f"rule_{rule.rule_name}",
                    "passed": rule_passed,
                    "details": f"{rule.condition_field} {rule.operator} {rule.expected_value} -> {value_to_check}"
                })
                
                if not rule_passed and rule.is_required:
                    error_msg = rule.error_message or f"Rule failed: {rule.rule_name}"
                    details["failures"].append(error_msg)
                
            except Exception as e:
                logger.error(f"Error validating rule {rule.id}: {str(e)}")
                if rule.is_required:
                    details["failures"].append(f"Rule validation error: {rule.rule_name}")
        
        # Calculate overall rule score
        if rule_scores:
            details["scores"]["overall_rule_score"] = sum(rule_scores) / len(rule_scores)
        
        is_eligible = len(details["failures"]) == 0
        return is_eligible, details
    
    def _check_renewal_eligibility(
        self, 
        student_id: int, 
        scholarship_type_id: int, 
        semester: str
    ) -> Tuple[bool, Dict[str, Any]]:
        """Check if student is eligible for renewal"""
        
        details = {
            "checks": [],
            "is_renewal_candidate": False,
            "previous_applications": []
        }
        
        # Look for previous approved applications
        previous_apps = self.db.query(Application).filter(
            and_(
                Application.student_id == student_id,
                Application.scholarship_type_id == scholarship_type_id,
                Application.status == ApplicationStatus.APPROVED.value
            )
        ).order_by(Application.created_at.desc()).all()
        
        if previous_apps:
            details["is_renewal_candidate"] = True
            details["previous_applications"] = [
                {
                    "app_id": app.app_id,
                    "semester": app.semester,
                    "academic_year": app.academic_year,
                    "approved_at": app.approved_at.isoformat() if app.approved_at else None
                }
                for app in previous_apps[:3]  # Last 3 applications
            ]
            
            details["checks"].append({
                "check": "renewal_candidate",
                "passed": True,
                "details": f"Found {len(previous_apps)} previous approved applications"
            })
        else:
            details["checks"].append({
                "check": "renewal_candidate",
                "passed": True,
                "details": "New applicant - no previous applications"
            })
        
        return True, details
    
    def _determine_student_type(self, student: Student) -> str:
        """Determine student type based on student data"""
        return student.get_student_type()
    
    def _get_student_value_for_rule(self, student: Student, field_name: str) -> Any:
        """Get student value for rule validation"""
        
        # Map field names to actual values from student model
        field_mapping = {
            "gpa": 3.0,  # Default GPA - should be fetched from external API
            "class_ranking": None,  # To be fetched from external API
            "completed_terms": student.std_termcount or 1,
            "student_id": student.std_stdcode,
            "department": student.std_depno,
            "grade": None,  # To be calculated from enrollment data
            # Add more field mappings as needed
        }
        
        return field_mapping.get(field_name)
    
    def run_batch_eligibility_verification(
        self, 
        scholarship_type_id: int, 
        semester: str,
        student_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Run eligibility verification for multiple students"""
        
        try:
            # Get students to check
            if student_ids:
                students = self.db.query(Student).filter(Student.id.in_(student_ids)).all()
            else:
                # Get all students if no specific list provided
                students = self.db.query(Student).all()
            
            results = {
                "scholarship_type_id": scholarship_type_id,
                "semester": semester,
                "total_students": len(students),
                "eligible_students": [],
                "ineligible_students": [],
                "verification_errors": []
            }
            
            for student in students:
                try:
                    is_eligible, failure_reasons, verification_details = self.verify_student_eligibility(
                        student.id, scholarship_type_id, semester
                    )
                    
                    student_result = {
                        "student_id": student.id,
                        "student_name": student.name,
                        "student_no": student.stdNo,
                        "is_eligible": is_eligible,
                        "failure_reasons": failure_reasons,
                        "eligibility_score": verification_details.get("eligibility_score", 0),
                        "verification_details": verification_details
                    }
                    
                    if is_eligible:
                        results["eligible_students"].append(student_result)
                    else:
                        results["ineligible_students"].append(student_result)
                        
                except Exception as e:
                    logger.error(f"Error verifying eligibility for student {student.id}: {str(e)}")
                    results["verification_errors"].append({
                        "student_id": student.id,
                        "error": str(e)
                    })
            
            results["eligible_count"] = len(results["eligible_students"])
            results["ineligible_count"] = len(results["ineligible_students"])
            results["error_count"] = len(results["verification_errors"])
            
            logger.info(f"Batch eligibility verification complete: {results['eligible_count']} eligible, {results['ineligible_count']} ineligible, {results['error_count']} errors")
            
            return results
            
        except Exception as e:
            logger.error(f"Error in batch eligibility verification: {str(e)}")
            return {
                "error": str(e),
                "total_students": 0,
                "eligible_count": 0,
                "ineligible_count": 0,
                "error_count": 1
            }
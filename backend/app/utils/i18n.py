"""
Internationalization (i18n) utilities for multilingual support
Supports Traditional Chinese (zh-TW) and English (en) as specified in issue #10
"""

from typing import Dict, Any, Optional
from enum import Enum

class Language(Enum):
    """Supported languages"""
    TRADITIONAL_CHINESE = "zh-TW"
    ENGLISH = "en"

class ScholarshipI18n:
    """Internationalization service for scholarship system"""
    
    # Translation dictionaries
    TRANSLATIONS = {
        Language.TRADITIONAL_CHINESE.value: {
            # Application Status
            "application_status": {
                "draft": "草稿",
                "submitted": "已提交",
                "under_review": "審核中",
                "professor_review": "教授審核中",
                "approved": "已核准",
                "rejected": "已拒絕",
                "withdrawn": "已撤回",
                "returned": "已退回",
                "cancelled": "已取消"
            },
            
            # Scholarship Types
            "scholarship_main_types": {
                "UNDERGRADUATE_FRESHMAN": "大學新鮮人獎學金",
                "PHD": "博士獎學金",
                "DIRECT_PHD": "直升博士獎學金"
            },
            
            "scholarship_sub_types": {
                "GENERAL": "一般類",
                "NSTC": "國科會類",
                "MOE_1W": "教育部一般",
                "MOE_2W": "教育部特殊"
            },
            
            # Common Messages
            "messages": {
                "application_submitted": "申請已成功提交",
                "application_approved": "恭喜！您的獎學金申請已獲核准",
                "application_rejected": "很抱歉，您的獎學金申請未獲核准",
                "eligibility_check_passed": "資格審查通過",
                "eligibility_check_failed": "資格審查未通過",
                "quota_exceeded": "名額已滿",
                "document_required": "需要文件",
                "review_deadline": "審核截止日期",
                "priority_processing": "優先處理",
                "renewal_application": "續領申請"
            },
            
            # Form Labels
            "form_labels": {
                "student_name": "學生姓名",
                "student_id": "學號",
                "scholarship_type": "獎學金類型",
                "semester": "學期",
                "academic_year": "學年度",
                "amount": "金額",
                "application_date": "申請日期",
                "submit_application": "提交申請",
                "save_draft": "儲存草稿",
                "upload_document": "上傳文件",
                "review_comment": "審核意見"
            },
            
            # Error Messages
            "errors": {
                "invalid_student_type": "學生類別不符合資格",
                "gpa_too_low": "GPA未達最低要求",
                "missing_documents": "缺少必要文件",
                "application_period_closed": "申請期間已結束",
                "not_in_whitelist": "您不在此獎學金的申請名單中",
                "already_applied": "您已經在本學期申請過此獎學金",
                "quota_full": "本獎學金名額已滿",
                "system_error": "系統錯誤，請稍後再試"
            },
            
            # Email Content
            "email": {
                "subject_application_submitted": "獎學金申請已提交",
                "subject_status_changed": "獎學金申請狀態更新",
                "subject_deadline_reminder": "獎學金審核期限提醒",
                "greeting": "親愛的",
                "closing": "此致\n獎學金管理小組",
                "auto_message_note": "此為系統自動發送之訊息，請勿回覆。"
            },
            
            # Dashboard Labels
            "dashboard": {
                "total_applications": "總申請數",
                "approved_applications": "已核准申請",
                "pending_applications": "待審核申請",
                "approval_rate": "核准率",
                "processing_time": "平均處理時間",
                "quota_status": "名額狀態",
                "overdue_applications": "逾期申請",
                "priority_distribution": "優先順序分布"
            }
        },
        
        Language.ENGLISH.value: {
            # Application Status
            "application_status": {
                "draft": "Draft",
                "submitted": "Submitted",
                "under_review": "Under Review",
                "professor_review": "Professor Review",
                "approved": "Approved",
                "rejected": "Rejected",
                "withdrawn": "Withdrawn",
                "returned": "Returned",
                "cancelled": "Cancelled"
            },
            
            # Scholarship Types
            "scholarship_main_types": {
                "UNDERGRADUATE_FRESHMAN": "Undergraduate Freshman Scholarship",
                "PHD": "PhD Scholarship",
                "DIRECT_PHD": "Direct PhD Scholarship"
            },
            
            "scholarship_sub_types": {
                "GENERAL": "General",
                "NSTC": "NSTC",
                "MOE_1W": "MOE Type 1W",
                "MOE_2W": "MOE Type 2W"
            },
            
            # Common Messages
            "messages": {
                "application_submitted": "Application submitted successfully",
                "application_approved": "Congratulations! Your scholarship application has been approved",
                "application_rejected": "We regret to inform you that your scholarship application was not approved",
                "eligibility_check_passed": "Eligibility check passed",
                "eligibility_check_failed": "Eligibility check failed",
                "quota_exceeded": "Quota exceeded",
                "document_required": "Document required",
                "review_deadline": "Review deadline",
                "priority_processing": "Priority processing",
                "renewal_application": "Renewal application"
            },
            
            # Form Labels
            "form_labels": {
                "student_name": "Student Name",
                "student_id": "Student ID",
                "scholarship_type": "Scholarship Type",
                "semester": "Semester",
                "academic_year": "Academic Year",
                "amount": "Amount",
                "application_date": "Application Date",
                "submit_application": "Submit Application",
                "save_draft": "Save Draft",
                "upload_document": "Upload Document",
                "review_comment": "Review Comment"
            },
            
            # Error Messages
            "errors": {
                "invalid_student_type": "Student type is not eligible",
                "gpa_too_low": "GPA does not meet minimum requirement",
                "missing_documents": "Missing required documents",
                "application_period_closed": "Application period has ended",
                "not_in_whitelist": "You are not authorized for this scholarship",
                "already_applied": "You have already applied for this scholarship this semester",
                "quota_full": "Scholarship quota is full",
                "system_error": "System error, please try again later"
            },
            
            # Email Content
            "email": {
                "subject_application_submitted": "Scholarship Application Submitted",
                "subject_status_changed": "Scholarship Application Status Update",
                "subject_deadline_reminder": "Scholarship Review Deadline Reminder",
                "greeting": "Dear",
                "closing": "Best regards,\nScholarship Management Team",
                "auto_message_note": "This is an automated message. Please do not reply."
            },
            
            # Dashboard Labels
            "dashboard": {
                "total_applications": "Total Applications",
                "approved_applications": "Approved Applications",
                "pending_applications": "Pending Applications",
                "approval_rate": "Approval Rate",
                "processing_time": "Average Processing Time",
                "quota_status": "Quota Status",
                "overdue_applications": "Overdue Applications",
                "priority_distribution": "Priority Distribution"
            }
        }
    }
    
    @classmethod
    def get_text(
        cls, 
        key: str, 
        category: str = "messages", 
        language: str = Language.TRADITIONAL_CHINESE.value,
        fallback_language: str = Language.ENGLISH.value
    ) -> str:
        """Get translated text for a given key"""
        
        try:
            # Try primary language
            if language in cls.TRANSLATIONS:
                if category in cls.TRANSLATIONS[language]:
                    if key in cls.TRANSLATIONS[language][category]:
                        return cls.TRANSLATIONS[language][category][key]
            
            # Fallback to fallback language
            if fallback_language in cls.TRANSLATIONS:
                if category in cls.TRANSLATIONS[fallback_language]:
                    if key in cls.TRANSLATIONS[fallback_language][category]:
                        return cls.TRANSLATIONS[fallback_language][category][key]
            
            # Return key if no translation found
            return key.replace("_", " ").title()
            
        except Exception:
            return key.replace("_", " ").title()
    
    @classmethod
    def get_application_status_text(cls, status: str, language: str = Language.TRADITIONAL_CHINESE.value) -> str:
        """Get translated application status text"""
        return cls.get_text(status, "application_status", language)
    
    @classmethod
    def get_scholarship_type_text(cls, type_value: str, language: str = Language.TRADITIONAL_CHINESE.value) -> str:
        """Get translated scholarship type text"""
        # Try main types first
        text = cls.get_text(type_value, "scholarship_main_types", language)
        if text == type_value.replace("_", " ").title():
            # Try sub types
            text = cls.get_text(type_value, "scholarship_sub_types", language)
        return text
    
    @classmethod
    def get_error_message(cls, error_key: str, language: str = Language.TRADITIONAL_CHINESE.value) -> str:
        """Get translated error message"""
        return cls.get_text(error_key, "errors", language)
    
    @classmethod
    def get_form_label(cls, label_key: str, language: str = Language.TRADITIONAL_CHINESE.value) -> str:
        """Get translated form label"""
        return cls.get_text(label_key, "form_labels", language)
    
    @classmethod
    def get_dashboard_label(cls, label_key: str, language: str = Language.TRADITIONAL_CHINESE.value) -> str:
        """Get translated dashboard label"""
        return cls.get_text(label_key, "dashboard", language)
    
    @classmethod
    def get_email_content(cls, content_key: str, language: str = Language.TRADITIONAL_CHINESE.value) -> str:
        """Get translated email content"""
        return cls.get_text(content_key, "email", language)
    
    @classmethod
    def localize_application_data(cls, application_data: Dict[str, Any], language: str = Language.TRADITIONAL_CHINESE.value) -> Dict[str, Any]:
        """Localize application data for display"""
        
        localized_data = application_data.copy()
        
        # Translate status
        if "status" in localized_data:
            localized_data["status_text"] = cls.get_application_status_text(localized_data["status"], language)
        
        # Translate scholarship types
        if "main_scholarship_type" in localized_data:
            localized_data["main_type_text"] = cls.get_scholarship_type_text(localized_data["main_scholarship_type"], language)
        
        if "sub_scholarship_type" in localized_data:
            localized_data["sub_type_text"] = cls.get_scholarship_type_text(localized_data["sub_scholarship_type"], language)
        
        # Add localized labels
        localized_data["labels"] = {
            "student_name": cls.get_form_label("student_name", language),
            "student_id": cls.get_form_label("student_id", language),
            "scholarship_type": cls.get_form_label("scholarship_type", language),
            "semester": cls.get_form_label("semester", language),
            "amount": cls.get_form_label("amount", language),
            "application_date": cls.get_form_label("application_date", language)
        }
        
        return localized_data
    
    @classmethod
    def get_supported_languages(cls) -> List[Dict[str, str]]:
        """Get list of supported languages"""
        return [
            {"code": Language.TRADITIONAL_CHINESE.value, "name": "繁體中文", "name_en": "Traditional Chinese"},
            {"code": Language.ENGLISH.value, "name": "English", "name_en": "English"}
        ]
    
    @classmethod
    def detect_language_from_request(cls, accept_language_header: Optional[str] = None) -> str:
        """Detect preferred language from request headers"""
        
        if not accept_language_header:
            return Language.TRADITIONAL_CHINESE.value
        
        # Simple language detection based on Accept-Language header
        if "zh" in accept_language_header.lower():
            return Language.TRADITIONAL_CHINESE.value
        elif "en" in accept_language_header.lower():
            return Language.ENGLISH.value
        else:
            return Language.TRADITIONAL_CHINESE.value  # Default to Traditional Chinese
    
    @classmethod
    def get_localized_email_template(
        cls, 
        template_type: str, 
        language: str = Language.TRADITIONAL_CHINESE.value,
        **kwargs
    ) -> Dict[str, str]:
        """Get localized email template"""
        
        templates = {
            "application_submitted": {
                "subject": cls.get_email_content("subject_application_submitted", language),
                "greeting": cls.get_email_content("greeting", language),
                "message": cls.get_text("application_submitted", "messages", language),
                "closing": cls.get_email_content("closing", language),
                "footer": cls.get_email_content("auto_message_note", language)
            },
            "status_changed": {
                "subject": cls.get_email_content("subject_status_changed", language),
                "greeting": cls.get_email_content("greeting", language),
                "closing": cls.get_email_content("closing", language),
                "footer": cls.get_email_content("auto_message_note", language)
            },
            "deadline_reminder": {
                "subject": cls.get_email_content("subject_deadline_reminder", language),
                "greeting": cls.get_email_content("greeting", language),
                "closing": cls.get_email_content("closing", language),
                "footer": cls.get_email_content("auto_message_note", language)
            }
        }
        
        return templates.get(template_type, templates["application_submitted"])


# Utility functions for easy access
def t(key: str, category: str = "messages", language: str = Language.TRADITIONAL_CHINESE.value) -> str:
    """Shorthand function for translation"""
    return ScholarshipI18n.get_text(key, category, language)

def get_user_language(user_data: Optional[Dict[str, Any]] = None, request_headers: Optional[Dict[str, str]] = None) -> str:
    """Get user's preferred language"""
    
    # Try to get from user preferences first
    if user_data and "preferred_language" in user_data:
        return user_data["preferred_language"]
    
    # Try to detect from request headers
    if request_headers and "accept-language" in request_headers:
        return ScholarshipI18n.detect_language_from_request(request_headers["accept-language"])
    
    # Default to Traditional Chinese
    return Language.TRADITIONAL_CHINESE.value
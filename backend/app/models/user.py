"""
User model for authentication and role management
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class UserRole(enum.Enum):
    """User role enum"""

    student = "student"
    professor = "professor"
    college = "college"
    admin = "admin"
    super_admin = "super_admin"


class UserType(enum.Enum):
    """Portal user type enum"""

    student = "student"
    employee = "employee"


class EmployeeStatus(enum.Enum):
    """Employee status enum"""

    active = "在職"
    retired = "退休"
    student = "在學"
    graduated = "畢業"

    @property
    def display_name(self) -> str:
        """Get Chinese display name for status"""
        # Values are already in Chinese, so return directly
        return self.value


class User(Base):
    """User model for authentication and authorization"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    nycu_id = Column(String(50), unique=True, nullable=False)  # nycuID
    name = Column(String(100), nullable=False)  # txtName
    email = Column(String(100))  # mail
    user_type = Column(
        Enum(UserType, values_callable=lambda obj: [e.value for e in obj]), nullable=False
    )  # employee / student
    status = Column(Enum(EmployeeStatus, values_callable=lambda obj: [e.value for e in obj]))  # 在學 / 畢業 / 在職 / 退休
    dept_code = Column(String(20))  # deptCode
    dept_name = Column(String(100))  # dept
    college_code = Column(String(10), nullable=True)  # College code for college role users
    role = Column(
        Enum(UserRole, values_callable=lambda obj: [e.value for e in obj]), default=UserRole.student
    )  # 系統內部使用角色

    # 註記欄位
    comment = Column(String(255))

    last_login_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now(timezone.utc),
        onupdate=datetime.now(timezone.utc),
    )

    raw_data = Column(JSON)  # 儲存整包 Portal 回傳資料（可選）

    # Relationships
    applications = relationship("Application", foreign_keys="[Application.user_id]", back_populates="student")
    reviews = relationship("ApplicationReview", back_populates="reviewer")
    college_reviews = relationship(
        "CollegeReview", foreign_keys="[CollegeReview.reviewer_id]", back_populates="reviewer"
    )
    notifications = relationship("Notification", back_populates="user")
    notification_reads = relationship("NotificationRead", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")
    admin_scholarships = relationship("AdminScholarship", back_populates="admin")

    # Professor-Student relationships
    professor_relationships = relationship(
        "ProfessorStudentRelationship",
        foreign_keys="[ProfessorStudentRelationship.professor_id]",
        lazy="select",
        overlaps="professor",
    )
    student_relationships = relationship(
        "ProfessorStudentRelationship",
        foreign_keys="[ProfessorStudentRelationship.student_id]",
        lazy="select",
        overlaps="student",
    )

    def __repr__(self):
        return f"<User(id={self.id}, nycu_id={self.nycu_id}, role={self.role.value})>"

    @property
    def display_name(self) -> str:
        """Get display name based on locale preference"""
        return str(self.name)

    def has_role(self, role: UserRole) -> bool:
        """Check if user has specific role"""
        return self.role == role

    def is_admin(self) -> bool:
        """Check if user is admin"""
        return bool(self.role == UserRole.admin)

    def is_student(self) -> bool:
        """Check if user is student"""
        return bool(self.role == UserRole.student)

    def is_professor(self) -> bool:
        """Check if user is professor"""
        return bool(self.role == UserRole.professor)

    def is_college(self) -> bool:
        """Check if user is college"""
        return bool(self.role == UserRole.college)

    def is_super_admin(self) -> bool:
        """Check if user is super admin"""
        return bool(self.role == UserRole.super_admin)

    def is_employee(self) -> bool:
        """Check if user is employee (professor, college, admin, super_admin)"""
        return self.role in [
            UserRole.professor,
            UserRole.college,
            UserRole.admin,
            UserRole.super_admin,
        ]

    def can_manage_scholarships(self) -> bool:
        """Check if user can manage scholarships"""
        return self.role in [UserRole.college, UserRole.admin, UserRole.super_admin]

    def can_assign_roles(self) -> bool:
        """Check if user can assign roles to others"""
        return self.role in [UserRole.admin, UserRole.super_admin]

    def has_scholarship_permission(self, scholarship_type_id: int) -> bool:
        """Check if user has permission to manage a specific scholarship"""
        # Super admins have access to all scholarships
        if self.is_super_admin():
            return True

        # Check if this admin has been assigned to this scholarship
        if self.is_admin():
            return any(
                admin_scholarship.scholarship_id == scholarship_type_id for admin_scholarship in self.admin_scholarships
            )

        # Other roles don't have scholarship management permissions
        return False

    def can_access_student_data(self, student_id: int, permission: str = "view_applications") -> bool:
        """Check if this professor can access a specific student's data"""
        if not self.is_professor():
            return False

        # Check for active professor-student relationship with required permission
        for rel in self.professor_relationships:
            if rel.student_id == student_id and rel.is_active and rel.has_permission(permission):
                return True

        return False

    def get_accessible_student_ids(self, permission: str = "view_applications") -> list[int]:
        """Get list of student IDs this professor can access"""
        if not self.is_professor():
            return []

        return [
            rel.student_id for rel in self.professor_relationships if rel.is_active and rel.has_permission(permission)
        ]

    def is_advisor_of(self, student_id: int) -> bool:
        """Check if this professor is an advisor of the specified student"""
        if not self.is_professor():
            return False

        for rel in self.professor_relationships:
            if rel.student_id == student_id and rel.is_active and rel.is_advisor:
                return True

        return False

    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission"""
        # Permission mapping based on user roles
        permission_map = {
            # Roster permissions
            "roster_create": [UserRole.admin, UserRole.super_admin],
            "roster_view_all": [UserRole.admin, UserRole.super_admin, UserRole.college],
            "roster_lock": [UserRole.admin, UserRole.super_admin],
            "roster_unlock": [UserRole.admin, UserRole.super_admin],
            "roster_export": [UserRole.admin, UserRole.super_admin, UserRole.college],
            "roster_download": [UserRole.admin, UserRole.super_admin, UserRole.college],
            "roster_delete": [UserRole.super_admin],
            "roster_audit_view": [UserRole.admin, UserRole.super_admin],
            # Default permissions for existing functionality
            "application_view": [
                UserRole.student,
                UserRole.professor,
                UserRole.college,
                UserRole.admin,
                UserRole.super_admin,
            ],
            "application_create": [UserRole.student],
            "application_review": [UserRole.professor, UserRole.college, UserRole.admin, UserRole.super_admin],
            "scholarship_manage": [UserRole.college, UserRole.admin, UserRole.super_admin],
            "user_manage": [UserRole.admin, UserRole.super_admin],
        }

        allowed_roles = permission_map.get(permission, [])
        return self.role in allowed_roles


class AdminScholarship(Base):
    """Admin-Scholarship relationship for pre-authorization"""

    __tablename__ = "admin_scholarships"

    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    scholarship_id = Column(Integer, ForeignKey("scholarship_types.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)

    admin = relationship("User", back_populates="admin_scholarships")
    scholarship = relationship("ScholarshipType", back_populates="admins")

    __table_args__ = (UniqueConstraint("admin_id", "scholarship_id", name="uq_admin_scholarship"),)

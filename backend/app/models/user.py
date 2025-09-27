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

    STUDENT = "STUDENT"
    PROFESSOR = "PROFESSOR"
    COLLEGE = "COLLEGE"
    ADMIN = "ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


class UserType(enum.Enum):
    """Portal user type enum"""

    STUDENT = "STUDENT"
    EMPLOYEE = "EMPLOYEE"


class EmployeeStatus(enum.Enum):
    """Employee status enum"""

    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    STUDENT = "STUDENT"
    GRADUATED = "GRADUATED"

    @property
    def display_name(self) -> str:
        """Get Chinese display name for status"""
        display_names = {
            "ACTIVE": "在職",
            "RETIRED": "退休",
            "STUDENT": "在學",
            "GRADUATED": "畢業",
        }
        return display_names.get(self.value, self.value)


class User(Base):
    """User model for authentication and authorization"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    nycu_id = Column(String(50), unique=True, nullable=False)  # nycuID
    name = Column(String(100), nullable=False)  # txtName
    email = Column(String(100))  # mail
    user_type = Column(Enum(UserType), nullable=False)  # employee / student
    status = Column(Enum(EmployeeStatus))  # 在學 / 畢業 / 在職 / 退休
    dept_code = Column(String(20))  # deptCode
    dept_name = Column(String(100))  # dept
    role = Column(Enum(UserRole), default=UserRole.STUDENT)  # 系統內部使用角色

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
    college_reviews = relationship("CollegeReview",
                                   foreign_keys="[CollegeReview.reviewer_id]",
                                   back_populates="reviewer")
    notifications = relationship("Notification", back_populates="user")
    notification_reads = relationship("NotificationRead", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")
    admin_scholarships = relationship("AdminScholarship", back_populates="admin")

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
        return bool(self.role == UserRole.ADMIN)

    def is_student(self) -> bool:
        """Check if user is student"""
        return bool(self.role == UserRole.STUDENT)

    def is_professor(self) -> bool:
        """Check if user is professor"""
        return bool(self.role == UserRole.PROFESSOR)

    def is_college(self) -> bool:
        """Check if user is college"""
        return bool(self.role == UserRole.COLLEGE)

    def is_super_admin(self) -> bool:
        """Check if user is super admin"""
        return bool(self.role == UserRole.SUPER_ADMIN)

    def is_employee(self) -> bool:
        """Check if user is employee (professor, college, admin, super_admin)"""
        return self.role in [
            UserRole.PROFESSOR,
            UserRole.COLLEGE,
            UserRole.ADMIN,
            UserRole.SUPER_ADMIN,
        ]

    def can_manage_scholarships(self) -> bool:
        """Check if user can manage scholarships"""
        return self.role in [UserRole.COLLEGE, UserRole.ADMIN, UserRole.SUPER_ADMIN]

    def can_assign_roles(self) -> bool:
        """Check if user can assign roles to others"""
        return self.role in [UserRole.ADMIN, UserRole.SUPER_ADMIN]

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

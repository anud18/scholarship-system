"""
根據 NCYU Portal 回傳的資料，更新 User 模型

Portal 回傳的資料格式如下：
{
    "status": "success",
    "message": "jwt pass",
    "data": {
        "iat": 1626859683,
        "txtID": "T00000",
        "nycuID": "T000000",
        "txtName": "測試帳號員",
        "idno": "A123456789",
        "mail": "T00000@nycu.edu.tw",
        "dept": "校務資訊組",
        "deptCode": "5802",
        "userType": "employee",
        "oldEmpNo": "T00000",
        "employeestatus": "在職"
    }
}

"""

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    nycu_id = Column(String(50), unique=True, nullable=False)  # nycuID
    name = Column(String(100), nullable=False)                 # txtName
    email = Column(String(100))
    user_type = Column(Enum(UserType), nullable=False)         # employee / student
    status = Column(Enum(EmployeeStatus))                      # 在學 / 畢業 / 在職 / 退休
    dept_code = Column(String(20))                             # deptCode
    dept_name = Column(String(100))                            # dept
    role = Column(Enum(Role), default=Role.student)            # 系統內部使用角色 (student / professor / college / admin / super_admin)
    
    # 註記欄位
    comment = Column(String(255))

    last_login_at = Column(DateTime, default=datetime.now(timezone.utc))
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    raw_data = Column(JSON)  # 儲存整包 Portal 回傳資料（可選）

    admin_scholarships = relationship("AdminScholarship", back_populates="admin")

---

"""
加入 AdminScholarship 關聯 多對多
- 一個 Admin 可以負責多個獎學金（scholarship）
- 一個獎學金可以有多個 Admin 負責

"""

class AdminScholarship(Base):
    __tablename__ = "admin_scholarships"

    id = Column(Integer, primary_key=True)
    admin_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    scholarship_id = Column(Integer, ForeignKey("scholarships.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)

    admin = relationship("User", back_populates="admin_scholarships")
    scholarship = relationship("Scholarship", back_populates="admins")

    __table_args__ = (UniqueConstraint("admin_id", "scholarship_id", name="uq_admin_scholarship"),)

"""
Student models for academic information with normalized database design
"""

from typing import Optional
from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, SmallInteger, Text, Table, UniqueConstraint, ForeignKeyConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.db.base_class import Base


# === 查詢表模型 ===

class Degree(Base):
    """學位表"""
    __tablename__ = "degrees"

    id = Column(SmallInteger, primary_key=True)
    name = Column(String(20), nullable=False)

    # 關聯
    enrollTypes = relationship("EnrollType", back_populates="degree")


class Identity(Base):
    """學生身份表"""
    __tablename__ = "identities"

    id = Column(SmallInteger, primary_key=True)
    name = Column(String(100), nullable=False)


class StudyingStatus(Base):
    """學籍狀態表"""
    __tablename__ = "studying_statuses"

    id = Column(SmallInteger, primary_key=True)
    name = Column(String(50))


class SchoolIdentity(Base):
    """學校身份表"""
    __tablename__ = "school_identities"

    id = Column(SmallInteger, primary_key=True)
    name = Column(String(50))


class Academy(Base):
    """學院表"""
    __tablename__ = "academies"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True)
    name = Column(String(100), nullable=False)


class Department(Base):
    """系所表"""
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True)
    name = Column(String(100), nullable=False)


class EnrollType(Base):
    """入學管道表"""
    __tablename__ = "enroll_types"

    degreeId = Column(SmallInteger, ForeignKey("degrees.id"), primary_key=True)
    code = Column(SmallInteger, primary_key=True)
    name = Column(String(100), nullable=False)
    name_en = Column(String(100), nullable=False)

    # 關聯
    degree = relationship("Degree", back_populates="enrollTypes")

    __table_args__ = (
        UniqueConstraint('degreeId', 'code', name='uq_degree_code'),
        {"sqlite_autoincrement": True}
    )

    def __repr__(self):
        return f"<EnrollType(id={self.id}, name={self.name}, degree={self.degreeId})>"


# === 主要學生資料表 ===

class Student(Base):
    """學生基本資料表 - 更新版本"""
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    
    # 學籍資料
    std_stdno = Column(String(20), unique=True, index=True, nullable=True)  # 學號代碼 (目前不知道用途 先保留)
    std_stdcode = Column(String(20), unique=True, index=True, nullable=False)  # 學號 (nycu_id)
    std_pid = Column(String(20), nullable=True)  # 身分證字號
    std_cname = Column(String(50), nullable=False)  # 中文姓名
    std_ename = Column(String(50), nullable=False)  # 英文姓名
    std_degree = Column(String(1), nullable=False)  # 攻讀學位：1:博士, 2:碩士, 3:學士
    std_studingstatus = Column(String(1), nullable=True)  # 在學狀態
    std_sex = Column(String(1), nullable=True)  # 性別: 1:男, 2:女
    std_enrollyear = Column(String(4), nullable=True)  # 入學學年度 (民國年)
    std_enrollterm = Column(String(1), nullable=True)  # 入學學期 (第一或第二)
    std_termcount = Column(Integer, nullable=True)  # 在學學期數

    # 國籍與身份
    std_nation = Column(String(20), nullable=True)    # 1: 中華民國 2: 其他
    std_schoolid = Column(String(10), nullable=True)  # 在學身份 (數字代碼)
    std_identity = Column(String(20), nullable=True)  # 陸生、僑生、外籍生等

    # 系所與學院
    std_depno = Column(String(20), nullable=True)  # 系所代碼
    std_depname = Column(String(100), nullable=True)  # 系所名稱
    std_aca_no = Column(String(20), nullable=True)  # 學院代碼
    std_aca_cname = Column(String(100), nullable=True)  # 學院名稱

    # 學歷背景
    std_highestschname = Column(String(100), nullable=True)  # 原就讀系所／畢業學校
    
    # 聯絡資訊
    com_cellphone = Column(String(20), nullable=True)
    com_email = Column(String(100), nullable=True)
    com_commzip = Column(String(10), nullable=True)
    com_commadd = Column(String(200), nullable=True)

    # 入學日期（可由 enrollyear + term 推算）
    std_enrolled_date = Column(Date, nullable=True)

    # 匯款資訊
    std_bank_account = Column(String(50), nullable=True)

    # 其他備註
    notes = Column(String(255), nullable=True)

    # 關聯
    applications = relationship("Application", back_populates="studentProfile")

    def __repr__(self):
        return f"<Student(id={self.id}, std_stdcode={self.std_stdcode}, std_cname={self.std_cname})>"

    @property
    def displayName(self) -> str:
        """Get student display name"""
        return str(self.std_cname or self.std_ename or self.std_stdcode or "")
    
    def get_student_type(self) -> "StudentType":
        """
        Get student type based on degree
        
        Returns:
            StudentType: The student type based on degree
        """
        if self.std_degree == "1":
            return StudentType.PHD
        elif self.std_degree == "2":
            return StudentType.MASTER
        else:
            return StudentType.UNDERGRADUATE


# === 移除學期成績記錄相關模型 ===
# 根據文件說明，學期資料不再需要存儲，將由 API 或學校學籍資料庫取得


class StudentType(enum.Enum):
    """Student type enum"""
    UNDERGRADUATE = "undergraduate"  # 學士
    MASTER = "master"  # 碩士
    PHD = "phd"  # 博士


class StudyStatus(enum.Enum):
    """Study status enum"""
    ACTIVE = "1"     # 在學
    EXTENDED = "2"   # 延畢
    LEAVE = "3"      # 休學
    DROPOUT = "4"    # 退學
    TRANSFER = "5"   # 轉學離校
    DEATH = "9"      # 死亡
    GRADUATE = "10"  # 畢業
    INCOMPLETE = "11" # 修業未畢 
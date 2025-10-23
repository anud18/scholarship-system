"""
Student reference data models for lookup tables only.
Student data is now fetched from external API instead of storing locally.
"""

from sqlalchemy import Column, ForeignKey, Integer, SmallInteger, String, UniqueConstraint
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import relationship

from app.db.base_class import Base

# === 參考資料表 (Reference Data Tables) ===
# These lookup tables are kept for scholarship configuration and reference purposes


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


class Gender(Base):
    """性別表"""

    __tablename__ = "genders"

    id = Column(SmallInteger, primary_key=True)
    name = Column(String(20), nullable=False)


class Academy(Base):
    """學院表"""

    __tablename__ = "academies"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    name_en = Column(String(200), nullable=True)

    # 關聯
    departments = relationship("Department", back_populates="academy")


class Department(Base):
    """系所表"""

    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    code = Column(String(10), unique=True)
    name = Column(String(100), nullable=False)
    academy_code = Column(String(10), ForeignKey("academies.code"), nullable=True, index=True)

    # 關聯
    academy = relationship("Academy", back_populates="departments")


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
        UniqueConstraint("degreeId", "code", name="uq_degree_code"),
        {"sqlite_autoincrement": True},
    )

    def __repr__(self):
        return f"<EnrollType(id={self.id}, name={self.name}, degree={self.degreeId})>"


# === 學生資料處理輔助函數 ===
# Helper functions for student data processing


async def get_student_type_from_degree(degree_code: str, session: AsyncSession) -> str:
    """
    Get student type based on degree code from database

    Args:
        degree_code: Degree code from external API (1:博士, 2:碩士, 3:學士)
        session: Database session

    Returns:
        str: The student type name from database
    """
    from sqlalchemy import select

    # Convert string degree_code to int for database lookup
    try:
        degree_id = int(degree_code)
    except (ValueError, TypeError):
        # Default to undergraduate if invalid code
        degree_id = 3

    # Query database for degree name
    result = await session.execute(select(Degree).where(Degree.id == degree_id))
    degree = result.scalar_one_or_none()

    if degree:
        # Return English equivalent for consistency
        if degree.name == "博士":
            return "phd"
        elif degree.name == "碩士":
            return "master"
        else:
            return "undergraduate"
    else:
        # Fallback to undergraduate if degree not found
        return "undergraduate"

from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class StudentInfo(BaseModel):
    std_stdno: str              # Student ID Code
    std_stdcode: str            # Student Number
    std_pid: str                # National ID
    std_cname: str              # Chinese Name
    std_ename: str              # English Name
    std_degree: int             # Degree Type
    std_studingstatus: int      # Study Status
    std_nation1: str            # Primary Nationality
    std_nation2: Optional[str]  # Secondary Nationality
    std_schoolid: int           # School Identity Type
    std_identity: int           # Student Identity Category
    std_termcount: int          # Terms Enrolled
    std_depno: str              # Department Number
    dep_depname: str            # Department Name
    std_academyno: str          # College Number
    aca_cname: str              # College Name
    std_enrolltype: int         # Enrollment Type
    std_directmemo: Optional[str]  # Direct PhD Notes
    std_highestschname: str     # Previous School/Department
    com_cellphone: str          # Phone Number
    com_email: str              # Email
    com_commzip: str            # Postal Code
    com_commadd: str            # Address
    std_sex: int                # Gender
    std_enrollyear: int         # Enrollment Year
    std_enrollterm: int         # Enrollment Term
    enrollment_date: str        # Derived from year/term


class SemesterRecord(BaseModel):
    trm_year: int               # Academic Year
    trm_term: int               # Semester (1: Fall, 2: Spring)
    trm_stdno: str              # Student Number
    trm_studystatus: int        # Study Status Code
    trm_ascore: float           # Semester Average Score
    trm_termcount: int          # Terms Completed
    grade_level: int            # Year Level
    trm_degree: int             # Degree Code
    trm_academyname: str        # College Name
    trm_depname: str            # Department Short Name
    trm_ascore_gpa: float       # Semester GPA
    trm_stdascore: float        # Cumulative Average Score
    trm_placingsrate: int       # Class Ranking
    trm_depplacingrate: int     # Department Ranking


class SemesterInfo(BaseModel):
    student_id: str
    semesters: List[SemesterRecord]


class ErrorResponse(BaseModel):
    error: str
    message: str
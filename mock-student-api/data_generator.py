import random
import sqlite3
from datetime import datetime
from typing import List, Tuple
import string

# Reference data from the issue
DEGREE_TYPES = {1: "PhD", 2: "Master's", 3: "Bachelor's"}
STUDY_STATUS = {
    1: "Enrolled", 2: "Should Graduate", 3: "Extended Study", 4: "Leave of Absence",
    5: "Mid-term Withdrawal", 6: "End-term Withdrawal", 7: "Expelled", 8: "Deceased",
    9: "Status Preserved", 10: "Admission Declined", 11: "Graduated"
}
SCHOOL_IDENTITY = {
    1: "Regular Student", 2: "Working Student", 3: "Credit Student", 4: "Exchange Student",
    5: "External Student", 6: "Early Selection Student", 7: "Cross-school Student", 8: "Special Program Student"
}
STUDENT_IDENTITY = {
    1: "Regular", 2: "Indigenous", 3: "Overseas Chinese with ROC citizenship", 4: "Foreign student with ROC citizenship",
    5: "Diplomatic personnel child", 6: "Student with disabilities", 7: "Sports merit student", 8: "Outlying islands",
    9: "Veterans", 10: "Regular scholarship recipient", 11: "Indigenous scholarship recipient",
    12: "Outlying islands scholarship recipient", 13: "Veteran scholarship recipient", 14: "Vision program student",
    17: "Mainland Chinese student", 30: "Other"
}
ENROLLMENT_TYPES = {
    1: "Regular admission exam", 2: "Working student admission exam", 3: "Credit student", 4: "Regular recommendation",
    5: "Working student recommendation", 6: "Overseas Chinese", 7: "Foreign student", 8: "Direct PhD from bachelor's",
    9: "Direct PhD from master's", 10: "Cross-school direct PhD from bachelor's", 11: "Cross-school direct PhD from master's",
    12: "Dual degree", 17: "Mainland Chinese student", 18: "Transfer", 26: "Special admission", 29: "TIGP", 30: "Other"
}
GENDERS = {1: "Male", 2: "Female"}

# Sample data for realistic generation
CHINESE_SURNAMES = ["王", "李", "張", "劉", "陳", "楊", "趙", "黃", "周", "吳", "徐", "孫", "胡", "朱", "高", "林", "何", "郭", "馬", "羅"]
CHINESE_GIVEN_NAMES = ["偉", "芳", "秀英", "敏", "靜", "麗", "強", "磊", "軍", "洋", "勇", "艷", "娜", "秀蘭", "傑", "娟", "濤", "明", "超", "秀珍"]
ENGLISH_FIRST_NAMES = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "William", "Elizabeth", "David", "Barbara", "Richard", "Susan", "Joseph", "Jessica", "Thomas", "Sarah", "Christopher", "Karen"]
ENGLISH_LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin"]

DEPARTMENTS = [
    ("CS", "Computer Science", "資訊工程學系", "EECS"),
    ("EE", "Electrical Engineering", "電機工程學系", "EECS"),
    ("ME", "Mechanical Engineering", "機械工程學系", "ENG"),
    ("CE", "Civil Engineering", "土木工程學系", "ENG"),
    ("MATH", "Mathematics", "數學系", "SCI"),
    ("PHYS", "Physics", "物理學系", "SCI"),
    ("CHEM", "Chemistry", "化學系", "SCI"),
    ("BIO", "Biology", "生物學系", "SCI"),
    ("ECON", "Economics", "經濟學系", "MGMT"),
    ("BA", "Business Administration", "企業管理學系", "MGMT")
]

COLLEGES = {
    "EECS": "電機資訊學院",
    "ENG": "工學院", 
    "SCI": "理學院",
    "MGMT": "管理學院"
}

NATIONALITIES = ["ROC", "USA", "JPN", "KOR", "SGP", "MYS", "THA", "VNM", "IDN", "PHL"]
TAIWAN_CITIES = ["台北市", "新北市", "桃園市", "台中市", "台南市", "高雄市", "新竹市", "基隆市", "嘉義市", "宜蘭縣"]


def generate_student_id() -> str:
    """Generate a realistic student ID"""
    return f"{''.join(random.choices(string.digits, k=9))}"


def generate_pid() -> str:
    """Generate a mock National ID"""
    return f"{''.join(random.choices(string.ascii_uppercase + string.digits, k=10))}"


def generate_phone() -> str:
    """Generate a mock phone number"""
    return f"09{''.join(random.choices(string.digits, k=8))}"


def generate_email(eng_name: str) -> str:
    """Generate email based on English name"""
    domains = ["gmail.com", "yahoo.com", "hotmail.com", "ntu.edu.tw", "student.ntu.edu.tw"]
    name_part = eng_name.lower().replace(" ", ".")
    return f"{name_part}@{random.choice(domains)}"


def generate_address() -> Tuple[str, str]:
    """Generate zip code and address"""
    city = random.choice(TAIWAN_CITIES)
    zip_code = f"{random.randint(100, 999):03d}"
    street_num = random.randint(1, 999)
    return zip_code, f"{city}中正區中山路{street_num}號"


def calculate_gpa(score: float) -> float:
    """Convert score to GPA (4.0 scale)"""
    if score >= 90:
        return round(random.uniform(3.7, 4.0), 2)
    elif score >= 80:
        return round(random.uniform(3.0, 3.7), 2)
    elif score >= 70:
        return round(random.uniform(2.3, 3.0), 2)
    elif score >= 60:
        return round(random.uniform(2.0, 2.3), 2)
    else:
        return round(random.uniform(0.0, 2.0), 2)


def generate_student_data(student_id: str) -> dict:
    """Generate complete student information"""
    # Basic info
    std_stdcode = student_id
    std_pid = generate_pid()
    
    # Names
    chinese_surname = random.choice(CHINESE_SURNAMES)
    chinese_given = random.choice(CHINESE_GIVEN_NAMES)
    std_cname = chinese_surname + chinese_given
    
    english_first = random.choice(ENGLISH_FIRST_NAMES)
    english_last = random.choice(ENGLISH_LAST_NAMES)
    std_ename = f"{english_first} {english_last}"
    
    # Academic info
    std_degree = random.choice([1, 2, 3])  # PhD, Master's, Bachelor's
    std_studingstatus = random.choices([1, 2, 3, 11], weights=[70, 10, 10, 10])[0]  # Mostly enrolled
    
    # Department and college
    dept_info = random.choice(DEPARTMENTS)
    std_depno, dep_depname_eng, dep_depname, college_code = dept_info
    std_academyno = college_code
    aca_cname = COLLEGES[college_code]
    
    # Identity and enrollment
    std_schoolid = random.choices(list(SCHOOL_IDENTITY.keys()), weights=[80, 10, 2, 2, 2, 2, 1, 1])[0]
    std_identity = random.choices(list(STUDENT_IDENTITY.keys()), weights=[70, 5, 5, 5, 2, 2, 2, 2, 2, 1, 1, 1, 1, 1, 2, 1])[0]
    std_enrolltype = random.choices(list(ENROLLMENT_TYPES.keys()), weights=[40, 15, 5, 20, 10, 2, 2, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1])[0]
    
    # Terms and year info
    current_year = 113  # 2024-2025 academic year
    std_enrollyear = random.randint(current_year - 6, current_year)
    std_enrollterm = random.choice([1, 2])
    
    # Calculate term count based on enrollment
    years_enrolled = current_year - std_enrollyear
    base_terms = years_enrolled * 2
    if std_enrollterm == 2:
        base_terms += 1
    # Add some variation for leaves of absence, etc.
    std_termcount = max(1, base_terms + random.randint(-2, 1))
    
    # Contact info
    std_nation1 = random.choice(NATIONALITIES)
    std_nation2 = random.choice([None, random.choice(NATIONALITIES)]) if random.random() < 0.1 else None
    com_cellphone = generate_phone()
    com_email = generate_email(std_ename)
    com_commzip, com_commadd = generate_address()
    
    # Personal info
    std_sex = random.choice([1, 2])
    std_directmemo = "直接攻讀博士學位" if std_degree == 1 and std_enrolltype in [8, 9] else None
    std_highestschname = f"{random.choice(['台灣大學', '清華大學', '交通大學', '成功大學', '中央大學'])}{random.choice(['電機系', '資工系', '機械系', '土木系'])}"
    
    # Enrollment date
    enrollment_date = f"{std_enrollyear + 1911}-{'09' if std_enrollterm == 1 else '02'}-01"
    
    return {
        "std_stdno": student_id,
        "std_stdcode": std_stdcode,
        "std_pid": std_pid,
        "std_cname": std_cname,
        "std_ename": std_ename,
        "std_degree": std_degree,
        "std_studingstatus": std_studingstatus,
        "std_nation1": std_nation1,
        "std_nation2": std_nation2,
        "std_schoolid": std_schoolid,
        "std_identity": std_identity,
        "std_termcount": std_termcount,
        "std_depno": std_depno,
        "dep_depname": dep_depname,
        "std_academyno": std_academyno,
        "aca_cname": aca_cname,
        "std_enrolltype": std_enrolltype,
        "std_directmemo": std_directmemo,
        "std_highestschname": std_highestschname,
        "com_cellphone": com_cellphone,
        "com_email": com_email,
        "com_commzip": com_commzip,
        "com_commadd": com_commadd,
        "std_sex": std_sex,
        "std_enrollyear": std_enrollyear,
        "std_enrollterm": std_enrollterm,
        "enrollment_date": enrollment_date
    }


def generate_semester_data(student_info: dict) -> List[dict]:
    """Generate semester progression data for a student"""
    semesters = []
    
    start_year = student_info["std_enrollyear"]
    start_term = student_info["std_enrollterm"]
    current_year = 113
    
    # Generate base academic performance
    base_score = random.uniform(70, 95)  # Base academic ability
    performance_trend = random.uniform(-0.5, 0.5)  # Slight improvement/decline over time
    
    year = start_year
    term = start_term
    term_count = 0
    cumulative_score_sum = 0
    cumulative_terms = 0
    
    while year <= current_year:
        if year == current_year and term > 1:
            break
            
        term_count += 1
        
        # Simulate some variability in performance
        semester_variation = random.uniform(-5, 5)
        trend_adjustment = performance_trend * term_count * 0.5
        semester_score = max(0, min(100, base_score + semester_variation + trend_adjustment))
        
        # Simulate occasional leave of absence or status changes
        study_status = student_info["std_studingstatus"]
        if random.random() < 0.05:  # 5% chance of temporary status change
            study_status = random.choice([4, 9])  # Leave of absence or status preserved
            semester_score = 0  # No score during leave
        elif term_count > 8 and random.random() < 0.1:  # Chance of graduation
            study_status = 11
        
        # Calculate cumulative average
        if semester_score > 0:
            cumulative_score_sum += semester_score
            cumulative_terms += 1
            cumulative_avg = cumulative_score_sum / cumulative_terms
        else:
            cumulative_avg = cumulative_score_sum / max(1, cumulative_terms)
        
        # Generate rankings (mock)
        class_ranking = random.randint(1, 50)
        dept_ranking = random.randint(1, 200)
        
        semester_record = {
            "trm_year": year,
            "trm_term": term,
            "trm_stdno": student_info["std_stdcode"],
            "trm_studystatus": study_status,
            "trm_ascore": round(semester_score, 2),
            "trm_termcount": term_count,
            "grade_level": (term_count + 1) // 2,  # Year level
            "trm_degree": student_info["std_degree"],
            "trm_academyname": student_info["aca_cname"],
            "trm_depname": student_info["dep_depname"],
            "trm_ascore_gpa": calculate_gpa(semester_score),
            "trm_stdascore": round(cumulative_avg, 2),
            "trm_placingsrate": class_ranking,
            "trm_depplacingrate": dept_ranking
        }
        
        semesters.append(semester_record)
        
        # Move to next semester
        if term == 1:
            term = 2
        else:
            term = 1
            year += 1
            
        # Stop if graduated
        if study_status == 11:
            break
    
    return semesters


def init_database():
    """Initialize SQLite database with sample data"""
    conn = sqlite3.connect('data/students.db')
    cursor = conn.cursor()
    
    # Create students table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            std_stdno TEXT PRIMARY KEY,
            std_stdcode TEXT,
            std_pid TEXT,
            std_cname TEXT,
            std_ename TEXT,
            std_degree INTEGER,
            std_studingstatus INTEGER,
            std_nation1 TEXT,
            std_nation2 TEXT,
            std_schoolid INTEGER,
            std_identity INTEGER,
            std_termcount INTEGER,
            std_depno TEXT,
            dep_depname TEXT,
            std_academyno TEXT,
            aca_cname TEXT,
            std_enrolltype INTEGER,
            std_directmemo TEXT,
            std_highestschname TEXT,
            com_cellphone TEXT,
            com_email TEXT,
            com_commzip TEXT,
            com_commadd TEXT,
            std_sex INTEGER,
            std_enrollyear INTEGER,
            std_enrollterm INTEGER,
            enrollment_date TEXT
        )
    ''')
    
    # Create semesters table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS semesters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            trm_year INTEGER,
            trm_term INTEGER,
            trm_stdno TEXT,
            trm_studystatus INTEGER,
            trm_ascore REAL,
            trm_termcount INTEGER,
            grade_level INTEGER,
            trm_degree INTEGER,
            trm_academyname TEXT,
            trm_depname TEXT,
            trm_ascore_gpa REAL,
            trm_stdascore REAL,
            trm_placingsrate INTEGER,
            trm_depplacingrate INTEGER,
            FOREIGN KEY (student_id) REFERENCES students (std_stdno)
        )
    ''')
    
    # Generate sample data for 100 students
    for i in range(100):
        student_id = generate_student_id()
        
        # Ensure unique student ID
        cursor.execute("SELECT std_stdno FROM students WHERE std_stdno = ?", (student_id,))
        if cursor.fetchone():
            continue
            
        student_data = generate_student_data(student_id)
        
        # Insert student data
        cursor.execute('''
            INSERT INTO students VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', tuple(student_data.values()))
        
        # Generate and insert semester data
        semester_data = generate_semester_data(student_data)
        for semester in semester_data:
            cursor.execute('''
                INSERT INTO semesters (student_id, trm_year, trm_term, trm_stdno, trm_studystatus, 
                                     trm_ascore, trm_termcount, grade_level, trm_degree, trm_academyname,
                                     trm_depname, trm_ascore_gpa, trm_stdascore, trm_placingsrate, trm_depplacingrate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (student_id, semester["trm_year"], semester["trm_term"], semester["trm_stdno"],
                  semester["trm_studystatus"], semester["trm_ascore"], semester["trm_termcount"],
                  semester["grade_level"], semester["trm_degree"], semester["trm_academyname"],
                  semester["trm_depname"], semester["trm_ascore_gpa"], semester["trm_stdascore"],
                  semester["trm_placingsrate"], semester["trm_depplacingrate"]))
    
    conn.commit()
    conn.close()
    print(f"Database initialized with sample data")


if __name__ == "__main__":
    init_database()
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
import sqlite3
import os
from models import StudentInfo, SemesterInfo, SemesterRecord, ErrorResponse
from data_generator import init_database
from typing import List, Optional

app = FastAPI(
    title="Mock Student Database API",
    description="⚠️ DEVELOPMENT/TESTING ONLY ⚠️ Mock API for student database access during development. DO NOT USE IN PRODUCTION.",
    version="1.0.0"
)

DATABASE_PATH = "data/students.db"

def get_db_connection():
    """Get database connection"""
    if not os.path.exists(DATABASE_PATH):
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        init_database()
    return sqlite3.connect(DATABASE_PATH)

def dict_factory(cursor, row):
    """Convert sqlite row to dictionary"""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

@app.on_event("startup")
async def startup_event():
    """Initialize database on startup if it doesn't exist"""
    if not os.path.exists(DATABASE_PATH):
        print("Initializing database...")
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        init_database()
        print("Database initialized successfully")

@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "Mock Student Database API",
        "warning": "⚠️ DEVELOPMENT/TESTING ONLY - DO NOT USE IN PRODUCTION ⚠️",
        "version": "1.0.0",
        "environment": "development",
        "endpoints": {
            "student_info": "/api/students/{student_id}",
            "student_semesters": "/api/students/{student_id}/semesters",
            "alternative_semesters": "/api/semesters?student_id={student_id}",
            "specific_semester": "/api/students/{student_id}/semesters/{year}/{term}",
            "health": "/health",
            "docs": "/docs"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM students")
        student_count = cursor.fetchone()[0]
        conn.close()
        
        return {
            "status": "healthy",
            "database": "connected",
            "student_count": student_count
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "unhealthy", "error": str(e)}
        )

@app.get("/api/students/{student_id}", response_model=StudentInfo)
async def get_student_info(student_id: str):
    """Get student information by student ID"""
    try:
        conn = get_db_connection()
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM students WHERE std_stdno = ?", (student_id,))
        student = cursor.fetchone()
        conn.close()
        
        if not student:
            raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
        
        return StudentInfo(**student)
    
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/api/students/{student_id}/semesters", response_model=SemesterInfo)
async def get_student_semesters(
    student_id: str,
    year: Optional[int] = Query(None, description="Filter by academic year"),
    term: Optional[int] = Query(None, description="Filter by semester (1 or 2)")
):
    """Get all semester records for a student"""
    try:
        conn = get_db_connection()
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        
        # Check if student exists
        cursor.execute("SELECT std_stdno FROM students WHERE std_stdno = ?", (student_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
        
        # Build query with optional filters
        query = "SELECT * FROM semesters WHERE student_id = ?"
        params = [student_id]
        
        if year is not None:
            query += " AND trm_year = ?"
            params.append(year)
        
        if term is not None:
            query += " AND trm_term = ?"
            params.append(term)
        
        query += " ORDER BY trm_year, trm_term"
        
        cursor.execute(query, params)
        semesters_data = cursor.fetchall()
        conn.close()
        
        # Convert to SemesterRecord objects
        semesters = []
        for semester_data in semesters_data:
            # Remove the id field that's not part of the model
            semester_data.pop('id', None)
            semester_data.pop('student_id', None)
            semesters.append(SemesterRecord(**semester_data))
        
        return SemesterInfo(student_id=student_id, semesters=semesters)
    
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/api/semesters", response_model=SemesterInfo)
async def get_semesters_by_student_id(
    student_id: str = Query(..., description="Student ID"),
    year: Optional[int] = Query(None, description="Filter by academic year"),
    term: Optional[int] = Query(None, description="Filter by semester (1 or 2)")
):
    """Alternative endpoint: Get semester records by student ID as query parameter"""
    return await get_student_semesters(student_id, year, term)

@app.get("/api/students/{student_id}/semesters/{year}/{term}", response_model=List[SemesterRecord])
async def get_specific_semester(student_id: str, year: int, term: int):
    """Get specific semester data for a student"""
    try:
        conn = get_db_connection()
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        
        # Check if student exists
        cursor.execute("SELECT std_stdno FROM students WHERE std_stdno = ?", (student_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
        
        cursor.execute(
            "SELECT * FROM semesters WHERE student_id = ? AND trm_year = ? AND trm_term = ?",
            (student_id, year, term)
        )
        semester_data = cursor.fetchone()
        conn.close()
        
        if not semester_data:
            raise HTTPException(
                status_code=404, 
                detail=f"No semester data found for student {student_id} in {year}-{term}"
            )
        
        # Remove fields not in the model
        semester_data.pop('id', None)
        semester_data.pop('student_id', None)
        
        return [SemesterRecord(**semester_data)]
    
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/api/students", response_model=List[dict])
async def list_students(
    limit: int = Query(10, ge=1, le=100, description="Number of students to return"),
    offset: int = Query(0, ge=0, description="Number of students to skip")
):
    """List students with pagination"""
    try:
        conn = get_db_connection()
        conn.row_factory = dict_factory
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT std_stdno, std_cname, std_ename, dep_depname, aca_cname FROM students LIMIT ? OFFSET ?",
            (limit, offset)
        )
        students = cursor.fetchall()
        conn.close()
        
        return students
    
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
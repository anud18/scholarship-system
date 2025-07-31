from typing import Dict, Any, Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from app.models.student import Student
from app.core.exceptions import NotFoundError
from datetime import datetime

class StudentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_student_snapshot(self, student: Union[Student, int]) -> Dict[str, Any]:
        """取得學生資料快照，用於申請時保存"""
        
        # If student_id is provided, fetch the student object
        if isinstance(student, int):
            result = await self.db.execute(
                select(Student).where(Student.id == student)
            )
            student = result.scalar_one()
        
        # Build snapshot with new model structure
        snapshot = {
            "id": student.id,
            "std_stdno": student.std_stdno,
            "std_stdcode": student.std_stdcode,
            "std_pid": student.std_pid,
            "std_cname": student.std_cname,
            "std_ename": student.std_ename,
            "std_degree": student.std_degree,
            "std_studingstatus": student.std_studingstatus,
            "std_sex": student.std_sex,
            "std_enrollyear": student.std_enrollyear,
            "std_enrollterm": student.std_enrollterm,
            "std_termcount": student.std_termcount,
            "std_nation": student.std_nation,
            "std_schoolid": student.std_schoolid,
            "std_identity": student.std_identity,
            "std_depno": student.std_depno,
            "std_depname": student.std_depname,
            "std_aca_no": student.std_aca_no,
            "std_aca_cname": student.std_aca_cname,
            "std_highestschname": student.std_highestschname,
            "com_cellphone": student.com_cellphone,
            "com_email": student.com_email,
            "com_commzip": student.com_commzip,
            "com_commadd": student.com_commadd,
            "std_enrolled_date": student.std_enrolled_date.isoformat() if student.std_enrolled_date else None,
            "std_bank_account": student.std_bank_account,
            "notes": student.notes,
            "student_type": student.get_student_type().value
        }
        
        return snapshot

    async def get_student_by_id(self, student_id: int) -> Optional[Student]:
        """根據 ID 取得學生資料"""
        result = await self.db.execute(
            select(Student).where(Student.id == student_id)
        )
        return result.scalar_one_or_none()

    async def get_student_by_stdcode(self, stdcode: str) -> Optional[Student]:
        """根據學號取得學生資料"""
        result = await self.db.execute(
            select(Student).where(Student.std_stdcode == stdcode)
        )
        return result.scalar_one_or_none()

    async def update_student_info(
        self,
        student_id: int,
        student_info: Dict[str, Any]
    ) -> Student:
        """更新學生資訊"""
        student = await self.get_student_by_id(student_id)
        if not student:
            raise NotFoundError(f"Student {student_id} not found")
            
        # 更新學生資訊
        for field, value in student_info.items():
            if hasattr(student, field):
                setattr(student, field, value)
                
        await self.db.commit()
        await self.db.refresh(student)
        
        return student

    async def create_student(self, student_data: Dict[str, Any]) -> Student:
        """建立新學生"""
        student = Student(**student_data)
        self.db.add(student)
        await self.db.commit()
        await self.db.refresh(student)
        return student

    async def get_students_by_department(self, depno: str) -> list[Student]:
        """根據系所代碼取得學生列表"""
        result = await self.db.execute(
            select(Student).where(Student.std_depno == depno)
        )
        return result.scalars().all()

    async def get_students_by_academy(self, aca_no: str) -> list[Student]:
        """根據學院代碼取得學生列表"""
        result = await self.db.execute(
            select(Student).where(Student.std_aca_no == aca_no)
        )
        return result.scalars().all() 
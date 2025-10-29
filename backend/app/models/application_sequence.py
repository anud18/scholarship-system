"""
Application sequence model for generating sequential application IDs
"""

from sqlalchemy import Column, Integer, String

from app.db.base_class import Base


class ApplicationSequence(Base):
    """
    Manages sequential numbering for application IDs

    Each academic year and semester combination has its own sequence counter.
    Format: APP-{academic_year}-{semester_code}-{sequence:05d}

    Example:
        - APP-113-1-00001 (Academic Year 113, Semester 1, Sequence 1)
        - APP-113-2-00125 (Academic Year 113, Semester 2, Sequence 125)
        - APP-114-0-00001 (Academic Year 114, Yearly, Sequence 1)
    """

    __tablename__ = "application_sequences"

    academic_year = Column(Integer, primary_key=True, nullable=False, comment="民國年，例如 113")
    semester = Column(String(20), primary_key=True, nullable=False, comment="學期：first, second, yearly")
    last_sequence = Column(Integer, default=0, nullable=False, comment="最後使用的序號")

    def __repr__(self):
        return (
            f"<ApplicationSequence(academic_year={self.academic_year}, "
            f"semester={self.semester}, last_sequence={self.last_sequence})>"
        )

    @staticmethod
    def get_semester_code(semester: str) -> str:
        """
        Convert semester enum value to code for app_id

        Args:
            semester: 'first', 'second', or 'yearly'

        Returns:
            str: '1' for first, '2' for second, '0' for yearly
        """
        semester_map = {
            "first": "1",
            "second": "2",
            "yearly": "0",
        }
        return semester_map.get(semester, "0")

    @staticmethod
    def format_app_id(academic_year: int, semester: str, sequence: int) -> str:
        """
        Format application ID with standard pattern

        Args:
            academic_year: Academic year (e.g., 113)
            semester: Semester enum value ('first', 'second', 'yearly')
            sequence: Sequential number

        Returns:
            str: Formatted app_id (e.g., 'APP-113-1-00001')
        """
        semester_code = ApplicationSequence.get_semester_code(semester)
        return f"APP-{academic_year}-{semester_code}-{sequence:05d}"

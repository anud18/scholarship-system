## ScholarshipType Model Update Proposal

### Purpose

Enhance the `ScholarshipType` model to support:

1. Academic year and semester (using ROC calendar format)
2. Application cycle type: semester-based vs. yearly
3. Distinct professor and college review periods
4. Sub-type selection mode: single, multiple, or hierarchical

---

### 1. Add Academic Year and Semester

```python
academic_year = Column(Integer, nullable=False)  # 民國年，如 113 表示 113 學年度

class Semester(enum.Enum):
    FIRST = "first"
    SECOND = "second"

semester = Column(Enum(Semester), nullable=False)
```

#### Property for Display

```python
@property
def academic_year_label(self) -> str:
    return f"{self.academic_year}學年度 {self.get_semester_label()}"

def get_semester_label(self) -> str:
    return {
        Semester.FIRST: "第一學期",
        Semester.SECOND: "第二學期",
    }.get(self.semester, "")
```

---

### 2. Add Application Cycle Type

```python
class CycleType(enum.Enum):
    SEMESTER = "semester"
    YEARLY = "yearly"

application_cycle = Column(Enum(CycleType), default=CycleType.SEMESTER, nullable=False)
```

---

### 3. Add Professor and College Review Periods

```python
professor_review_start = Column(DateTime(timezone=True))
professor_review_end = Column(DateTime(timezone=True))

college_review_start = Column(DateTime(timezone=True))
college_review_end = Column(DateTime(timezone=True))
```

---

### 4. Add Sub-Type Selection Mode

```python
class SubTypeSelectionMode(enum.Enum):
    SINGLE = "single"          # 僅能選擇一個子項目
    MULTIPLE = "multiple"      # 可自由多選
    HIERARCHICAL = "hierarchical"  # 需依序選取：A → AB → ABC

sub_type_selection_mode = Column(Enum(SubTypeSelectionMode), default=SubTypeSelectionMode.SINGLE, nullable=False)
```

#### Example Validation Function

```python
def is_valid_sub_type_selection(self, selected: List[str]) -> bool:
    if self.sub_type_selection_mode == SubTypeSelectionMode.SINGLE:
        return len(selected) == 1
    elif self.sub_type_selection_mode == SubTypeSelectionMode.MULTIPLE:
        return all(s in self.sub_type_list for s in selected)
    elif self.sub_type_selection_mode == SubTypeSelectionMode.HIERARCHICAL:
        expected = self.sub_type_list[:len(selected)]
        return selected == expected
    return False
```

---

### Summary of Added Fields

| Field Name                   | Type                       | Description            |
| ---------------------------- | -------------------------- | ---------------------- |
| `academic_year`              | Integer                    | 民國學年度 (e.g., 113)      |
| `semester`                   | Enum(Semester)             | 學期 (FIRST, SECOND)     |
| `application_cycle`          | Enum(CycleType)            | 申請週期 (semester/yearly) |
| `professor_review_start/end` | DateTime                   | 教授審查起訖時間               |
| `college_review_start/end`   | DateTime                   | 學院審查起訖時間               |
| `sub_type_selection_mode`    | Enum(SubTypeSelectionMode) | 子項目選擇模式                |


## ProfessorReview & Application Model Update Proposal

### Purpose

Refactor `ProfessorReview` model to support granular recommendations per scholarship sub-type, and align the `Application` model with updated academic term and sub-type selection logic from `ScholarshipType`.

---

## 1. Overview

In the current structure, `ProfessorReview` stores overall recommendation and a list of selected sub-awards. However, to allow professors to approve or reject individual sub-types, we introduce a new child model: `ProfessorReviewItem`.

Additionally, the `Application` model is updated to explicitly track academic year/semester and sub-type selection behavior, providing full alignment with `ScholarshipType` configurations.

---

## 2. Updated Application Model Fields

### 2.1 Academic Year and Semester Format

```python
academic_year = Column(Integer, nullable=False)  # 民國年，例如 113

class Semester(enum.Enum):
    FIRST = "first"
    SECOND = "second"

semester = Column(Enum(Semester), nullable=False)
```

### 2.2 Sub-Type Selection Mode Tracking

```python
class SubTypeSelectionMode(enum.Enum):
    SINGLE = "single"
    MULTIPLE = "multiple"
    HIERARCHICAL = "hierarchical"

sub_type_selection_mode = Column(Enum(SubTypeSelectionMode), nullable=False)
```

### 2.3 Stronger Data Integrity

```python
scholarship_type_id = Column(Integer, ForeignKey("scholarship_types.id"), nullable=False)
scholarship_subtype_list = Column(JSON, nullable=False, default=[])
```

### 2.4 Property for Academic Term Label

```python
@property
def academic_term_label(self) -> str:
    return f"{self.academic_year}學年度 {self.get_semester_label()}"

def get_semester_label(self) -> str:
    return {
        Semester.FIRST: "第一學期",
        Semester.SECOND: "第二學期",
    }.get(self.semester, "")
```

---

## 3. New Model: ProfessorReviewItem

```python
class ProfessorReviewItem(Base):
    __tablename__ = "professor_review_items"
    id = Column(Integer, primary_key=True, index=True)

    review_id = Column(Integer, ForeignKey("professor_reviews.id"), nullable=False)
    sub_type_code = Column(String(50), nullable=False)  # e.g., "moe_1w"

    is_recommended = Column(Boolean, nullable=False, default=False)
    comments = Column(Text)  # 教授針對該子項目的意見

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    review = relationship("ProfessorReview", back_populates="items")
```

---

## 4. Updated Model: ProfessorReview

```python
class ProfessorReview(Base):
    __tablename__ = "professor_reviews"
    id = Column(Integer, primary_key=True, index=True)

    application_id = Column(Integer, ForeignKey("applications.id"), nullable=False)
    professor_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    recommendation = Column(Text)  # 對整體申請的意見（可留可不留）
    review_status = Column(String(20), default="pending")
    reviewed_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="professor_reviews")
    professor = relationship("User")
    items = relationship("ProfessorReviewItem", back_populates="review", cascade="all, delete-orphan")
```

---

## 5. Usage Example

If a student applied for:

```json
["moe_1w", "moe_2w", "nstc"]
```

The professor could respond with:

```json
[
  {"sub_type_code": "moe_1w", "is_recommended": true, "comments": "非常推薦"},
  {"sub_type_code": "moe_2w", "is_recommended": false, "comments": "不符合條件"},
  {"sub_type_code": "nstc", "is_recommended": true, "comments": "可考慮申請"}
]
```

---

## 6. Validation Rule: Must Match Student Application

Professors should only review sub-types that the student actually applied for. Use `Application.scholarship_subtype_list` to validate.

### Service Layer Example

```python
def validate_professor_review_items(application: Application, review_items: List[ProfessorReviewItemSchema]):
    valid_subtypes = set(application.scholarship_subtype_list)
    for item in review_items:
        if item.sub_type_code not in valid_subtypes:
            raise ValueError(f"無效子項目：{item.sub_type_code} 不在學生實際申請清單中")
```

### Optional: Detect Missing Reviews

```python
missing = set(application.scholarship_subtype_list) - set(item.sub_type_code for item in review.items)
```

> This can be used to show prompts in the frontend for incomplete professor reviews.

---

## 7. Summary of Changes

| Model               | Field Name                 | Type                       | Description |
| ------------------- | -------------------------- | -------------------------- | ----------- |
| Application         | academic\_year             | Integer                    | 民國學年度       |
| Application         | semester                   | Enum(Semester)             | 學期（第一或第二）   |
| Application         | sub\_type\_selection\_mode | Enum(SubTypeSelectionMode) | 子類型選擇模式     |
| Application         | scholarship\_type\_id      | Integer, not nullable      | 主獎學金識別      |
| Application         | scholarship\_subtype\_list | JSON, not nullable         | 子獎學金代碼清單    |
| ProfessorReview     | items                      | Relationship               | 多筆子項目推薦紀錄   |
| ProfessorReviewItem | review\_id                 | FK                         | 對應上層推薦記錄    |
| ProfessorReviewItem | sub\_type\_code            | String                     | 子獎學金代碼      |
| ProfessorReviewItem | is\_recommended            | Boolean                    | 是否同意推薦該項目   |
| ProfessorReviewItem | comments                   | Text                       | 教授對該子項目的評論  |

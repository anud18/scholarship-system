# 獎學金續領申請期間設計

## 概述

本設計為獎學金系統添加了續領申請期間功能，允許系統優先處理續領申請，然後再處理一般申請。這樣的設計確保了續領申請的優先權，並提供了清晰的審查流程。

## 設計原則

1. **優先處理續領申請**：續領申請期間先於一般申請期間
2. **分階段審查**：續領和一般申請都有獨立的教授和學院審查期間
3. **時間不重疊**：確保各階段時間不衝突
4. **靈活配置**：可以為不同獎學金類型設定不同的時間安排

## 時間流程

```
時間軸：
[續領申請] → [續領教授審查] → [續領學院審查] → [一般申請] → [一般教授審查] → [一般學院審查]
```

**重要**：續領的完整流程（申請+教授審查+學院審查）都結束後，才開始一般申請的流程，沒有重疊。

### 詳細時間安排

1. **續領申請期間** (`renewal_application_start_date` 到 `renewal_application_end_date`)
   - 只有符合續領條件的學生可以申請
   - 優先處理，確保續領學生權益

2. **續領教授審查期間** (`renewal_professor_review_start` 到 `renewal_professor_review_end`)
   - 教授審查續領申請
   - 提供推薦意見

3. **續領學院審查期間** (`renewal_college_review_start` 到 `renewal_college_review_end`)
   - 學院層級審查續領申請
   - 最終決定續領結果

4. **一般申請期間** (`application_start_date` 到 `application_end_date`)
   - **只有在續領流程完全結束後才開始**
   - 開放給所有符合條件的學生
   - 包括新申請者和未通過續領的學生

5. **一般教授審查期間** (`professor_review_start` 到 `professor_review_end`)
   - 教授審查一般申請

6. **一般學院審查期間** (`college_review_start` 到 `college_review_end`)
   - 學院層級審查一般申請

## 資料庫設計

### ScholarshipType 模型新增欄位

```python
# 續領申請期間（優先處理）
renewal_application_start_date = Column(DateTime(timezone=True), nullable=True)
renewal_application_end_date = Column(DateTime(timezone=True), nullable=True)

# 續領審查期間
renewal_professor_review_start = Column(DateTime(timezone=True), nullable=True)
renewal_professor_review_end = Column(DateTime(timezone=True), nullable=True)
renewal_college_review_start = Column(DateTime(timezone=True), nullable=True)
renewal_college_review_end = Column(DateTime(timezone=True), nullable=True)
```

### Application 模型使用現有欄位

```python
# 續領申請標識
is_renewal = Column(Boolean, default=False, nullable=False)  # 是否為續領申請
```

## 核心方法

### 申請期間檢測

```python
@property
def is_renewal_application_period(self) -> bool:
    """檢查是否在續領申請期間"""

@property
def is_general_application_period(self) -> bool:
    """檢查是否在一般申請期間"""

@property
def current_application_type(self) -> Optional[str]:
    """獲取當前申請類型：'renewal' 或 'general' 或 None"""
```

### 審查階段檢測

```python
def get_current_review_stage(self) -> Optional[str]:
    """獲取當前審查階段：
    'renewal_professor', 'renewal_college', 
    'general_professor', 'general_college' 或 None
    """
```

### 申請資格檢查

```python
def can_student_apply(self, student_id: int, existing_applications: List['Application'], is_renewal: bool = None) -> bool:
    """檢查學生是否可以申請（考慮申請類型）"""

def can_student_apply_renewal(self, student_id: int, existing_applications: List['Application']) -> bool:
    """檢查學生是否可以申請續領"""

def can_student_apply_general(self, student_id: int, existing_applications: List['Application']) -> bool:
    """檢查學生是否可以申請一般申請"""
```

## 使用範例

### 檢查當前申請期間

```python
scholarship = get_scholarship_by_id(scholarship_id)

if scholarship.is_renewal_application_period:
    print("目前是續領申請期間")
    application_type = "renewal"
elif scholarship.is_general_application_period:
    print("目前是一般申請期間")
    application_type = "general"
else:
    print("目前不在申請期間")
    return
```

### 檢查審查階段

```python
current_stage = scholarship.get_current_review_stage()

if current_stage == "renewal_professor":
    print("續領教授審查階段")
elif current_stage == "renewal_college":
    print("續領學院審查階段")
elif current_stage == "general_professor":
    print("一般教授審查階段")
elif current_stage == "general_college":
    print("一般學院審查階段")
```

### 創建申請

```python
# 根據當前期間自動設定申請類型
application = Application(
    student_id=student_id,
    scholarship_type_id=scholarship_id,
    is_renewal=(scholarship.current_application_type == "renewal"),
    academic_year=scholarship.academic_year,
    semester=scholarship.semester
)
```

## 業務邏輯

### 續領資格

1. **學生必須是現有獎學金持有者**
2. **符合續領條件**（GPA、研究進度等）
3. **在續領申請期間內申請**

### 申請限制

1. **每個學生在每個學期只能有一種類型的申請**
2. **續領申請優先於一般申請**
3. **如果續領被拒絕，可以申請一般申請**

### 審查流程

1. **續領申請** → **續領教授審查** → **續領學院審查**
2. **一般申請** → **一般教授審查** → **一般學院審查**

## 配置建議

### 時間安排建議

```
續領申請期間：2週
續領教授審查：1週
續領學院審查：1週
[續領流程結束]
一般申請期間：3週
一般教授審查：2週
一般學院審查：2週
```

### 總時程：11週

這樣的安排確保了：
- 續領申請有足夠的優先處理時間
- 續領流程完全結束後才開始一般申請
- 教授和學院有充足的審查時間
- 整體流程在學期內完成
- 避免續領和一般申請的時間衝突

## 測試

參考 `backend/app/tests/test_scholarship_renewal.py` 中的測試案例，包括：

- 申請期間檢測
- 審查階段檢測
- 時間軸生成
- 下一個截止日期計算

## 遷移注意事項

1. **資料庫遷移**：需要添加新的欄位到 `scholarship_types` 和 `applications` 表
2. **現有資料**：現有的申請會被標記為 `application_type = "general"`
3. **向後相容**：保留 `is_renewal` 欄位以維持向後相容性 
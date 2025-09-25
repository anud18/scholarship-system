# 續領申請期間改動總結

## 概述

本次改動為獎學金系統添加了續領申請期間功能，允許系統優先處理續領申請，然後再處理一般申請。

## 主要改動

### 1. 資料庫模型改動

#### ScholarshipType 模型新增欄位
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

#### Application 模型使用現有欄位
```python
# 續領申請標識（使用現有的 is_renewal 欄位）
is_renewal = Column(Boolean, default=False, nullable=False)
```

### 2. 新增方法

#### ScholarshipType 模型新增方法
- `is_renewal_application_period()` - 檢查是否在續領申請期間
- `is_general_application_period()` - 檢查是否在一般申請期間
- `current_application_type` - 獲取當前申請類型
- `is_renewal_professor_review_period()` - 檢查是否在續領教授審查期間
- `is_renewal_college_review_period()` - 檢查是否在續領學院審查期間
- `get_current_review_stage()` - 獲取當前審查階段
- `can_student_apply()` - 更新為支援續領和一般申請
- `get_application_timeline()` - 獲取完整申請時間軸
- `get_next_deadline()` - 獲取下一個截止日期

#### Application 模型新增方法
- `is_renewal_application` - 檢查是否為續領申請
- `is_general_application` - 檢查是否為一般申請
- `application_type_label` - 獲取申請類型標籤
- `get_review_stage()` - 獲取當前審查階段

### 3. 資料庫遷移

#### 新增遷移文件
- `add_renewal_periods_to_scholarships.py` - 添加續領期間欄位到 scholarship_types 表

#### 遷移命令
```bash
# 執行遷移
alembic upgrade head

# 如果需要回滾
alembic downgrade -1
```

### 4. 初始化資料更新

#### init_db.py 更新
- 為所有測試獎學金添加續領期間設定
- 續領申請期間比一般申請期間早5天開始和結束
- 續領審查期間在續領申請結束後立即開始

### 5. 測試更新

#### 新增測試文件
- `test_scholarship_renewal.py` - 測試續領期間功能
- 包含申請期間檢測、審查階段檢測、時間軸生成等測試

#### 現有測試更新
- `test_application_renewal.py` - 已存在的測試，使用 `is_renewal` 欄位

### 6. 文檔更新

#### 新增文檔
- `scholarship_renewal_design.md` - 詳細的設計文檔
- `renewal_period_changes_summary.md` - 本總結文檔

## 時間流程

```
時間軸：
[續領申請] → [續領教授審查] → [續領學院審查] → [一般申請] → [一般教授審查] → [一般學院審查]
```

**重要**：續領的完整流程（申請+教授審查+學院審查）都結束後，才開始一般申請的流程，沒有重疊。

### 開發環境時間設定
```python
# 續領期間設定（優先處理，完整流程）
renewal_start = now - timedelta(days=60)  # 續領申請開始
renewal_end = now - timedelta(days=40)    # 續領申請結束
renewal_professor_start = now - timedelta(days=39)  # 續領教授審查開始
renewal_professor_end = now - timedelta(days=30)    # 續領教授審查結束
renewal_college_start = now - timedelta(days=29)    # 續領學院審查開始
renewal_college_end = now - timedelta(days=20)      # 續領學院審查結束

# 一般申請期間設定（續領流程完全結束後）
start_date = now - timedelta(days=15)     # 一般申請開始
end_date = now + timedelta(days=15)       # 一般申請結束
```

## 向後相容性

### 保持相容的部分
1. **Application 模型**：繼續使用現有的 `is_renewal` 欄位
2. **API 介面**：所有現有的 API 端點保持不變
3. **前端組件**：不需要修改現有組件
4. **資料庫約束**：保持現有的唯一約束

### 新增功能
1. **續領期間管理**：新的時間管理功能
2. **分階段審查**：續領和一般申請的獨立審查流程
3. **時間軸顯示**：完整的申請時間軸
4. **截止日期提醒**：下一個截止日期計算

## 使用方式

### 檢查當前申請期間
```python
scholarship = get_scholarship_by_id(scholarship_id)

if scholarship.is_renewal_application_period:
    print("目前是續領申請期間")
elif scholarship.is_general_application_period:
    print("目前是一般申請期間")
else:
    print("目前不在申請期間")
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

## 部署注意事項

### 1. 資料庫遷移
```bash
# 在部署前執行遷移
alembic upgrade head
```

### 2. 初始化資料
```bash
# 重新初始化資料庫（開發環境）
python -m app.core.init_db
```

### 3. 測試驗證
```bash
# 執行測試
pytest backend/app/tests/test_scholarship_renewal.py -v
pytest backend/app/tests/test_application_renewal.py -v
```

## 未來擴展

### 可能的改進
1. **動態時間設定**：允許管理員動態調整時間
2. **多階段審查**：支援更複雜的審查流程
3. **自動化通知**：在階段轉換時自動發送通知
4. **統計分析**：續領和一般申請的統計分析

### 配置建議
1. **生產環境時間設定**：根據實際業務需求調整時間
2. **監控和日誌**：添加階段轉換的監控和日誌
3. **備份策略**：確保資料庫遷移的備份策略

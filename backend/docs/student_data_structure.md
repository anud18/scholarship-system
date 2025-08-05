# 學生資料儲存結構說明

## 概述

系統已經移除了 Student 資料庫模型，所有學生相關資料現在透過以下方式處理：
1. **基本學生資料**：透過外部 Student API 獲取
2. **申請特定資料**：儲存在 `applications.student_data` JSON 欄位中

## 新的資料結構

### StudentDataSchema - 完整學生資料結構

```python
class StudentDataSchema(BaseModel):
    # 基本學生資料 (來自外部 API)
    student_id: Optional[str] = "學號"
    name: Optional[str] = "姓名"
    email: Optional[str] = "Email"
    department: Optional[str] = "系所"
    degree: Optional[str] = "學位"
    
    # 金融帳戶資訊 (使用者輸入)
    financial_info: Optional[StudentFinancialInfo]
    
    # 指導教授資訊 (使用者輸入)
    supervisor_info: Optional[SupervisorInfo]
    
    # 聯絡資訊 (使用者輸入)
    contact_phone: Optional[str] = "聯絡電話"
    contact_address: Optional[str] = "聯絡地址"
    
    # 學術資訊 (外部 API + 使用者輸入)
    gpa: Optional[float] = "GPA"
    class_ranking: Optional[int] = "班級排名"
    class_total: Optional[int] = "班級總人數"
    dept_ranking: Optional[int] = "系所排名"
    dept_total: Optional[int] = "系所總人數"
```

### StudentFinancialInfo - 金融帳戶資訊

```python
class StudentFinancialInfo(BaseModel):
    bank_postal_account: Optional[str] = "銀行或郵局帳號"
    bank_book_photo_url: Optional[str] = "銀行或郵局帳簿封面照片URL"
    bank_name: Optional[str] = "銀行或郵局名稱"
    account_holder_name: Optional[str] = "帳戶戶名"
```

### SupervisorInfo - 指導教授資訊

```python
class SupervisorInfo(BaseModel):
    supervisor_employee_id: Optional[str] = "指導教授工號"
    supervisor_email: Optional[str] = "指導教授email"
    supervisor_name: Optional[str] = "指導教授姓名"
    supervisor_department: Optional[str] = "指導教授所屬系所"
```

## API 端點

### 更新學生資料
```
PUT /api/v1/applications/{application_id}/student-data
```

請求範例：
```json
{
  "financial_info": {
    "bank_postal_account": "123456789",
    "bank_book_photo_url": "https://storage.example.com/bank-book.jpg",
    "bank_name": "台灣銀行",
    "account_holder_name": "王小明"
  },
  "supervisor_info": {
    "supervisor_employee_id": "T001234",
    "supervisor_email": "supervisor@university.edu.tw",
    "supervisor_name": "李教授",
    "supervisor_department": "資訊工程學系"
  },
  "contact_phone": "0912345678",
  "contact_address": "台北市大安區..."
}
```

### 取得學生資料
```
GET /api/v1/applications/{application_id}/student-data
```

## 資料庫儲存

所有學生相關資料都儲存在 `applications` 表的 `student_data` JSON 欄位中：

```sql
-- applications 表結構
CREATE TABLE applications (
    id SERIAL PRIMARY KEY,
    app_id VARCHAR(20) UNIQUE NOT NULL,
    user_id INTEGER NOT NULL,
    scholarship_type_id INTEGER,
    ...
    student_data JSONB,  -- 儲存完整學生資料
    submitted_form_data JSONB,
    ...
);
```

## 檔案上傳處理

銀行帳簿封面照片透過現有的檔案上傳系統處理：
1. 前端上傳檔案到 MinIO 儲存系統
2. 後端回傳檔案 URL
3. 將 URL 儲存在 `financial_info.bank_book_photo_url` 欄位中

## 權限控制

- **學生**：只能修改自己申請的學生資料
- **管理員/學院**：可以查看所有申請的學生資料
- **狀態限制**：只有 `draft` 或 `returned` 狀態的申請可以修改學生資料

## 注意事項

1. **外部 API 整合**：基本學生資料（學號、姓名、系所等）應優先從外部 Student API 獲取
2. **資料合併**：系統會將外部 API 資料與使用者輸入資料合併儲存
3. **JSON 儲存**：使用 PostgreSQL 的 JSONB 格式，支援高效查詢和索引
4. **向下相容性**：已移除舊版欄位，不再支援向下相容性
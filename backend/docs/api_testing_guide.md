# API 測試指南

## 學生資料 API 端點

### 1. 更新申請的學生資料

```bash
# 更新學生資料（需要認證）
curl -X PUT "http://localhost:8000/api/v1/applications/{application_id}/student-data" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {token}" \
  -d '{
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
    "contact_address": "台北市大安區...",
    "gpa": 3.8
  }'
```

### 2. 取得申請的學生資料

```bash
# 取得學生資料（需要認證）
curl -X GET "http://localhost:8000/api/v1/applications/{application_id}/student-data" \
  -H "Authorization: Bearer {token}"
```

### 3. 重新從外部 API 獲取學生基本資料並更新

```bash
# 更新學生資料並重新從外部 API 獲取基本資料
curl -X PUT "http://localhost:8000/api/v1/applications/{application_id}/student-data?refresh_from_api=true" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {token}" \
  -d '{
    "financial_info": {
      "bank_postal_account": "987654321",
      "bank_name": "郵局"
    }
  }'
```

## 資料結構

### StudentDataSchema 回應格式

```json
{
  "student_id": "110123456",
  "name": "王小明",
  "email": "student@university.edu.tw",
  "department": "資訊工程學系",
  "degree": "博士班",
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
  "contact_address": "台北市大安區...",
  "gpa": 3.8,
  "class_ranking": 5,
  "class_total": 30,
  "dept_ranking": 12,
  "dept_total": 200
}
```

## 錯誤處理

### 常見錯誤回應

1. **申請不存在或無權限存取**
```json
{
  "detail": "Application not found or access denied"
}
```

2. **申請狀態不允許編輯**
```json
{
  "detail": "Cannot update student data for submitted applications"
}
```

3. **權限不足**
```json
{
  "detail": "You can only update your own application data"
}
```

## 權限說明

- **學生用戶**: 只能修改和查看自己的申請學生資料
- **管理員/學院用戶**: 可以查看所有申請的學生資料
- **狀態限制**: 只有 `draft` 或 `returned` 狀態的申請可以修改學生資料

## 資料快照機制

1. **申請建立時**: 系統會自動從外部學生 API 獲取基本學生資料並建立快照
2. **資料更新時**: 用戶輸入的資料會與現有快照合併
3. **API 重新整理**: 使用 `refresh_from_api=true` 參數可重新從外部 API 獲取最新的基本學生資料

## 使用場景

1. **學生填寫申請**: 提供銀行帳號、指導教授資訊等額外資料
2. **資料更正**: 學生可以更新聯絡資訊、銀行帳號等
3. **管理員查看**: 管理員可以查看申請時的完整學生資料快照
4. **歷史保存**: 每個申請都保留申請當時的學生資料，確保歷史完整性
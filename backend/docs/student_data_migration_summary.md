# 學生資料系統重構總結

## 概述

本次重構成功將學生資料系統從本地資料庫模型轉換為外部 API 整合模式，同時新增了申請特定的學生資料儲存功能。

## 完成的工作

### ✅ 1. 移除 Student 資料庫模型

- **移除檔案和參考**：
  - 從所有服務檔案中移除 Student 模型的 import
  - 更新相關的 schema 和 API 端點
  - 註釋掉依賴 Student 模型的查詢（如 scholarship_configurations.py）

- **更新的檔案**：
  - `app/services/bulk_approval_service.py`
  - `app/services/eligibility_verification_service.py`
  - `app/services/analytics_service.py`
  - `app/services/scholarship_notification_service.py`
  - `app/services/scholarship_service.py`
  - `app/api/v1/endpoints/scholarship_configurations.py`
  - `app/schemas/__init__.py`

### ✅ 2. 實現學生資料快照功能

- **application_service.py** 中的 `create_application` 方法：
  ```python
  # 從外部 API 獲取學生資料快照
  student_snapshot = await self.student_service.get_student_snapshot(student_code)

  # 儲存到 application 的 student_data 欄位
  application = Application(
      # ...
      student_data=student_snapshot,
      # ...
  )
  ```

### ✅ 3. 新增學生相關資料儲存結構

建立了完整的學生資料架構：

#### StudentFinancialInfo - 金融帳戶資訊
- `bank_postal_account`: 銀行或郵局帳號 ✅
- `bank_book_photo_url`: 銀行或郵局帳簿封面照片URL ✅
- `bank_name`: 銀行或郵局名稱
- `account_holder_name`: 帳戶戶名

#### SupervisorInfo - 指導教授資訊
- `supervisor_employee_id`: 指導教授工號 ✅
- `supervisor_email`: 指導教授email ✅
- `supervisor_name`: 指導教授姓名
- `supervisor_department`: 指導教授所屬系所

#### StudentDataSchema - 完整學生資料結構
結合外部 API 資料與使用者輸入的完整資料結構

### ✅ 4. API 端點實現

- **更新學生資料**：
  ```
  PUT /api/v1/applications/{application_id}/student-data
  ```
  - 支援部分更新
  - 支援從外部 API 重新獲取基本資料 (`refresh_from_api` 參數)
  - 完整的權限檢查和狀態驗證

- **取得學生資料**：
  ```
  GET /api/v1/applications/{application_id}/student-data
  ```
  - 權限控制（學生只能看自己的，管理員可看所有）

### ✅ 5. 服務層更新

- **ApplicationService.update_student_data()** 方法：
  - 智慧合併外部 API 資料與使用者輸入
  - 深度合併嵌套物件（financial_info, supervisor_info）
  - 完整的權限和狀態檢查

## 資料儲存方式

```sql
-- applications 表中的 student_data 欄位
{
  // 基本學生資料 (來自外部 API)
  "student_id": "110123456",
  "name": "王小明",
  "department": "資訊工程學系",

  // 金融帳戶資訊 (使用者輸入)
  "financial_info": {
    "bank_postal_account": "123456789",
    "bank_book_photo_url": "https://storage.example.com/bank-book.jpg",
    "bank_name": "台灣銀行",
    "account_holder_name": "王小明"
  },

  // 指導教授資訊 (使用者輸入)
  "supervisor_info": {
    "supervisor_employee_id": "T001234",
    "supervisor_email": "supervisor@university.edu.tw",
    "supervisor_name": "李教授",
    "supervisor_department": "資訊工程學系"
  },

  // 其他聯絡和學術資訊
  "contact_phone": "0912345678",
  "gpa": 3.8
}
```

## 系統架構優勢

1. **資料快照**：每個申請都保存申請當時的學生資料快照，確保歷史資料的完整性
2. **外部整合**：通過 StudentService 與外部學生 API 整合
3. **彈性儲存**：使用 JSON 欄位儲存，支援動態資料結構
4. **權限控制**：完整的 RBAC 權限系統
5. **狀態管理**：只有特定狀態的申請可以修改學生資料

## 待優化項目

- [ ] 重新實現 scholarship_configurations.py 中的配額查詢功能
- [ ] 完善其他依賴 Student 模型的服務方法
- [ ] 建立學生資料同步機制

## 技術細節

- **資料庫**：PostgreSQL JSONB 欄位，支援高效查詢
- **API**：RESTful 設計，支援部分更新
- **驗證**：Pydantic schema 驗證
- **錯誤處理**：自定義異常處理
- **日誌**：完整的操作日誌記錄

這次重構成功地將系統從本地學生資料庫遷移到外部 API 整合模式，同時保留了申請歷史資料的完整性，並新增了用戶要求的銀行帳號和指導教授資訊儲存功能。

# College Application Materials Export Package

**Date:** 2026-04-07
**Status:** Approved
**Branch:** `feat/college-export-package`

## Overview

學院使用者在審查過程中，可以隨時下載所屬學院各系所的申請資料 ZIP 檔。ZIP 內按系所代碼分資料夾，每個學生一個子資料夾，包含後端即時生成的「學生資料彙整 PDF」及所有上傳附件。

## API Endpoint

### `GET /api/v1/college-review/export-package`

**Query Parameters:**

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `scholarship_type_id` | int | Yes | 獎學金類型 |
| `academic_year` | int | Yes | 學年度 |
| `semester` | string | No | 學期（first/second/null for annual） |

**Response:**
- `StreamingResponse` with `Content-Type: application/zip`
- `Content-Disposition: attachment; filename="{獎學金名稱}_申請資料_{學年}_{學期}_{學院名}.zip"`

**權限:**
- College / Admin / Super Admin
- College 使用者只能下載自己學院的申請資料（由 `AdminScholarship` 權限 + 使用者的 `college_code` 過濾）

**錯誤情境:**
- 無符合條件的申請 → 400 "無申請資料可匯出"
- 無權限 → 403

## ZIP Structure

### 檔名

```
{獎學金名稱}_申請資料_{學年}_{學期}_{學院名}.zip
```

Example: `研究獎助生_申請資料_113_1_電機學院.zip`

### 內部結構（三層）

```
0701_資訊工程學系/
  B11234567_王小明/
    學生資料彙整.pdf              ← 後端生成
    成績單.pdf                    ← MinIO 原檔
    推薦信.pdf                    ← MinIO 原檔
  B11234568_李大華/
    學生資料彙整.pdf
    存摺封面.pdf
0702_電子工程學系/
  B11345678_張小英/
    學生資料彙整.pdf
    成績單.pdf
```

### 命名規則

- **系所資料夾**: `{系所代碼}_{系所名稱}/`（來自 `student_data.trm_depno` + `trm_depname`）
- **學生資料夾**: `{學號}_{姓名}/`（來自 `student_data.std_stdcode` + `std_cname`）
- **彙整 PDF**: `學生資料彙整.pdf`（固定名稱）
- **附件檔案**: 用 `file_type` 中文對照命名，同類型多個加序號（`成績單_1.pdf`、`成績單_2.pdf`）
- **特殊字元處理**: 檔名中的 `/`、`\`、`:`、`*` 等替換為 `_`

### file_type 中文對照

| file_type | 中文名 |
|-----------|--------|
| transcript | 成績單 |
| research_proposal | 研究計畫 |
| recommendation_letter | 推薦信 |
| certificate | 證書 |
| insurance_record | 投保紀錄 |
| agreement | 切結書 |
| bank_account_cover | 存摺封面 |
| other | 其他文件 |

## Student Summary PDF Content

用 weasyprint 從 HTML template 生成，包含以下區塊：

### 1. 基本資料

| 欄位 | 來源 |
|------|------|
| 學號 | `std_stdcode` |
| 姓名 | `std_cname` |
| 英文姓名 | `std_ename` |
| 學院 | `trm_academyname` |
| 系所 | `trm_depname` |
| 學位 | `trm_degree`（對照：1=學士、2=碩士、3=博士） |
| 入學年度 | `std_enrollyear` |
| Email | `com_email` |
| 手機 | `com_cellphone` |

### 2. 學業表現

| 欄位 | 來源 |
|------|------|
| 學年/學期 | `trm_year` / `trm_term` |
| GPA | `trm_ascore_gpa` |
| 班排名/班人數 | `trm_placings` / 排名百分比 |
| 系排名/系人數 | `trm_depplacing` / 排名百分比 |
| 修業學期數 | `trm_termcount` |

### 3. 表單填寫資料

- 動態渲染 `submitted_form_data.fields` 所有欄位
- 每個欄位顯示「欄位名稱：填寫值」
- 依 field_id 順序排列

### 4. 上傳文件清單

- 列出所有 `submitted_form_data.documents` 的文件名稱與上傳時間
- 僅清單，實際檔案在同資料夾內

### 5. 頁首/頁尾

- 頁首：獎學金名稱 + 學年學期
- 頁尾：匯出時間 + 頁碼

## Technical Architecture

### New Files

| 檔案 | 用途 |
|------|------|
| `backend/app/services/export_package_service.py` | ZIP 打包 + PDF 生成核心邏輯 |
| `backend/app/templates/student_summary.html` | 彙整 PDF 的 HTML template |
| `backend/app/api/v1/endpoints/college_review/export_package.py` | API endpoint |
| `frontend/lib/api/modules/college-review.ts` | 新增 `exportPackage()` API 方法 |
| 申請列表頁元件 | 新增匯出按鈕 + loading 狀態 |
| Next.js proxy route | ZIP 下載 proxy |

### Processing Flow

```
1. 接收請求，驗證權限
2. 查詢符合條件的 Applications（JOIN ApplicationFile）
3. 按 trm_depno 分組
4. 建立 ZipFile（寫入 BytesIO）
   ├── 對每個系所：
   │   └── 對每個學生：
   │       ├── 用 weasyprint 生成「學生資料彙整.pdf」
   │       ├── 從 MinIO 下載每個 ApplicationFile
   │       └── 寫入 ZIP（系所資料夾/學生資料夾/檔名）
5. 回傳 StreamingResponse
```

### Key Implementation Details

**weasyprint 依賴:**
- Dockerfile 安裝: `libpango-1.0-0`, `libpangocairo-1.0-0`, `libgdk-pixbuf2.0-0`, `libffi-dev`
- 中文字型: `fonts-noto-cjk`

**串流策略:**
- 規模 10-50 份，在記憶體中組裝完整 ZIP（`BytesIO`），再用 `StreamingResponse` 回傳

**MinIO 檔案讀取:**
- 複用現有 `minio_service.get_file_stream()` 取得檔案內容
- 讀入 bytes 後寫入 zip entry

**錯誤處理:**
- 單一檔案下載失敗不中斷整個 ZIP，改為在該學生資料夾放一個 `_錯誤_找不到檔案.txt` 說明
- PDF 生成失敗則記 log，同樣放 `_錯誤_彙整PDF生成失敗.txt`

## Frontend UI

### 觸發位置

在 college review 申請列表頁，篩選條件旁新增「匯出申請資料」按鈕（右側對齊，下載 icon）。

### 互動流程

1. 選好篩選條件（獎學金類型 + 學年 + 學期）後，按鈕啟用
2. 點擊 → 按鈕 loading 狀態（「匯出中...」）
3. 前端發 GET 請求，接收 blob response
4. 下載完成 → 自動觸發瀏覽器下載 ZIP
5. 失敗 → toast 提示錯誤訊息

### Next.js Proxy

新增 proxy route 處理 ZIP 下載，確保 token 認證和 Docker 內部網路通訊（同現有 file proxy 架構）。

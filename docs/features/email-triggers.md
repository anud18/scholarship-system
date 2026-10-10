# 系統寄信時機點 (Email Trigger Points)

> 適用範圍：`backend/` 全部寄信路徑。
> 最後盤點日期：2026-07-28（依 `main` 分支程式碼實際呼叫關係整理，非依設計文件）。

---

## 目錄

1. [一分鐘總覽](#1-一分鐘總覽)
2. [寄信管線架構](#2-寄信管線架構)
3. [時機點總表](#3-時機點總表)
4. [各時機點詳細說明](#4-各時機點詳細說明)
5. [自動化規則（DB 驅動）](#5-自動化規則db-驅動)
6. [排程任務時間表](#6-排程任務時間表)
7. [郵件測試模式](#7-郵件測試模式)
8. [目前「不會」寄信的環節](#8-目前不會寄信的環節)
9. [除錯指引](#9-除錯指引)

---

## 1. 一分鐘總覽

實際會送出郵件的時機點只有 **7 個**，可分成三類：

| 類別 | 時機點 | 觸發者 |
|---|---|---|
| **申請流程** | 學生送出申請 | 學生（自動） |
| | 管理員/學院指派教授 | 管理員（自動附帶） |
| | 承辦人建立補件要求 | 承辦人（自動附帶） |
| **排程提醒** | 申請截止前 7/3/1 天 | 排程（每日 09:00） |
| | 教授審核截止前 3 天內（每日） | 排程（每日 09:00） |
| **管理操作** | 批次核准／批次退件 | 管理員（可關閉） |
| | 撤銷／停發獎助生 | 管理員（自動附帶） |
| **（工具）** | 管理後台「寄送測試信」 | 管理員手動 |

⚠️ **重要**：**教授完成審核、學院完成審核、最終錄取結果** 這三個關鍵節點，
程式雖然寫好了觸發函式，但**目前沒有任何地方呼叫**，所以**不會寄信**。
詳見 [第 8 節](#8-目前不會寄信的環節)。

---

## 2. 寄信管線架構

系統有 **兩條** 實際會呼叫 SMTP 的路徑，其中只有第一條在使用中。

```
┌─────────────────────────────────────────────────────────────────┐
│ 主線（99% 的信走這裡）                                            │
│                                                                 │
│  業務事件                                                        │
│     │                                                           │
│     ├─(A) 走自動化規則 ──► EmailAutomationService                 │
│     │                        .process_trigger(trigger_event)     │
│     │                     查 email_automation_rules 表            │
│     │                     用 condition_query 撈收件人             │
│     │                     呼叫前端 render 出 HTML                 │
│     │                              │                            │
│     ├─(B) 直接排入佇列 ────────────┤                             │
│     │                              ▼                            │
│     │                     scheduled_emails（信件佇列，status=pending）│
│     │                              │                            │
│     │                     每 N 秒由 email_processor 撈出          │
│     │                              ▼                            │
│     └─(C) 立即直送 ──────► EmailService.send_email()              │
│                                    │                            │
│                            測試模式攔截 / 改收件人                 │
│                                    ▼                            │
│                              aiosmtplib → SMTP                   │
│                                    │                            │
│                            寫入 email_history（成功與失敗都寫）    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 副線（目前形同休眠，見 §8）                                        │
│  NotificationService.create_notification()                       │
│     └─ 若使用者的 NotificationPreference.email_enabled = true     │
│          └─ fastapi_mail → SMTP（不寫 email_history）             │
└─────────────────────────────────────────────────────────────────┘
```

**三種送信方式的差異**

| 方式 | 何時送出 | 有 HTML 版型 | 失敗會怎樣 |
|---|---|---|---|
| (A) 自動化規則 | 排入佇列，下一輪 processor 送出 | 有（React Email） | 佇列標 `failed`，記 `last_error`，可重試 |
| (B) 直接排佇列 | 同上 | 有 | 同上 |
| (C) 立即直送 | 當下同步送 | 多為純文字／inline HTML | 記入 `email_history` status=failed |

**關鍵檔案**

| 角色 | 檔案 |
|---|---|
| SMTP 發送、測試模式、歷程記錄 | `backend/app/services/email_service.py` |
| 事件觸發 → 規則比對 → 排隊 | `backend/app/services/email_automation_service.py` |
| 佇列處理器（每 N 秒） | `backend/app/tasks/email_processor.py` |
| 截止日檢查（每日 09:00） | `backend/app/tasks/deadline_checker.py` |
| 排程註冊 | `backend/app/services/roster_scheduler_service.py:init_scheduler()` |
| React Email 版型 | `frontend/emails/*.tsx` |

---

## 3. 時機點總表

| # | 時機點 | 收件人 | 送信方式 | 版型 / template_key | 觸發程式位置 |
|---|---|---|---|---|---|
| 1 | 學生送出申請 | 學生本人 | (A) 規則 | `application_submitted_student` | `application_service.py:1298`（送出草稿）<br>`application_service.py:585`（直接送出） |
| 2 | 學生送出申請 | 指導教授 | (A) 規則 | `professor_review_notification` | 同上（同一個 trigger，兩條規則） |
| 3 | 指派教授 | 該教授 | (B) 佇列 | `professor_review_notification` | `application_service.py:2870` (`assign_professor`) |
| 4 | 建立補件要求 | 學生本人 | (A) 規則 | `supplement_requested` 事件 | `endpoints/document_requests.py:100` |
| 5 | 申請截止前 7/3/1 天 | 尚有草稿的學生 | (A) 規則 | `deadline_approaching` 事件 | `tasks/deadline_checker.py:176`（申請截止）<br>`tasks/deadline_checker.py:257`（補件截止） |
| 6 | 教授審核截止前 3 天內 | 未完成審核的教授 | (B) 佇列 | `professor_review_notification` | `tasks/deadline_checker.py:425` |
| 7 | 批次核准／批次退件 | 學生本人 | (C) 直送 | 程式內嵌 HTML | `bulk_approval_service.py:110 / 218` |
| 8 | 批次作業完成 | 指定管理員信箱 | (C) 直送 | 程式內嵌 HTML | `bulk_approval_service.py:516` |
| 9 | 撤銷／停發獎助生 | **操作的管理員本人** | (C) 直送（背景） | 程式內嵌純文字 | `endpoints/manual_distribution.py:769 / 808` |
| 10 | 後台寄送測試信 | 指定信箱 | (C) 直送 | 管理員自填 | `endpoints/email_management.py:555` |

> 註：#5 與 #6 都由每日 09:00 的同一個排程觸發，但走不同管線。

---

## 4. 各時機點詳細說明

### 4.1 學生送出申請（#1、#2）

**觸發條件**

- 學生把草稿送出 → `ApplicationService.submit_application()`
- 或建立申請時直接送出（`is_draft = False`）→ `ApplicationService.create_application()`

兩條路徑都呼叫 `email_automation_service.trigger_application_submitted()`，
發出 `application_submitted` 事件。

**這個事件目前掛了兩條啟用中的規則：**

| 規則名稱 | 收件人來源 | 版型 |
|---|---|---|
| 申請提交確認郵件 | `student_data->>'com_email'`，找不到才 fallback 到 `users.email` | `application-submitted.tsx` |
| 教授審核通知 | `applications.professor_id → users.email`，找不到才 fallback 到 `user_profiles.advisor_email` | `professor-review-request.tsx` |

**注意事項**

- 整段包在 `try/except` 裡：**寄信失敗不會讓申請送出失敗**，只會寫 log
  （`❌ Failed to trigger automated submission emails`）。
- 草稿狀態（`is_draft = True`）**不寄信**。
- 若學生沒有指導教授（`professor_id` 與 `advisor_email` 皆空），
  教授那封信會因為 `condition_query` 撈不到收件人而**靜默略過**，
  log 會出現 `No recipients found for rule ... — skipping send`。

---

### 4.2 指派教授（#3）

**觸發條件**：管理員或學院承辦在後台把申請指派給某位教授
（`ApplicationService.assign_professor()`）。

**特別之處**：這條**不走自動化規則**，而是直接呼叫前端把
`professor-review-request` 版型渲染成 HTML，再手動排進 `scheduled_emails`。

**信件內容**：主旨 `審查通知 - {學生姓名} 的 {獎學金名稱} 申請`

**注意事項**

- 教授沒有 email 就直接略過。
- 同樣包在 `try/except`：寄信失敗不影響指派結果。
- 同時還會建立一則**站內通知**（in-app notification）。

---

### 4.3 建立補件要求（#4）

**觸發條件**：承辦人在申請詳情頁建立 `DocumentRequest`
（`POST /api/v1/document-requests`）。

**流程**：先寫入 `document_requests` 與稽核紀錄，commit 之後才發出
`supplement_requested` 事件。

**注意事項**

- ⚠️ **預設種子資料裡沒有 `supplement_requested` 的規則**。
  也就是說，除非管理員在「郵件自動化」後台自行新增並啟用規則，
  否則這個事件**發了也不會有信**。
- 收件人以 `student_data['email']` 為主，fallback 到 `users.email`。

---

### 4.4 截止日提醒（#5、#6）

由每日 09:00 的 `run_deadline_check()` 統一觸發，內部檢查三種截止日：

#### (a) 申請送出截止 — `check_submission_deadlines()`

- 門檻：截止前 **7 / 3 / 1 天**（`WARNING_DAYS = [7, 3, 1]`）
- 同時檢查**續領申請截止**（`renewal_application_end_date`）與
  **一般申請截止**（`application_end_date`）
- 對象：該獎學金設定下，狀態為 `draft` 或 `in_progress` 的申請
- 發出 `deadline_approaching` 事件，`deadline_type` 分別為
  `renewal_submission` / `submission`

#### (b) 補件截止 — `check_document_request_deadlines()`

- 門檻：同樣 7 / 3 / 1 天
- 對象：`status = pending` 且 `deadline` 落在該日的 `DocumentRequest`
- 發出 `deadline_approaching` 事件，`deadline_type = document_request`

> ⚠️ (a) 與 (b) 都靠 `deadline_approaching` 規則，而**種子資料同樣沒有這條規則**，
> 需管理員自行建立才會實際寄信。

#### (c) 教授審核截止提醒 — `send_professor_review_deadline_reminders()`

這條**不走自動化規則**，一定會寄。

- 條件：獎學金設定的 `professor_review_end` 落在**未來 3 天內**（尚未過期）
- 對象：該設定下 `submitted` / `under_review` 且**教授尚未送出審核**的申請
- **防重複**：同一申請當天若已排過 `professor_review_notification`，就跳過
  → 效果是「截止前 3 天起，每天最多一封」
- 主旨：`[提醒] 尚有 N 天 — 請完成審核 {申請編號}`

---

### 4.5 批次核准／批次退件（#7、#8）

**觸發條件**：管理員呼叫 `POST /api/v1/admin/applications/bulk-approve`。

**開關**：由 request payload 的 `send_notifications` 控制（預設 `true`）。
設為 `false` 就完全不寄信。

**信件內容**：`ScholarshipNotificationService.send_status_change_notification()`
產生的**英文 HTML** 信，內容依新狀態而異：

| 新狀態 | 標題 |
|---|---|
| `under_review` | Application Under Review |
| `approved` | Application Approved! 🎉 |
| `rejected` | Application Decision（含退件原因） |
| `returned` | Application Returned for Revision |

**批次完成通知（#8）**：只有走 `batch_process_with_notifications()` 且
呼叫端有帶 `admin_email` 時才會寄，內容是處理統計摘要。

**注意事項**

- 這是**同步直送**：每一封都會實際連 SMTP，批次量大時該 API 會變慢。
- 退件原因取自最近一筆有 `comments` 的 `ApplicationReview`。

---

### 4.6 撤銷／停發獎助生（#9）

**觸發條件**

- `POST /api/v1/manual-distribution/applications/{id}/revoke`（撤銷）
- `POST /api/v1/manual-distribution/applications/{id}/suspend`（停發）

**收件人**：⚠️ 不是學生，而是**執行操作的管理員本人**——這是一封操作紀錄存證信。

**信件內容**（純文字）：申請編號、學生姓名與學號、獎學金名稱、
撤銷/停發原因、操作時間。

**注意事項**

- 用 FastAPI `BackgroundTasks` 在**回應送出後**才寄，
  所以 SMTP 慢或不通不會拖慢撤銷 API。
- 背景任務自己開新的 DB session（原 request session 當時已關閉）。
- 管理員沒有 email 就跳過，只寫 log。
- **復原（restore）操作不寄信。**

---

### 4.7 後台寄送測試信（#10）

`POST /api/v1/email-management/send-simple-test`（限管理員）。
主旨自動加上 `[TEST] ` 前綴；若 body 以 `<!doctype` 或 `<html` 開頭，
會被當成 HTML 信寄出。

---

## 5. 自動化規則（DB 驅動）

「時機點」與「實際寄不寄信」是**兩件事**。程式只負責發出 *trigger event*，
真正決定寄不寄、寄給誰、用什麼版型的是 **`email_automation_rules` 資料表**。

### 5.1 支援的事件（`TriggerEvent` enum）

| 事件值 | 中文 | 程式是否會發出？ |
|---|---|---|
| `application_submitted` | 申請提交時 | ✅ 會 |
| `supplement_requested` | 要求補件時 | ✅ 會 |
| `deadline_approaching` | 截止日期接近時 | ✅ 會 |
| `professor_review_submitted` | 教授審核提交時 | ❌ **無人呼叫** |
| `college_review_submitted` | 學院審核提交時 | ❌ **無人呼叫** |
| `final_result_decided` | 最終結果決定時 | ❌ **無人呼叫** |

### 5.2 預設種子規則

`seed_email_automation_rules()`（`backend/app/db/seed_scholarship_configs.py`）：

| 規則名稱 | 事件 | 版型 | 預設狀態 |
|---|---|---|---|
| 申請提交確認郵件 | `application_submitted` | `application_submitted_student` | ✅ 啟用 |
| 教授審核通知 | `application_submitted` | `professor_review_notification` | ✅ 啟用 |
| 學院審核通知 | `professor_review_submitted` | `college_review_notification` | ❌ 停用 |

> 前兩條由 migration `enable_automation_rules_001` 明確設為啟用。
> 種子只在資料表**完全為空**時寫入——已有資料就整段跳過。

### 5.3 規則的四個欄位

| 欄位 | 作用 |
|---|---|
| `trigger_event` | 綁定哪個事件 |
| `template_key` | 用哪個郵件版型（決定主旨與內文） |
| `condition_query` | 一段 SQL，**第一個欄位就是收件人 email**；`{application_id}` 之類的佔位符會被轉成綁定參數（防注入） |
| `delay_hours` | 延遲幾小時寄；`0` = 排入佇列後下一輪就送 |
| `is_active` | 停用的規則直接跳過 |

管理入口：`/api/v1/email-automation`（GET / POST / PUT / DELETE / PATCH toggle）。

### 5.4 版型對應

DB 的 `template_key` 會再對到 React Email 版型（`_get_react_email_template_name()`）：

| template_key | React 版型（`frontend/emails/`） |
|---|---|
| `application_submitted_student` | `application-submitted.tsx` |
| `professor_review_notification` | `professor-review-request.tsx` |
| `college_review_notification` | `college-review-request.tsx` |
| `application_deadline_reminder` | `deadline-reminder.tsx` |
| `document_request_notification` | `document-request.tsx` |
| `result_notification_student` | `result-notification.tsx` |
| `roster_notification` | `roster-notification.tsx` |
| `whitelist_notification` | `whitelist-notification.tsx` |

找不到對應版型時，退回 DB 版型的純文字內容。

---

## 6. 排程任務時間表

註冊於 `roster_scheduler_service.py:init_scheduler()`，backend 啟動時自動掛上，
**不需要設定 cron**。

| 任務 | 頻率 | 用途 |
|---|---|---|
| `email_processor` | 每 N 秒（預設 60，可由系統設定 `email_processor_interval_seconds` 調整） | 撈出 `scheduled_emails` 中到期的信並送出 |
| `deadline_checker` | 每日 **09:00** | 檢查三種截止日並觸發提醒 |
| `batch_import_cleanup` | 每日 02:00 | 清理批次匯入資料（與郵件無關） |

**email_processor 的行為**

- 啟動後 **5 秒內不處理**（避免服務剛起來就爆信）
- 每輪最多取 50 封，依 `priority ASC, scheduled_for ASC` 排序
- 只送 `status = 'pending'`、`scheduled_for <= NOW()`、
  且（`requires_approval = false` 或已核准）的信
- 送成功標 `sent`；失敗標 `failed`、`retry_count + 1`、記 `last_error`

**手動執行**

```bash
python -m app.tasks.email_processor     # 立刻處理佇列
python -m app.tasks.deadline_checker    # 立刻跑截止日檢查
```

也可用 API：`POST /api/v1/email-management/scheduled/process`。

> ⚠️ 佇列有**兩個**處理器實作：排程用的
> `EmailAutomationService.process_scheduled_emails()`（支援 HTML）與 API 用的
> `EmailManagementService.process_due_emails()`（純文字）。兩者操作同一張表，
> 手動觸發 API 時信會變成純文字版。

---

## 7. 郵件測試模式

避免測試環境誤寄給真實使用者的保護機制，設定存在 `system_settings` 的
`email_test_mode` key。

**啟用後，每一封經過 `EmailService.send_email()` 的信都會：**

1. 收件人改成 `redirect_emails` 清單，**CC / BCC 全部清空**
2. 主旨加上 `[TEST] ` 前綴
3. 內文（純文字與 HTML）頂端插入黃色警示橫幅，標明原收件人
4. 加上 `X-Test-Mode` / `X-Test-Session-ID` / `X-Original-To` 等 header
5. 在 `email_test_mode_audit` 寫一筆攔截紀錄

**其他行為**

- 可設定 `expires_at`，過期後**自動關閉**並記錄 audit
- 啟用但沒設定 `redirect_emails` → 直接 `raise ValueError`，信不會寄出

**操作端點**

```
GET  /api/v1/email-management/test-mode/status
POST /api/v1/email-management/test-mode/enable
POST /api/v1/email-management/test-mode/disable
GET  /api/v1/email-management/test-mode/audit
```

> ⚠️ 副線的 `NotificationService._send_email_notification()`（fastapi_mail）
> **不經過測試模式攔截**。目前該路徑形同休眠（見 §8），但若日後啟用需特別注意。

---

## 8. 目前「不會」寄信的環節

盤點時發現以下項目「看起來會寄信、實際不會」，列出以免誤判為 bug。

### 8.1 三個關鍵節點沒有接上

`EmailAutomationService` 已寫好這三個觸發函式，但**全專案沒有任何呼叫點**：

| 函式 | 對應節點 |
|---|---|
| `trigger_professor_review_submitted()` | 教授送出審核 → 通知學院 |
| `trigger_college_review_submitted()` | 學院送出審核 |
| `trigger_final_result_decided()` | 最終錄取結果公布 |

連帶影響：種子規則「學院審核通知」即使被管理員手動啟用，
也**永遠不會被觸發**，因為它綁的 `professor_review_submitted` 事件沒人發。

同理，`ApplicationService.update_application_status()`（一般狀態變更）
與 `reviews.py`、`college_review.py` 等審核端點**完全沒有寄信邏輯**。
唯一會因狀態變更寄信的，是**批次**核准/退件（§4.5）。

### 8.2 EmailService 上的一整組未使用方法

`email_service.py` 有一組 `send_*_notification()` 便利方法，
除了被自己的測試呼叫外，**全部沒有生產程式碼在用**：

`send_application_submitted_notification` /
`send_professor_review_notification` / `send_college_review_notification` /
`send_whitelist_notification` / `send_deadline_reminder` /
`send_supplement_request` / `send_document_request_notification` /
`send_result_notifications` / `send_roster_notification` /
`send_to_professor`（已標 DEPRECATED）

實務上的意義：

- **白名單開放申請通知**（`whitelist-notification.tsx` 版型存在）→ 不會寄
- **造冊/獲獎名冊通知**（`roster-notification.tsx` 版型存在）→ 不會寄
- **審核結果通知**（`result-notification.tsx` 版型存在）→ 不會寄

`ScholarshipNotificationService` 也有三個無人呼叫的方法：
`send_application_submitted_notification`、`send_professor_review_request`、
`send_deadline_reminder_notifications`。

### 8.3 站內通知的 email 通道形同休眠

`NotificationService` 建立站內通知時，會依 `NotificationPreference` 決定通道。
`email_enabled` 的 model 預設雖是 `True`，但：

- **沒有任何 API 或前端可以建立 `NotificationPreference` 記錄**
- 查不到記錄時，`_get_user_preferred_channels()` 回傳 `[in_app]`

所以實際上**所有站內通知都只走站內**，那條 fastapi_mail 路徑不會執行。
（`roster_notification_service.py` 完全沒有 email 相關程式碼，純站內通知。）

### 8.4 其他

- **系統公告**（`POST /admin/announcements`）寫死 `send_email=False`，不寄信。
- **撤銷/停發的「復原」操作**不寄信。
- **造冊產生 / 確認分發**流程本身不寄信。

---

## 9. 除錯指引

### 「為什麼沒收到信？」的檢查順序

```
1. email_history 有紀錄嗎？
   ├─ 有，status = sent   → 系統已送出，查 SMTP server / 垃圾信匣
   ├─ 有，status = failed → 看 error_message，多半是 SMTP 設定或網路
   └─ 沒有 ↓

2. scheduled_emails 有紀錄嗎？
   ├─ status = pending   → email_processor 沒跑，或 scheduled_for 還沒到
   ├─ status = failed    → 看 last_error
   └─ 沒有 ↓

3. 測試模式開著嗎？
   GET /api/v1/email-management/test-mode/status
   → 開著的話信被轉到 redirect_emails 了

4. 對應的自動化規則存在且啟用嗎？
   SELECT name, trigger_event, template_key, is_active
   FROM email_automation_rules;
   → 很多事件預設沒有規則（見 §5.2）

5. condition_query 撈得到收件人嗎？
   backend log 搜尋：
   "No recipients found for rule"        → 收件人查詢回傳空集合
   "Found N recipients"                  → 有撈到，繼續往下看
   "Template not found"                  → template_key 對不到 email_templates
   "EMAIL AUTOMATION TRIGGERED"          → 事件確實有發出

6. 這個節點根本沒接寄信邏輯？
   → 對照 §8
```

### 常用查詢

```sql
-- 最近 20 封信的結果
SELECT sent_at, recipient_email, subject, status, error_message
FROM email_history ORDER BY sent_at DESC LIMIT 20;

-- 佇列中卡住的信
SELECT id, recipient_email, subject, status, scheduled_for, retry_count, last_error
FROM scheduled_emails WHERE status IN ('pending','failed')
ORDER BY scheduled_for;

-- 目前生效的自動化規則
SELECT name, trigger_event, template_key, delay_hours, is_active
FROM email_automation_rules ORDER BY trigger_event;
```

### 相關 log 關鍵字

| 關鍵字 | 意義 |
|---|---|
| `🚀 EMAIL AUTOMATION TRIGGERED` | 事件已發出 |
| `Found N active rules for '...'` | 比對到幾條規則 |
| `No recipients found for rule` | 收件人查詢空集合，信被略過 |
| `📬 Processing N scheduled emails` | 佇列處理器正在跑 |
| `Test mode: Redirecting email from ... to ...` | 測試模式攔截 |
| `❌ Failed to trigger automated submission emails` | 送出申請時寄信失敗（不影響申請） |

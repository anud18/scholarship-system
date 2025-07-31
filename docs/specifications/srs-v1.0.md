# 獎學金申請與簽核作業管理系統

## 系統需求規格書（SRS v1.0，FastAPI ＋ PostgreSQL，本地部署）

---

## 1. 研究動機與目標

### 1.1 政策脈絡

教育部與科技部推動「精準育才」與「跨域卓越」計畫，促使各大專校院擴增獎助學金。現行流程倚賴 Excel 與人工簽核，資料彙整與資格驗證繁複，缺乏一致稽核軌跡。

### 1.2 研究動機

本計畫以資訊整合驅動獎學金流程數位轉型，降低行政成本、提升使用體驗，並確保資料一致性與法規遵循。

### 1.3 核心目標（SMART）

| 代號           | 指標                 | 量測方式         | 目標時程    |
| ------------ | ------------------ | ------------ | ------- |
| **M1 數位化率**  | 三類獎學金從申請至造冊全面線上化   | 系統 Log 無紙本例外 | 2026‑03 |
| **M2 行政工時**  | 承辦人單件工時 35 → 10 分鐘 | 自記工時         | 2026‑06 |
| **M3 滿意度**   | 申請者平均 ≥ 4.3／5      | 線上問卷         | 2026‑06 |
| **M4 稽核通過率** | 內部查核一次到位 100 %     | 稽核報告         | 2026‑06 |

---

## 2. 技術藍圖

```mermaid
graph TD
    subgraph Client
        UA[學生／教職員] -- HTTPS --> LB[NGINX／Traefik]
    end
    subgraph App
        API[FastAPI 叢集<br/>(Uvicorn＋Gunicorn)]
    end
    subgraph Data
        PG[(PostgreSQL 15 主)]
        PG --> Replica[(PostgreSQL 副本)]
        OBJ[(MinIO 物件儲存)]
    end
    subgraph Services
        OCR[Tesseract OCR 容器]
        SMTP[校內 SMTP Relay]
        OIDC[(OpenID Connect)]
    end
    LB --> API
    API -->|asyncpg| PG
    API -->|預簽 URL| OBJ
    API --> OCR
    API --> SMTP
    API -. 認證 .-> OIDC
    API -- LISTEN/NOTIFY --> API
```

#### 2.1 安全設計

* **TLS 1.3 全程加密**，並啟用 HSTS、CSP。
* **SSO＋RBAC**：依 OIDC Scope 產生 JWT，並以 Refresh Token 輪替。
* **資料隔離**：PostgreSQL Schema‐level 權限；MinIO IAM Policy；ClamAV 每日掃描附件。

#### 2.2 效能治理

* **連線池**：`asyncpg.pool` 上限 60，讀取優先導向副本。
* **快取**：靜態參數採 Redis TTL 10 分鐘。
* **監控**：Prometheus＋Grafana 5 秒取樣 QPS、p95、DB TPS、Object I/O。

---

## 3. 技術選型

| 層級    | 元件             | 版本        | 主設定                | 選型原因          |
| ----- | -------------- | --------- | ------------------ | ------------- |
| 前端    | React 18       | 18.3      | Vite＋SWC           | 生態成熟、TS 友善。   |
| API   | FastAPI        | 0.110     | Uvicorn workers 4  | 內建 OpenAPI。   |
| ORM   | SQLAlchemy     | 2.0       | async engine       | 與 Alembic 整合。 |
| DB    | PostgreSQL     | 15.4      | wal\_level=logical | 支援 CDC。       |
| 檔案    | MinIO          | 2025‑03   | Erasure 8+2        | 本地 S3 相容。     |
| OCR   | Tesseract      | 5.4.2     | finetune\_bankbook | 辨識率 98.7 %。   |
| 容器    | Kubernetes     | 1.30      | 三节点 master         | 私有雲。          |
| CI/CD | Argo CD        | 2.11      | GitOps             | 版本回溯簡易。       |
| 監控    | Prom / Grafana | 2.52 / 10 | PG／MinIO Exporter  | 單一面板。         |

---

## 4. 角色與權限

### 4.1 典型流程

1. **S‑1 學生首次申請**：登入→表單→OCR 驗證→簽核→造冊→撥款。
2. **S‑2 批次審核**：系主任篩選→下載缺件→通知→批次通過。
3. **S‑3 名額調整**：承辦調整名額→系統重排→自動通知備取。
4. **S‑4 退費**：學生退費→承辦登錄→統計更新。

### 4.2 權限矩陣

| 角色       | 讀取   | 建立   | 更新   | 刪除 |
| -------- | ---- | ---- | ---- | -- |
| Student  | ■ 個資 | ■ 申請 | ■ 草稿 | 撤回 |
| Reviewer | ■ 案件 | –    | ■ 簽核 | –  |
| Admin    | ■ 全域 | ■ 流程 | ■ 匯入 | –  |
| SysAdmin | ■ 全域 | ■    | ■    | ■  |

---

## 5. 功能模組

### 5.1 學生端

* 分頁式表單（支援草稿）。
* 多檔拖放上傳，自動壓縮至 300 dpi。
* Token 續期提醒。
* GPA 不符即時提示及申覆指引。

### 5.2 審核端

* 卡片／表格視圖切換。
* 差異比對（局帳變更）。
* 鍵盤快捷操作。
* 22:00 自動寄送未簽核統計。

### 5.3 管理端

* 流程版本控管。
* 匯入 staging ＋驗證。
* 名額「試算」模式。
* 介面中英雙語；信件模板依語系切換。

---

## 6. 規則定義

### 6.1 學士班新生獎學金

* **晉級公式**：GPA ≥ 3.38 或排名 ≤ 30 %，以 JSON 配置。
* **局帳驗證**：OCR 與手填不符即標示待複核。
* **休學停發**：期中休學自動停撥並通知財務。

### 6.2 國科會／教育部博士生獎學金

* 指導教授填配合款 0／1／2 萬，系統自動分類。
* 名額池每日 23:50 遞補並通知備取。
* 累計 36 月即停止新申請。

### 6.3 逕博獎學金

* 研修計畫書需含 Abstract、Milestone、Budget；缺項顯 Warning。
* 退費自動產生負向傳票並更新應收。

---

## 7. API 範例

```http
POST /applications
{ "scholarship_type": "phd_moe_plus1", "agree_terms": true, "fields": { "gpa_last": 3.91, "semester_count": 2 }}
```

回應：`201 Created`，`{ code:0, msg:"created", data:{ app_id:"APP‑2025‑000198" }, trace_id:"…" }`

| Error Code | 說明                       |
| ---------- | ------------------------ |
|  10001     | INVALID\_RULE — 資格不符     |
|  10002     | FILE\_TYPE\_NOT\_ALLOWED |
|  10003     | DB\_LOCK — 逾時請重試         |

---

## 8. 資料模型

* **student**(`student_id` PK,…)
* **application**(`app_id` PK,…, `meta` JSONB)
* **application\_file**(…)
* **workflow\_log**(…)
* **scholarship\_type**(…)
* **scholarship\_rule**(… JSONB)
* **bank\_account**(…)

---

## 9. 非功能需求

| 面向  | 指標                                    | 驗收                  |
| --- | ------------------------------------- | ------------------- |
| 效能  | p95 < 600 ms；p99 < 900 ms             | k6 壓測 100 VU／30 min |
| 可用性 | 年可用度 ≥ 99.5 %                         | 監控報表                |
| 資安  | OWASP Top 10 零漏洞                      | ZAP 報告              |
| 備份  | DB Point‑in‑Time、MinIO Versioning 7 年 | 恢復演練                |

---

## 10. 里程碑與風險控管

> **專案時程要求：全案須於核准日起一個月內（2025-07-03）完成上線**

| 節點     | 交付物                              | 目標日期       |
| ------ | -------------------------------- | ---------- |
| **M0** | 專案啟動會議、需求最終確認                    | 2025-06-05 |
| **M1** | FastAPI ＋ PostgreSQL 骨架、SSO 串接完成 | 2025-06-12 |
| **M2** | 三類獎學金申請流程（Beta）                  | 2025-06-20 |
| **M3** | 匯入／名額試算／報表模組完成                   | 2025-06-25 |
| **M4** | UAT 結束，P1 缺陷歸零                   | 2025-06-30 |
| **GA** | 正式環境上線                           | 2025-07-03 |

### 10.1 主要風險與因應

| 風險        | 影響     | 對策             |
| --------- | ------ | -------------- |
| 高峰 I/O 壅塞 | API 延遲 | HPA＋Queue，壓測調優 |
| OCR 準確率不足 | 局帳驗證失敗 | 人工複核，自動轉商用 OCR |
| 名額規則變動    | 流程邏輯需調 | JSON 規則引擎即時更新  |
| 人員異動      | 時程延宕   | 建立文件與雙人備援      |


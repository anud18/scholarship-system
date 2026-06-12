# PII 加密金鑰保存與輪替 Runbook（G27 / #989）

> 對象:`applications.student_data.std_pid`(身分證字號)以 AES-256-GCM
> envelope 加密,信封內嵌**金鑰版本**(`v1`, `v2`, …),由
> `PII_ENCRYPTION_KEYS`(JSON map `{版本: base64url 32-byte key}`)解密。
> 解密**沒有 fallback**:信封指到的版本不在 map 裡 → 該筆資料永久不可讀。
> 這是刻意設計(防默默用錯金鑰),代價是金鑰管理必須遵守本文件。

## 鐵律

1. **舊版本金鑰在「該版本最後一筆資料的保存年限屆滿」前,絕不從
   `PII_ENCRYPTION_KEYS` 移除。** 申請紀錄保存年限以校方核定之檔案保存年
   限區分表為準(涉撥款者建議以 10 年計,見 #995 報告第 3 節)。實務上:
   除非完成全量 re-encrypt 並驗證,否則**永不移除舊 key**。
2. 金鑰只能「新增版本」與「切換 active 版本」,不可原地改值。
3. `PII_ENCRYPTION_KEYS` 的每次變更(staging/production secrets)都要在
   變更紀錄(GitHub secret 變更 + 部署 PR)留下誰、何時、為什麼。

## 輪替程序(新增 v(n+1) 並汰換 v(n))

1. 產生新金鑰:
   ```bash
   python -c 'import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode())'
   ```
2. 更新 secret 為**新舊並存**:
   `PII_ENCRYPTION_KEYS={"v1":"<old>","v2":"<new>"}`、
   `PII_ENCRYPTION_ACTIVE_VERSION=v2`,重新部署。
   此時:新寫入用 v2,舊資料仍以 v1 解密 — 系統正常。
3. **Dry-run 驗證全量可解密**(輪替前的安全閥):
   ```bash
   docker exec scholarship_backend_staging \
       python scripts/rotate_pii_keys.py --dry-run
   ```
   任何一筆解密失敗 → 停止,先調查(代表已存在用未知版本加密的資料)。
4. 執行 re-encrypt(冪等、可重跑):
   ```bash
   docker exec scholarship_backend_staging \
       python scripts/rotate_pii_keys.py
   ```
5. 驗證:再跑一次 `--dry-run`,確認所有信封版本 == active 版本。
6. **僅在第 5 步全綠、且確認備份(pg_dump 歸檔)中的舊版本資料也已超過
   保存年限或另行 re-encrypt 後**,才可從 secret 移除 v1。
   注意:S3 異地備份裡的 dump 仍是 v1 加密 — 移除 v1 後那些備份內的
   std_pid 等同銷毀。若備份保存年限未到,**v1 必須保留**。

## 回滾

把 `PII_ENCRYPTION_ACTIVE_VERSION` 設回前一版本並重跑
`rotate_pii_keys.py`(腳本以信封內嵌版本判斷來源,冪等)。

## 與稽核的關係

- audit_logs 內的 PII 已在寫入時 `[REDACTED]`(`redact_dict_pii`),不受
  金鑰輪替影響 — 金鑰遺失只影響本文資料(student_data),不影響稽核軌跡
  的可讀性。
- 年度稽核(內稽/會計)若需調閱 3+ 年前申請的身分證字號,前提即是本文件
  的鐵律 1 有被遵守。

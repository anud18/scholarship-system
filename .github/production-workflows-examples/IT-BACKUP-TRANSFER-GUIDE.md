# IT 部門備份搬移指南

## 📋 概述

此文檔為 IT 人員提供 Scholarship System production 環境備份搬移的操作指南。

### 重要資訊

- **備份位置**: `/var/backups/scholarship-system/`
- **DB VM 限制**: Database VM 無法連接外網
- **自動清理**: Server 上的備份會保留 7 天後自動刪除
- **備份頻率**:
  - 每日 02:00 UTC 完整備份
  - 每 6 小時增量備份

## 📁 備份目錄結構

```
/var/backups/scholarship-system/
├── database/
│   ├── 20250125/
│   │   ├── database-backup-20250125-020015.sql.gz
│   │   └── database-backup-20250125-020015.sql.gz.sha256
│   ├── 20250126/
│   └── 20250127/
├── files/
│   ├── 20250125/
│   │   ├── files-backup-20250125-020045.tar.gz
│   │   └── files-backup-20250125-020045.tar.gz.sha256
│   ├── 20250126/
│   └── 20250127/
└── backup-manifest-YYYYMMDD.txt  # 備份清單檔案
```

## 🔍 每日檢查清單

### 1. 查看備份清單

```bash
# SSH 到 production server
ssh production-server

# 查看最新的備份清單
TODAY=$(date +%Y%m%d)
cat /var/backups/scholarship-system/backup-manifest-${TODAY}.txt
```

### 2. 驗證備份完整性

```bash
# 驗證資料庫備份 checksum
cd /var/backups/scholarship-system/database/${TODAY}
sha256sum -c database-backup-*.sha256

# 驗證檔案備份 checksum
cd /var/backups/scholarship-system/files/${TODAY}
sha256sum -c files-backup-*.sha256
```

**預期輸出**:
```
database-backup-20250125-020015.sql.gz: OK
files-backup-20250125-020045.tar.gz: OK
```

⚠️ **如果 checksum 驗證失敗**: 請勿搬移該備份，聯繫系統管理員重新備份。

### 3. 檢查備份檔案大小

```bash
# 查看今日備份大小
cd /var/backups/scholarship-system
du -sh database/${TODAY}
du -sh files/${TODAY}

# 查看總備份大小
du -sh .
```

**正常範圍** (僅供參考，實際大小會隨資料成長):
- Database: 50 MB - 500 MB (壓縮後)
- Files: 100 MB - 1 GB

⚠️ **異常情況**:
- 檔案大小 < 10 MB: 可能備份失敗
- 檔案大小突然增加 10 倍: 需要檢查
- 檔案不存在: 備份 workflow 可能失敗

## 📤 搬移備份到外部儲存

### 方法 A: 使用 rsync (推薦)

```bash
#!/bin/bash
# backup-transfer.sh

# 設定變數
BACKUP_SOURCE="/var/backups/scholarship-system"
BACKUP_DEST="your-backup-server:/backups/scholarship-system"
TODAY=$(date +%Y%m%d)

# 驗證 checksum
echo "驗證備份完整性..."
cd ${BACKUP_SOURCE}/database/${TODAY}
sha256sum -c database-backup-*.sha256 || exit 1

cd ${BACKUP_SOURCE}/files/${TODAY}
sha256sum -c files-backup-*.sha256 || exit 1

# 搬移資料庫備份
echo "搬移資料庫備份..."
rsync -avz --progress \
  ${BACKUP_SOURCE}/database/${TODAY}/ \
  ${BACKUP_DEST}/database/${TODAY}/

# 搬移檔案備份
echo "搬移檔案備份..."
rsync -avz --progress \
  ${BACKUP_SOURCE}/files/${TODAY}/ \
  ${BACKUP_DEST}/files/${TODAY}/

# 搬移清單檔案
echo "搬移備份清單..."
rsync -avz --progress \
  ${BACKUP_SOURCE}/backup-manifest-${TODAY}.txt \
  ${BACKUP_DEST}/

echo "✅ 備份搬移完成"
```

### 方法 B: 使用 scp

```bash
#!/bin/bash
# 設定變數
TODAY=$(date +%Y%m%d)
BACKUP_SOURCE="/var/backups/scholarship-system"
BACKUP_SERVER="backup-server"
BACKUP_DEST="/backups/scholarship-system"

# 搬移資料庫備份
scp -r ${BACKUP_SOURCE}/database/${TODAY} \
  ${BACKUP_SERVER}:${BACKUP_DEST}/database/

# 搬移檔案備份
scp -r ${BACKUP_SOURCE}/files/${TODAY} \
  ${BACKUP_SERVER}:${BACKUP_DEST}/files/

# 搬移清單
scp ${BACKUP_SOURCE}/backup-manifest-${TODAY}.txt \
  ${BACKUP_SERVER}:${BACKUP_DEST}/
```

### 方法 C: 掛載網路磁碟 (NFS/CIFS)

```bash
# 掛載網路磁碟
sudo mount -t nfs backup-server:/backups /mnt/backup

# 複製備份
TODAY=$(date +%Y%m%d)
cp -r /var/backups/scholarship-system/database/${TODAY} \
  /mnt/backup/scholarship-system/database/

cp -r /var/backups/scholarship-system/files/${TODAY} \
  /mnt/backup/scholarship-system/files/

# 卸載
sudo umount /mnt/backup
```

## ✅ 搬移後驗證

### 1. 驗證檔案已成功複製

```bash
# 在備份 server 上驗證 checksum
ssh backup-server
cd /backups/scholarship-system/database/${TODAY}
sha256sum -c database-backup-*.sha256

cd /backups/scholarship-system/files/${TODAY}
sha256sum -c files-backup-*.sha256
```

### 2. 比較檔案大小

```bash
# 在 production server
du -sh /var/backups/scholarship-system/database/${TODAY}
du -sh /var/backups/scholarship-system/files/${TODAY}

# 在 backup server (應該相同)
ssh backup-server
du -sh /backups/scholarship-system/database/${TODAY}
du -sh /backups/scholarship-system/files/${TODAY}
```

### 3. 記錄備份完成

建議在備份系統中記錄:
- ✅ 備份日期: 2025-01-25
- ✅ 搬移時間: 2025-01-25 10:30
- ✅ 檔案大小: DB 250 MB, Files 500 MB
- ✅ Checksum: 已驗證
- ✅ 搬移人員: IT Name

## 🔄 自動化腳本範例

### 完整自動化搬移腳本

```bash
#!/bin/bash
#
# scholarship-backup-transfer.sh
# 自動搬移 Scholarship System 備份到外部儲存
#
# 使用方式: ./scholarship-backup-transfer.sh [YYYYMMDD]
# 例如: ./scholarship-backup-transfer.sh 20250125
#       ./scholarship-backup-transfer.sh  # 預設使用今天

set -e  # 遇到錯誤立即停止

# ============================================================================
# 設定
# ============================================================================

BACKUP_SOURCE="/var/backups/scholarship-system"
BACKUP_SERVER="backup-server"
BACKUP_DEST="/backups/scholarship-system"

# SSH 設定 (如果需要)
# SSH_KEY="/path/to/key"
# SSH_OPTS="-i ${SSH_KEY}"

# 日期設定
if [ -n "$1" ]; then
  TARGET_DATE="$1"
else
  TARGET_DATE=$(date +%Y%m%d)
fi

# 日誌
LOG_FILE="/var/log/scholarship-backup-transfer.log"

# ============================================================================
# 函數
# ============================================================================

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
  log "❌ ERROR: $1"
  exit 1
}

verify_checksum() {
  local dir="$1"
  local pattern="$2"

  log "驗證 $dir 的 checksum..."
  cd "$dir" || error "無法進入目錄: $dir"

  if ! sha256sum -c ${pattern}.sha256; then
    error "Checksum 驗證失敗: $dir"
  fi

  log "✅ Checksum 驗證通過"
}

# ============================================================================
# 主程式
# ============================================================================

log "========================================="
log "開始備份搬移流程"
log "目標日期: ${TARGET_DATE}"
log "========================================="

# 1. 檢查來源目錄是否存在
if [ ! -d "${BACKUP_SOURCE}/database/${TARGET_DATE}" ]; then
  error "資料庫備份目錄不存在: ${BACKUP_SOURCE}/database/${TARGET_DATE}"
fi

if [ ! -d "${BACKUP_SOURCE}/files/${TARGET_DATE}" ]; then
  error "檔案備份目錄不存在: ${BACKUP_SOURCE}/files/${TARGET_DATE}"
fi

# 2. 驗證來源檔案的 checksum
log "步驟 1/4: 驗證來源備份完整性..."
verify_checksum "${BACKUP_SOURCE}/database/${TARGET_DATE}" "database-backup-*"
verify_checksum "${BACKUP_SOURCE}/files/${TARGET_DATE}" "files-backup-*"

# 3. 搬移資料庫備份
log "步驟 2/4: 搬移資料庫備份..."
rsync -avz --progress \
  ${BACKUP_SOURCE}/database/${TARGET_DATE}/ \
  ${BACKUP_SERVER}:${BACKUP_DEST}/database/${TARGET_DATE}/ \
  || error "資料庫備份搬移失敗"

# 4. 搬移檔案備份
log "步驟 3/4: 搬移檔案備份..."
rsync -avz --progress \
  ${BACKUP_SOURCE}/files/${TARGET_DATE}/ \
  ${BACKUP_SERVER}:${BACKUP_DEST}/files/${TARGET_DATE}/ \
  || error "檔案備份搬移失敗"

# 5. 搬移清單檔案
if [ -f "${BACKUP_SOURCE}/backup-manifest-${TARGET_DATE}.txt" ]; then
  log "搬移備份清單..."
  rsync -avz \
    ${BACKUP_SOURCE}/backup-manifest-${TARGET_DATE}.txt \
    ${BACKUP_SERVER}:${BACKUP_DEST}/ \
    || log "⚠️  清單檔案搬移失敗 (非致命錯誤)"
fi

# 6. 驗證目的地的 checksum (在 backup server 上)
log "步驟 4/4: 驗證搬移後的備份完整性..."
ssh ${BACKUP_SERVER} bash <<EOF
  set -e
  cd ${BACKUP_DEST}/database/${TARGET_DATE}
  sha256sum -c database-backup-*.sha256 || exit 1

  cd ${BACKUP_DEST}/files/${TARGET_DATE}
  sha256sum -c files-backup-*.sha256 || exit 1
EOF

if [ $? -eq 0 ]; then
  log "✅ 目的地 checksum 驗證通過"
else
  error "目的地 checksum 驗證失敗"
fi

# 7. 記錄成功
log "========================================="
log "✅ 備份搬移成功完成"
log "日期: ${TARGET_DATE}"
log "========================================="

# 可選: 發送通知
# mail -s "Scholarship Backup Transfer Success" admin@example.com <<< "Backup for ${TARGET_DATE} transferred successfully."
```

### Cron 排程範例

```bash
# 編輯 crontab
crontab -e

# 每天早上 8:00 自動執行備份搬移 (備份在 02:00 完成)
0 8 * * * /usr/local/bin/scholarship-backup-transfer.sh >> /var/log/scholarship-backup-transfer.log 2>&1
```

## 🚨 故障排除

### 問題 1: Checksum 驗證失敗

**原因**: 備份檔案損壞或傳輸過程中出現錯誤

**解決**:
```bash
# 1. 重新執行備份 (在 GitHub Actions)
# 2. 或手動創建備份
ssh production-server
cd /opt/scholarship-system
docker compose exec -T postgres pg_dump \
  -U scholarship_user \
  -d scholarship_db \
  --format=custom \
  --compress=9 > /var/backups/manual-backup-$(date +%Y%m%d-%H%M%S).sql
```

### 問題 2: 磁碟空間不足

**檢查**:
```bash
# 檢查 production server 空間
df -h /var/backups

# 檢查 backup server 空間
ssh backup-server df -h /backups
```

**解決**:
```bash
# 刪除舊的備份 (謹慎操作)
cd /var/backups/scholarship-system/database
ls -lt | tail -n +8  # 列出 7 天前的備份
# 手動刪除確認不需要的舊備份
```

### 問題 3: 網路連線問題

**測試連線**:
```bash
# Ping backup server
ping backup-server

# 測試 SSH
ssh backup-server echo "Connection OK"

# 測試 rsync
rsync --dry-run -avz /tmp/test backup-server:/tmp/
```

### 問題 4: 權限問題

**檢查權限**:
```bash
# Production server
ls -la /var/backups/scholarship-system/database/${TODAY}/

# Backup server
ssh backup-server ls -la /backups/scholarship-system/
```

**修正權限**:
```bash
# 確保備份檔案可讀
chmod 640 /var/backups/scholarship-system/database/${TODAY}/*
chmod 640 /var/backups/scholarship-system/files/${TODAY}/*
```

## 📞 聯繫資訊

遇到問題時的聯繫方式:

1. **自動化問題** (GitHub Actions workflow):
   - 查看: GitHub Actions → Backup Production Data
   - 聯繫: DevOps 團隊

2. **Database 問題**:
   - 聯繫: Database 管理員

3. **備份儲存問題**:
   - 聯繫: IT 基礎設施團隊

## 📚 相關文檔

- Production Workflows 範例: `.github/production-workflows-examples/README.md`
- Backup Workflow: `.github/production-workflows-examples/backup.yml`
- 還原指南: (待建立)

## 🔐 安全注意事項

1. ✅ **備份包含敏感資料**: 確保搬移過程使用加密傳輸 (SSH/rsync)
2. ✅ **Checksum 驗證**: 每次搬移前後都要驗證
3. ✅ **訪問控制**: 備份檔案權限應設為 640 (僅 owner 和 group 可讀)
4. ✅ **日誌記錄**: 記錄每次搬移操作
5. ✅ **定期測試還原**: 每月至少測試一次備份還原流程

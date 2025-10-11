# Nginx 監控功能測試指南

## 📝 修改概述

已對以下配置檔案添加監控支援：
- `nginx.conf` (開發環境)
- `nginx/nginx.prod.conf` (生產環境)
- `nginx/nginx.staging.conf` (測試環境)

### 新增功能
1. ✅ JSON 結構化日誌格式
2. ✅ Nginx stub_status endpoint (`/nginx_status`)
3. ✅ 請求時間指標 (`request_time`, `upstream_response_time`)
4. ✅ 請求追蹤 ID (`X-Request-ID` header)

---

## 🧪 驗證步驟

### 1. 語法檢查

在容器外驗證（推薦）：
```bash
# 使用 nginx -t 檢查配置語法
docker run --rm -v $(pwd)/nginx.conf:/etc/nginx/nginx.conf:ro nginx:alpine nginx -t
docker run --rm -v $(pwd)/nginx/nginx.prod.conf:/etc/nginx/nginx.conf:ro nginx:alpine nginx -t
docker run --rm -v $(pwd)/nginx/nginx.staging.conf:/etc/nginx/nginx.conf:ro nginx:alpine nginx -t
```

如果服務已運行，在容器內驗證：
```bash
# 開發環境
docker exec scholarship_nginx nginx -t

# 生產環境
docker exec scholarship_nginx_prod nginx -t

# 測試環境
docker exec scholarship_nginx_staging nginx -t
```

預期輸出：
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

---

### 2. 重新載入配置

⚠️ **注意**: 只在語法檢查通過後執行此步驟

```bash
# 開發環境
docker exec scholarship_nginx nginx -s reload

# 生產環境
docker exec scholarship_nginx_prod nginx -s reload

# 測試環境
docker exec scholarship_nginx_staging nginx -s reload
```

或使用 docker-compose：
```bash
# 開發環境
docker-compose restart nginx

# 生產環境
docker-compose -f docker-compose.prod.yml restart nginx

# 測試環境
docker-compose -f docker-compose.staging.yml restart nginx
```

---

### 3. 測試 Stub Status Endpoint

#### 本地測試（開發環境）
```bash
curl http://localhost/nginx_status

# 預期輸出:
# Active connections: 2
# server accepts handled requests
#  10 10 15
# Reading: 0 Writing: 1 Waiting: 1
```

#### 容器內測試
```bash
# 開發環境
docker exec scholarship_nginx curl http://localhost/nginx_status

# 生產環境（HTTPS）
docker exec scholarship_nginx_prod curl -k https://localhost/nginx_status

# 測試環境（HTTPS）
docker exec scholarship_nginx_staging curl -k https://localhost/nginx_status
```

#### 外部訪問（應該被拒絕）
```bash
# 從主機訪問（應該返回 403 Forbidden）
curl http://localhost/nginx_status
# 預期: 403 Forbidden

# 這是預期行為，因為只允許內部網路訪問
```

---

### 4. 驗證 JSON 日誌格式

#### 觸發請求
```bash
# 發送測試請求
curl -v http://localhost/api/v1/health
# 或
curl -v http://localhost/
```

#### 查看日誌
```bash
# 開發環境
docker exec scholarship_nginx tail -5 /var/log/nginx/access.log

# 生產環境
docker exec scholarship_nginx_prod tail -5 /var/log/nginx/access.log

# 測試環境
docker exec scholarship_nginx_staging tail -5 /var/log/nginx/access.log
```

#### 驗證 JSON 格式
```bash
# 使用 jq 解析最新日誌
docker exec scholarship_nginx tail -1 /var/log/nginx/access.log | jq '.'

# 預期輸出（格式化的 JSON）:
# {
#   "time_local": "11/Oct/2025:07:00:00 +0000",
#   "time_iso8601": "2025-10-11T07:00:00+00:00",
#   "remote_addr": "172.20.0.1",
#   "remote_user": "",
#   "request": "GET /api/v1/health HTTP/1.1",
#   "request_method": "GET",
#   "request_uri": "/api/v1/health",
#   "status": 200,
#   "body_bytes_sent": 123,
#   "request_time": 0.023,
#   "upstream_response_time": "0.019",
#   "upstream_addr": "172.20.0.5:8000",
#   "upstream_status": "200",
#   "http_referrer": "",
#   "http_user_agent": "curl/7.81.0",
#   "http_x_forwarded_for": "",
#   "request_id": "abc123def456..."
# }
```

---

### 5. 驗證請求時間指標

檢查日誌中的性能指標：
```bash
# 提取請求時間和 upstream 響應時間
docker exec scholarship_nginx sh -c "tail -10 /var/log/nginx/access.log | jq -r '[.request_uri, .request_time, .upstream_response_time] | @tsv'"

# 預期輸出（每行格式: URL | 總時間 | Upstream 時間）:
# /api/v1/health      0.023   0.019
# /                   0.145   0.142
# /api/v1/users       0.067   0.063
```

找出慢請求（> 1 秒）：
```bash
docker exec scholarship_nginx sh -c "tail -100 /var/log/nginx/access.log | jq 'select(.request_time > 1) | {uri: .request_uri, time: .request_time}'"
```

---

### 6. 驗證 X-Request-ID Header

#### 檢查 Nginx 發送的 Header
```bash
# 使用 httpbin 測試（如果有）
curl -v http://localhost/api/v1/health 2>&1 | grep -i "x-request-id"

# 或檢查後端日誌
docker logs scholarship_backend --tail 10 | grep "X-Request-ID"
```

#### 在後端驗證（如果後端記錄 headers）
```bash
# 發送請求並記錄 Request ID
REQUEST_ID=$(docker exec scholarship_nginx sh -c "tail -1 /var/log/nginx/access.log | jq -r '.request_id'")
echo "Last Request ID: $REQUEST_ID"

# 在後端日誌中搜尋相同的 Request ID
docker logs scholarship_backend | grep "$REQUEST_ID"
```

---

### 7. 整合測試腳本

創建並運行完整的測試腳本：

```bash
#!/bin/bash
# 檔案: test_nginx_monitoring.sh

echo "🧪 Nginx Monitoring Features Test"
echo "=================================="

# 顏色定義
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 測試計數器
TESTS=0
PASSED=0
FAILED=0

test_syntax() {
    TESTS=$((TESTS+1))
    echo -e "\n${YELLOW}[Test $TESTS]${NC} Nginx Configuration Syntax"
    if docker exec scholarship_nginx nginx -t 2>&1 | grep -q "syntax is ok"; then
        echo -e "${GREEN}✓ PASSED${NC}: Configuration syntax is valid"
        PASSED=$((PASSED+1))
    else
        echo -e "${RED}✗ FAILED${NC}: Configuration syntax error"
        FAILED=$((FAILED+1))
    fi
}

test_stub_status() {
    TESTS=$((TESTS+1))
    echo -e "\n${YELLOW}[Test $TESTS]${NC} Nginx Stub Status Endpoint"
    if docker exec scholarship_nginx curl -s http://localhost/nginx_status | grep -q "Active connections"; then
        echo -e "${GREEN}✓ PASSED${NC}: stub_status endpoint is working"
        PASSED=$((PASSED+1))
    else
        echo -e "${RED}✗ FAILED${NC}: stub_status endpoint not responding"
        FAILED=$((FAILED+1))
    fi
}

test_json_logs() {
    TESTS=$((TESTS+1))
    echo -e "\n${YELLOW}[Test $TESTS]${NC} JSON Log Format"

    # 發送測試請求
    curl -s http://localhost/api/v1/health > /dev/null
    sleep 1

    # 檢查最新日誌是否為 JSON 格式
    if docker exec scholarship_nginx sh -c "tail -1 /var/log/nginx/access.log | jq -e '.request_time' > /dev/null 2>&1"; then
        echo -e "${GREEN}✓ PASSED${NC}: Logs are in JSON format"
        PASSED=$((PASSED+1))
    else
        echo -e "${RED}✗ FAILED${NC}: Logs are not in JSON format"
        FAILED=$((FAILED+1))
    fi
}

test_request_time() {
    TESTS=$((TESTS+1))
    echo -e "\n${YELLOW}[Test $TESTS]${NC} Request Time Metrics"

    # 發送測試請求
    curl -s http://localhost/ > /dev/null
    sleep 1

    # 檢查請求時間字段
    if docker exec scholarship_nginx sh -c "tail -1 /var/log/nginx/access.log | jq -e '.request_time != null and .upstream_response_time != null' > /dev/null 2>&1"; then
        REQUEST_TIME=$(docker exec scholarship_nginx sh -c "tail -1 /var/log/nginx/access.log | jq -r '.request_time'")
        UPSTREAM_TIME=$(docker exec scholarship_nginx sh -c "tail -1 /var/log/nginx/access.log | jq -r '.upstream_response_time'")
        echo -e "${GREEN}✓ PASSED${NC}: Request time tracked (Total: ${REQUEST_TIME}s, Upstream: ${UPSTREAM_TIME}s)"
        PASSED=$((PASSED+1))
    else
        echo -e "${RED}✗ FAILED${NC}: Request time metrics not found"
        FAILED=$((FAILED+1))
    fi
}

test_request_id() {
    TESTS=$((TESTS+1))
    echo -e "\n${YELLOW}[Test $TESTS]${NC} Request ID Header"

    # 發送測試請求
    curl -s http://localhost/api/v1/health > /dev/null
    sleep 1

    # 檢查 request_id 字段
    if REQUEST_ID=$(docker exec scholarship_nginx sh -c "tail -1 /var/log/nginx/access.log | jq -r '.request_id' 2>/dev/null") && [ -n "$REQUEST_ID" ] && [ "$REQUEST_ID" != "null" ]; then
        echo -e "${GREEN}✓ PASSED${NC}: Request ID tracked (ID: ${REQUEST_ID:0:16}...)"
        PASSED=$((PASSED+1))
    else
        echo -e "${RED}✗ FAILED${NC}: Request ID not found in logs"
        FAILED=$((FAILED+1))
    fi
}

# 執行所有測試
test_syntax
test_stub_status
test_json_logs
test_request_time
test_request_id

# 總結
echo -e "\n=================================="
echo -e "📊 Test Results Summary"
echo -e "=================================="
echo -e "Total Tests:  $TESTS"
echo -e "${GREEN}Passed:       $PASSED${NC}"
if [ $FAILED -gt 0 ]; then
    echo -e "${RED}Failed:       $FAILED${NC}"
else
    echo -e "Failed:       $FAILED"
fi
echo -e "Success Rate: $(awk "BEGIN {printf \"%.1f\", ($PASSED/$TESTS)*100}")%"

if [ $FAILED -eq 0 ]; then
    echo -e "\n${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "\n${RED}✗ Some tests failed. Please review the errors above.${NC}"
    exit 1
fi
```

運行測試：
```bash
chmod +x test_nginx_monitoring.sh
./test_nginx_monitoring.sh
```

---

## 🔍 監控整合驗證

### Prometheus Nginx Exporter 測試

1. 部署 nginx-exporter（參考 Issue #94）
2. 驗證 metrics 端點：
```bash
curl http://localhost:9113/metrics | grep nginx_
```

### Grafana Alloy 日誌收集測試

1. 配置 Alloy 指向 nginx JSON 日誌
2. 在 Loki 查詢日誌：
```logql
{job="nginx"} | json
```

---

## 🚨 常見問題排除

### 問題 1: nginx -t 失敗
**症狀**: `nginx: configuration file /etc/nginx/nginx.conf test failed`

**解決方案**:
```bash
# 查看詳細錯誤
docker exec scholarship_nginx nginx -t

# 檢查語法錯誤位置
docker exec scholarship_nginx nginx -T 2>&1 | grep -A 5 "error"
```

### 問題 2: /nginx_status 返回 404
**症狀**: `curl http://localhost/nginx_status` 返回 404

**解決方案**:
```bash
# 確認配置已重新載入
docker exec scholarship_nginx nginx -s reload

# 檢查 location 區塊是否存在
docker exec scholarship_nginx grep -A 5 "nginx_status" /etc/nginx/nginx.conf
```

### 問題 3: 日誌不是 JSON 格式
**症狀**: 日誌仍然是純文本格式

**解決方案**:
```bash
# 檢查 log_format 定義
docker exec scholarship_nginx grep -A 10 "log_format json_combined" /etc/nginx/nginx.conf

# 檢查 access_log 指令
docker exec scholarship_nginx grep "access_log" /etc/nginx/nginx.conf

# 重啟 nginx（不是 reload）
docker-compose restart nginx
```

### 問題 4: request_time 始終為 null
**症狀**: JSON 日誌中 `request_time` 欄位為 null

**解決方案**:
```bash
# 檢查是否使用正確的變數名稱（無 $ 前綴在 JSON 定義中是錯誤的）
# 正確: "request_time":$request_time
# 錯誤: "request_time":"$request_time"

# 檢查 log_format 定義
docker exec scholarship_nginx nginx -T | grep -A 20 "log_format json_combined"
```

---

## 📊 預期監控效益

### 指標可視化
- **Request Rate**: 每秒請求數
- **Error Rate**: 4xx/5xx 錯誤比例
- **Response Time**: P50/P95/P99 延遲
- **Upstream Performance**: 後端服務響應時間

### 日誌追蹤
- **Request Tracing**: 通過 request_id 追蹤請求鏈路
- **Slow Query Detection**: 識別 > 1s 的慢請求
- **Error Analysis**: JSON 格式便於結構化查詢

---

## ✅ 驗證完成確認清單

- [ ] 所有配置檔案語法檢查通過
- [ ] Nginx 服務成功重新載入
- [ ] `/nginx_status` endpoint 可訪問
- [ ] 日誌格式為有效的 JSON
- [ ] `request_time` 和 `upstream_response_time` 有值
- [ ] `request_id` 在每個請求中生成
- [ ] X-Request-ID header 傳遞到後端
- [ ] 監控系統（如 Prometheus）可抓取 metrics

---

## 📚 相關文件

- [GitHub Issue #94](https://github.com/jotpalch/scholarship-system/issues/94) - 完整監控系統實施計畫
- [Nginx stub_status 文檔](http://nginx.org/en/docs/http/ngx_http_stub_status_module.html)
- [Nginx Prometheus Exporter](https://github.com/nginxinc/nginx-prometheus-exporter)
- [Grafana Alloy Documentation](https://grafana.com/docs/alloy/latest/)

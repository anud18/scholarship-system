---
name: check-log
description: Investigate PRODUCTION logs (ss.aa.nycu.edu.tw Grafana → Loki) for a stated purpose — e.g. "看王小明 (<學號>) log 裡面有沒有相關 error", "昨天下午 500 是什麼", "匯出造冊失敗的 traceback". Finds the person's footprint by 學號/user id, correlates their requests (client IP, time windows) with backend errors, and reports findings in zh-TW. Use whenever the user asks to check prod logs, Grafana, Loki, or why a specific user/feature failed in production.
argument-hint: "[用途，例如：看王小明 (<學號>) log 裡面有沒有相關 error]"
---

# /check-log — production log investigation

用途 (purpose): **$ARGUMENTS**

If the purpose is empty, ask what to look for (who / which feature / roughly when) and stop.

Answer the purpose with evidence from the logs. Report in **Traditional Chinese**; quote the
decisive log lines (timestamps in UTC **and** Taipei time, UTC+8).

## Access

Credentials are in `~/.ssaa.env` (`username`, `password`, `grafana_link` =
`https://ss.aa.nycu.edu.tw/monitoring`). **Never print the file or the password.**
Always go through the helper — it reads the env file, calls the Grafana datasource proxy,
and handles the gotchas below:

```bash
H=.claude/skills/check-log/scripts/loki.py      # run from the repo root
python3 -I $H query '<LogQL>' [--since 24h | --start 2026-01-01T09:00 --end 2026-01-01T10:00] [--limit 500] [--full] [--raw]
python3 -I $H labels [container]                 # list labels / values
```

- Times passed to `--start/--end` are **UTC** when no offset is given (`+08:00` for Taipei).
- `--full` prints whole tracebacks (default: last line only). `--raw` disables dedupe/formatting.
- A `(hit --limit …)` note on stderr means results were truncated — narrow the window or raise `--limit` (max 5000).
- Do **not** use raw `curl`: the rtk hook rewrites curl output into a JSON schema stub.

## What is in Loki

Only `Loki (Production)` has data (staging/dev datasources are empty). Retention ≈ 30 days,
so `--since` beyond `30d` returns nothing extra. Labels: `container`, `environment=prod`,
`service_name`, `stream` (stdout/stderr), `vm` (`ap-vm`, `db-vm`).

| container | content |
|---|---|
| `/scholarship_backend_prod` | FastAPI. JSON lines `{"timestamp","level","name","message","exception"}` + uvicorn access lines (`INFO: … "GET /api/… HTTP/1.1" 500`) |
| `/scholarship_nginx_prod` | JSON access log: `remote_addr`, `request`, `status`, `request_time`, `http_user_agent`, `upstream_status` |
| `/scholarship_frontend_prod` | Next.js server output |
| `/scholarship_postgres_prod`, `/scholarship_redis_prod` | DB / cache |

Always select app containers explicitly, e.g. `{container=~"/scholarship_(backend|nginx|frontend)_prod"}`,
never bare `{environment="prod"}`: our own Grafana queries are logged by `monitoring_*` containers
and nginx (`/monitoring/…`), and they echo the search string so they fill the result limit.
Add `!= "/monitoring/"` on nginx queries. The helper also drops these, but only after the limit is applied.

Things the helper already does: drops the backend's plain-text duplicate of every JSON log line
and its per-line traceback fragments; **redacts session JWTs** in `/auth/sso-callback?token=…`
to `<jwt sub=<user id> nycu_id=<學號> role=…>`.

## How users show up in the logs

Logs carry **學號 / nycu_id** and the internal **user id**, almost never the Chinese name (search
the name once anyway; expect no hits). There is no request-id propagation from nginx to the backend,
so tie a user to their requests by **time + client IP**:

- Login: backend `portal_sso_service … User <學號> verified as student …` / `Redirecting user <學號>`,
  and nginx `POST /api/v1/auth/portal-sso/verify` + `GET /auth/sso-callback?token=<jwt sub=… nycu_id=…>` → gives **IP** and **user id**.
- Student-data calls: `student_service … for <學號>` (SIS term API: `403 - 無資料`, `timed out` …).
- Staff viewing the student: URLs containing the 學號 (`/college-review/students/<學號>/preview`), backend `User <staff id> requesting … for student <學號>`.
- Some messages use the user id: `user_id=<id>`, `User <id> …`, `/users/<id>`.

Shared campus/NAT IPs exist — when attributing an IP's requests to a person, check the user agent
matches and the requests sit next to that person's login.

## Investigation recipe

1. **Parse the purpose** → identifiers (學號, name, user id, `APP-115-1-00012`, endpoint, scholarship),
   symptom (error / 500 / 上傳失敗 / 看不到…), time hint (default: last 7d, widen to 30d if nothing).

2. **Footprint** — every line mentioning the identifier:
   ```bash
   python3 -I $H query '{container=~"/scholarship_(backend|nginx|frontend)_prod"} |= "<學號>" != "/monitoring/"' --since 30d --limit 2000
   ```
   Note: login times, user id (from `<jwt sub=…>`), IPs, application ids, and any WARNING/ERROR already present.

3. **Their session traffic** — for each active period, the requests from that IP, errors first:
   ```bash
   python3 -I $H query '{container="/scholarship_nginx_prod"} != "/monitoring/" | json | remote_addr="<client-ip>" | status >= 400' --since 7d
   python3 -I $H query '{container="/scholarship_nginx_prod"} != "/monitoring/" | json | remote_addr="<client-ip>" |= "/api/"' --start 2026-01-01T09:00 --end 2026-01-01T09:30
   ```
   A burst of `401` right after `sso-callback`, before the first `200 /auth/me`, is the normal token hand-off — not a bug. `499` = client closed the request.

4. **Backend errors in those windows** (a few minutes around each failed request):
   ```bash
   python3 -I $H query '{container="/scholarship_backend_prod"} | json | level=~"ERROR|CRITICAL|WARNING"' --start 2026-01-01T09:00 --end 2026-01-01T09:30 --full
   python3 -I $H query '{container="/scholarship_backend_prod"} |~ "\" (5\\d\\d) "' --start … --end …     # uvicorn 5xx access lines
   ```
   Match an error to the user only when its timestamp/endpoint lines up with their request or the
   message names their 學號/user id/application. Otherwise list it as "同時段其他錯誤（無法確認與此人有關）".

5. **Explain the error from the code** — for each relevant traceback, open the file/line it names
   (`/app/app/...` ↔ `backend/app/...`) and say what triggered it. Prod runs the released image, which
   may lag `main`; say so if the code at that line no longer matches.

Useful extra queries:
- Error volume over time: `sum by (level) (count_over_time({container="/scholarship_backend_prod"} | json | level=~"ERROR|WARNING" [1h]))`
- Slow requests: `{container="/scholarship_nginx_prod"} != "/monitoring/" | json | request_time > 5`
- One feature: `{container="/scholarship_backend_prod"} |= "roster"` / `|= "pdf_merge"` / `|= "export"`

## Report format (zh-TW)

1. **結論** — one or two sentences: was there an error for this person/purpose, and what it was.
2. **時間線** — the person's relevant activity, `UTC / 台北時間`, request → status → related backend log.
3. **錯誤詳情** — each error: log line(s), traceback summary, code location, likely cause, whether it is user-side (bad file, no SIS data) or a system bug.
4. **同時段其他錯誤** — only if notable.
5. **建議** — next step (fix, data check, or "沒有 error，行為符合預期").

Privacy: these are real students. Quote only the lines needed; never paste tokens, cookies, ID
numbers (身分證), or bulk lists of other students' 學號 into the report.

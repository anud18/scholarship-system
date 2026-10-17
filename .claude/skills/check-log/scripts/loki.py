#!/usr/bin/env python3
"""Query the production Loki through the Grafana datasource proxy.

Credentials come from ~/.ssaa.env (username / password / grafana_link).
Stdlib only, so it runs with `python3 -I` and bypasses the rtk curl filter.

  loki.py query '<LogQL>' [--since 72h | --start ISO --end ISO] [--limit N]
  loki.py labels [LABEL]
"""

import argparse
import base64
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENV_FILE = Path.home() / ".ssaa.env"
DATASOURCES = {"prod": "loki-prod-uid", "staging": "loki-staging-uid", "dev": "loki-dev-uid"}
DEFAULT_LIMIT = 500
MAX_LIMIT = 5000
REQUEST_TIMEOUT_SECONDS = 120

# Backend logs every record twice: a JSON line and a plain "ts - name - LEVEL - msg"
# twin whose traceback is split into one Loki entry per line. The JSON line carries
# the full traceback in "exception", so the plain twin is noise.
PLAIN_TWIN = re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} - \S+ - [A-Z]+ - ")
TRACEBACK_FRAGMENT = re.compile(
    r"^(\s|Traceback \(most recent call last\)|During handling of the above|"
    r"The above exception was|[A-Za-z_][\w.]*(Error|Exception|Warning)\b)"
)
# Our own Grafana API calls land in the nginx log and in the monitoring_* containers'
# query logs (which echo the LogQL, so they "match" every search); never report them.
SELF_TRAFFIC = "/monitoring/"
MONITORING_CONTAINER_PREFIX = "monitoring_"
DURATION = re.compile(r"^(\d+)([mhd])$")
# nginx logs the live session JWT in /auth/sso-callback?token=...; never print it.
JWT = re.compile(r"eyJ[\w-]+\.(eyJ[\w-]+)\.[\w-]+")


def load_env():
    if not ENV_FILE.exists():
        sys.exit(f"missing {ENV_FILE} (needs username, password, grafana_link)")
    env = {}
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")
    missing = {"username", "password", "grafana_link"} - env.keys()
    if missing:
        sys.exit(f"{ENV_FILE} is missing: {', '.join(sorted(missing))}")
    return env


def grafana_get(env, path, params):
    url = env["grafana_link"].rstrip("/") + path + "?" + urllib.parse.urlencode(params)
    token = base64.b64encode(f"{env['username']}:{env['password']}".encode()).decode()
    request = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Grafana HTTP {exc.code}: {exc.read().decode(errors='replace')[:500]}")
    except urllib.error.URLError as exc:
        sys.exit(f"cannot reach Grafana at {env['grafana_link']}: {exc.reason}")


def parse_time(value):
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def time_range(args):
    end = parse_time(args.end) if args.end else datetime.now(timezone.utc)
    if args.start:
        return parse_time(args.start), end
    match = DURATION.match(args.since)
    if not match:
        sys.exit(f"--since must look like 30m / 6h / 7d, got {args.since!r}")
    amount, unit = int(match.group(1)), match.group(2)
    delta = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount), "d": timedelta(days=amount)}[unit]
    return end - delta, end


def is_noise(container, line):
    if SELF_TRAFFIC in line or container.startswith(MONITORING_CONTAINER_PREFIX):
        return True
    return bool(PLAIN_TWIN.match(line) or TRACEBACK_FRAGMENT.match(line))


def redact_jwt(match):
    payload = match.group(1)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, json.JSONDecodeError):
        return "<jwt>"
    return f"<jwt sub={claims.get('sub')} nycu_id={claims.get('nycu_id')} role={claims.get('role')}>"


def format_line(line, full):
    if not line.startswith("{"):
        return line
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        return line
    if "message" in record:  # backend structured log
        text = f"{record.get('level', '?')} {record.get('name', '?')}: {record['message']}"
        exception = record.get("exception")
        if exception:
            text += "\n" + (exception if full else "    " + exception.strip().splitlines()[-1])
        return text
    if "request" in record:  # nginx access log
        return (
            f"{record.get('status')} {record.get('request')} ip={record.get('remote_addr')} "
            f"rt={record.get('request_time')} ua={record.get('http_user_agent', '')[:60]}"
        )
    return line


def run_query(env, args):
    start, end = time_range(args)
    data = grafana_get(
        env,
        f"/api/datasources/proxy/uid/{DATASOURCES[args.env]}/loki/api/v1/query_range",
        {
            "query": args.logql,
            "start": str(int(start.timestamp() * 1e9)),
            "end": str(int(end.timestamp() * 1e9)),
            "limit": str(min(args.limit, MAX_LIMIT)),
            "direction": "backward",
        },
    )
    if data.get("status") != "success":
        sys.exit(f"Loki error: {json.dumps(data)[:500]}")
    result = data["data"]
    if result.get("resultType") != "streams":  # metric query: one line per sample
        for series in result["result"]:
            labels = ",".join(f"{k}={v}" for k, v in series["metric"].items()) or "{}"
            for ts, value in series.get("values", [series.get("value")]):
                print(f"{datetime.fromtimestamp(float(ts), timezone.utc):%Y-%m-%dT%H:%MZ} {labels} {value}")
        return

    entries = [
        (int(ts), container, line)
        for stream in result["result"]
        for container in [stream["stream"].get("container", "?").lstrip("/")]
        for ts, line in stream["values"]
        if args.raw or not is_noise(container, line)
    ]
    entries.sort()
    for ts, container, line in entries:
        stamp = datetime.fromtimestamp(ts / 1e9, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        body = JWT.sub(redact_jwt, line if args.raw else format_line(line, args.full))
        print(f"{stamp[:23]}Z [{container}] {body}")

    total = sum(len(s["values"]) for s in result["result"])
    note = " (hit --limit; narrow the range or raise it)" if total >= args.limit else ""
    print(
        f"-- {len(entries)} shown / {total} fetched, {start:%Y-%m-%dT%H:%M}Z → {end:%Y-%m-%dT%H:%M}Z{note}",
        file=sys.stderr,
    )


def run_labels(env, args):
    base = f"/api/datasources/proxy/uid/{DATASOURCES[args.env]}/loki/api/v1"
    path = f"{base}/label/{args.label}/values" if args.label else f"{base}/labels"
    since = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp() * 1e9)
    print("\n".join(grafana_get(env, path, {"start": str(since)}).get("data", [])))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", choices=DATASOURCES, default="prod")
    sub = parser.add_subparsers(dest="command", required=True)

    query = sub.add_parser("query", help="run a LogQL query")
    query.add_argument("logql")
    query.add_argument("--since", default="24h", help="look-back window, e.g. 30m / 6h / 7d (default 24h)")
    query.add_argument("--start", help="ISO time; naive = UTC (overrides --since)")
    query.add_argument("--end", help="ISO time; naive = UTC (default now)")
    query.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    query.add_argument("--full", action="store_true", help="print full tracebacks")
    query.add_argument("--raw", action="store_true", help="no dedupe / formatting")

    labels = sub.add_parser("labels", help="list labels or one label's values")
    labels.add_argument("label", nargs="?")

    args = parser.parse_args()
    env = load_env()
    if args.command == "query":
        run_query(env, args)
    else:
        run_labels(env, args)


if __name__ == "__main__":
    main()

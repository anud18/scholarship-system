"""
Tiny Grafana → GitHub repository_dispatch webhook bridge.

Why this exists:
    Grafana webhook contact-points only let you customize the `message`
    field *inside* their standard Alertmanager-style envelope. They
    can't send a raw JSON body. GitHub's /repos/{owner}/{repo}/dispatches
    endpoint strictly requires `{event_type, client_payload}` and
    rejects everything else with HTTP 422.

    This bridge listens on :8080, accepts Grafana's standard envelope
    on POST /grafana, extracts the first alert's fields, and reposts
    to GitHub /dispatches in the right shape.

Configuration (env):
    GH_PAT_FILE       path to file containing the GitHub PAT
                      (default /etc/webhook-bridge/gh_pat)
    GH_REPO           owner/repo to dispatch to (required)
    GH_EVENT_TYPE     event_type for repository_dispatch
                      (default monitoring-alert)
    LISTEN_HOST       default 0.0.0.0
    LISTEN_PORT       default 8080
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Response, status

GH_PAT_FILE = os.environ.get("GH_PAT_FILE", "/etc/webhook-bridge/gh_pat")
GH_REPO = os.environ.get("GH_REPO", "").strip()
GH_EVENT_TYPE = os.environ.get("GH_EVENT_TYPE", "monitoring-alert")
LISTEN_HOST = os.environ.get("LISTEN_HOST", "0.0.0.0")
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8080"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("webhook-bridge")

app = FastAPI(title="grafana-github-webhook-bridge", version="1.0")


def read_pat() -> str:
    """Read the PAT from disk on every request so token rotation doesn't
    require a container restart."""
    with open(GH_PAT_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def transform_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Collapse a Grafana envelope (which can carry 25+ alerts for the
    same rule firing on different instances) into ONE GitHub
    /dispatches payload. The handler workflow dedupes by
    `(alertname, env)` labels anyway, so per-alert fan-out just spams
    the same issue with redundant comments. Instead, fold the
    instance list into a single payload so the issue body shows all
    affected instances at once.

    Max 10 client_payload keys (GitHub /dispatches limit)."""
    alerts = envelope.get("alerts") or []
    a0 = (alerts[0] if alerts else {}) or {}
    labels0 = a0.get("labels") or {}
    annotations0 = a0.get("annotations") or {}

    # Collect distinct instances across all alerts so the issue body
    # shows the full footprint, not just the first one.
    instances = []
    seen = set()
    for a in alerts:
        inst = (a.get("labels") or {}).get("instance") or ""
        if inst and inst not in seen:
            seen.add(inst)
            instances.append(inst)
    # Truncate to keep the payload reasonable (issue body / GH JSON size).
    MAX_LISTED = 20
    instance_str = ", ".join(instances[:MAX_LISTED])
    if len(instances) > MAX_LISTED:
        instance_str += f" (+{len(instances) - MAX_LISTED} more)"

    return {
        "event_type": GH_EVENT_TYPE,
        "client_payload": {
            "alertname": labels0.get("alertname") or "(unknown)",
            "severity": labels0.get("severity") or "info",
            "status": envelope.get("status") or a0.get("status") or "firing",
            "summary": annotations0.get("summary") or "(no summary)",
            "description": annotations0.get("description") or "(no description)",
            # `instance` now carries the full deduped list (up to 20).
            "instance": instance_str or labels0.get("instance") or "",
            "environment": labels0.get("environment") or "",
            "value": f"{len(alerts)} alert(s) in this batch",
            "fired_at": str(a0.get("startsAt") or ""),
            "grafana_url": envelope.get("externalURL") or "",
        },
    }


@app.get("/")
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/grafana")
async def grafana(request: Request):
    if not GH_REPO:
        log.error("GH_REPO env var not set")
        raise HTTPException(500, "GH_REPO env var not set")

    try:
        envelope = await request.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("invalid JSON from grafana: %s", exc)
        raise HTTPException(400, f"invalid json: {exc}") from exc

    alerts = envelope.get("alerts") or []
    if not alerts:
        log.info("no alerts in envelope; ignoring")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        pat = read_pat()
    except OSError as exc:
        log.error("failed to read PAT file: %s", exc)
        raise HTTPException(500, f"failed to read PAT file: {exc}") from exc

    payload = transform_envelope(envelope)
    cp = payload["client_payload"]
    log.info(
        "forwarding alertname=%s severity=%s status=%s alerts=%d instances=%s",
        cp["alertname"], cp["severity"], cp["status"], len(alerts),
        cp["instance"][:80],
    )

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {pat}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "grafana-github-webhook-bridge/1.0",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            r = await client.post(
                f"https://api.github.com/repos/{GH_REPO}/dispatches",
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            log.error("upstream connection failed: %s", exc)
            raise HTTPException(502, f"upstream connection failed: {exc}") from exc

    if 200 <= r.status_code < 300:
        log.info("github accepted: %s", r.status_code)
        return {"status": "ok", "alerts_collapsed": len(alerts), "github_status": r.status_code}
    log.warning("github rejected: %s body=%s", r.status_code, r.text[:200])
    raise HTTPException(502, f"upstream {r.status_code}: {r.text[:200]}")


def main():
    if not GH_REPO:
        log.error("GH_REPO env var must be set (e.g. owner/repo)")
        sys.exit(2)
    log.info(
        "listening on %s:%s repo=%s event_type=%s",
        LISTEN_HOST, LISTEN_PORT, GH_REPO, GH_EVENT_TYPE,
    )
    uvicorn.run(app, host=LISTEN_HOST, port=LISTEN_PORT, log_config=None)


if __name__ == "__main__":
    main()

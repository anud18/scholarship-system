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


def transform_one(
    a: dict[str, Any], envelope_status: str, external_url: str
) -> dict[str, Any]:
    """Build one GitHub-/dispatches-shaped payload for a single alert
    (max 10 client_payload keys)."""
    labels = a.get("labels") or {}
    annotations = a.get("annotations") or {}
    return {
        "event_type": GH_EVENT_TYPE,
        "client_payload": {
            "alertname": labels.get("alertname") or "(unknown)",
            "severity": labels.get("severity") or "info",
            "status": envelope_status or a.get("status") or "firing",
            "summary": annotations.get("summary") or "(no summary)",
            "description": annotations.get("description") or "(no description)",
            "instance": labels.get("instance") or "",
            "environment": labels.get("environment") or "",
            "value": str(a.get("valueString") or ""),
            "fired_at": str(a.get("startsAt") or ""),
            "grafana_url": external_url or "",
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

    envelope_status = envelope.get("status") or ""
    external_url = envelope.get("externalURL") or ""
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {pat}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "grafana-github-webhook-bridge/1.0",
    }

    # Fan out: send one /dispatches per alert. Grafana groups alerts by
    # (alertname, environment) so a single envelope can carry 25+ alerts
    # for the same rule firing across multiple instances. The previous
    # implementation only forwarded the first alert and silently dropped
    # the rest. The handler workflow already deduplicates by labels, so
    # repeats from the same group append a comment instead of opening
    # duplicate issues.
    sent = 0
    failures: list[str] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for a in alerts:
            payload = transform_one(a, envelope_status, external_url)
            cp = payload["client_payload"]
            log.info(
                "forwarding alertname=%s severity=%s status=%s instance=%s",
                cp["alertname"], cp["severity"], cp["status"], cp["instance"],
            )
            try:
                r = await client.post(
                    f"https://api.github.com/repos/{GH_REPO}/dispatches",
                    json=payload,
                    headers=headers,
                )
            except httpx.HTTPError as exc:
                log.error("upstream connection failed: %s", exc)
                failures.append(f"connection: {exc}")
                continue

            if 200 <= r.status_code < 300:
                sent += 1
            else:
                log.warning(
                    "github rejected: %s body=%s",
                    r.status_code, r.text[:200],
                )
                failures.append(f"{r.status_code}: {r.text[:80]}")

    if failures and sent == 0:
        raise HTTPException(502, f"all {len(alerts)} dispatches failed; first: {failures[0]}")
    log.info("forwarded %d/%d alerts", sent, len(alerts))
    return {"status": "ok", "sent": sent, "total": len(alerts), "failures": failures}


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

"""Render the security-audit PDFs from CodeQL SARIF and the ZAP JSON report.

Usage (inside report.Dockerfile's image):
    render_reports.py --sarif-dir DIR --zap-dir DIR --out-dir DIR

--zap-dir holds the ZAP job's output: zap-raw-report.json, openapi.json and
response-headers.txt. Run metadata (repo, commit, scan settings) comes from
the AUDIT_* / *_MINUTES / TARGET_HOST / RELAXED_RATE environment variables.

Writes security-audit-summary.pdf, codeql-report.pdf, zap-report.pdf and
counts.json (for the workflow's job summary). A missing input is rendered as
"not produced" rather than skipped, so a half-failed audit can never yield a
report that looks clean.
"""

import argparse
import html
import json
import os
import pathlib
import re
from collections import Counter
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration

TEMPLATE_DIR = pathlib.Path(__file__).parent / "templates"
SEVERITIES = ["Critical", "High", "Medium", "Low", "Info"]
ZAP_RISKS = {3: "High", 2: "Medium", 1: "Low", 0: "Informational"}
ZAP_RISK_ORDER = ["High", "Medium", "Low", "Informational"]
ZAP_CONFIDENCE = {0: "False Positive", 1: "Low", 2: "Medium", 3: "High", 4: "Confirmed"}
SARIF_LEVEL = {"error": "High", "warning": "Medium", "note": "Low", "none": "Info"}
LANGUAGE_NAMES = {"python": "Python", "javascript": "JavaScript/TypeScript", "actions": "GitHub Actions"}
# One SARIF per CodeQL matrix leg (security-audit.yml). A missing one means that
# leg failed and must be called out, not silently dropped from the tables.
EXPECTED_SARIF = ("actions", "javascript", "python")
MAX_INSTANCES_PER_ALERT = 10
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
META_ENV = {
    "repo": "AUDIT_REPO",
    "ref": "AUDIT_REF",
    "commit": "AUDIT_COMMIT",
    "run_url": "AUDIT_RUN_URL",
    "target_host": "TARGET_HOST",
    "api_scan_minutes": "API_SCAN_MINUTES",
    "frontend_scan_minutes": "FRONTEND_SCAN_MINUTES",
    "spider_minutes": "SPIDER_MINUTES",
    "relaxed_rate": "RELAXED_RATE",
}


def paragraphs(text: str) -> list:
    """ZAP descriptions are HTML fragments: split into plain-text paragraphs."""
    text = re.sub(r"</p>|<br\s*/?>", "\n", text or "")
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    return [line.strip() for line in text.splitlines() if line.strip()]


def codeql_severity(result: dict, rule: dict) -> str:
    score = rule.get("properties", {}).get("security-severity")
    if score is None:
        # A result omits `level` when it equals the rule's default.
        default_level = rule.get("defaultConfiguration", {}).get("level", "warning")
        return SARIF_LEVEL.get(result.get("level", default_level), "Medium")
    score = float(score)
    if score >= 9.0:
        return "Critical"
    if score >= 7.0:
        return "High"
    if score >= 4.0:
        return "Medium"
    return "Low"


def rules_by_id(run: dict) -> dict:
    """CodeQL pack output keeps rules in tool.extensions[].rules, not tool.driver.rules."""
    tool = run.get("tool", {})
    components = [tool.get("driver", {}), *tool.get("extensions", [])]
    return {rule["id"]: rule for component in components for rule in component.get("rules", []) if "id" in rule}


def parse_sarif(sarif_dir: pathlib.Path) -> dict:
    files = sorted(sarif_dir.rglob("*.sarif")) if sarif_dir.exists() else []
    findings, languages, version = [], [], ""
    for sarif_file in files:
        language = LANGUAGE_NAMES.get(sarif_file.stem, sarif_file.stem)
        languages.append(language)
        for run in json.loads(sarif_file.read_text(encoding="utf-8")).get("runs", []):
            driver = run.get("tool", {}).get("driver", {})
            version = version or driver.get("semanticVersion", "")
            rules = rules_by_id(run)
            for result in run.get("results", []):
                rule = rules.get(result.get("ruleId"), {})
                location = (result.get("locations") or [{}])[0].get("physicalLocation", {})
                findings.append(
                    {
                        "language": language,
                        "rule_id": result.get("ruleId", "unknown"),
                        "rule_name": rule.get("shortDescription", {}).get("text", ""),
                        "severity": codeql_severity(result, rule),
                        "file": location.get("artifactLocation", {}).get("uri", "?"),
                        "line": location.get("region", {}).get("startLine", 0),
                        "message": result.get("message", {}).get("text", ""),
                    }
                )
    findings.sort(key=lambda f: (SEVERITIES.index(f["severity"]), f["language"], f["file"], f["line"]))
    by_language = {lang: Counter(f["severity"] for f in findings if f["language"] == lang) for lang in languages}
    present = {f.stem for f in files}
    return {
        "produced": bool(files),
        "missing": [LANGUAGE_NAMES.get(stem, stem) for stem in EXPECTED_SARIF if stem not in present],
        "version": version,
        "languages": languages,
        "findings": findings,
        "counts": Counter(f["severity"] for f in findings),
        "by_language": by_language,
        "rules": Counter((f["severity"], f["rule_id"], f["rule_name"]) for f in findings),
    }


def parse_zap(zap_json: pathlib.Path) -> dict:
    if not zap_json.exists():
        return {"produced": False, "alerts": [], "counts": Counter(), "version": ""}
    data = json.loads(zap_json.read_text(encoding="utf-8"))
    alerts = []
    for site in data.get("site", []):
        for alert in site.get("alerts", []):
            instances = alert.get("instances", [])
            alerts.append(
                {
                    "name": alert.get("name") or alert.get("alert", "?"),
                    "plugin_id": alert.get("pluginid", ""),
                    "risk": ZAP_RISKS.get(int(alert.get("riskcode", 0)), "Informational"),
                    "confidence": ZAP_CONFIDENCE.get(int(alert.get("confidence", 2)), "?"),
                    "cwe": alert.get("cweid", ""),
                    "count": int(alert.get("count", len(instances))),
                    "desc": paragraphs(alert.get("desc", "")),
                    "solution": paragraphs(alert.get("solution", "")),
                    "reference": paragraphs(alert.get("reference", "")),
                    "instances": instances[:MAX_INSTANCES_PER_ALERT],
                    "truncated": max(0, len(instances) - MAX_INSTANCES_PER_ALERT),
                    "areas": sorted({"API" if "/api/" in i.get("uri", "") else "前端" for i in instances}),
                }
            )
    alerts.sort(key=lambda a: (ZAP_RISK_ORDER.index(a["risk"]), -a["count"]))
    return {
        "produced": True,
        "version": data.get("@version", ""),
        "alerts": alerts,
        "counts": Counter(a["risk"] for a in alerts),
    }


def load_meta(zap_dir: pathlib.Path) -> dict:
    meta = {key: os.environ.get(var, "") for key, var in META_ENV.items()}
    spec = zap_dir / "openapi.json"
    if spec.exists():
        paths = json.loads(spec.read_text(encoding="utf-8")).get("paths", {})
        meta["openapi_operations"] = sum(1 for ops in paths.values() for m in ops if m in HTTP_METHODS)
    else:
        meta["openapi_operations"] = "?"
    headers = zap_dir / "response-headers.txt"
    meta["response_headers"] = headers.read_text(encoding="utf-8").replace("\r", "").strip() if headers.exists() else ""
    meta["generated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return meta


def render_pdf(env: Environment, template: str, out: pathlib.Path, **context) -> None:
    html_text = env.get_template(template).render(**context)
    out.with_suffix(".html").write_text(html_text, encoding="utf-8")
    fonts = FontConfiguration()
    page = CSS(string="@page { size: A4; margin: 14mm; }", font_config=fonts)
    HTML(string=html_text, base_url=str(TEMPLATE_DIR)).write_pdf(out, stylesheets=[page], font_config=fonts)
    print(f"wrote {out} ({out.stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sarif-dir", type=pathlib.Path, required=True)
    parser.add_argument("--zap-dir", type=pathlib.Path, required=True)
    parser.add_argument("--out-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()

    meta = load_meta(args.zap_dir)
    codeql = parse_sarif(args.sarif_dir)
    zap = parse_zap(args.zap_dir / "zap-raw-report.json")

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=select_autoescape(["html", "j2"]))
    common = {"meta": meta, "codeql": codeql, "zap": zap, "severities": SEVERITIES, "zap_risks": ZAP_RISK_ORDER}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    render_pdf(env, "summary.html.j2", args.out_dir / "security-audit-summary.pdf", **common)
    render_pdf(env, "codeql.html.j2", args.out_dir / "codeql-report.pdf", **common)
    render_pdf(env, "zap.html.j2", args.out_dir / "zap-report.pdf", **common)

    counts = {
        "codeql_produced": codeql["produced"],
        "codeql_missing_languages": codeql["missing"],
        "zap_produced": zap["produced"],
        **{f"codeql_{s.lower()}": codeql["counts"][s] for s in SEVERITIES},
        **{f"zap_{r.lower()}": zap["counts"][r] for r in ZAP_RISK_ORDER},
    }
    (args.out_dir / "counts.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
    print(json.dumps(counts))


if __name__ == "__main__":
    main()

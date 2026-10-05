"""Which response headers / embed strategy make Safari render a framed PDF?

Issue #1434: in real Safari the student wizard's PDF preview stays blank while
the PNG preview works. This harness is self-contained (no dev stack, no
secrets): it serves a tiny page + a valid one-page PDF under several header
sets, frames it once from a blob: URL and once from its own URL, drives real
Safari (safaridriver) on a macOS runner, and measures the pixels the PDF viewer
actually painted (WebDriver screenshot crop, cross-checked by a native capture).

Header sets mirror frontend/lib/security-headers.ts + middleware.ts. The result
that pinned the bug: a blob: PDF frame is blank exactly when the page carries
`frame-ancestors 'none'` (the blob document inherits it); the same-origin URL
frame paints under every set. `real-self` is today's production set
(`frame-ancestors 'self'`, X-Frame-Options DENY) and must paint both ways.

Env: OUT_DIR (default safari-matrix), BROWSER=safari|chrome|edge, GATE=0 to
report only (never fail), ONLY (comma list
of "<headers>/<mode>" to restrict), PORT (default 8765).
"""

import http.server
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import WebDriverException

OUT_DIR = pathlib.Path(os.environ.get("OUT_DIR", "safari-matrix"))
BROWSER = os.environ.get("BROWSER", "safari")
PORT = int(os.environ.get("PORT", "8765"))
SETTLE_SECONDS = 5
SAFARI_LAUNCH_ATTEMPTS = 3
# Text pixels of the rendered PDF are black; a blank iframe shows the white
# page background. Anything above this share of dark pixels counts as painted.
DARK_PIXEL_THRESHOLD = 60
MIN_DARK_PIXELS = 150


def build_pdf() -> bytes:
    """A valid one-page PDF (correct xref) with large black text."""
    stream = b"BT /F1 40 Tf 30 130 Td (SAFARI PDF PREVIEW OK) Tj ET"
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 600 300]/Contents 4 0 R" b"/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length %d>>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica-Bold>>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    return out


PDF_BYTES = build_pdf()

PROD_CSP = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "frame-src 'self' blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "base-uri 'self'",
        "object-src 'none'",
    ]
)
TRIO = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
}

NONCE = "matrixnonce123"
FULL_PERMISSIONS_POLICY = ", ".join(
    [
        "accelerometer=()", "autoplay=()", "browsing-topics=()", "camera=()",
        "clipboard-read=()", "clipboard-write=(self)", "display-capture=()",
        "encrypted-media=()", "fullscreen=(self)", "geolocation=()", "gyroscope=()",
        "hid=()", "idle-detection=()", "local-fonts=()", "magnetometer=()",
        "microphone=()", "midi=()", "payment=()", "picture-in-picture=()",
        "publickey-credentials-get=()", "screen-wake-lock=()", "serial=()", "usb=()",
        "xr-spatial-tracking=()",
    ]
)  # fmt: skip


def real_csp(frame_ancestors: str | None = "'self'") -> str:
    """frontend/middleware.ts production CSP (minus upgrade-insecure-requests,
    which only matters over https), for a NON-preview page. `frame_ancestors`
    is the directive's value; None omits the directive."""
    directives = [
        "default-src 'self'",
        f"script-src 'self' 'nonce-{NONCE}' 'strict-dynamic'",
        f"style-src 'self' 'nonce-{NONCE}'",
        "style-src-attr 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "frame-src 'self' blob:",
        "font-src 'self'",
        "connect-src 'self' https://*.nycu.edu.tw",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ]
    if frame_ancestors:
        directives.append(f"frame-ancestors {frame_ancestors}")
    return "; ".join(directives)


def real_headers(frame_ancestors: str | None = "'self'") -> dict:
    """The full production header set of a non-preview page (X-Frame-Options
    stays DENY, exactly as middleware.ts + nginx send it)."""
    return {
        "Content-Security-Policy": real_csp(frame_ancestors),
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Frame-Options": "DENY",
        "Permissions-Policy": FULL_PERMISSIONS_POLICY,
        **TRIO,
    }


# name -> headers applied to BOTH the page and the framed PDF response (the
# PDF response is relaxed to same-origin framing, like /api/v1/preview).
HEADER_SETS = {
    "current": {"Content-Security-Policy": PROD_CSP, **TRIO},
    "bare": {},
    # Today's production set (#1434): frame-ancestors 'self'.
    "real-self": real_headers("'self'"),
    # The pre-#1434 set: 'none' blanks a blob: PDF frame in Safari (documented
    # finding, EXPECTED blank — not gated).
    "real-none": real_headers("'none'"),
    "real-no-frame-ancestors": real_headers(None),
}
MODES = ["blob-iframe", "direct-iframe"]
# Sets whose blob: PDF frame is EXPECTED to stay blank in Safari.
BLOB_BLANK_EXPECTED = {"real-none"}


def framable(headers: dict) -> dict:
    """The same headers with framing relaxed to same-origin (preview proxy)."""
    relaxed = dict(headers)
    if "Content-Security-Policy" in relaxed:
        relaxed["Content-Security-Policy"] = relaxed["Content-Security-Policy"].replace(
            "frame-ancestors 'none'", "frame-ancestors 'self'"
        )
    if "X-Frame-Options" in relaxed:
        relaxed["X-Frame-Options"] = "SAMEORIGIN"
    return relaxed


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>matrix</title></head>
<body style="margin:0;background:#fff">
<div id="status" style="font:14px sans-serif;padding:4px">loading</div>
<div id="host" style="width:800px;height:420px"></div>
<script nonce="%s" src="harness.js"></script>
</body></html>
"""

HARNESS_JS = """
const mode = new URLSearchParams(location.search).get("mode");
const status = document.getElementById("status");
const host = document.getElementById("host");
function mountIframe(src) {
  const el = document.createElement("iframe");
  el.id = "viewer";
  el.src = src;
  el.style.cssText = "width:800px;height:420px;border:0";
  host.appendChild(el);
}
async function run() {
  try {
    if (mode === "direct-iframe") {
      mountIframe("file.pdf");
    } else {
      const response = await fetch("file.pdf", { credentials: "same-origin" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const blob = await response.blob();
      mountIframe(URL.createObjectURL(new Blob([blob], { type: "application/pdf" })));
    }
    status.textContent = "mounted " + mode;
  } catch (error) {
    status.textContent = "ERROR " + error;
  }
  window.__mounted = true;
}
window.addEventListener("error", e => (window.__errors = (window.__errors || []).concat(String(e.message))));
window.addEventListener("unhandledrejection", e => (window.__errors = (window.__errors || []).concat("rejection: " + e.reason)));
run();
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the CI log readable
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 2 or parts[0] not in HEADER_SETS:
            self.send_error(404)
            return
        name, resource = parts
        if resource == "index.html":
            body, ctype = (PAGE % NONCE).encode(), "text/html; charset=utf-8"
        elif resource == "harness.js":
            body, ctype = HARNESS_JS.encode(), "text/javascript"
        elif resource == "file.pdf":
            body, ctype = PDF_BYTES, "application/pdf"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        headers = dict(HEADER_SETS[name])
        if resource == "file.pdf":
            headers = framable(headers)
            headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


def start_server() -> http.server.ThreadingHTTPServer:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def start_safari() -> webdriver.Remote:
    for attempt in range(1, SAFARI_LAUNCH_ATTEMPTS + 1):
        try:
            return webdriver.Safari()
        except WebDriverException as exc:
            print(f"[driver] Safari launch attempt {attempt} failed: {exc.msg}", flush=True)
            if attempt == SAFARI_LAUNCH_ATTEMPTS:
                raise
            subprocess.run(["pkill", "-x", "Safari"], check=False)
            time.sleep(10)
    raise RuntimeError("unreachable")


def make_driver() -> webdriver.Remote:
    if BROWSER == "safari":
        driver = start_safari()
    elif BROWSER == "edge":
        options = webdriver.EdgeOptions()
        options.add_argument("--headless=new")
        driver = webdriver.Edge(options=options)
    else:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        driver = webdriver.Chrome(options=options)
    driver.set_window_rect(0, 0, 1200, 900)
    return driver


def count_dark_pixels(png_path: pathlib.Path, crop_css_rect=None) -> int:
    """Dark pixels in a screenshot, optionally cropped to a CSS-pixel rect
    (x, y, w, h) — scaled by the screenshot-to-viewport ratio (retina)."""
    from PIL import Image

    with Image.open(png_path) as image:
        if crop_css_rect:
            scale = image.width / crop_css_rect[4]
            x, y, w, h = (v * scale for v in crop_css_rect[:4])
            image = image.crop((int(x), int(y), int(x + w), int(y + h)))
        gray = image.convert("L")
        return sum(1 for value in gray.getdata() if value < DARK_PIXEL_THRESHOLD)


def capture_viewer(driver, base: pathlib.Path, selector: str = "#viewer") -> dict:
    """Measure what the viewer painted.

    Primary metric: dark pixels inside the viewer's rect on the WebDriver
    screenshot (it does include the PDF plugin in Safari 26). A native
    screencapture of the same rect is kept as a cross-check, but its screen
    coordinates drift when the window sits low on the runner's display.
    """
    result: dict = {}
    rect = driver.execute_script(
        "const r = document.querySelector(arguments[0])?.getBoundingClientRect();"
        "return r ? [Math.max(r.left, 0), Math.max(r.top, 0),"
        " Math.min(r.width, innerWidth - Math.max(r.left, 0)),"
        " Math.min(r.height, innerHeight - Math.max(r.top, 0)), innerWidth,"
        " screenX + r.left, screenY + outerHeight - innerHeight + r.top] : null;",
        selector,
    )
    if not rect:
        result["viewer"] = "missing"
        return result
    shot = pathlib.Path(f"{base}-webdriver.png")
    try:
        driver.save_screenshot(str(shot))
        result["dark_pixels"] = count_dark_pixels(shot, rect[:5])
    except WebDriverException as exc:
        result["webdriver_shot_error"] = exc.msg
    if sys.platform == "darwin":
        native = pathlib.Path(f"{base}-native.png")
        region = ",".join(str(int(v)) for v in (rect[5], rect[6], rect[2], rect[3]))
        subprocess.run(["screencapture", "-x", "-R", region, str(native)], check=False)
        if native.exists():
            result["native_dark_pixels"] = count_dark_pixels(native)
    return result


def run_case(driver, name: str, mode: str) -> dict:
    url = f"http://127.0.0.1:{PORT}/{name}/index.html?mode={mode}"
    case = {"headers": name, "mode": mode}
    driver.get(url)
    time.sleep(SETTLE_SECONDS)
    case["status"] = driver.execute_script("return document.getElementById('status').textContent;")
    case["errors"] = driver.execute_script("return window.__errors || [];")
    case.update(capture_viewer(driver, OUT_DIR / f"{name}--{mode}"))
    dark = case.get("dark_pixels")
    case["painted"] = None if dark is None else dark >= MIN_DARK_PIXELS
    print(f"[case] {json.dumps(case, ensure_ascii=False)}", flush=True)
    return case


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    only = {item for item in os.environ.get("ONLY", "").split(",") if item}
    server = start_server()
    driver = make_driver()
    cases = []
    try:
        print(
            f"[env] {driver.capabilities.get('browserName')} " f"{driver.capabilities.get('browserVersion')}",
            flush=True,
        )
        for name in HEADER_SETS:
            for mode in MODES:
                if only and f"{name}/{mode}" not in only:
                    continue
                cases.append(run_case(driver, name, mode))
    finally:
        driver.quit()
        server.shutdown()
    (OUT_DIR / "results.json").write_text(json.dumps(cases, indent=2, ensure_ascii=False))
    print("\nheaders          mode            painted  dark_px")
    for case in cases:
        print(f"{case['headers']:<16} {case['mode']:<15} " f"{str(case['painted']):<8} {case.get('dark_pixels')}")
    # Gate on what the app relies on: a PDF framed by its own same-origin URL
    # (remote previews) AND from a blob: URL (just-picked local file) must both
    # paint under every header set — except the pre-#1434 `frame-ancestors
    # 'none'` set, where a blank blob frame is the documented finding.
    unpainted = [
        f"{c['headers']}/{c['mode']}"
        for c in cases
        if not c["painted"] and not (c["mode"] == "blob-iframe" and c["headers"] in BLOB_BLANK_EXPECTED)
    ]
    if unpainted and os.environ.get("GATE", "1") != "0":
        print(f"FAIL: expected a painted PDF frame, got blank: {unpainted}")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--write-pdf":
        pathlib.Path(sys.argv[2]).write_bytes(PDF_BYTES)
        sys.exit(0)
    sys.exit(main())

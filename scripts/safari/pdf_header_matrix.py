"""Which response headers / embed strategy make Safari render a framed PDF?

Issue #1434: in real Safari the student wizard's PDF preview stays blank while
the PNG preview works. This harness is self-contained (no dev stack, no
secrets): it serves a tiny page + a valid one-page PDF under several header
sets and embed modes, drives real Safari (safaridriver) on a macOS runner, and
measures the pixels the PDF viewer actually painted with a native screencapture
(the WebDriver snapshot leaves PDF plugin areas blank).

Header sets mirror frontend/lib/security-headers.ts + middleware.ts.

Env: OUT_DIR (default safari-matrix), BROWSER=safari|chrome, ONLY (comma list
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
from urllib.parse import parse_qs, urlparse

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

PERMISSIONS_POLICY = "clipboard-write=(self), fullscreen=(self)"
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
CSP_OBJECT_OK = PROD_CSP.replace("object-src 'none'", "object-src 'self' blob:")
TRIO = {
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
}

# name -> headers applied to BOTH the page and the framed PDF response
HEADER_SETS = {
    "current": {"Content-Security-Policy": PROD_CSP, **TRIO},
    "no-coep": {
        "Content-Security-Policy": PROD_CSP,
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
    },
    "no-trio": {"Content-Security-Policy": PROD_CSP},
    "trio-only": dict(TRIO),
    "bare": {},
}
# Modes that need `object-src` get a CSP that allows it (except in "bare").
MODES = ["blob-iframe", "direct-iframe", "blob-object", "blob-embed"]


def headers_for(name: str, mode: str) -> dict:
    headers = dict(HEADER_SETS[name])
    if mode in ("blob-object", "blob-embed") and "Content-Security-Policy" in headers:
        headers["Content-Security-Policy"] = CSP_OBJECT_OK
    return headers


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>matrix</title></head>
<body style="margin:0;background:#fff">
<div id="status" style="font:14px sans-serif;padding:4px">loading</div>
<div id="host" style="width:800px;height:420px"></div>
<script src="harness.js"></script>
</body></html>
"""

HARNESS_JS = """
const mode = new URLSearchParams(location.search).get("mode");
const status = document.getElementById("status");
const host = document.getElementById("host");
function mount(tag, src) {
  const el = document.createElement(tag);
  el.id = "viewer";
  if (tag === "iframe") el.src = src;
  else el.setAttribute("data" in el ? "data" : "src", src);
  if (tag === "embed") el.src = src;
  if (tag === "object") el.data = src;
  el.type = "application/pdf";
  el.style.cssText = "width:800px;height:420px;border:0";
  host.appendChild(el);
  return el;
}
async function run() {
  try {
    if (mode === "direct-iframe") {
      mount("iframe", "file.pdf");
    } else {
      const response = await fetch("file.pdf", { credentials: "same-origin" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const blob = await response.blob();
      const url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
      const tag = mode === "blob-object" ? "object" : mode === "blob-embed" ? "embed" : "iframe";
      mount(tag, url);
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
        mode = parse_qs(parsed.query).get("mode", ["blob-iframe"])[0]
        if resource == "index.html":
            body, ctype = PAGE.encode(), "text/html; charset=utf-8"
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
        for key, value in headers_for(name, mode).items():
            self.send_header(key, value)
        if resource == "file.pdf":
            self.send_header("X-Frame-Options", "SAMEORIGIN")
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
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--write-pdf":
        pathlib.Path(sys.argv[2]).write_bytes(PDF_BYTES)
        sys.exit(0)
    sys.exit(main())

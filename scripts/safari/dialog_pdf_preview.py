"""Drive the REAL FilePreviewDialog in real Safari and measure what paints.

Companion to pdf_header_matrix.py, which pinned issue #1434 on the page's
`frame-ancestors 'none'`: Safari paints a blob: PDF iframe blank because the
blob document inherits that CSP. The fix serves every page `frame-ancestors
'self'`. Targets the production Next build (real middleware headers) served by
the workflow with the harness page from scripts/safari/harness/.

Each case opens a PDF the way the app does — a just-picked local file
(`local`, a blob: URL) or a saved file behind the same-origin proxy (`remote`,
fetched and re-wrapped as a blob by the dialog) — in the real
FilePreviewDialog, samples the iframe once a second, and judges `painted` from
the dark pixels inside its rectangle on a WebDriver screenshot. The `-again`
cases re-open the dialog on the same page. `control` is a bare blob: iframe.

Env: TARGET_URL (default http://localhost:3000), OUT_DIR, BROWSER=safari|chrome,
     EXPECT_PAINTED=1 to fail the run when a MUST_PAINT case ends unpainted.
"""

import json
import os
import pathlib
import sys
import time

from pdf_header_matrix import MIN_DARK_PIXELS, capture_viewer, make_driver
from selenium.webdriver.common.by import By

TARGET_URL = os.environ.get("TARGET_URL", "http://localhost:3000").rstrip("/")
OUT_DIR = pathlib.Path(os.environ.get("OUT_DIR", "safari-dialog"))
SAMPLE_SECONDS = 5
DIALOG_CLOSE_LABEL = "關閉"
HYDRATION_SECONDS = 6
DIALOG_FRAME = "iframe[data-source-url]"  # the dialog's PDF iframe
# (label, harness button suffix, painted-area selector, fresh page?)
CASES = [
    # A bare blob: PDF iframe on the real page: painted only if the page's
    # `frame-ancestors` is not `'none'` (#1434).
    ("control", "control", 'iframe[data-variant="control"]', True),
    ("local", "local", DIALOG_FRAME, True),
    ("remote", "remote", DIALOG_FRAME, True),
    ("local-again", "local", DIALOG_FRAME, False),
    ("remote-again", "remote", DIALOG_FRAME, False),
]
# Cases that leave a dialog open; the `-again` cases reuse the page, so it must
# be closed before the next case.
CLOSE_AFTER = {"local", "remote", "local-again", "remote-again"}
# Cases that must paint (EXPECT_PAINTED=1): the bare blob control plus both
# real-dialog paths, first open and re-open.
MUST_PAINT = {"control", "local", "remote", "local-again", "remote-again"}

ERROR_HOOK_SCRIPT = """
window.__errors = [];
window.addEventListener('error', e => window.__errors.push(String(e.message)));
window.addEventListener('unhandledrejection', e => window.__errors.push('rejection: ' + e.reason));
document.addEventListener('securitypolicyviolation', e =>
  window.__errors.push('csp: ' + e.violatedDirective + ' ' + e.blockedURI));
"""

STATE_SCRIPT = """
const frame = document.querySelector(arguments[0]);
return {
  has_iframe: !!frame,
  src_kind: frame ? (frame.getAttribute('src') || '').split(':')[0] : null,
  opacity: frame ? getComputedStyle(frame).opacity : null,
  skeleton: !!document.querySelector('[role=dialog] .animate-pulse'),
  errors: window.__errors || [],
};
"""


def open_variant(driver, button_suffix: str, selector: str) -> None:
    driver.find_element(By.ID, f"open-{button_suffix}").click()
    deadline = time.time() + 20
    while time.time() < deadline:
        if driver.find_elements(By.CSS_SELECTOR, selector):
            return
        time.sleep(0.25)
    dump_diagnostics(driver, f"no-iframe-after-{button_suffix}")
    raise RuntimeError(f"iframe {selector} never appeared after open-{button_suffix}")


def dump_diagnostics(driver, label: str) -> None:
    """A screenshot plus what the page saw, for a case that never got going."""
    driver.save_screenshot(str(OUT_DIR / f"{label}.png"))
    info = driver.execute_script(
        "const button = document.querySelector('button');"
        "return {errors: window.__errors || [], text: document.body.innerText.slice(0, 300),"
        " dialogs: document.querySelectorAll('[role=dialog]').length,"
        " hydrated: !!button && Object.keys(button).some(k => k.startsWith('__reactProps'))};"
    )
    print(f"[diagnostics] {label}: {json.dumps(info, ensure_ascii=False)}", flush=True)


def is_dialog_open(driver) -> bool:
    return bool(driver.find_elements(By.CSS_SELECTOR, "[role=dialog]"))


def close_dialog(driver) -> None:
    """Close via the 關閉 button (keyboard focus can be stuck inside the PDF
    viewer, so Escape is unreliable) and verify it went away."""
    main_handle = driver.window_handles[0]
    for handle in driver.window_handles[1:]:  # a stray "open in new window"
        driver.switch_to.window(handle)
        driver.close()
    driver.switch_to.window(main_handle)

    driver.execute_script(
        "[...document.querySelectorAll('[role=dialog] button')]"
        ".find(b => b.textContent.trim() === arguments[0])?.click();",
        DIALOG_CLOSE_LABEL,
    )
    time.sleep(1)
    if is_dialog_open(driver):
        dump_diagnostics(driver, "dialog-would-not-close")
        raise RuntimeError("dialog did not close")


def load_harness(driver) -> None:
    driver.get(f"{TARGET_URL}/safari-harness")
    driver.execute_script(ERROR_HOOK_SCRIPT)
    time.sleep(HYDRATION_SECONDS)


def run_case(driver, case_def) -> dict:
    label, button_suffix, selector, fresh_page = case_def
    case: dict = {"case": label, "timeline": []}
    if fresh_page:
        load_harness(driver)
    open_variant(driver, button_suffix, selector)
    for second in range(1, SAMPLE_SECONDS + 1):
        time.sleep(1)
        state = driver.execute_script(STATE_SCRIPT, selector)
        state["t"] = second
        case["timeline"].append(state)
    case.update(capture_viewer(driver, OUT_DIR / label, selector=selector))
    dark = case.get("dark_pixels")
    case["painted"] = None if dark is None else dark >= MIN_DARK_PIXELS
    last = case["timeline"][-1]
    print(
        f"[case] {label}: painted={case['painted']} dark={dark} "
        f"opacity={last['opacity']} skeleton={last['skeleton']} src={last['src_kind']}",
        flush=True,
    )
    if label in CLOSE_AFTER:
        close_dialog(driver)
    return case


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    driver = make_driver()
    cases = []
    try:
        print(
            f"[env] {driver.capabilities.get('browserName')} {driver.capabilities.get('browserVersion')}",
            flush=True,
        )
        for case_def in CASES:
            try:
                cases.append(run_case(driver, case_def))
            except Exception as exc:  # keep going: one broken variant must not hide the rest
                print(f"[case] {case_def[0]}: ERROR {type(exc).__name__}: {exc}", flush=True)
                cases.append({"case": case_def[0], "painted": None, "error": str(exc)})
    finally:
        driver.quit()
    (OUT_DIR / "results.json").write_text(json.dumps(cases, indent=2, ensure_ascii=False))
    print("\ncase           painted  dark_px")
    for case in cases:
        print(f"{case['case']:<14} {str(case['painted']):<8} {case.get('dark_pixels')}")
    if os.environ.get("EXPECT_PAINTED") == "1":
        unpainted = [c["case"] for c in cases if c["case"] in MUST_PAINT and not c["painted"]]
        if unpainted:
            print(f"FAIL: expected painted, got blank/error: {unpainted}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

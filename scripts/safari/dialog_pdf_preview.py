"""Drive the REAL FilePreviewDialog in real Safari and measure what paints.

Companion to pdf_header_matrix.py (which showed the response headers are NOT
the cause of issue #1434). Targets the production Next build served by the
workflow with the harness page from scripts/safari/harness/.

Per case (open local blob / open remote proxy URL, first open and re-open) it
samples the dialog's iframe once a second for SAMPLE_SECONDS: is the skeleton
still up, the iframe's computed opacity, and the dark-pixel count of a native
screencapture of the iframe rectangle. The verdict is `painted` at the end.

Env: TARGET_URL (default http://localhost:3000), OUT_DIR, BROWSER=safari|chrome,
     EXPECT_PAINTED=1 to fail the run when any case ends unpainted.
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
SAMPLE_SECONDS = 8
IFRAME_SELECTOR = "iframe[data-source-url]"
DIALOG_CLOSE_LABEL = "關閉"

HYDRATION_SECONDS = 6
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


def open_dialog(driver, button_id: str) -> None:
    driver.find_element(By.ID, button_id).click()
    deadline = time.time() + 20
    while time.time() < deadline:
        if driver.find_elements(By.CSS_SELECTOR, IFRAME_SELECTOR):
            return
        time.sleep(0.25)
    dump_diagnostics(driver, f"no-dialog-after-{button_id}")
    raise RuntimeError(f"dialog iframe never appeared after #{button_id}")


def dump_diagnostics(driver, label: str) -> None:
    """A screenshot plus what the page saw, for a case that never got going."""
    driver.save_screenshot(str(OUT_DIR / f"{label}.png"))
    info = driver.execute_script(
        "return {errors: window.__errors || [], text: document.body.innerText.slice(0, 500),"
        " dialogs: document.querySelectorAll('[role=dialog]').length};"
    )
    print(f"[diagnostics] {label}: {json.dumps(info, ensure_ascii=False)}", flush=True)


def close_dialog(driver) -> None:
    driver.execute_script("document.querySelector('[role=dialog]')" f"?.querySelector('button:last-of-type')?.click();")
    driver.execute_script("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));")
    time.sleep(1)


def run_case(driver, label: str, button_id: str) -> dict:
    case: dict = {"case": label, "timeline": []}
    open_dialog(driver, button_id)
    for second in range(1, SAMPLE_SECONDS + 1):
        time.sleep(1)
        state = driver.execute_script(STATE_SCRIPT, IFRAME_SELECTOR)
        state["t"] = second
        case["timeline"].append(state)
    case.update(capture_viewer(driver, OUT_DIR / label, selector=IFRAME_SELECTOR))
    dark = case.get("dark_pixels")
    case["painted"] = None if dark is None else dark >= MIN_DARK_PIXELS
    last = case["timeline"][-1]
    print(
        f"[case] {label}: painted={case['painted']} dark={dark} "
        f"opacity={last['opacity']} skeleton={last['skeleton']} src={last['src_kind']}",
        flush=True,
    )
    close_dialog(driver)
    return case


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    driver = make_driver()
    cases = []
    try:
        print(
            f"[env] {driver.capabilities.get('browserName')} " f"{driver.capabilities.get('browserVersion')}",
            flush=True,
        )
        driver.get(f"{TARGET_URL}/safari-harness")
        driver.execute_script(ERROR_HOOK_SCRIPT)
        time.sleep(HYDRATION_SECONDS)
        for label, button in [
            ("local-first", "open-local"),
            ("local-second", "open-local"),
            ("remote-first", "open-remote"),
            ("remote-second", "open-remote"),
        ]:
            cases.append(run_case(driver, label, button))
    finally:
        driver.quit()
    (OUT_DIR / "results.json").write_text(json.dumps(cases, indent=2, ensure_ascii=False))
    print("\ncase           painted  dark_px")
    for case in cases:
        print(f"{case['case']:<14} {str(case['painted']):<8} {case.get('dark_pixels')}")
    if os.environ.get("EXPECT_PAINTED") == "1" and not all(c["painted"] for c in cases):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

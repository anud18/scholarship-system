"""Walk the student wizard in a real browser and screenshot the upload preview.

Built for the macOS GitHub runner (real Safari via safaridriver), runnable
locally with BROWSER=chrome for debugging. Flow (student 315551401 by default):

    mock-SSO login → 獎學金申請 → read 獎學金要點 → agree → confirm SIS data
    → pick 博士生獎學金 → attach a PDF (doc slot) + PNG (存摺封面)
    → preview each (local blob: URL) → 暫存草稿 → preview the PDF again
    → reopen the draft (編輯) → preview again, now served by /api/v1/preview

Every step writes a numbered screenshot to OUT_DIR, and results.json records
what each preview dialog actually rendered (iframe/img src, error text).

Env: TARGET_URL (required), STUDENT_ID, OUT_DIR, BROWSER=safari|chrome,
     CHROME_BINARY (optional, chrome only).
"""

import base64
import json
import os
import pathlib
import subprocess
import sys
import time
import traceback

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE_URL = os.environ["TARGET_URL"].rstrip("/")
STUDENT_ID = os.environ.get("STUDENT_ID", "315551401")
OUT_DIR = pathlib.Path(os.environ.get("OUT_DIR", "safari-shots"))
BROWSER = os.environ.get("BROWSER", "safari")
SCHOLARSHIP_LABEL = os.environ.get("SCHOLARSHIP_LABEL", "博士生獎學金")

DEFAULT_TIMEOUT = 60
PREVIEW_SETTLE_SECONDS = 6
PDF_NAME = "safari-transcript.pdf"
PNG_NAME = "safari-passbook.png"

# A one-page PDF with visible text so a rendered preview is recognisable.
PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 400 300]"
    b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    b"4 0 obj<</Length 53>>stream\n"
    b"BT /F1 28 Tf 40 150 Td (SAFARI PDF PREVIEW OK) Tj ET\n"
    b"endstream endobj\n"
    b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)
# 2x2 red PNG — scaled up by the <img>, clearly visible when it renders.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP4z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg=="
)

results: dict = {"browser": BROWSER, "student": STUDENT_ID, "steps": [], "previews": []}
_shot_counter = 0


def make_driver() -> webdriver.Remote:
    if BROWSER == "safari":
        driver = webdriver.Safari()
    else:
        options = webdriver.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--ignore-certificate-errors")
        options.accept_insecure_certs = True
        if os.environ.get("CHROME_BINARY"):
            options.binary_location = os.environ["CHROME_BINARY"]
        driver = webdriver.Chrome(options=options)
    driver.set_window_rect(0, 0, 1440, 1000)
    return driver


def shot(driver, name: str) -> None:
    """Browser screenshot, plus on macOS a native capture of the page area
    (shows the PDF plugin even if the WebDriver snapshot leaves it blank).
    The native capture is cropped to the viewport so the address bar — and
    with it the target host — never lands in a public artifact."""
    global _shot_counter
    _shot_counter += 1
    base = OUT_DIR / f"{_shot_counter:02d}-{name}"
    try:
        driver.save_screenshot(f"{base}.png")
    except WebDriverException as exc:
        print(f"[shot] browser screenshot failed for {name}: {exc}")
    if sys.platform == "darwin":
        x, y, width, height = driver.execute_script(
            "return [screenX, screenY + outerHeight - innerHeight, innerWidth, innerHeight];"
        )
        region = f"{x},{y},{width},{height}"
        subprocess.run(["screencapture", "-x", "-R", region, f"{base}-screen.png"], check=False)


def step(name: str, detail: str = "") -> None:
    print(f"[step] {name} {detail}".rstrip(), flush=True)
    results["steps"].append({"name": name, "detail": detail, "t": round(time.time(), 1)})


def wait_for(driver, fn, timeout: int = DEFAULT_TIMEOUT, what: str = "condition"):
    try:
        return WebDriverWait(driver, timeout, poll_frequency=0.5).until(lambda d: fn(d))
    except TimeoutException as exc:
        raise TimeoutException(f"timed out waiting for {what}") from exc


def find_xpath(driver, xpath: str):
    elements = driver.find_elements(By.XPATH, xpath)
    visible = [e for e in elements if e.is_displayed()]
    return visible[0] if visible else None


def click(driver, element) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    try:
        element.click()
    except WebDriverException:
        driver.execute_script("arguments[0].click();", element)


def click_button_text(driver, text: str, timeout: int = DEFAULT_TIMEOUT) -> None:
    xpath = f"//button[contains(normalize-space(.), '{text}') and not(@disabled)]"
    button = wait_for(driver, lambda d: find_xpath(d, xpath), timeout, f"button「{text}」")
    click(driver, button)


def press_escape(driver) -> None:
    ActionChains(driver).send_keys(Keys.ESCAPE).perform()
    time.sleep(1)


def close_dialog(driver) -> None:
    """Click the dialog's own 關閉 button: once a PDF iframe has focus the
    Escape key goes to the embedded viewer and the dialog stays open."""
    driver.execute_script("""
        const dialog = [...document.querySelectorAll('[role=dialog]')].pop();
        if (!dialog) return;
        const buttons = [...dialog.querySelectorAll('button')];
        const close = buttons.find(b => b.textContent.trim() === '關閉')
          || buttons.find(b => (b.getAttribute('aria-label') || '').match(/close|關閉/i))
          || buttons.find(b => b.querySelector('svg.lucide-x'));
        if (close) close.click();
        """)
    wait_for(driver, lambda d: not find_xpath(d, "//*[@role='dialog']"), timeout=15, what="dialog to close")


def login(driver) -> None:
    driver.get(f"{BASE_URL}/")
    wait_for(driver, lambda d: d.execute_script("return document.readyState") == "complete", what="page load")
    outcome = driver.execute_async_script(
        """
        const [nycuId, done] = arguments;
        fetch('/api/v1/auth/mock-sso/login', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({nycu_id: nycuId}),
        }).then(r => r.json()).then(body => {
          const data = body.data || {};
          if (!data.access_token) { done('ERR ' + JSON.stringify(body)); return; }
          localStorage.setItem('auth_token', data.access_token);
          localStorage.setItem('token', data.access_token);
          localStorage.setItem('user', JSON.stringify(data.user));
          done('ok');
        }).catch(e => done('ERR ' + e));
        """,
        STUDENT_ID,
    )
    if outcome != "ok":
        raise RuntimeError(f"mock login failed: {outcome}")
    step("login", STUDENT_ID)
    delete_own_drafts(driver)
    driver.get(f"{BASE_URL}/")


def delete_own_drafts(driver) -> None:
    """Drop drafts a previous run left behind so the wizard starts fresh."""
    outcome = driver.execute_async_script("""
        const done = arguments[0];
        const headers = {Authorization: 'Bearer ' + localStorage.getItem('auth_token')};
        fetch('/api/v1/applications?status=draft', {headers})
          .then(r => r.json())
          .then(body => Promise.all((body.data || []).map(app =>
            fetch('/api/v1/applications/' + app.id, {method: 'DELETE', headers}).then(r => app.app_id + ':' + r.status))))
          .then(deleted => done(deleted.join(',') || 'none'))
          .catch(e => done('ERR ' + e));
        """)
    step("delete-old-drafts", str(outcome))


def reopen_draft(driver) -> None:
    driver.get(f"{BASE_URL}/")
    tab = wait_for(
        driver,
        lambda d: find_xpath(d, "//*[@role='tab' and contains(normalize-space(.), '我的申請紀錄')]"),
        timeout=120,
        what="我的申請紀錄 tab",
    )
    click(driver, tab)
    click_button_text(driver, "編輯")
    wait_for(
        driver,
        lambda d: find_xpath(d, f"//*[normalize-space(text())='{PDF_NAME}']"),
        timeout=60,
        what="saved file listed",
    )
    time.sleep(2)
    shot(driver, "draft-reopened")
    step("draft-reopened")


def read_regulations(driver) -> None:
    click_button_text(driver, "閱讀獎學金要點", timeout=120)
    wait_for(
        driver,
        lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid=pdf-scroll-container]"),
        what="regulations PDF viewer",
    )
    time.sleep(3)
    shot(driver, "regulations-open")

    def scrolled_to_end(d) -> bool:
        d.execute_script("""
            const el = document.querySelector('[data-testid=pdf-scroll-container]');
            if (el) { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event('scroll')); }
            """)
        box = d.find_elements(By.ID, "read-notice")
        return bool(box) and box[0].get_attribute("data-state") == "checked"

    wait_for(driver, scrolled_to_end, timeout=90, what="#read-notice to become checked")
    press_escape(driver)
    step("regulations-read")


def agree_and_continue(driver) -> None:
    agree = wait_for(
        driver, lambda d: find_xpath(d, "//button[@id='agree-terms' and not(@disabled)]"), what="#agree-terms"
    )
    click(driver, agree)
    click_button_text(driver, "同意並繼續")
    step("agreed")
    click_button_text(driver, "確認資料無誤", timeout=120)
    step("student-data-confirmed")


def select_scholarship(driver) -> None:
    trigger = wait_for(
        driver, lambda d: find_xpath(d, "//button[@role='combobox']"), timeout=90, what="scholarship select"
    )
    click(driver, trigger)
    time.sleep(1)
    shot(driver, "scholarship-options")
    option = wait_for(
        driver,
        lambda d: find_xpath(d, f"//*[@role='option' and contains(normalize-space(.), '{SCHOLARSHIP_LABEL}')]")
        or find_xpath(d, "//*[@role='option']"),
        what="scholarship option",
    )
    step("scholarship-selected", option.text.strip())
    click(driver, option)
    wait_for(
        driver, lambda d: len(d.find_elements(By.CSS_SELECTOR, "input[type=file]")) >= 2, timeout=90, what="file inputs"
    )
    time.sleep(2)
    shot(driver, "application-form")


def attach_file(driver, input_index: int, name: str, mime: str, payload: bytes) -> None:
    """Set a File on an <input type=file> through DataTransfer and fire the
    change event React listens to. safaridriver cannot send_keys a path."""
    outcome = driver.execute_script(
        """
        const [index, name, mime, b64] = arguments;
        const inputs = [...document.querySelectorAll('input[type=file]')];
        const input = index < 0 ? inputs[inputs.length + index] : inputs[index];
        if (!input) return 'no input at ' + index + ' of ' + inputs.length;
        const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
        const transfer = new DataTransfer();
        transfer.items.add(new File([bytes], name, {type: mime}));
        input.files = transfer.files;
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
        return 'ok accept=' + (input.accept || '');
        """,
        input_index,
        name,
        mime,
        base64.b64encode(payload).decode(),
    )
    step("attach", f"{name} → input[{input_index}]: {outcome}")
    if not str(outcome).startswith("ok"):
        raise RuntimeError(f"attach {name} failed: {outcome}")
    wait_for(
        driver,
        lambda d: find_xpath(d, f"//*[normalize-space(text())='{name}']"),
        timeout=30,
        what=f"{name} listed after attach",
    )


def open_preview(driver, file_name: str, label: str) -> None:
    button = wait_for(
        driver,
        lambda d: d.execute_script(
            """
            const name = arguments[0];
            const label = [...document.querySelectorAll('p, span')].find(e => e.textContent.trim() === name);
            if (!label) return null;
            let node = label;
            while (node && !(node.querySelector && node.querySelector('button svg.lucide-eye'))) node = node.parentElement;
            return node ? node.querySelector('button svg.lucide-eye').closest('button') : null;
            """,
            file_name,
        ),
        timeout=30,
        what=f"preview button for {file_name}",
    )
    click(driver, button)
    wait_for(driver, lambda d: find_xpath(d, "//*[@role='dialog']"), timeout=30, what="preview dialog")
    time.sleep(PREVIEW_SETTLE_SECONDS)
    info = driver.execute_script("""
        const dialog = [...document.querySelectorAll('[role=dialog]')].pop();
        const frame = dialog.querySelector('iframe, embed, object');
        const img = dialog.querySelector('img');
        const text = dialog.innerText || '';
        return {
          iframe_src: frame ? (frame.src || frame.data || '') : null,
          img_src: img ? img.src : null,
          img_loaded: img ? (img.complete && img.naturalWidth > 0) : null,
          error_text: /無法載入|載入失敗|error|錯誤/i.test(text) ? text.slice(0, 300) : null,
          // A saved file is fetched through the /api/v1/preview proxy and then
          // shown as a blob:, so the iframe src alone cannot tell the paths apart.
          preview_proxy_fetches: performance.getEntriesByType('resource')
            .filter(e => e.name.includes('/api/v1/preview?')).length,
        };
        """)
    info.update({"label": label, "file": file_name})
    results["previews"].append(info)
    step("preview", json.dumps(info, ensure_ascii=False))
    shot(driver, f"preview-{label}")
    close_dialog(driver)


def save_draft(driver) -> None:
    click_button_text(driver, "暫存草稿")
    time.sleep(8)
    shot(driver, "draft-saved")
    step("draft-saved")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    driver = make_driver()
    exit_code = 0
    try:
        results["user_agent"] = driver.execute_script("return navigator.userAgent")
        login(driver)
        tab = wait_for(
            driver,
            lambda d: find_xpath(d, "//*[@role='tab' and contains(normalize-space(.), '獎學金申請')]"),
            timeout=120,
            what="獎學金申請 tab",
        )
        shot(driver, "dashboard")
        click(driver, tab)
        read_regulations(driver)
        agree_and_continue(driver)
        select_scholarship(driver)
        attach_file(driver, -1, PDF_NAME, "application/pdf", PDF_BYTES)
        attach_file(driver, 0, PNG_NAME, "image/png", PNG_BYTES)
        shot(driver, "files-attached")
        open_preview(driver, PDF_NAME, "pdf-local")
        open_preview(driver, PNG_NAME, "png-local")
        save_draft(driver)
        reopen_draft(driver)
        open_preview(driver, PDF_NAME, "pdf-reopened")
    except Exception:  # noqa: BLE001 - capture evidence for any failure
        exit_code = 1
        results["error"] = traceback.format_exc()
        print(results["error"], file=sys.stderr)
        shot(driver, "failure")
    finally:
        # Artifacts of a public repo are public: keep the target host out.
        report = json.dumps(results, ensure_ascii=False, indent=2).replace(BASE_URL, "<target>")
        (OUT_DIR / "results.json").write_text(report)
        driver.quit()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

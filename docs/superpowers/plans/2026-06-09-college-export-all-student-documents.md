# Include All Student-Uploaded Documents in College 申請資料 ZIP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the college 申請資料 ZIP export bundle every student-uploaded document — add the missing 申請文件 (`application_document_url`) and correctly label the cloned 存摺封面.

**Architecture:** All changes live in one backend service module, `backend/app/services/export_package_service.py`. We add three module-level pure helpers (extension derivation, the 申請文件 ZIP-entry descriptor, and a MinIO fetch-and-write), refactor the existing `app.files` loop to use the fetch helper (behavior preserved), then append the 申請文件 to each student's folder by composing the helpers. The query already loads everything needed — no DB/query/schema/API/frontend changes.

**Tech Stack:** Python 3, FastAPI, SQLAlchemy (async), MinIO, reportlab, pytest. zh-TW UI strings.

---

## Background (read first)

The ZIP builder `ExportPackageService._add_application_to_zip` currently writes, per student folder: a summary PDF, then every `ApplicationFile` in `app.files`. Two student-uploaded sources are wrong:

1. **申請文件 missing.** `POST /applications/{id}/application-document` (`backend/app/api/v1/endpoints/applications.py:937`, `require_student`) stores a student-uploaded PDF on `application.application_document_url` + `application.application_document_original_filename` — **not** as an `ApplicationFile`. The ZIP never reads it.
2. **存摺封面 mislabeled.** The cloned passbook is an `ApplicationFile` with `file_type = "bank_account_proof"` (`application_service.py:2118`), but `FILE_TYPE_LABELS` only maps `"bank_account_cover"`, so it falls through to the `"其他文件"` default.

`MinIOService.get_file_stream(object_name)` reads from `self.default_bucket` — the same bucket the 申請文件 is written to — and raises `HTTPException(404)` (an `Exception` subclass) on a missing object, so the existing `except Exception` fallback already handles a missing 申請文件 gracefully.

### Current code being refactored

`backend/app/services/export_package_service.py`, inside `_add_application_to_zip`, the per-file block (≈ lines 217–253) currently inlines the MinIO fetch + write + error fallback:

```python
        # Add uploaded files from ApplicationFile records
        type_totals = Counter(af.file_type or "other" for af in app.files)
        file_type_counter: Dict[str, int] = defaultdict(int)
        for af in app.files:
            ft = af.file_type or "other"
            file_type_counter[ft] += 1
            count = file_type_counter[ft]
            label = FILE_TYPE_LABELS.get(ft, "其他文件")

            # Determine file extension from original filename or mime_type
            ext = ""
            if af.original_filename and "." in af.original_filename:
                ext = "." + af.original_filename.rsplit(".", 1)[1]
            elif af.mime_type and "/" in af.mime_type:
                ext_map = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
                ext = ext_map.get(af.mime_type, "")

            # Add sequence number only if multiple files of same type
            if type_totals[ft] > 1:
                filename = f"{student_prefix}_{label}_{count}{ext}"
            else:
                filename = f"{student_prefix}_{label}{ext}"

            try:
                response = await asyncio.to_thread(self.minio.get_file_stream, af.object_name)
                try:
                    file_bytes = await asyncio.to_thread(response.read)
                finally:
                    response.close()
                    response.release_conn()
                zf.writestr(f"{base_path}/{_sanitize_filename(filename)}", file_bytes)
            except Exception as e:
                logger.exception(f"Failed to fetch file {af.object_name} for app {app.id}")
                zf.writestr(
                    f"{base_path}/_錯誤_找不到檔案_{_sanitize_filename(label)}.txt",
                    f"檔案下載失敗：{af.original_filename or af.object_name}\n錯誤：{str(e)}",
                )
```

### Test-suite routing (important)

CI splits tests: the **unit** suite runs `app/tests/test_*.py -m "not integration and not asyncio"`; the **integration** suite runs only `app/tests/test_*_service*.py -m "integration or asyncio"`. `test_export_package_pure_helpers.py` does **not** match `*_service*`, so an `async def test_` there would be collected by **neither** suite and silently never run. **Rule for this plan: every test in that file stays a plain `def` (sync).** The one async helper is exercised by calling `asyncio.run(...)` inside a sync test.

### Running the tests

These are pure-import tests (no live DB). Run in the backend dev container:

```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py -p no:cacheprovider -v
```

If the container mounts a different checkout than this worktree, run locally instead with the env vars from the `backend_local_pytest_env` memory note (`DATABASE_URL`, `DATABASE_URL_SYNC`, `SECRET_KEY`, `MINIO_*`) from `backend/`.

### Lint gates (run before the final commit)

```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app/services/export_package_service.py backend/app/tests/test_export_package_pure_helpers.py
flake8 app --select=B904,B014 --max-line-length=120
```

---

## File Structure

- **Modify** `backend/app/services/export_package_service.py`
  - `FILE_TYPE_LABELS` — add `"bank_account_proof": "存摺封面"`.
  - New module-level `_ext_for_application_document(original_filename, object_name) -> str`.
  - New module-level `_application_document_entry(object_name, original_filename, base_path, student_prefix) -> Optional[dict]`.
  - New module-level `async _fetch_and_write(zf, minio, object_name, zip_path, error_path, error_label) -> None`.
  - `_add_application_to_zip` — refactor the `app.files` loop to call `_fetch_and_write`; append the 申請文件 block.
- **Modify** `backend/app/tests/test_export_package_pure_helpers.py`
  - Update the `FILE_TYPE_LABELS` pin (8 → 9 keys) + add `bank_account_proof` label assertion.
  - New tests for `_ext_for_application_document`, `_application_document_entry`, `_fetch_and_write`.

---

## Task 1: Fix the 存摺封面 label

**Files:**
- Modify: `backend/app/tests/test_export_package_pure_helpers.py` (class `TestFileTypeLabels`)
- Modify: `backend/app/services/export_package_service.py` (`FILE_TYPE_LABELS`)

- [ ] **Step 1: Update the pin test to expect the new key**

In `backend/app/tests/test_export_package_pure_helpers.py`, replace the `test_all_8_known_file_types_present` method (inside `class TestFileTypeLabels`) with:

```python
    def test_all_9_known_file_types_present(self):
        # Pin: exactly 9 file types. bank_account_proof is the
        # value actually stored on the cloned passbook
        # ApplicationFile (application_service.py:2118); it must
        # have a label or it falls through to the 其他文件 default.
        expected_keys = {
            "transcript",
            "research_proposal",
            "recommendation_letter",
            "certificate",
            "insurance_record",
            "agreement",
            "bank_account_cover",
            "bank_account_proof",
            "other",
        }
        assert set(FILE_TYPE_LABELS.keys()) == expected_keys
```

Then, immediately after the existing `test_bank_account_cover_label` method, add:

```python
    def test_bank_account_proof_label(self):
        # Pin: the cloned passbook's real file_type
        # (bank_account_proof) maps to 存摺封面 so it stops landing
        # under 其他文件 in the export ZIP.
        assert FILE_TYPE_LABELS["bank_account_proof"] == "存摺封面"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py::TestFileTypeLabels -p no:cacheprovider -v
```
Expected: FAIL — `test_all_9_known_file_types_present` (set inequality: actual is missing `bank_account_proof`) and `test_bank_account_proof_label` (KeyError).

- [ ] **Step 3: Add the label**

In `backend/app/services/export_package_service.py`, change the `FILE_TYPE_LABELS` dict so the bank entry reads:

```python
    "bank_account_cover": "存摺封面",
    "bank_account_proof": "存摺封面",  # value actually stored on the cloned passbook ApplicationFile
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py::TestFileTypeLabels -p no:cacheprovider -v
```
Expected: PASS (all `TestFileTypeLabels` tests green).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/export_package_service.py backend/app/tests/test_export_package_pure_helpers.py
git commit -m "fix: label cloned passbook as 存摺封面 in college 申請資料 ZIP"
```

---

## Task 2: Add `_ext_for_application_document` pure helper

**Files:**
- Modify: `backend/app/tests/test_export_package_pure_helpers.py` (new test class + import)
- Modify: `backend/app/services/export_package_service.py` (new module-level function)

- [ ] **Step 1: Write the failing tests**

In `backend/app/tests/test_export_package_pure_helpers.py`, extend the import at the top of the file:

```python
from app.services.export_package_service import (
    _sanitize_filename,
    _ext_for_application_document,
    FILE_TYPE_LABELS,
    DEGREE_LABELS,
)
```

Then add this new test class at the end of the file:

```python
class TestExtForApplicationDocument:
    """Pin: extension derivation for the student-uploaded 申請文件.
    Prefers the original filename's extension, falls back to the
    stored MinIO object name's suffix."""

    def test_uses_original_filename_extension(self):
        assert (
            _ext_for_application_document("申請文件.pdf", "application-documents/12_x.pdf")
            == ".pdf"
        )

    def test_original_filename_extension_wins_over_object_name(self):
        assert (
            _ext_for_application_document("draft.docx", "application-documents/12_x.pdf")
            == ".docx"
        )

    def test_falls_back_to_object_name_when_no_original(self):
        assert (
            _ext_for_application_document(None, "application-documents/12_x.pdf") == ".pdf"
        )

    def test_empty_original_falls_back_to_object_name(self):
        assert (
            _ext_for_application_document("", "application-documents/12_x.pdf") == ".pdf"
        )

    def test_returns_empty_when_no_extension_anywhere(self):
        assert _ext_for_application_document("noext", "application-documents/12_x") == ""

    def test_directory_dot_not_mistaken_for_extension(self):
        # A dot in a directory segment must not be treated as the
        # file extension — only the last path segment counts.
        assert _ext_for_application_document(None, "v1.2/objectname") == ""
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py::TestExtForApplicationDocument -p no:cacheprovider -v
```
Expected: FAIL at import — `ImportError: cannot import name '_ext_for_application_document'`.

- [ ] **Step 3: Implement the helper**

In `backend/app/services/export_package_service.py`, add this module-level function directly below the existing `_sanitize_filename` function:

```python
def _ext_for_application_document(original_filename: Optional[str], object_name: str) -> str:
    """Extension (with leading dot) for the student-uploaded 申請文件.

    Prefers the original filename's extension, falls back to the stored
    object name's suffix. Only the last path segment is inspected, so a dot
    in a directory name is never mistaken for an extension.
    """
    for source in (original_filename, object_name):
        if source:
            last_segment = source.rsplit("/", 1)[-1]
            if "." in last_segment:
                return "." + last_segment.rsplit(".", 1)[1]
    return ""
```

(`Optional` is already imported at the top of the module via `from typing import Dict, List, Optional, Tuple`.)

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py::TestExtForApplicationDocument -p no:cacheprovider -v
```
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/export_package_service.py backend/app/tests/test_export_package_pure_helpers.py
git commit -m "feat: add _ext_for_application_document helper for 申請文件 export"
```

---

## Task 3: Add `_application_document_entry` pure helper

**Files:**
- Modify: `backend/app/tests/test_export_package_pure_helpers.py` (new test class + import)
- Modify: `backend/app/services/export_package_service.py` (new module-level function)

- [ ] **Step 1: Write the failing tests**

Extend the import in `backend/app/tests/test_export_package_pure_helpers.py`:

```python
from app.services.export_package_service import (
    _sanitize_filename,
    _ext_for_application_document,
    _application_document_entry,
    FILE_TYPE_LABELS,
    DEGREE_LABELS,
)
```

Add this test class at the end of the file:

```python
class TestApplicationDocumentEntry:
    """Pin: descriptor for placing the student-uploaded 申請文件 into
    the ZIP. Returns None when the application has no 申請文件."""

    def test_returns_none_when_no_object_name(self):
        assert (
            _application_document_entry(None, "x.pdf", "117_資工系", "310_王小明") is None
        )

    def test_returns_none_when_object_name_empty(self):
        assert (
            _application_document_entry("", "x.pdf", "117_資工系", "310_王小明") is None
        )

    def test_builds_entry_with_expected_paths(self):
        entry = _application_document_entry(
            "application-documents/12_x.pdf",
            "申請文件.pdf",
            "117_資工系",
            "310_王小明",
        )
        assert entry == {
            "object_name": "application-documents/12_x.pdf",
            "zip_path": "117_資工系/310_王小明_申請文件.pdf",
            "error_path": "117_資工系/_錯誤_找不到檔案_申請文件.txt",
            "error_label": "申請文件.pdf",
        }

    def test_error_label_falls_back_to_object_name(self):
        entry = _application_document_entry(
            "application-documents/12_x.pdf", None, "117_資工系", "310_王小明"
        )
        assert entry["error_label"] == "application-documents/12_x.pdf"

    def test_zip_filename_is_sanitized(self):
        # A student name containing a path separator must not escape
        # the student folder (ZIP path-traversal guard).
        entry = _application_document_entry(
            "application-documents/12_x.pdf", "x.pdf", "117_資工系", "310_a/b"
        )
        assert "/" not in entry["zip_path"].rsplit("/", 1)[-1]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py::TestApplicationDocumentEntry -p no:cacheprovider -v
```
Expected: FAIL at import — `ImportError: cannot import name '_application_document_entry'`.

- [ ] **Step 3: Implement the helper**

In `backend/app/services/export_package_service.py`, add this module-level function directly below `_ext_for_application_document`:

```python
def _application_document_entry(
    object_name: Optional[str],
    original_filename: Optional[str],
    base_path: str,
    student_prefix: str,
) -> Optional[Dict[str, str]]:
    """Describe where the student-uploaded 申請文件 goes in the ZIP.

    Returns None when the application has no 申請文件. Otherwise returns the
    kwargs for `_fetch_and_write`: the source object name, the sanitized ZIP
    path, the error-placeholder path, and a human label for the error text.
    """
    if not object_name:
        return None
    ext = _ext_for_application_document(original_filename, object_name)
    filename = _sanitize_filename(f"{student_prefix}_申請文件{ext}")
    return {
        "object_name": object_name,
        "zip_path": f"{base_path}/{filename}",
        "error_path": f"{base_path}/_錯誤_找不到檔案_申請文件.txt",
        "error_label": original_filename or object_name,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py::TestApplicationDocumentEntry -p no:cacheprovider -v
```
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/export_package_service.py backend/app/tests/test_export_package_pure_helpers.py
git commit -m "feat: add _application_document_entry descriptor for 申請文件 export"
```

---

## Task 4: Add `_fetch_and_write` helper and refactor the `app.files` loop

**Files:**
- Modify: `backend/app/tests/test_export_package_pure_helpers.py` (new test class + import)
- Modify: `backend/app/services/export_package_service.py` (new module-level async function + loop refactor)

- [ ] **Step 1: Write the failing tests**

Extend the import in `backend/app/tests/test_export_package_pure_helpers.py`:

```python
from app.services.export_package_service import (
    _sanitize_filename,
    _ext_for_application_document,
    _application_document_entry,
    _fetch_and_write,
    FILE_TYPE_LABELS,
    DEGREE_LABELS,
)
```

Add this test class at the end of the file. Note it is a **sync** `def` test that drives the async helper via `asyncio.run` — see the "Test-suite routing" note above for why no `async def` is allowed in this file:

```python
class TestFetchAndWrite:
    """Pin: the shared MinIO fetch-and-write used by both the
    app.files loop and the 申請文件. On success the bytes land at
    zip_path; on any MinIO error a placeholder .txt lands at
    error_path instead (the ZIP build never aborts)."""

    def test_success_writes_bytes_and_releases_connection(self):
        import asyncio
        import io
        import zipfile
        from unittest.mock import MagicMock

        fake_response = MagicMock()
        fake_response.read.return_value = b"PDF-BYTES"
        minio = MagicMock()
        minio.get_file_stream.return_value = fake_response

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            asyncio.run(
                _fetch_and_write(
                    zf,
                    minio,
                    object_name="application-documents/12_x.pdf",
                    zip_path="dept/stu/stu_申請文件.pdf",
                    error_path="dept/stu/_錯誤_找不到檔案_申請文件.txt",
                    error_label="申請文件.pdf",
                )
            )

        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            assert zf.read("dept/stu/stu_申請文件.pdf") == b"PDF-BYTES"
            assert "dept/stu/_錯誤_找不到檔案_申請文件.txt" not in zf.namelist()
        fake_response.close.assert_called_once()
        fake_response.release_conn.assert_called_once()

    def test_failure_writes_error_placeholder(self):
        import asyncio
        import io
        import zipfile
        from unittest.mock import MagicMock

        minio = MagicMock()
        minio.get_file_stream.side_effect = Exception("object missing")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            asyncio.run(
                _fetch_and_write(
                    zf,
                    minio,
                    object_name="application-documents/12_x.pdf",
                    zip_path="dept/stu/stu_申請文件.pdf",
                    error_path="dept/stu/_錯誤_找不到檔案_申請文件.txt",
                    error_label="申請文件.pdf",
                )
            )

        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "dept/stu/stu_申請文件.pdf" not in names
            assert "dept/stu/_錯誤_找不到檔案_申請文件.txt" in names
            content = zf.read("dept/stu/_錯誤_找不到檔案_申請文件.txt").decode("utf-8")
            assert "object missing" in content
            assert "申請文件.pdf" in content
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py::TestFetchAndWrite -p no:cacheprovider -v
```
Expected: FAIL at import — `ImportError: cannot import name '_fetch_and_write'`.

- [ ] **Step 3: Implement the helper**

In `backend/app/services/export_package_service.py`, add this module-level async function directly below `_application_document_entry`:

```python
async def _fetch_and_write(
    zf: zipfile.ZipFile,
    minio: MinIOService,
    object_name: str,
    zip_path: str,
    error_path: str,
    error_label: str,
) -> None:
    """Stream one MinIO object into the ZIP at `zip_path`.

    On any failure, writes a `_錯誤_…txt` placeholder at `error_path`
    instead so a single bad object never aborts the whole ZIP build.
    """
    try:
        response = await asyncio.to_thread(minio.get_file_stream, object_name)
        try:
            file_bytes = await asyncio.to_thread(response.read)
        finally:
            response.close()
            response.release_conn()
        zf.writestr(zip_path, file_bytes)
    except Exception as e:
        logger.exception(f"Failed to fetch file {object_name}")
        zf.writestr(error_path, f"檔案下載失敗：{error_label}\n錯誤：{str(e)}")
```

- [ ] **Step 4: Run the new tests to verify they pass**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py::TestFetchAndWrite -p no:cacheprovider -v
```
Expected: PASS (2 tests).

- [ ] **Step 5: Refactor the `app.files` loop to use the helper**

In `backend/app/services/export_package_service.py`, inside `_add_application_to_zip`, replace the `try/except` block at the end of the `for af in app.files:` loop (the block shown in "Current code being refactored" above) with a single call:

```python
            await _fetch_and_write(
                zf,
                self.minio,
                object_name=af.object_name,
                zip_path=f"{base_path}/{_sanitize_filename(filename)}",
                error_path=f"{base_path}/_錯誤_找不到檔案_{_sanitize_filename(label)}.txt",
                error_label=af.original_filename or af.object_name,
            )
```

Leave everything above it in the loop (the `type_totals`, `file_type_counter`, `label`, `ext`, and `filename` computation) unchanged. The ZIP paths and error-filename format are identical to before — this is a pure extract-method refactor.

- [ ] **Step 6: Run the full file to confirm the refactor preserved behavior**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py -p no:cacheprovider -v
```
Expected: PASS (all classes, including the original sanitize/label/degree tests).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/export_package_service.py backend/app/tests/test_export_package_pure_helpers.py
git commit -m "refactor: extract _fetch_and_write for ZIP export file streaming"
```

---

## Task 5: Append the 申請文件 to each student's folder

**Files:**
- Modify: `backend/app/services/export_package_service.py` (`_add_application_to_zip`)

This task wires together the helpers from Tasks 2–4. Its behavior is fully covered by those helpers' unit tests; the new code here is a four-line composition. Verification is the full test run plus a dev-container smoke (Step 3).

- [ ] **Step 1: Add the 申請文件 block**

In `backend/app/services/export_package_service.py`, in `_add_application_to_zip`, immediately **after** the `for af in app.files:` loop (i.e. at the end of the method), add:

```python
        # Student-uploaded 申請文件 — stored on the application itself,
        # not as an ApplicationFile, so the app.files loop above misses it.
        entry = _application_document_entry(
            app.application_document_url,
            app.application_document_original_filename,
            base_path,
            student_prefix,
        )
        if entry:
            await _fetch_and_write(zf, self.minio, **entry)
```

`base_path` and `student_prefix` are already defined near the top of `_add_application_to_zip` (`base_path = f"{dept_folder}/{student_folder}"`, `student_prefix = f"{std_code}_{std_name}"`).

- [ ] **Step 2: Run the full test file**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py -p no:cacheprovider -v
```
Expected: PASS (all tests).

- [ ] **Step 3: Dev-container smoke test (manual, end-to-end)**

Confirm a real export now contains the 申請文件 and the correctly-labeled passbook. With the dev stack running:

1. As a student (e.g. `stuphd001`), submit an application and upload a 申請文件 via the application-document upload, plus a verified bank passbook.
2. As a college user (e.g. `cs_college`), call the export:
   ```bash
   curl -s -o /tmp/export.zip -H "Authorization: Bearer <college_token>" \
     "http://localhost:8000/api/v1/college-review/export-package?scholarship_type_id=<id>&academic_year=<yr>&semester=<sem>"
   unzip -l /tmp/export.zip
   ```
3. Verify the student's folder contains a `…_申請文件.<ext>` entry and a `…_存摺封面.<ext>` entry (not `…_其他文件…`).

Expected: both entries present; no `_錯誤_…txt` placeholders for files that exist.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/export_package_service.py
git commit -m "feat: include student-uploaded 申請文件 in college 申請資料 ZIP"
```

---

## Task 6: Lint, full-suite check, and finish

**Files:** none (verification only)

- [ ] **Step 1: black**

Run:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 \
  backend/app/services/export_package_service.py \
  backend/app/tests/test_export_package_pure_helpers.py
```
Expected: `All done!` / no files would be reformatted. If it reports changes, drop `--check` to apply, then re-run.

- [ ] **Step 2: flake8 hard-gated rules**

Run (from `backend/`):
```bash
cd backend && flake8 app --select=B904,B014 --max-line-length=120
```
Expected: no output (exit 0). `_fetch_and_write` does not re-raise inside its `except`, so B904 does not apply.

- [ ] **Step 3: Full pure-helpers file once more**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_export_package_pure_helpers.py -p no:cacheprovider -v
```
Expected: PASS (all classes).

- [ ] **Step 4: Finish the branch**

Use the superpowers:finishing-a-development-branch skill to choose how to integrate (PR / merge / cleanup). The branch contains the four feature commits from Tasks 1–5 plus the spec/plan docs.

---

## Self-Review Notes (for the planner; remove or keep)

- **Spec coverage:** label fix (Task 1), 申請文件 inclusion (Tasks 2,3,5), shared fetch/error-fallback (Task 4), out-of-scope summary-PDF untouched (no task), error-placeholder behavior (Task 4 Step 1 second test + Task 5 smoke). All spec sections map to a task.
- **Type/name consistency:** `_fetch_and_write` kwargs (`object_name`, `zip_path`, `error_path`, `error_label`) match exactly the keys returned by `_application_document_entry`, so `**entry` unpacks cleanly. `_ext_for_application_document(original_filename, object_name)` signature is used consistently in Task 3.
- **No placeholders:** every code step shows full code; every run step shows the command and expected outcome.

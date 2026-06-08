# College 申請資料 ZIP — Include All Student-Uploaded Documents

**Date:** 2026-06-09
**Status:** Approved design, ready for implementation plan
**Scope owner:** college review / export-package

## Problem

The college-facing **申請資料 ZIP** export (`/api/v1/college-review/export-package`,
backed by `ExportPackageService.generate_export_zip`) is supposed to bundle every
document a student uploaded for their application, grouped by department and
student. It does not.

The ZIP builder iterates only `Application.files` (the `ApplicationFile` rows).
That misses one entire student-upload path and mislabels another:

| Source | Student-uploaded? | In ZIP today |
|---|---|---|
| `app.files` — dynamic-form uploads (成績單, 研究計畫, …) | ✅ | ✅ included |
| `app.files` — cloned 存摺封面 (`file_type = "bank_account_proof"`) | ✅ | ⚠️ included but mislabeled as 「其他文件」 |
| `application.application_document_url` — 申請文件 single PDF | ✅ | ❌ **missing entirely** |

### Why these two

- **申請文件 (`application_document_url`).** The endpoint
  `POST /applications/{id}/application-document` (`applications.py:937`) is
  `require_student` and stores the upload on `application.application_document_url`
  (plus `application_document_original_filename`) — **not** as an `ApplicationFile`
  row. Because the ZIP loops `app.files` only, this student-uploaded PDF never
  appears in the export.
- **存摺封面 label.** At submission the passbook is cloned into an `ApplicationFile`
  with `file_type = "bank_account_proof"` (`application_service.py:2118, 2180`),
  but `FILE_TYPE_LABELS` in `export_package_service.py` only maps the string
  `"bank_account_cover"`. So `bank_account_proof` falls through to the `"其他文件"`
  default. The file is present in the ZIP; only its name is wrong.

`submitted_form_data.documents` is **not** a separate source — it is derived from
`app.files` (`application_service.py:686–723`), so nothing extra hides there.

## Goal

After this change the 申請資料 ZIP contains, per student folder:

1. The auto-generated summary PDF (unchanged).
2. Every `app.files` upload, with the cloned passbook correctly labeled 「存摺封面」.
3. The student-uploaded 申請文件 (`application_document_url`), when present.

## Out of scope

- The summary PDF's 「四、上傳文件清單」 section is **left as-is**. It is derived
  from `app.files` / `submitted_form_data.documents` and will not list the 申請文件.
  Deliberately excluded to keep the change focused.
- No change to the 申請總表 Excel export (`department-summary-export*`), the
  200-application cap, permission checks, or audit logging.
- Batch-import handling is unaffected. Note `application_document_url` is also the
  column batch-import populates; including it in the ZIP is correct regardless of
  who set it (it is "the application's document"), but no batch-import-specific
  behavior is added.

## Design

All changes are confined to `backend/app/services/export_package_service.py`.
The query in `_query_applications` already eager-loads `app.files` via
`selectinload`, and `application_document_url` / `application_document_original_filename`
are plain (non-deferred) columns on `Application`, so **no query change is needed**.

### 1. Fix the 存摺封面 label

Add the real stored `file_type` to the label map:

```python
FILE_TYPE_LABELS = {
    ...
    "bank_account_proof": "存摺封面",   # the value actually stored on ApplicationFile
    "bank_account_cover": "存摺封面",   # retained; harmless, may be referenced elsewhere
    ...
}
```

Result: cloned passbooks render as `{學號}_{姓名}_存摺封面{ext}` instead of
`…_其他文件…`. Existing per-file-type sequence numbering (the
`if type_totals[ft] > 1` branch) is unchanged.

### 2. Extract a MinIO fetch-and-write helper (Approach B)

The current `for af in app.files` loop inlines a block that: fetches the object
from MinIO on a worker thread, writes the bytes into the ZIP, and on failure
writes a `_錯誤_…txt` placeholder into the same folder. Adding the 申請文件 would
duplicate that block, so extract it first:

```python
async def _fetch_and_write(
    self,
    zf: zipfile.ZipFile,
    object_name: str,
    zip_path: str,
    error_path: str,
    error_label: str,
) -> None:
    """Stream one MinIO object into the ZIP; on failure write an error .txt
    placeholder into the same folder. Behavior identical to the prior inline
    block in the app.files loop."""
    try:
        response = await asyncio.to_thread(self.minio.get_file_stream, object_name)
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

The `app.files` loop is refactored to call `_fetch_and_write` instead of inlining
the fetch — same ZIP paths, same error filenames, no behavioral change.

> Note: `MinIOService.get_file_stream` reads from `self.default_bucket`, which is
> the same bucket the 申請文件 upload writes to (`minio_service.default_bucket`,
> object name `application-documents/{id}_{timestamp}{ext}`). It raises
> `HTTPException(404)` on a missing object; that is an `Exception` subclass, so the
> `except Exception` fallback catches it and writes the placeholder — no 500 leaks
> out of the ZIP build.

### 3. Add the 申請文件 to the student folder

After the `app.files` loop in `_add_application_to_zip`, append:

```python
# Student-uploaded 申請文件 (stored on the application, not as an ApplicationFile)
if app.application_document_url:
    ext = _ext_for_application_document(
        app.application_document_original_filename,
        app.application_document_url,
    )
    doc_path = f"{base_path}/{_sanitize_filename(f'{student_prefix}_申請文件{ext}')}"
    await self._fetch_and_write(
        zf,
        object_name=app.application_document_url,
        zip_path=doc_path,
        error_path=f"{base_path}/_錯誤_找不到檔案_申請文件.txt",
        error_label=app.application_document_original_filename or app.application_document_url,
    )
```

Extension derivation (small pure helper, unit-testable):

```python
def _ext_for_application_document(original_filename: str | None, object_name: str) -> str:
    """Prefer the original filename's extension; fall back to the object-name
    suffix (the stored object name always ends in the uploaded extension)."""
    for source in (original_filename, object_name):
        if source and "." in source.rsplit("/", 1)[-1]:
            return "." + source.rsplit(".", 1)[1]
    return ""
```

Properties:
- **Additive.** Applications using the dynamic-form flow have
  `application_document_url IS NULL` and get nothing extra.
- **No collision.** The 申請文件 label is distinct from every `app.files` label, so
  it never clashes with the per-file-type sequence naming.
- **Both can coexist.** An application with dynamic uploads *and* an
  `application_document_url` gets both in the folder.

## Error handling

- Missing/unreadable 申請文件 object → `_錯誤_找不到檔案_申請文件.txt` in that
  student's folder (same pattern as existing per-file errors). The ZIP build for
  other students/files continues.
- Per project policy, no fallback/mock data: a genuinely absent object surfaces as
  an explicit error placeholder inside the ZIP, not a silent omission.

## Testing

Test file: `backend/app/tests/test_export_package_pure_helpers.py` (pure-helper
style — no live MinIO/DB/reportlab at import).

1. **`FILE_TYPE_LABELS` pin update.** The existing test asserts the 8 known file
   types; update it so `bank_account_proof` maps to `"存摺封面"` (and the count/key
   set reflects the added entry). This is a deliberate label addition, not drift.
2. **`_ext_for_application_document` pure helper:**
   - `("申請文件.pdf", "application-documents/12_x.pdf")` → `".pdf"`
   - `(None, "application-documents/12_x.pdf")` → `".pdf"`
   - `("noext", "application-documents/12_x")` → `""`
   - original filename's extension wins over the object name's.
3. **申請文件 ZIP path naming** (pure, no MinIO): given a student prefix + ext,
   assert the path is `{base}/{學號}_{姓名}_申請文件{ext}` and is `_sanitize_filename`-safe.
4. **Fetch path with mocked MinIO** (kept minimal): `_fetch_and_write` writes bytes
   on success and an `_錯誤_…txt` placeholder when `get_file_stream` raises — mock
   `self.minio` so no live MinIO is needed. Optional if the pure-path coverage above
   is judged sufficient; the success/fallback branch is the one new behavioral
   surface worth pinning.

Run in the dev container:
`python -m pytest app/tests/test_export_package_pure_helpers.py -p no:cacheprovider`.

## Files touched

- `backend/app/services/export_package_service.py` — label map, `_fetch_and_write`
  helper, `_ext_for_application_document` helper, 申請文件 block in
  `_add_application_to_zip`.
- `backend/app/tests/test_export_package_pure_helpers.py` — updated label pin + new
  helper/path tests.

No migrations, no API/schema changes, no frontend changes, no OpenAPI regeneration.

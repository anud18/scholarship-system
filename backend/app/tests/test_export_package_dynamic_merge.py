"""Integration tests: generate_export_zip ships one extra per-student
申請資料合併檔 PDF merging that student's 學生資料彙整 summary with their
admin-configured dynamic documents (file_type not in FILE_TYPE_LABELS).
Fixed-type files (transcript, …) stay out of the merge; the merged PDF is
built for every student (a student with no dynamic documents gets one holding
just the summary); a download failure becomes a placeholder page inside the
merge; and a wholesale merge failure degrades to a `_錯誤_…txt` without losing
the rest of the ZIP.

Uses a fake MinIO (dict of object_name → bytes) and the real reportlab/pypdf
pipeline — the WQY CJK font is available in the backend image and CI.
"""

import io
import zipfile
from types import SimpleNamespace

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from app.models.application import Application
from app.services.export_package_service import ExportPackageService


def _blank_pdf(num_pages=1):
    w = PdfWriter()
    for _ in range(num_pages):
        w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (60, 90), (200, 10, 10)).save(buf, "PNG")
    return buf.getvalue()


def _mk_file(file_type, original_filename, object_name, mime_type="application/pdf"):
    return SimpleNamespace(
        file_type=file_type,
        original_filename=original_filename,
        object_name=object_name,
        mime_type=mime_type,
    )


def _mk_app(app_id, user_id, std_code, cname, files, submitted_form_data=None):
    a = Application(
        user_id=user_id,
        scholarship_type_id=1,
        academic_year=114,
        student_data={
            "trm_depno": "1000",
            "trm_depname": "A系",
            "trm_academyname": "某學院",
            "std_stdcode": std_code,
            "std_cname": cname,
        },
        submitted_form_data=submitted_form_data or {},
    )
    a.id = app_id
    # Bypass relationship instrumentation — SimpleNamespace file stubs are
    # duck-typed, not mapped ApplicationFile instances.
    a.__dict__["files"] = files
    return a


class _FakeMinioResponse:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return self._payload

    def close(self):
        pass

    def release_conn(self):
        pass


class _FakeMinio:
    """dict-backed MinIO double; unknown object_name raises like NoSuchKey."""

    def __init__(self, objects):
        self.objects = objects

    def get_file_stream(self, object_name):
        if object_name not in self.objects:
            raise Exception(f"NoSuchKey: {object_name}")
        return _FakeMinioResponse(self.objects[object_name])


def _coro_returning(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


def _stype():
    return SimpleNamespace(name="某獎學金", code="phd", sub_type_configs=[])


async def _run_export(monkeypatch, apps, minio, field_labels=None):
    async def _fake_aux(db, *, scholarship_type, applications):
        return ([], {}, {}, {})

    monkeypatch.setattr("app.services.export_summary_tables.load_export_aux_data", _fake_aux)
    monkeypatch.setattr(
        "app.services.export_package_service.load_form_field_labels",
        _coro_returning(field_labels if field_labels is not None else {}),
    )

    svc = ExportPackageService(db=None, minio_service=minio)
    monkeypatch.setattr(svc, "_get_scholarship_type", _coro_returning(_stype()))
    monkeypatch.setattr(svc, "_query_applications", _coro_returning(apps))

    buf, _ = await svc.generate_export_zip(
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        college_code="A",
    )
    return zipfile.ZipFile(buf)


@pytest.mark.asyncio
async def test_merged_pdf_covers_summary_and_dynamic_docs_only(monkeypatch):
    minio = _FakeMinio(
        {
            "obj/transcript.pdf": _blank_pdf(1),
            "obj/toefl.pdf": _blank_pdf(2),
            "obj/club.png": _png_bytes(),
        }
    )
    apps = [
        _mk_app(
            1,
            11,
            "001",
            "甲",
            [
                _mk_file("transcript", "transcript.pdf", "obj/transcript.pdf"),
                _mk_file("語言檢定證明", "toefl.pdf", "obj/toefl.pdf"),
                _mk_file("社團證明", "club.png", "obj/club.png", mime_type="image/png"),
            ],
        ),
        # Only fixed-type files → still gets a merged PDF, holding just the summary
        _mk_app(2, 12, "002", "乙", [_mk_file("transcript", "transcript.pdf", "obj/transcript.pdf")]),
    ]

    zf = await _run_export(monkeypatch, apps, minio)
    names = zf.namelist()

    merged_path = "1000_A系/001_甲/001_甲_申請資料合併檔.pdf"
    assert merged_path in names
    assert "1000_A系/002_乙/002_乙_申請資料合併檔.pdf" in names

    # Individual files are still shipped alongside the merge, and the summary
    # PDF stays in the folder in its own right.
    assert "1000_A系/001_甲/001_甲_成績單.pdf" in names
    assert "1000_A系/001_甲/001_甲_語言檢定證明.pdf" in names
    assert "1000_A系/001_甲/001_甲_學生資料彙整.pdf" in names

    reader = PdfReader(io.BytesIO(zf.read(merged_path)))
    # cover(1) + sep+1 page (summary) + sep+2 pages (toefl) + sep+1 page (club image) = 8
    assert len(reader.pages) == 8
    cover = reader.pages[0].extract_text()
    assert "申請資料合併檔" in cover
    assert "學生資料彙整" in cover
    assert "語言檢定證明" in cover
    assert "社團證明" in cover
    assert "成績單" not in cover
    assert "001 甲" in cover

    # The no-dynamic-documents student's merge is summary-only:
    # cover(1) + sep+1 page (summary) = 3
    solo = PdfReader(io.BytesIO(zf.read("1000_A系/002_乙/002_乙_申請資料合併檔.pdf")))
    assert len(solo.pages) == 3
    solo_cover = solo.pages[0].extract_text()
    assert "學生資料彙整" in solo_cover
    assert "成績單" not in solo_cover


@pytest.mark.asyncio
async def test_field_labels_reach_the_summary_pdf_inside_the_zip(monkeypatch):
    # Wiring test: generate_export_zip loads the label map once and threads it
    # down to _generate_summary_pdf. Dropping that argument anywhere in the
    # chain silently reverts 三、表單填寫資料 to English field ids.
    apps = [
        _mk_app(
            1,
            11,
            "001",
            "甲",
            [],
            submitted_form_data={
                "fields": {
                    "master_school_info": {"field_id": "master_school_info", "value": "交大資工所"},
                    "advisor_name": {"field_id": "advisor_name", "value": "王教授"},
                },
                "documents": [],
            },
        )
    ]

    zf = await _run_export(
        monkeypatch,
        apps,
        _FakeMinio({}),
        field_labels={"master_school_info": "碩士畢業學校/學院/系所", "advisor_name": "指導教授姓名"},
    )

    summary = PdfReader(io.BytesIO(zf.read("1000_A系/001_甲/001_甲_學生資料彙整.pdf")))
    text = "\n".join(page.extract_text() for page in summary.pages)

    assert "碩士畢業學校/學院/系所" in text
    assert "指導教授姓名" in text
    assert "master_school_info" not in text
    assert "advisor_name" not in text


@pytest.mark.asyncio
async def test_download_failure_becomes_placeholder_page(monkeypatch):
    # club.png is missing from storage → per-file error txt AND a
    # placeholder page inside the merged PDF (document list stays complete).
    minio = _FakeMinio({"obj/toefl.pdf": _blank_pdf(1)})
    apps = [
        _mk_app(
            1,
            11,
            "001",
            "甲",
            [
                _mk_file("語言檢定證明", "toefl.pdf", "obj/toefl.pdf"),
                _mk_file("社團證明", "club.png", "obj/club.png", mime_type="image/png"),
            ],
        )
    ]

    zf = await _run_export(monkeypatch, apps, minio)
    names = zf.namelist()

    assert "1000_A系/001_甲/_錯誤_找不到檔案_社團證明.txt" in names
    merged_path = "1000_A系/001_甲/001_甲_申請資料合併檔.pdf"
    assert merged_path in names

    reader = PdfReader(io.BytesIO(zf.read(merged_path)))
    # cover(1) + sep+1 page (summary) + sep+1 page (toefl) + sep+1 placeholder = 7
    assert len(reader.pages) == 7
    placeholder_text = reader.pages[6].extract_text()
    assert "檔案下載失敗" in placeholder_text
    # The concrete fetch error surfaces on the placeholder page, matching
    # the per-file error txt, so reviewers see the actual reason
    assert "NoSuchKey" in placeholder_text


@pytest.mark.asyncio
async def test_merged_pdf_name_collision_keeps_both_entries(monkeypatch):
    # An admin-configured dynamic document named exactly 申請資料合併檔 must not
    # shadow (or be shadowed by) the merged artifact — the second writer gets
    # a _2 suffix instead of a duplicate ZIP entry.
    minio = _FakeMinio({"obj/tricky.pdf": _blank_pdf(1)})
    apps = [_mk_app(1, 11, "001", "甲", [_mk_file("申請資料合併檔", "tricky.pdf", "obj/tricky.pdf")])]

    zf = await _run_export(monkeypatch, apps, minio)
    names = zf.namelist()

    assert "1000_A系/001_甲/001_甲_申請資料合併檔.pdf" in names  # the student's upload
    assert "1000_A系/001_甲/001_甲_申請資料合併檔_2.pdf" in names  # the merged artifact
    assert len(names) == len(set(names))  # no duplicate ZIP entries anywhere


@pytest.mark.asyncio
async def test_two_same_type_download_failures_get_distinct_error_files(monkeypatch):
    # Two files of one dynamic type both missing from storage: the second
    # error placeholder must not silently overwrite the first.
    minio = _FakeMinio({})
    apps = [
        _mk_app(
            1,
            11,
            "001",
            "甲",
            [
                _mk_file("語言檢定證明", "toefl.pdf", "obj/gone1.pdf"),
                _mk_file("語言檢定證明", "ielts.pdf", "obj/gone2.pdf"),
            ],
        )
    ]

    zf = await _run_export(monkeypatch, apps, minio)
    names = zf.namelist()

    assert "1000_A系/001_甲/_錯誤_找不到檔案_語言檢定證明.txt" in names
    assert "1000_A系/001_甲/_錯誤_找不到檔案_語言檢定證明_2.txt" in names
    assert len(names) == len(set(names))

    # Both failures still appear in the merged PDF as placeholder pages:
    # cover(1) + sep+1 page (summary) + 2 * (separator + download-failure placeholder) = 7
    merged = zf.read("1000_A系/001_甲/001_甲_申請資料合併檔.pdf")
    reader = PdfReader(io.BytesIO(merged))
    assert len(reader.pages) == 7


@pytest.mark.asyncio
async def test_merge_failure_degrades_to_error_placeholder(monkeypatch):
    minio = _FakeMinio({"obj/toefl.pdf": _blank_pdf(1)})
    apps = [_mk_app(1, 11, "001", "甲", [_mk_file("語言檢定證明", "toefl.pdf", "obj/toefl.pdf")])]

    def _boom(*args, **kwargs):
        raise RuntimeError("merge exploded")

    monkeypatch.setattr("app.services.export_package_service.build_merged_pdf", _boom)

    zf = await _run_export(monkeypatch, apps, minio)
    names = zf.namelist()

    # Merge failure never aborts the export: materials + summary PDF intact
    assert "1000_A系/001_甲/001_甲_語言檢定證明.pdf" in names
    assert "1000_A系/001_甲/001_甲_學生資料彙整.pdf" in names
    assert not any(n.endswith("申請資料合併檔.pdf") for n in names)
    error_path = "1000_A系/001_甲/_錯誤_申請資料合併檔PDF生成失敗.txt"
    assert error_path in names
    assert "merge exploded" in zf.read(error_path).decode("utf-8")

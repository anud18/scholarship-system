"""Streaming contract of the export ZIP (issue #1376): the archive leaves as
fixed-size blocks, is never held in memory as a whole, stays a valid ZIP when
an object-storage stream dies half-way, and every 4xx-worthy condition is
raised by prepare_export() before a single byte is sent.

Real reportlab/pypdf/zipfile pipeline (the WQY CJK font ships in the backend
image and CI); MinIO is the shared dict-backed fake.
"""

import io
import os
import tracemalloc
import zipfile
from types import SimpleNamespace

import pytest
from pypdf import PdfReader, PdfWriter

from app.services.export_package_service import MAX_EXPORT_APPLICATIONS, ExportPackageService
from app.services.zip_stream import STREAM_BLOCK_SIZE
from app.tests.export_package_fakes import FakeMinio, collect_zip, make_application, make_file

_MIB = 1024 * 1024
_DATA_DESCRIPTOR_FLAG = 0x08


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _coro_returning(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


async def _prepare(monkeypatch, apps, minio, summary_pdf=None):
    async def _fake_aux(db, *, scholarship_type, applications):
        return ([], {}, {}, {})

    monkeypatch.setattr("app.services.export_summary_tables.load_export_aux_data", _fake_aux)
    monkeypatch.setattr("app.services.export_package_service.load_form_field_labels", _coro_returning({}))

    svc = ExportPackageService(db=None, minio_service=minio)
    stype = SimpleNamespace(name="某獎學金", code="phd", sub_type_configs=[])
    monkeypatch.setattr(svc, "_get_scholarship_type", _coro_returning(stype))
    monkeypatch.setattr(svc, "_query_applications", _coro_returning(apps))
    if summary_pdf is not None:
        monkeypatch.setattr(svc, "_generate_summary_pdf", summary_pdf)
    plan = await svc.prepare_export(scholarship_type_id=1, academic_year=114, semester="first", college_code="A")
    return svc, plan


def _students_with(count, files):
    return [make_application(i, f"{i:03d}", files) for i in range(1, count + 1)]


@pytest.mark.asyncio
async def test_archive_leaves_in_fixed_blocks_and_round_trips(monkeypatch):
    transcript = os.urandom(3 * _MIB)  # incompressible, like a scanned PDF
    certificate = os.urandom(2 * _MIB)
    minio = FakeMinio({"obj/t.pdf": transcript, "obj/c.pdf": certificate}, chunk_size=256 * 1024)
    files = [make_file("transcript", "t.pdf", "obj/t.pdf"), make_file("certificate", "c.pdf", "obj/c.pdf")]
    blank = _blank_pdf()
    svc, plan = await _prepare(monkeypatch, _students_with(3, files), minio, summary_pdf=lambda *a, **k: blank)

    assert plan.application_count == 3
    assert plan.zip_filename == "某獎學金_申請資料_114_1_某學院.zip"

    chunks = [chunk async for chunk in svc.iter_export_zip(plan)]

    # Every chunk but the tail is exactly one block — no line-by-line dribble
    # (the old iter(BytesIO) path) and no oversized bursts either.
    assert all(len(chunk) == STREAM_BLOCK_SIZE for chunk in chunks[:-1])
    assert 0 < len(chunks[-1]) < STREAM_BLOCK_SIZE
    assert len(chunks) >= (3 * 5 * _MIB) // STREAM_BLOCK_SIZE

    with zipfile.ZipFile(io.BytesIO(b"".join(chunks))) as zf:
        assert zf.testzip() is None
        assert zf.read("1000_A系/001_甲/001_甲_成績單.pdf") == transcript
        assert zf.read("1000_A系/003_甲/003_甲_證書.pdf") == certificate
        assert "1000_A系/002_甲/002_甲_申請資料合併檔.pdf" in zf.namelist()
        # Streaming mode end to end: zipfile never seeked back into the output.
        assert all(info.flag_bits & _DATA_DESCRIPTOR_FLAG for info in zf.infolist())


@pytest.mark.asyncio
async def test_peak_memory_stays_far_below_the_archive_size(monkeypatch):
    scan = os.urandom(4 * _MIB)
    minio = FakeMinio({"obj/scan.pdf": scan}, chunk_size=256 * 1024)
    files = [make_file("transcript", "scan.pdf", "obj/scan.pdf"), make_file("certificate", "scan.pdf", "obj/scan.pdf")]
    blank = _blank_pdf()
    svc, plan = await _prepare(monkeypatch, _students_with(6, files), minio, summary_pdf=lambda *a, **k: blank)

    tracemalloc.start()
    try:
        total = 0
        async for chunk in svc.iter_export_zip(plan):
            total += len(chunk)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert total > 6 * 2 * 4 * _MIB  # six students × two incompressible 4 MiB scans, plus the PDFs
    # A whole-archive BytesIO (the #1376 behaviour) puts the peak at or above
    # `total`; streaming keeps it around a single student's entries.
    assert peak < total // 2


@pytest.mark.asyncio
async def test_storage_dropping_midstream_keeps_the_archive_valid_and_flags_the_entry(monkeypatch):
    minio = FakeMinio(
        {"obj/toefl.pdf": _blank_pdf(), "obj/dies.pdf": os.urandom(4096)},
        chunk_size=1024,
        fail_midstream=frozenset({"obj/dies.pdf"}),
    )
    files = [make_file("語言檢定證明", "toefl.pdf", "obj/toefl.pdf"), make_file("社團證明", "dies.pdf", "obj/dies.pdf")]
    svc, plan = await _prepare(monkeypatch, [make_application(1, "001", files)], minio)

    with zipfile.ZipFile(await collect_zip(svc, plan)) as zf:
        assert zf.testzip() is None
        names = zf.namelist()
        # The truncated copy is still a well-formed member (its header had
        # already left the building), and the placeholder beside it says so.
        assert "1000_A系/001_甲/001_甲_社團證明.pdf" in names
        assert len(zf.read("1000_A系/001_甲/001_甲_社團證明.pdf")) == 1024
        note = zf.read("1000_A系/001_甲/_錯誤_找不到檔案_社團證明.txt").decode("utf-8")
        assert "不完整" in note
        assert "connection reset" in note
        # The merged PDF lists the document as a download failure, not silently short.
        merged = PdfReader(io.BytesIO(zf.read("1000_A系/001_甲/001_甲_申請資料合併檔.pdf")))
        last_page = merged.pages[-1].extract_text()
        assert "檔案下載失敗" in last_page
        assert "connection reset" in last_page


@pytest.mark.asyncio
async def test_prepare_export_rejects_empty_and_oversized_selections_before_streaming(monkeypatch):
    with pytest.raises(ValueError, match="無申請資料可匯出"):
        await _prepare(monkeypatch, [], FakeMinio({}))
    with pytest.raises(ValueError, match=str(MAX_EXPORT_APPLICATIONS)):
        await _prepare(monkeypatch, [object()] * (MAX_EXPORT_APPLICATIONS + 1), FakeMinio({}))


@pytest.mark.asyncio
async def test_precheck_plan_skips_the_summary_workbooks(monkeypatch):
    # The dry_run precheck only needs filename + count: the workbooks are the
    # expensive part of preparation and must not be built twice per export.
    async def _must_not_run(*args, **kwargs):
        raise AssertionError("summary tables built for a precheck")

    monkeypatch.setattr("app.services.export_package_service.build_embedded_summary_tables", _must_not_run)
    monkeypatch.setattr("app.services.export_package_service.load_form_field_labels", _coro_returning({}))
    svc = ExportPackageService(db=None, minio_service=FakeMinio({}))
    stype = SimpleNamespace(name="某獎學金", code="phd", sub_type_configs=[])
    monkeypatch.setattr(svc, "_get_scholarship_type", _coro_returning(stype))
    monkeypatch.setattr(svc, "_query_applications", _coro_returning([make_application(1, "001", [])]))

    plan = await svc.prepare_export(
        scholarship_type_id=1, academic_year=114, semester="first", college_code="A", include_summary_tables=False
    )

    assert plan.summary_tables == {}
    assert plan.application_count == 1
    assert plan.zip_filename == "某獎學金_申請資料_114_1_某學院.zip"

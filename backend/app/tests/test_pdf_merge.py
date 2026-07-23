"""Unit tests for `app.services.pdf_merge.build_merged_pdf` — the per-student
merged dynamic-documents PDF shipped inside the college export ZIP.

Layout contract pinned here: page 1 is a cover listing every document, then
each document contributes one separator page followed by its own pages —
appended verbatim for readable PDFs, one A4 page for JPG/PNG images, and one
placeholder page for anything unreadable (Word files, corrupt/encrypted PDFs,
download failures). A bad document must never abort the merge.

Requires the WQY CJK font (installed in the backend image and in CI's
"Install CJK font" step) — pages carry zh-TW text.
"""

import io

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from app.services.pdf_merge import MergeItem, build_merged_pdf

A4_WIDTH_PT = 595  # rounded reportlab A4 width/height in points
A4_HEIGHT_PT = 842


def _blank_pdf(num_pages=1, size=200):
    w = PdfWriter()
    for _ in range(num_pages):
        w.add_blank_page(width=size, height=size)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _png_bytes(mode="RGB", size=(60, 90)):
    img = Image.new(mode, size, (200, 10, 10) if mode == "RGB" else None)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _encrypted_pdf(user_password, owner_password=None):
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    w.encrypt(user_password=user_password, owner_password=owner_password)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _merge(items):
    return build_merged_pdf(
        title="學生動態文件合併",
        subtitle_lines=["某獎學金 114學年度 第一學期", "001 甲"],
        items=items,
    )


class TestBuildMergedPdf:
    def test_two_pdfs_page_layout(self):
        # cover(1) + sep(1)+2 pages + sep(1)+1 page = 6
        out = _merge(
            [
                MergeItem(label="語言檢定證明", filename="toefl.pdf", content=_blank_pdf(2)),
                MergeItem(label="社團證明", filename="club.pdf", content=_blank_pdf(1)),
            ]
        )
        assert out.startswith(b"%PDF")
        reader = PdfReader(io.BytesIO(out))
        assert len(reader.pages) == 6

    def test_cover_lists_documents_in_order(self):
        out = _merge(
            [
                MergeItem(label="語言檢定證明", filename="toefl.pdf", content=_blank_pdf()),
                MergeItem(label="社團證明", filename="club.pdf", content=_blank_pdf()),
            ]
        )
        cover = PdfReader(io.BytesIO(out)).pages[0].extract_text()
        assert "學生動態文件合併" in cover
        assert "某獎學金 114學年度 第一學期" in cover
        assert cover.index("1. 語言檢定證明") < cover.index("2. 社團證明")

    def test_separator_page_carries_label_and_filename(self):
        out = _merge([MergeItem(label="語言檢定證明", filename="toefl.pdf", content=_blank_pdf())])
        sep = PdfReader(io.BytesIO(out)).pages[1].extract_text()
        assert "文件 1／1：語言檢定證明" in sep
        assert "原始檔名：toefl.pdf" in sep

    def test_pdf_pages_appended_verbatim(self):
        # The document's own 200x200 page survives (NOT re-rendered onto A4).
        out = _merge([MergeItem(label="證明", filename="doc.pdf", content=_blank_pdf(size=200))])
        page = PdfReader(io.BytesIO(out)).pages[2]
        assert round(page.mediabox.width) == 200
        assert round(page.mediabox.height) == 200

    def test_pdf_detected_by_magic_bytes_without_extension(self):
        # Upload named .bin but with %PDF content merges as a PDF.
        out = _merge([MergeItem(label="證明", filename="upload.bin", content=_blank_pdf())])
        reader = PdfReader(io.BytesIO(out))
        assert len(reader.pages) == 3
        assert round(reader.pages[2].mediabox.width) == 200

    def test_image_rendered_on_a4_page(self):
        out = _merge([MergeItem(label="社團證明", filename="club.png", content=_png_bytes())])
        reader = PdfReader(io.BytesIO(out))
        assert len(reader.pages) == 3
        page = reader.pages[2]
        assert round(page.mediabox.width) == A4_WIDTH_PT
        assert round(page.mediabox.height) == A4_HEIGHT_PT

    def test_transparent_png_merges(self):
        out = _merge([MergeItem(label="印章", filename="stamp.png", content=_png_bytes(mode="RGBA"))])
        assert len(PdfReader(io.BytesIO(out)).pages) == 3

    def test_unsupported_word_file_gets_placeholder(self):
        out = _merge([MergeItem(label="推薦函", filename="rec.docx", content=b"PK\x03\x04 not a docx")])
        reader = PdfReader(io.BytesIO(out))
        assert len(reader.pages) == 3
        assert "無法合併" in reader.pages[2].extract_text()

    def test_corrupt_pdf_gets_placeholder_not_crash(self):
        out = _merge([MergeItem(label="證明", filename="bad.pdf", content=b"%PDF-1.4 garbage")])
        reader = PdfReader(io.BytesIO(out))
        assert len(reader.pages) == 3
        assert "無法讀取" in reader.pages[2].extract_text()

    def test_user_password_pdf_gets_placeholder(self):
        out = _merge([MergeItem(label="證明", filename="enc.pdf", content=_encrypted_pdf("secret"))])
        reader = PdfReader(io.BytesIO(out))
        assert len(reader.pages) == 3
        assert "無法讀取" in reader.pages[2].extract_text()

    def test_owner_password_only_pdf_is_unlocked_and_merged(self):
        # Permissions-only encryption (empty user password) must merge, not placeholder.
        out = _merge([MergeItem(label="證明", filename="owner.pdf", content=_encrypted_pdf("", "owner-pass"))])
        reader = PdfReader(io.BytesIO(out))
        assert len(reader.pages) == 3
        assert round(reader.pages[2].mediabox.width) == 200

    def test_missing_content_gets_download_failure_placeholder(self):
        out = _merge([MergeItem(label="證明", filename="lost.pdf", content=None, error="minio 404")])
        reader = PdfReader(io.BytesIO(out))
        assert len(reader.pages) == 3
        text = reader.pages[2].extract_text()
        assert "檔案下載失敗" in text
        assert "minio 404" in text

    def test_bad_document_never_aborts_good_neighbours(self):
        out = _merge(
            [
                MergeItem(label="好文件", filename="ok.pdf", content=_blank_pdf()),
                MergeItem(label="壞文件", filename="bad.pdf", content=b"%PDF-1.4 garbage"),
                MergeItem(label="圖片", filename="pic.png", content=_png_bytes()),
            ]
        )
        # cover + 3 * (sep + 1 page)
        assert len(PdfReader(io.BytesIO(out)).pages) == 7

    def test_empty_items_raises(self):
        with pytest.raises(ValueError):
            _merge([])

    def test_exif_orientation_is_applied(self):
        # A portrait phone photo stores landscape pixels + Orientation=6;
        # the merged page must embed the transposed (upright) image, matching
        # what every OS viewer shows for the original file.
        img = Image.new("RGB", (400, 200), (10, 120, 40))
        exif = Image.Exif()
        exif[274] = 6  # Orientation: rotate 90 CW to display
        buf = io.BytesIO()
        img.save(buf, "JPEG", exif=exif)

        out = _merge([MergeItem(label="社團證明", filename="photo.jpg", content=buf.getvalue())])
        page = PdfReader(io.BytesIO(out)).pages[2]
        xobject = list(page["/Resources"]["/XObject"].values())[0].get_object()
        assert (xobject["/Width"], xobject["/Height"]) == (200, 400)

    def test_oversized_image_gets_dedicated_placeholder(self, monkeypatch):
        # Decompression-bomb budget: the header-declared pixel count is
        # checked BEFORE decoding, and the reviewer gets a distinct reason.
        monkeypatch.setattr("app.services.pdf_merge._MAX_IMAGE_PIXELS", 1000)
        out = _merge([MergeItem(label="社團證明", filename="huge.png", content=_png_bytes(size=(60, 90)))])
        reader = PdfReader(io.BytesIO(out))
        assert len(reader.pages) == 3
        assert "圖片尺寸過大" in reader.pages[2].extract_text()

    def test_image_with_pdf_filename_is_rendered_not_placeholdered(self):
        # Upload validation is extension-only, so a JPEG/PNG saved as
        # scan.pdf must land on the image path (magic-bytes-first detection),
        # not on a misleading 'PDF 檔案無法讀取' placeholder.
        out = _merge([MergeItem(label="證明", filename="scan.pdf", content=_png_bytes())])
        reader = PdfReader(io.BytesIO(out))
        assert len(reader.pages) == 3
        page = reader.pages[2]
        assert round(page.mediabox.width) == A4_WIDTH_PT
        assert "無法讀取" not in (page.extract_text() or "")

    def test_acroform_survives_normalization(self):
        # NeedAppearances form fills (LibreOffice/pdftk) render blank if the
        # document /AcroForm is dropped — append(), not per-page add_page.
        from reportlab.lib.pagesizes import A4 as RL_A4
        from reportlab.pdfgen import canvas as rl_canvas

        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=RL_A4)
        c.acroForm.textfield(name="agree_name", x=100, y=600, value="FILLED-VALUE")
        c.showPage()
        c.save()

        out = _merge([MergeItem(label="切結書", filename="form.pdf", content=buf.getvalue())])
        fields = PdfReader(io.BytesIO(out)).get_fields()
        assert fields is not None
        assert "agree_name" in fields

    def test_javascript_annotation_is_stripped(self):
        # A page-level Link annotation carrying an /S /JavaScript action must
        # not survive into the file reviewers are steered to open; benign
        # URI links stay.
        from pypdf.generic import (
            ArrayObject,
            DictionaryObject,
            NameObject,
            NumberObject,
            TextStringObject,
        )

        w = PdfWriter()
        page = w.add_blank_page(width=200, height=200)
        rect = ArrayObject([NumberObject(0), NumberObject(0), NumberObject(50), NumberObject(50)])
        js_annot = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/Rect"): rect,
                NameObject("/A"): DictionaryObject(
                    {
                        NameObject("/S"): NameObject("/JavaScript"),
                        NameObject("/JS"): TextStringObject("app.alert('pwned-marker')"),
                    }
                ),
            }
        )
        uri_annot = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Annot"),
                NameObject("/Subtype"): NameObject("/Link"),
                NameObject("/Rect"): rect,
                NameObject("/A"): DictionaryObject(
                    {
                        NameObject("/S"): NameObject("/URI"),
                        NameObject("/URI"): TextStringObject("https://example.edu/keep-me"),
                    }
                ),
            }
        )
        page[NameObject("/Annots")] = ArrayObject([js_annot, uri_annot])
        buf = io.BytesIO()
        w.write(buf)

        out = _merge([MergeItem(label="證明", filename="tricky.pdf", content=buf.getvalue())])
        assert b"pwned-marker" not in out
        assert b"/JavaScript" not in out
        # The benign URI link survives (pypdf octal-escapes the URI string in
        # the raw bytes, so inspect the parsed annotations instead)
        annots = PdfReader(io.BytesIO(out)).pages[-1]["/Annots"]
        assert len(annots) == 1
        action = annots[0].get_object()["/A"]
        assert action["/S"] == "/URI"
        assert "keep-me" in action["/URI"]

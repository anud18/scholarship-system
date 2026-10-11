"""指導教授審核結果/評語 in the exports.

- professor_review_export: loading professor verdicts (professors only), the
  column set and the shared cell wording (推薦 / 不推薦 / 未審核 / —,
  co-advisor joins);
- CollegeRankingExportService: the result columns, then the comment columns,
  right after 指導教授姓名, in both xlsx and PDF;
- professor_review_pdf: the 合併檔's 指導教授評語 page.
"""

import io
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus, Semester
from app.models.review import ApplicationReview, ApplicationReviewItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.college_ranking_export_service import STATIC_HEADERS, CollegeRankingExportService, ExportRow
from app.services.professor_review_export import (
    DEFAULT_SUB_TYPE,
    NO_REVIEW_LABEL,
    NOT_REVIEWED_LABEL,
    ProfessorReviewData,
    ProfessorReviewEntry,
    applied_sub_types,
    load_professor_review_data,
    load_professor_reviews,
    review_sub_type_columns,
)
from app.services.professor_review_pdf import _rows, build_professor_review_pdf

LABELS = {"nstc": "國科會", "moe_1w": "教育部(一萬)"}
REVIEWED_AT = datetime(2026, 10, 5, 6, 30, tzinfo=timezone.utc)  # 14:30 Taipei
APP_ID = 1


def _entry(code, rec, comments=None, name="王教授"):
    return ProfessorReviewEntry(
        sub_type_code=code, recommendation=rec, comments=comments, reviewer_name=name, reviewed_at=REVIEWED_AT
    )


def _app(sub_types=("nstc", "moe_1w")):
    return SimpleNamespace(
        id=APP_ID,
        scholarship_subtype_list=list(sub_types),
        sub_type_preferences=None,
        sub_scholarship_type=None,
        student_data={"std_stdcode": "001", "std_cname": "甲"},
        submitted_form_data={},
    )


def _review(entries=(), sub_types=("nstc", "moe_1w"), required=True):
    return ProfessorReviewData(
        sub_types=tuple(sub_types),
        entries_by_app={APP_ID: list(entries)},
        review_required_app_ids=frozenset({APP_ID}) if required else frozenset(),
    )


# ─── column set ──────────────────────────────────────────────────────


def test_columns_follow_the_scholarship_sub_type_order():
    stype = SimpleNamespace(sub_type_list=["NSTC ", "moe_1w", "nstc"])
    assert review_sub_type_columns(stype) == ("nstc", "moe_1w")


@pytest.mark.parametrize("sub_type_list", [None, [], ["general"]])
def test_scholarship_without_sub_types_gets_one_default_pair(sub_type_list):
    columns = review_sub_type_columns(SimpleNamespace(sub_type_list=sub_type_list))
    assert columns == (DEFAULT_SUB_TYPE,)
    assert ProfessorReviewData(sub_types=columns).headers(LABELS) == ["指導教授審核結果", "指導教授評語"]


def test_verdict_under_an_unlisted_code_gets_its_own_column():
    # e.g. the professor UI's 'default' fallback on a scholarship with real sub-types
    stype = SimpleNamespace(sub_type_list=["nstc", "moe_1w"])
    columns = review_sub_type_columns(stype, {APP_ID: [_entry(DEFAULT_SUB_TYPE, "approve")]})
    assert columns == ("nstc", "moe_1w", DEFAULT_SUB_TYPE)


def test_headers_put_every_result_before_every_comment():
    assert _review().headers(LABELS) == [
        "國科會-指導教授審核結果",
        "教育部(一萬)-指導教授審核結果",
        "國科會-指導教授評語",
        "教育部(一萬)-指導教授評語",
    ]


def test_applied_sub_types_folds_general_and_empty_into_default():
    assert applied_sub_types(_app(())) == [DEFAULT_SUB_TYPE]
    assert applied_sub_types(_app(("general",))) == [DEFAULT_SUB_TYPE]
    assert applied_sub_types(_app((" NSTC",))) == ["nstc"]


# ─── cell wording ────────────────────────────────────────────────────


def test_cells_render_verdict_comment_and_missing_states():
    app = _app(("nstc",))
    review = _review([_entry("nstc", "reject", "已獲其他補助")])
    assert review.cell_pair(app, "nstc") == ("不推薦", "已獲其他補助")
    # Did not apply for moe_1w → nothing for the professor to review.
    assert review.cell_pair(app, "moe_1w") == (NO_REVIEW_LABEL, "")
    # Applied, review required, no verdict yet
    assert _review().cell_pair(app, "nstc") == (NOT_REVIEWED_LABEL, "")


def test_flow_without_professor_step_is_not_reported_as_pending():
    # e.g. a renewal whose config has renewal_requires_professor_review=False
    assert _review(required=False).cell_pair(_app(("nstc",)), "nstc") == (NO_REVIEW_LABEL, "")


def test_general_placeholder_application_shows_pending_not_unapplied():
    review = _review(sub_types=(DEFAULT_SUB_TYPE,))
    assert review.cells(_app(("general",))) == [NOT_REVIEWED_LABEL, ""]


def test_cells_order_matches_headers():
    review = _review([_entry("nstc", "approve", "研究表現優異"), _entry("moe_1w", "reject", None)])
    assert review.cells(_app()) == ["推薦", "不推薦", "研究表現優異", ""]


def test_co_advisors_on_one_sub_type_are_all_kept():
    review = _review([_entry("nstc", "approve", "很好", name="王教授"), _entry("nstc", "reject", None, name="李教授")])
    result, comment = review.cell_pair(_app(("nstc",)), "nstc")
    assert result == "王教授：推薦；李教授：不推薦"
    assert comment == "王教授：很好"


# ─── 學生資料彙整表 columns ──────────────────────────────────────────


def _row():
    return ExportRow(rank_position=1, application=_app(), advisor_names="王教授")


def _workbook(review, **kwargs):
    payload = CollegeRankingExportService().build_workbook(
        rows=[_row()],
        dynamic_fields=[],
        sub_type_labels=LABELS,
        title="t",
        sheet_name="s",
        professor_review=review,
        **kwargs,
    )
    return load_workbook(io.BytesIO(payload)).active


def test_workbook_places_review_columns_after_advisor_name():
    ws = _workbook(_review([_entry("nstc", "approve", "研究表現優異"), _entry("moe_1w", "reject", "已獲國科會支持")]))
    headers = [c.value for c in ws[2]]
    advisor_idx = headers.index("指導教授姓名")
    assert advisor_idx == len(STATIC_HEADERS) - 1
    assert headers[advisor_idx + 1 : advisor_idx + 5] == [
        "國科會-指導教授審核結果",
        "教育部(一萬)-指導教授審核結果",
        "國科會-指導教授評語",
        "教育部(一萬)-指導教授評語",
    ]
    values = [c.value for c in ws[3]]
    assert values[advisor_idx + 1 : advisor_idx + 5] == ["推薦", "不推薦", "研究表現優異", "已獲國科會支持"]


def test_workbook_comment_columns_wrap_at_a_readable_width():
    ws = _workbook(_review([_entry("nstc", "approve", "長" * 200)]))
    comment_col = len(STATIC_HEADERS) + 3  # 1-based: static, 2 results, first comment
    letter = ws.cell(row=2, column=comment_col).column_letter
    assert ws.cell(row=2, column=comment_col).value == "國科會-指導教授評語"
    assert ws.column_dimensions[letter].width == 40
    assert ws.cell(row=3, column=comment_col).alignment.wrap_text is True


def test_workbook_survives_control_characters_in_a_comment():
    # Word's manual line break (\x0b) would raise openpyxl IllegalCharacterError
    ws = _workbook(_review([_entry("nstc", "approve", "第一行\x0b第二行")]))
    assert "第一行第二行" in [c.value for c in ws[3]]


def test_workbook_without_professor_review_has_no_review_columns():
    headers = [c.value for c in _workbook(None)[2]]
    assert headers == STATIC_HEADERS


def test_pdf_widths_cover_review_and_seal_columns():
    service = CollegeRankingExportService()
    columns = service._columns([], LABELS, _review(), include_college_seal=True)
    widths = service._pdf_col_widths(columns, 785.0)
    headers = [c.header for c in columns]
    assert len(widths) == len(headers)
    assert sum(widths) == pytest.approx(785.0)
    comment_idx = headers.index("國科會-指導教授評語")
    assert widths[comment_idx] > widths[comment_idx - 2]  # comment wider than its verdict


def test_pdf_renders_long_review_comment():
    out = CollegeRankingExportService().build_pdf(
        rows=[_row()],
        dynamic_fields=[],
        sub_type_labels=LABELS,
        title="t",
        include_college_seal=True,
        professor_review=_review([_entry("nstc", "approve", "研究表現優異" * 400)]),
    )
    assert out[:5] == b"%PDF-"


# ─── 合併檔 指導教授評語 page ────────────────────────────────────────


def test_pdf_page_rows_cover_every_column():
    review = _review(
        [_entry("nstc", "approve", "很好"), _entry(DEFAULT_SUB_TYPE, "reject", "舊資料")],
        sub_types=("nstc", "moe_1w", DEFAULT_SUB_TYPE),
    )
    assert _rows(_app(("nstc",)), review, LABELS) == [
        ["國科會", "推薦", "很好", "王教授", "2026-10-05 14:30"],
        ["教育部(一萬)", NO_REVIEW_LABEL, "", "", ""],
        ["整體推薦", "不推薦", "舊資料", "王教授", "2026-10-05 14:30"],
    ]


def test_pdf_page_renders_text_and_survives_a_page_long_comment():
    out = build_professor_review_pdf(
        subtitle_lines=["某獎學金 114學年度 全學年", "001 甲"],
        application=_app(),
        review=_review([_entry("nstc", "approve", "研究表現<優異>\n第二行"), _entry("moe_1w", "reject", "長" * 6000)]),
        sub_type_labels=LABELS,
    )
    reader = PdfReader(io.BytesIO(out))
    assert len(reader.pages) >= 2  # the long comment flowed onto another page
    text = reader.pages[0].extract_text()
    assert "指導教授評語" in text
    assert "國科會" in text
    assert "研究表現<優異>" in text
    assert "王教授" in text


# ─── loaders ─────────────────────────────────────────────────────────


async def _user(db: AsyncSession, suffix: str, role: UserRole, name: str) -> User:
    user = User(
        nycu_id=f"pre_{suffix}",
        name=name,
        email=f"pre_{suffix}@u.edu",
        user_type=UserType.student if role == UserRole.student else UserType.employee,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _review_row(db: AsyncSession, app_id: int, reviewer: User, items) -> None:
    review = ApplicationReview(
        application_id=app_id, reviewer_id=reviewer.id, recommendation="approve", reviewed_at=REVIEWED_AT
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    for code, rec, comments in items:
        db.add(ApplicationReviewItem(review_id=review.id, sub_type_code=code, recommendation=rec, comments=comments))
    await db.commit()


async def _application(db: AsyncSession, student: User, sch: ScholarshipType, cfg, suffix: str, **kwargs):
    app = Application(
        app_id=f"APP-PRE-{suffix}",
        user_id=student.id,
        scholarship_type_id=sch.id,
        scholarship_configuration_id=cfg.id,
        sub_type_selection_mode="multiple",
        academic_year=114,
        semester=Semester.first.value,
        status=ApplicationStatus.submitted.value,
        agree_terms=True,
        **kwargs,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@pytest.mark.asyncio
async def test_loaders_return_professor_verdicts_and_review_requirement(db: AsyncSession):
    student = await _user(db, "stu", UserRole.student, "學生")
    prof = await _user(db, "prof", UserRole.professor, "王教授")
    admin = await _user(db, "adm", UserRole.admin, "管理員")
    sch = ScholarshipType(code="pre_sch", name="Pre Sch", status="active", sub_type_list=["general"])
    db.add(sch)
    await db.commit()
    await db.refresh(sch)
    cfg = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code="pre_cfg",
        config_name="Pre cfg",
        academic_year=114,
        semester=Semester.first.value,
        amount=30000,
        currency="TWD",
        is_active=True,
        requires_professor_recommendation=True,
        renewal_requires_professor_review=False,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    new_app = await _application(db, student, sch, cfg, "new", scholarship_subtype_list=["general"])
    renewer = await _user(db, "stu2", UserRole.student, "續領生")
    renewal = await _application(db, renewer, sch, cfg, "ren", scholarship_subtype_list=["general"], is_renewal=True)

    await _review_row(db, new_app.id, prof, [(" General", "approve", "很好")])
    await _review_row(db, new_app.id, admin, [("general", "reject", "admin note")])

    raw = await load_professor_reviews(db, [new_app.id])
    assert [(e.sub_type_code, e.recommendation, e.comments, e.reviewer_name) for e in raw[new_app.id]] == [
        ("general", "approve", "很好", "王教授"),
    ]
    assert await load_professor_reviews(db, []) == {}

    data = await load_professor_review_data(db, scholarship_type=sch, applications=[new_app, renewal])
    assert data.sub_types == (DEFAULT_SUB_TYPE,)
    assert data.cells(new_app) == ["推薦", "很好"]  # 'general' verdict lands in the default column
    assert data.is_review_required(new_app)
    assert not data.is_review_required(renewal)
    assert data.cells(renewal) == [NO_REVIEW_LABEL, ""]

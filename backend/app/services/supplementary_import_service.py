"""Supplementary import service — adds new students to an existing ranking post-distribution."""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from openpyxl import load_workbook

logger = logging.getLogger(__name__)

# Column indices (1-based, matching 學生資料彙整表 export format)
_COL_RANK = 2
_COL_SCHOLARSHIP_TYPE = 3
_COL_STUDENT_ID = 13
_COL_BANK_ACCOUNT = 15
_COL_ADVISOR_NAME = 18
_STATIC_COL_COUNT = 18


@dataclass
class SupplementaryRow:
    """Parsed data for one student from the supplementary import Excel."""

    student_id: str
    excel_rank: int  # Value from col 2 (will be offset by max existing rank)
    sub_type_preferences: List[str]
    bank_account: Optional[str]
    advisor_name: Optional[str]
    submitted_form_fields: Dict[str, str]  # field_name -> raw cell value


def parse_scholarship_type_cell(cell_value: str, label_to_code: Dict[str, str]) -> List[str]:
    """Parse 申請獎學金類別 cell into ordered sub_type_preference codes.

    Formats:
        "XXX"                                      -> [code_of_XXX]
        "XXX(第一志願)暨YYY(第二志願)"              -> [code_of_XXX, code_of_YYY]
    """
    cell_value = (cell_value or "").strip()
    dual_match = re.fullmatch(
        r"(.+?)\(第一志願\)暨(.+?)\(第二志願\)", cell_value
    )
    if dual_match:
        first_label = dual_match.group(1).strip()
        second_label = dual_match.group(2).strip()
        for label in (first_label, second_label):
            if label not in label_to_code:
                raise ValueError(f"無法識別的獎學金類別：「{label}」")
        return [label_to_code[first_label], label_to_code[second_label]]

    if cell_value in label_to_code:
        return [label_to_code[cell_value]]

    raise ValueError(f"無法識別的獎學金類別：「{cell_value}」")


class SupplementaryImportService:
    """Handles all logic for supplementary student import after distribution."""

    # -------- Pure helpers (no DB / no HTTP) --------

    @staticmethod
    def parse_excel(
        file_bytes: bytes,
        label_to_code: Dict[str, str],
        dynamic_field_names: List[str],
    ) -> Tuple[List[SupplementaryRow], List[str]]:
        """Parse a 學生資料彙整表 Excel file.

        Returns (rows, errors). If errors is non-empty the caller should
        abort and return them to the client; rows may be partially populated.
        """
        errors: List[str] = []
        rows: List[SupplementaryRow] = []
        seen_student_ids: Dict[str, int] = {}  # student_id -> first excel row number
        seen_ranks: Dict[int, int] = {}        # rank -> first excel row number

        try:
            wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
            ws = wb.active
        except Exception as exc:
            return [], [f"無法讀取 Excel 檔案：{exc}"]

        # Row 1 = title, Row 2 = headers, Row 3+ = data
        excel_row_num = 2  # last header row
        for excel_row in ws.iter_rows(min_row=3, values_only=True):
            excel_row_num += 1
            student_id_raw = excel_row[_COL_STUDENT_ID - 1] if len(excel_row) >= _COL_STUDENT_ID else None
            if not student_id_raw:
                continue  # skip empty rows

            student_id = str(student_id_raw).strip()

            # Duplicate student ID check
            if student_id in seen_student_ids:
                errors.append(
                    f"學號重複：{student_id}（首次出現在第 {seen_student_ids[student_id]} 行）"
                )
                continue
            seen_student_ids[student_id] = excel_row_num

            # Parse rank (col 2)
            rank_raw = excel_row[_COL_RANK - 1] if len(excel_row) >= _COL_RANK else None
            try:
                excel_rank = int(rank_raw)
                if excel_rank < 1:
                    raise ValueError()
            except (TypeError, ValueError):
                errors.append(f"排名無效（學號 {student_id}）：必須為正整數，收到 '{rank_raw}'")
                continue

            if excel_rank in seen_ranks:
                errors.append(f"排名重複：第 {excel_rank} 名出現超過一次（學號 {student_id}）")
                continue
            seen_ranks[excel_rank] = excel_row_num

            # Parse 申請獎學金類別 (col 3)
            scholarship_cell_raw = excel_row[_COL_SCHOLARSHIP_TYPE - 1] if len(excel_row) >= _COL_SCHOLARSHIP_TYPE else None
            scholarship_cell = str(scholarship_cell_raw or "").strip()
            try:
                sub_type_preferences = parse_scholarship_type_cell(scholarship_cell, label_to_code)
            except ValueError as exc:
                errors.append(f"學號 {student_id}：{exc}")
                continue

            # Other static columns
            bank_account_raw = excel_row[_COL_BANK_ACCOUNT - 1] if len(excel_row) >= _COL_BANK_ACCOUNT else None
            bank_account = str(bank_account_raw).strip() if bank_account_raw else None

            advisor_raw = excel_row[_COL_ADVISOR_NAME - 1] if len(excel_row) >= _COL_ADVISOR_NAME else None
            advisor_name = str(advisor_raw).strip() if advisor_raw else None

            # Dynamic columns (col 19+)
            submitted_form_fields: Dict[str, str] = {}
            for idx, field_name in enumerate(dynamic_field_names):
                col_idx = _STATIC_COL_COUNT + idx  # 0-based
                if col_idx < len(excel_row):
                    raw = excel_row[col_idx]
                    if raw is not None and str(raw).strip():
                        submitted_form_fields[field_name] = str(raw).strip()

            rows.append(
                SupplementaryRow(
                    student_id=student_id,
                    excel_rank=excel_rank,
                    sub_type_preferences=sub_type_preferences,
                    bank_account=bank_account,
                    advisor_name=advisor_name,
                    submitted_form_fields=submitted_form_fields,
                )
            )

        # Validate rank sequence is consecutive starting from 1
        if rows and not errors:
            expected = set(range(1, len(rows) + 1))
            actual = {r.excel_rank for r in rows}
            missing = expected - actual
            if missing:
                errors.append(
                    f"排名不連續：缺少第 {', '.join(str(r) for r in sorted(missing))} 名"
                )

        return rows, errors

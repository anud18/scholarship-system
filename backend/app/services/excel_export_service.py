"""
Excel匯出服務
Excel export service for payment roster generation
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.core.config import settings
from app.core.exceptions import FileStorageError
from app.models.payment_roster import PaymentRoster, PaymentRosterItem

logger = logging.getLogger(__name__)


class ExcelExportService:
    """Excel匯出服務"""

    def __init__(self):
        self.export_base_path = getattr(settings, "roster_export_dir", "./exports")
        self.template_dir = getattr(settings, "roster_template_dir", "./app/templates")
        default_template = getattr(settings, "roster_excel_template", "STD_UP_MIXLISTA.xlsx")
        self.template_path = os.path.join(self.template_dir, default_template)
        self.default_template_name = default_template
        self.ensure_export_directory()
        self._load_template_structure()

    def _load_template_structure(self):
        """Load template structure from STD_UP_MIXLISTA.xlsx"""
        try:
            if os.path.exists(self.template_path):
                wb = load_workbook(self.template_path)
                ws = wb.active

                # Extract headers from template
                self.template_columns = []
                for col in range(1, 31):  # 30 columns max
                    cell_value = ws.cell(row=1, column=col).value
                    if cell_value:
                        self.template_columns.append(str(cell_value))
                    else:
                        break

                logger.info(f"Loaded {len(self.template_columns)} columns from template")
                wb.close()
            else:
                logger.warning(f"Template not found at {self.template_path}, using default columns")
                self._set_default_columns()
        except Exception as e:
            logger.error(f"Failed to load template: {e}, using default columns")
            self._set_default_columns()

    def _set_default_columns(self):
        """Set default STD_UP_MIXLISTA 30-column structure according to specification"""
        self.template_columns = [
            "身分證字號",  # 1. 必填
            "姓名",  # 2. 必填
            "帳號",  # 3. 若無則標註於說明欄
            "銀行代碼",  # 4. 若無則標註於說明欄
            "職別(稱)",  # 5. 固定值"學生"
            "戶籍地址",  # 6. 選填
            "身份別代碼",  # 7. 學生固定為1
            "單位",  # 8. 固定值"次"
            "數量",  # 9. 固定值"1"
            "單價",  # 10. 獎學金金額
            "健保費",  # 11. 學生不適用，填0
            "勞保費",  # 12. 學生不適用，填0
            "就保費",  # 13. 學生不適用，填0
            "勞退費",  # 14. 學生不適用，填0
            "職災費",  # 15. 學生不適用，填0
            "補充保費",  # 16. 學生不適用，填0
            "所得稅",  # 17. 學生不適用，填0
            "入會費",  # 18. 學生不適用，填0
            "互助費",  # 19. 學生不適用，填0
            "其他費用1",  # 20. 學生不適用，填0
            "其他費用2",  # 21. 學生不適用，填0
            "其他費用3",  # 22. 學生不適用，填0
            "其他費用4",  # 23. 學生不適用，填0
            "其他費用5",  # 24. 學生不適用，填0
            "說明",  # 25. 組合字串：期間+獎學金+狀態
            "E-MAIL",  # 26. 選填
            "個人身分別",  # 27. 本國人=1
            "居留天數",  # 28. 本國人預設"是"
            "保留欄位1",  # 29. 保留
            "保留欄位2",  # 30. 保留
        ]

        # Field mapping for easy access
        self.field_mapping = {
            "id_number": 0,  # 身分證字號
            "name": 1,  # 姓名
            "bank_account": 2,  # 帳號
            "bank_code": 3,  # 銀行代碼
            "job_title": 4,  # 職別(稱)
            "address": 5,  # 戶籍地址
            "identity_code": 6,  # 身份別代碼
            "unit": 7,  # 單位
            "quantity": 8,  # 數量
            "amount": 9,  # 單價
            "remarks": 24,  # 說明
            "email": 25,  # E-MAIL
            "personal_identity": 26,  # 個人身分別
            "residence_days": 27,  # 居留天數
        }

    def ensure_export_directory(self):
        """確保匯出目錄存在"""
        Path(self.export_base_path).mkdir(parents=True, exist_ok=True)

    def export_roster_to_excel(
        self,
        roster: PaymentRoster,
        include_excluded: bool = False,
        *,
        template_name: Optional[str] = None,
        include_header: bool = True,
        include_statistics: bool = True,
        async_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        匯出造冊至Excel檔案

        Args:
            roster: 造冊對象
            include_excluded: 是否包含被排除的項目
            template_name: 指定模板名稱 (預設為設定檔定義)
            include_header: 是否在檔案中包含表頭
            include_statistics: 是否加入統計資訊工作表
            async_mode: 是否以非同步模式回傳背景任務資訊

        Returns:
            Dict[str, Any]: 匯出結果
            {
                "file_path": str,
                "file_name": str,
                "file_size": int,
                "file_hash": str,
                "total_rows": int,
                "qualified_count": int,
                "disqualified_count": int,
                "template_name": str,
                "include_header": bool,
                "include_statistics": bool,
            }

        Raises:
            FileStorageError: 檔案儲存失敗
        """
        resolved_template_path = self._resolve_template_path(template_name)
        resolved_template_name = os.path.basename(resolved_template_path)

        if async_mode:
            task_id = f"roster-export-{uuid4().hex}"
            estimated_completion = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
            return {
                "task_id": task_id,
                "status": "queued",
                "template_name": resolved_template_name,
                "include_header": include_header,
                "include_statistics": include_statistics,
                "estimated_completion": estimated_completion,
            }

        try:
            # 取得造冊明細
            roster_items = self._get_roster_items(roster, include_excluded)

            # 產生檔案名稱
            file_name = roster.generate_excel_filename()
            file_path = os.path.join(self.export_base_path, file_name)

            # 準備Excel資料
            excel_data = self._prepare_excel_data(roster, roster_items)

            # 驗證資料品質
            validation_result = self._validate_export_data(excel_data)
            if validation_result["warnings"]:
                logger.warning(f"Data validation warnings: {validation_result['warnings']}")
            if not validation_result["is_valid"]:
                logger.error(f"Data validation failed: {validation_result['errors']}")
                raise FileStorageError(
                    f"Data validation failed: {'; '.join(validation_result['errors'])}", file_name=file_name
                )

            # 建立Excel檔案
            self._create_excel_file(
                excel_data,
                file_path,
                roster,
                template_path=resolved_template_path,
                include_header=include_header,
                include_statistics=include_statistics,
            )

            # 計算檔案資訊
            file_size = os.path.getsize(file_path)
            file_hash = self._calculate_file_hash(file_path)

            # 更新造冊檔案資訊
            roster.excel_filename = file_name
            roster.excel_file_path = file_path
            roster.excel_file_size = file_size
            roster.excel_file_hash = file_hash

            qualified_count = sum(1 for item in roster_items if item.is_qualified and item.is_included)
            disqualified_count = len(roster_items) - qualified_count

            logger.info(f"Excel export completed: {file_name} ({file_size} bytes)")

            return {
                "file_path": file_path,
                "file_name": file_name,
                "file_size": file_size,
                "file_hash": file_hash,
                "total_rows": len(roster_items),
                "qualified_count": qualified_count,
                "disqualified_count": disqualified_count,
                "validation_result": validation_result,
                "template_columns": self.template_columns,
                "template_name": resolved_template_name,
                "include_header": include_header,
                "include_statistics": include_statistics,
            }

        except Exception as e:
            logger.error(f"Excel export failed: {e}")
            raise FileStorageError(f"Failed to export Excel file: {e}", file_name=file_name)

    def _get_roster_items(self, roster: PaymentRoster, include_excluded: bool) -> List[PaymentRosterItem]:
        """取得造冊明細"""
        items = roster.items

        if not include_excluded:
            items = [item for item in items if item.is_included]

        return sorted(items, key=lambda x: x.student_name)

    def _resolve_template_path(self, template_name: Optional[str]) -> str:
        """Resolve Excel template path based on optional template name"""
        if not template_name:
            return self.template_path

        candidate = template_name if template_name.lower().endswith(".xlsx") else f"{template_name}.xlsx"
        candidate_path = os.path.join(self.template_dir, candidate)

        if os.path.exists(candidate_path):
            return candidate_path

        logger.warning("Template %s not found. Falling back to default template.", candidate_path)
        return self.template_path

    def _get_filtered_roster_items(self, roster: PaymentRoster, include_excluded: bool) -> List[PaymentRosterItem]:
        """Compatibility helper for legacy calls that expect filtered roster items"""
        return self._get_roster_items(roster, include_excluded)

    def _prepare_excel_data(self, roster: PaymentRoster, roster_items: List[PaymentRosterItem]) -> List[Dict]:
        """準備Excel資料 - STD_UP_MIXLISTA 30欄位格式"""
        excel_data = []

        for idx, item in enumerate(roster_items, start=1):
            # 取得學生相關資訊

            # 驗證必填欄位
            if not item.student_id_number or not item.student_name:
                logger.warning(
                    f"Skipping item {idx} due to missing required fields: ID={item.student_id_number}, Name={item.student_name}"
                )
                continue

            # 生成備註 (第25欄) - 包含期間標籤、獎學金名稱和狀態
            remarks_parts = []
            if hasattr(roster, "period_label") and roster.period_label:
                remarks_parts.append(f"期間:{roster.period_label}")
            remarks_parts.append(f"獎學金:{item.scholarship_name}")
            if not item.is_included:
                remarks_parts.append("狀態:不合格")
            if not item.bank_account or not item.bank_code:
                remarks_parts.append("缺銀行資訊")
            remarks = " ".join(remarks_parts)

            # 建立STD_UP_MIXLISTA 30欄位資料映射
            row_data = {
                # 1. 身分證字號 (必填)
                "身分證字號": item.student_id_number,
                # 2. 姓名 (必填)
                "姓名": item.student_name,
                # 3. 帳號 (若無則標註於說明欄)
                "帳號": item.bank_account or "",
                # 4. 銀行代碼 (若無則標註於說明欄)
                "銀行代碼": item.bank_code or "",
                # 5. 職別(稱) (固定值"學生")
                "職別(稱)": "學生",
                # 6. 戶籍地址 (選填)
                "戶籍地址": item.permanent_address or "",
                # 7. 是否為學生 (固定值"1")
                "是否為學生": "1",
                # 8. 給付總額
                "給付總額": float(item.scholarship_amount) if item.scholarship_amount else 0,
                # 9. 免稅額
                "免稅額": float(item.scholarship_amount) if item.scholarship_amount else 0,  # 獎學金通常全額免稅
                # 10. 應扣繳稅額
                "應扣繳稅額": 0,  # 獎學金免稅
                # 11-24. 各月份金額 (都填"0")
                "1月": "0",
                "2月": "0",
                "3月": "0",
                "4月": "0",
                "5月": "0",
                "6月": "0",
                "7月": "0",
                "8月": "0",
                "9月": "0",
                "10月": "0",
                "11月": "0",
                "12月": "0",
                "本期獎金": "0",
                "其他": "0",
                # 25. 說明
                "說明": remarks,
                # 26. 身分證件字號 (與第1欄相同)
                "身分證件字號": item.student_id_number,
                # 27. 統一證號
                "統一證號": "",  # 個人通常為空
                # 28. 扣繳憑單類別
                "扣繳憑單類別": "50",  # 獎學金所得類別代碼
                # 29. 所得格式代碼
                "所得格式代碼": "50",  # 獎學金格式代碼
                # 30. 申報年度
                "申報年度": str(roster.academic_year)
                if hasattr(roster, "academic_year") and roster.academic_year
                else datetime.now().year,
            }

            # 根據造冊月份，將獎學金金額填入對應月份欄位
            if hasattr(roster, "period_label") and roster.period_label:
                period_label = roster.period_label
                amount_str = str(float(item.scholarship_amount)) if item.scholarship_amount else "0"

                # 解析期間標籤並填入對應月份
                if "-" in period_label:
                    try:
                        if period_label.count("-") == 1:  # YYYY-MM 格式
                            year, month = period_label.split("-")
                            month_num = int(month)
                            if 1 <= month_num <= 12:
                                month_name = f"{month_num}月"
                                if month_name in row_data:
                                    row_data[month_name] = amount_str
                        elif "H1" in period_label or "H2" in period_label:  # 半年度格式
                            # 上半年(H1)或下半年(H2)的處理可以在這裡實作
                            pass
                    except (ValueError, IndexError):
                        logger.warning(f"Failed to parse period_label: {period_label}")

            # 儲存Excel行資料到資料庫
            item.excel_row_data = row_data
            item.excel_remarks = remarks

            excel_data.append(row_data)

        logger.info(f"Prepared {len(excel_data)} rows for STD_UP_MIXLISTA export")
        return excel_data

    def _validate_export_data(self, excel_data: List[Dict]) -> Dict[str, Any]:
        """驗證STD_UP_MIXLISTA格式匯出資料品質"""
        validation_result = {"is_valid": True, "warnings": [], "errors": [], "statistics": {}}

        if not excel_data:
            validation_result["errors"].append("No data to export")
            validation_result["is_valid"] = False
            return validation_result

        # 統計資料
        total_rows = len(excel_data)
        missing_bank_info = 0
        missing_required_info = 0
        invalid_amounts = 0
        invalid_format = 0

        # STD_UP_MIXLISTA必填欄位檢查
        required_fields = ["身分證字號", "姓名"]  # 第1、2欄必填

        for idx, row in enumerate(excel_data, start=1):
            # 檢查必填欄位
            missing_required = False
            for field in required_fields:
                if not row.get(field) or str(row.get(field)).strip() == "":
                    missing_required = True
                    break

            if missing_required:
                missing_required_info += 1

            # 檢查銀行資訊 (第3、4欄)
            if not row.get("銀行代碼") or not row.get("帳號"):
                missing_bank_info += 1

            # 檢查金額格式 (第8欄給付總額)
            amount = row.get("給付總額", 0)
            if not isinstance(amount, (int, float)) or amount <= 0:
                invalid_amounts += 1

            # 檢查職別固定值 (第5欄)
            if row.get("職別(稱)") != "學生":
                invalid_format += 1

            # 檢查學生標記 (第7欄)
            if row.get("是否為學生") != "1":
                invalid_format += 1

            # 檢查扣繳憑單類別 (第28欄)
            if row.get("扣繳憑單類別") != "50":
                invalid_format += 1

        # 產生錯誤和警告
        if missing_required_info > 0:
            validation_result["errors"].append(f"{missing_required_info} records missing required fields (身分證字號/姓名)")
            validation_result["is_valid"] = False

        if missing_bank_info > 0:
            validation_result["warnings"].append(f"{missing_bank_info} records missing bank information (將標註於說明欄)")

        if invalid_amounts > 0:
            validation_result["warnings"].append(f"{invalid_amounts} records have invalid amounts")

        if invalid_format > 0:
            validation_result["warnings"].append(f"{invalid_format} records have format issues")

        # 計算完整性統計
        complete_records = total_rows - missing_bank_info
        completion_rate = (complete_records / total_rows * 100) if total_rows > 0 else 0

        validation_result["statistics"] = {
            "total_rows": total_rows,
            "missing_bank_info": missing_bank_info,
            "missing_required_info": missing_required_info,
            "invalid_amounts": invalid_amounts,
            "invalid_format": invalid_format,
            "completion_rate": completion_rate,
            "std_up_mixlista_compliant": missing_required_info == 0 and invalid_format == 0,
        }

        logger.info(
            f"STD_UP_MIXLISTA validation: {total_rows} total rows, "
            f"{missing_required_info} missing required, {missing_bank_info} missing bank info, "
            f"completion rate: {completion_rate:.1f}%"
        )

        return validation_result

    def _create_excel_file(
        self,
        excel_data: List[Dict],
        file_path: str,
        roster: PaymentRoster,
        *,
        template_path: str,
        include_header: bool,
        include_statistics: bool,
    ):
        """建立Excel檔案 - 優先使用模板檔案"""
        try:
            use_template = include_header and os.path.exists(template_path)

            if use_template:
                wb = load_workbook(template_path)
                ws = wb.active
                logger.info("Using template file for Excel generation: %s", template_path)
            else:
                wb = Workbook()
                ws = wb.active
                ws.title = "印領清冊"

                if include_header:
                    for col_idx, column_name in enumerate(self.template_columns, start=1):
                        cell = ws.cell(row=1, column=col_idx, value=column_name)
                        cell.font = Font(bold=True)
                        cell.alignment = Alignment(horizontal="center", vertical="center")
                        cell.fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid")

                logger.info("Created new Excel file using default structure (include_header=%s)", include_header)

            start_row = 2 if include_header else 1

            if include_header and ws.max_row >= start_row:
                ws.delete_rows(start_row, ws.max_row - start_row + 1)
            elif not include_header and ws.max_row >= 1:
                ws.delete_rows(1, ws.max_row)

            for row_idx, row_data in enumerate(excel_data, start=start_row):
                for col_idx, column_name in enumerate(self.template_columns, start=1):
                    value = row_data.get(column_name, "")
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)

                    if column_name in ["金額", "扣繳稅額"] and isinstance(value, (int, float)):
                        cell.number_format = "#,##0"
                    elif column_name in ["序號", "流水號"]:
                        cell.alignment = Alignment(horizontal="center")
                    elif column_name in ["申請日期", "核准日期", "造冊日期"] and isinstance(value, str) and value:
                        cell.alignment = Alignment(horizontal="center")

            total_rows = max(len(excel_data) + (1 if include_header else 0), 1)
            self._apply_excel_styling(ws, total_rows, include_header)

            if include_statistics:
                self._add_worksheet_info(wb, roster)

            wb.save(file_path)
            logger.info("Excel file created successfully: %s", file_path)

        except Exception as e:
            logger.error(f"Failed to create Excel file: {e}")
            raise FileStorageError(f"Failed to create Excel file: {e}", file_name=os.path.basename(file_path))

    def _apply_excel_styling(self, ws, max_row: int, include_header: bool):
        """應用Excel樣式"""
        self._set_column_widths(ws)
        self._set_borders(ws, max_row)
        ws.freeze_panes = "A2" if include_header else None

    def _set_column_widths(self, ws):
        """設定欄寬 - 智慧調整基於欄位內容"""
        # 預設欄寬設定
        default_widths = {
            "序號": 6,
            "流水號": 6,
            "身分證字號": 12,
            "姓名": 10,
            "學校代碼": 8,
            "學校名稱": 15,
            "郵遞區號": 8,
            "地址": 25,
            "電話": 12,
            "電子信箱": 20,
            "銀行代號": 8,
            "銀行名稱": 12,
            "帳號": 15,
            "戶名": 10,
            "金額": 10,
            "所得類別": 8,
            "扣繳稅額": 8,
            "身分別": 8,
            "居留天數是否滿183天": 12,
            "統一編號": 10,
            "機關代號": 8,
            "獎學金名稱": 20,
            "獎學金子類型": 15,
            "學年度": 8,
            "學期": 8,
            "系所": 15,
            "年級": 6,
            "學號": 12,
            "指導教授": 10,
            "申請日期": 10,
            "核准日期": 10,
            "造冊日期": 10,
            "審核狀態": 8,
            "備註": 20,
            "驗證狀態": 10,
        }

        for col_idx, column_name in enumerate(self.template_columns, start=1):
            width = default_widths.get(column_name, 12)
            column_letter = get_column_letter(col_idx)
            ws.column_dimensions[column_letter].width = width

    def _set_borders(self, ws, max_row: int):
        """設定邊框"""
        thin_border = Border(
            left=Side(style="thin"), right=Side(style="thin"), top=Side(style="thin"), bottom=Side(style="thin")
        )

        for row in range(1, max_row + 1):
            for col in range(1, len(self.template_columns) + 1):
                ws.cell(row=row, column=col).border = thin_border

    def _add_worksheet_info(self, wb: Workbook, roster: PaymentRoster):
        """加入工作表資訊"""
        info_ws = wb.create_sheet("造冊資訊")

        info_data = [
            ["造冊代碼", roster.roster_code],
            ["期間標記", roster.period_label],
            ["學年度", roster.academic_year],
            ["造冊週期", roster.roster_cycle.value],
            ["觸發方式", roster.trigger_type.value],
            ["產生時間", roster.started_at.strftime("%Y-%m-%d %H:%M:%S") if roster.started_at else ""],
            ["完成時間", roster.completed_at.strftime("%Y-%m-%d %H:%M:%S") if roster.completed_at else ""],
            ["總申請數", roster.total_applications or 0],
            ["合格人數", roster.qualified_count or 0],
            ["不合格人數", roster.disqualified_count or 0],
            ["總金額", float(roster.total_amount) if roster.total_amount else 0],
            ["學籍驗證啟用", "是" if roster.student_verification_enabled else "否"],
            ["API失敗次數", roster.verification_api_failures or 0],
        ]

        for row_idx, (label, value) in enumerate(info_data, start=1):
            info_ws.cell(row=row_idx, column=1, value=label).font = Font(bold=True)
            info_ws.cell(row=row_idx, column=2, value=value)

        info_ws.column_dimensions["A"].width = 15
        info_ws.column_dimensions["B"].width = 20

    def _extract_postal_code(self, address: Optional[str]) -> str:
        """從地址中提取郵遞區號"""
        if not address:
            return ""

        # 簡單的郵遞區號提取邏輯
        import re

        match = re.match(r"^(\d{3,5})", address.strip())
        return match.group(1) if match else ""

    def _get_advisor_name(self, student) -> str:
        """取得指導教授姓名"""
        if not student:
            return ""

        try:
            # 查詢學生的指導教授關係
            from sqlalchemy.orm import sessionmaker

            from app.db.session import engine
            from app.models.professor_student_relationship import ProfessorStudentRelationship

            SessionLocal = sessionmaker(bind=engine)
            db = SessionLocal()

            try:
                relationship = (
                    db.query(ProfessorStudentRelationship)
                    .filter(
                        ProfessorStudentRelationship.student_id == student.id,
                        ProfessorStudentRelationship.is_active.is_(True),
                    )
                    .first()
                )

                if relationship and relationship.professor:
                    return relationship.professor.name

            finally:
                db.close()

        except Exception as e:
            logger.warning(f"Failed to get advisor name for student {student.id}: {e}")

        return ""

    def _generate_remarks(self, item: PaymentRosterItem, roster: PaymentRoster) -> str:
        """產生備註欄內容"""
        remarks = []

        # 基本造冊資訊
        remarks.append(f"造冊期間: {roster.period_label}")
        if roster.scholarship_configuration:
            remarks.append(f"獎學金: {roster.scholarship_configuration.config_code}")

        # 判斷狀態
        if not item.is_included:
            if item.exclusion_reason:
                remarks.append(f"排除原因: {item.exclusion_reason}")
        elif item.verification_status.value != "verified":
            remarks.append(f"學籍狀態: {self._get_verification_status_label(item.verification_status)}")
        elif not item.bank_account or not item.bank_code:
            remarks.append("缺少銀行資訊")
        else:
            remarks.append("合格")

        # 添加規則驗證警告（如果有）
        if item.warning_rules:
            warning_msg = "警告: " + "; ".join(item.warning_rules)
            remarks.append(warning_msg)

        return "; ".join(remarks)

    def _get_verification_status_label(self, status) -> str:
        """取得驗證狀態標籤"""
        labels = {
            "verified": "已驗證",
            "graduated": "已畢業",
            "suspended": "休學中",
            "withdrawn": "已退學",
            "api_error": "驗證錯誤",
            "not_found": "查無此人",
        }
        return labels.get(status.value if hasattr(status, "value") else str(status), str(status))

    def _calculate_file_hash(self, file_path: str) -> str:
        """計算檔案SHA256雜湊值"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def get_excel_file_info(self, roster: PaymentRoster) -> Optional[Dict[str, Any]]:
        """取得Excel檔案資訊"""
        if not roster.excel_file_path or not os.path.exists(roster.excel_file_path):
            return None

        return {
            "file_name": roster.excel_filename,
            "file_path": roster.excel_file_path,
            "file_size": roster.excel_file_size,
            "file_hash": roster.excel_file_hash,
            "created_at": roster.completed_at,
        }

    def delete_excel_file(self, roster: PaymentRoster) -> bool:
        """刪除Excel檔案"""
        if not roster.excel_file_path:
            return False

        try:
            if os.path.exists(roster.excel_file_path):
                os.remove(roster.excel_file_path)

            # 清除資料庫中的檔案資訊
            roster.excel_filename = None
            roster.excel_file_path = None
            roster.excel_file_size = None
            roster.excel_file_hash = None

            logger.info(f"Deleted Excel file: {roster.excel_file_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete Excel file: {e}")
            return False

    def preview_roster_export(
        self,
        roster: PaymentRoster,
        template_name: str = "STD_UP_MIXLISTA",
        include_header: bool = True,
        max_preview_rows: int = 10,
        *,
        include_excluded: bool = False,
    ) -> Dict[str, Any]:
        """
        預覽造冊匯出內容
        Preview roster export content without creating actual file
        """
        try:
            # 取得造冊項目
            roster_items = self._get_filtered_roster_items(roster, include_excluded=include_excluded)

            # 準備Excel資料
            excel_data = self._prepare_excel_data(roster, roster_items)

            # 驗證資料
            validation_result = self._validate_export_data(excel_data)

            # 限制預覽行數
            preview_data = excel_data[:max_preview_rows] if max_preview_rows > 0 else excel_data

            # 產生metadata
            metadata = {
                "template_name": template_name,
                "total_rows": len(excel_data),
                "preview_rows": len(preview_data),
                "roster_code": roster.roster_code,
                "period_label": getattr(roster, "period_label", ""),
                "generated_at": datetime.now().isoformat(),
                "std_up_mixlista_format": True,
            }

            return {
                "preview_data": preview_data,
                "total_rows": len(excel_data),
                "column_headers": self.template_columns,
                "validation_result": validation_result,
                "metadata": metadata,
            }

        except Exception as e:
            logger.error(f"Failed to preview roster export: {e}")
            raise FileStorageError(f"預覽產生失敗: {str(e)}")

    def process_async_export(
        self,
        roster_id: int,
        task_id: str,
        user_id: int,
        *,
        template_name: Optional[str] = None,
        include_header: bool = True,
        include_statistics: bool = True,
        include_excluded: bool = False,
    ):
        """
        處理非同步匯出任務
        Process asynchronous export task
        """
        try:
            from app.core.database import get_db_sync
            from app.services.audit_service import audit_service
            from app.services.minio_service import minio_service

            # 取得資料庫session
            db = next(get_db_sync())

            try:
                # 取得造冊
                roster = db.query(PaymentRoster).filter(PaymentRoster.id == roster_id).first()
                if not roster:
                    raise ValueError(f"Roster {roster_id} not found")

                # 執行匯出
                export_result = self.export_roster_to_excel(
                    roster=roster,
                    template_name=template_name or self.default_template_name,
                    include_header=include_header,
                    include_statistics=include_statistics,
                    include_excluded=include_excluded,
                    async_mode=False,
                )

                # 上傳到MinIO
                with open(export_result["file_path"], "rb") as f:
                    file_content = f.read()

                minio_result = minio_service.upload_roster_file(
                    file_content=file_content,
                    filename=os.path.basename(export_result["file_path"]),
                    roster_id=roster_id,
                    metadata={"task_id": task_id, "user_id": str(user_id)},
                )

                # 記錄稽核日誌
                audit_service.log_excel_export(
                    roster_id=roster_id,
                    filename=minio_result["object_name"],
                    file_size=minio_result["file_size"],
                    record_count=len(self._get_filtered_roster_items(roster, include_excluded=include_excluded)),
                    user_id=user_id,
                    user_name=f"user_{user_id}",
                    export_format="xlsx",
                    db=db,
                )

                logger.info(f"Async export completed: roster_id={roster_id}, task_id={task_id}")

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Async export failed: roster_id={roster_id}, task_id={task_id}, error={e}")
            # 這裡可以實作錯誤通知機制

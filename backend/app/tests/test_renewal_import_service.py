import io

import pandas as pd
import pytest
from unittest.mock import Mock

from app.models.scholarship import ScholarshipType
from app.services.renewal_import_service import RenewalImportService


def _xlsx_bytes(rows):
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="續領")
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def service(db):
    return RenewalImportService(db)


@pytest.fixture
def mock_scholarship():
    s = Mock(spec=ScholarshipType)
    s.id = 1
    s.name = "PhD Scholarship"
    s.code = "phd"
    s.sub_type_list = ["nstc", "moe_1w"]
    return s


@pytest.mark.asyncio
async def test_parse_keeps_only_passed_rows(service, mock_scholarship):
    content = _xlsx_bytes(
        [
            {
                "學號": "413271002",
                "學生姓名": "曾美麗",
                "獎學金類別": "國科會",
                "學生是否申請續領": "是",
                "續領審核結果": "通過",
                "郵局帳號": "1234567890123",
                "指導教授本校人事編號": "P001",
            },
            {
                "學號": "413271003",
                "學生姓名": "王大明",
                "獎學金類別": "教育部",
                "學生是否申請續領": "否",
                "續領審核結果": "領獎期滿，無續領",
                "郵局帳號": "",
                "指導教授本校人事編號": "",
            },
        ]
    )
    service.db.get = Mock(return_value=mock_scholarship)

    async def _get(*a, **k):
        return mock_scholarship

    service.db.get = _get
    parsed, skipped, errors = await service.parse_renewal_excel(
        content, scholarship_type_id=1, academic_year=114, semester="first"
    )
    assert [r["student_id"] for r in parsed] == ["413271002"]
    assert parsed[0]["sub_type"] == "nstc"
    assert len(skipped) == 1
    assert errors == []

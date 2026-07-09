import io

import pandas as pd
import pytest
from unittest.mock import AsyncMock, Mock

from app.models.application import Application, ApplicationStatus
from app.models.batch_import import BatchImport
from app.models.enums import ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
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


@pytest.mark.asyncio
async def test_validate_flags_sis_not_found_as_error(service):
    service.student_service = Mock()
    service.student_service.api_enabled = True
    service.student_service.get_student_basic_info = AsyncMock(return_value=None)
    parsed = [
        {
            "student_id": "999",
            "student_name": "x",
            "sub_type": "nstc",
            "postal_account": None,
            "advisor_nycu_id": None,
            "advisor_name": None,
            "row_number": 2,
        }
    ]

    errors, warnings = await service.validate_and_preview(
        parsed, college_code="A", scholarship_type_id=1, academic_year=114, semester="first"
    )
    assert any(e["error_type"] == "sis_not_found" for e in errors)
    assert any(w["warning_type"] == "missing_postal_account" for w in warnings)


@pytest.mark.asyncio
async def test_create_renewals_sets_approved_fields(service):
    scholarship = Mock(spec=ScholarshipType)
    scholarship.id = 1
    scholarship.name = "PhD"
    scholarship.sub_type_selection_mode = "single"

    config = Mock(spec=ScholarshipConfiguration)
    config.id = 7
    config.amount = 40000

    batch = Mock(spec=BatchImport)
    batch.id = 3
    batch.importer_id = 10

    user = Mock(spec=User)
    user.id = 99
    user.nycu_id = "413271002"

    parsed = [
        {
            "student_id": "413271002",
            "student_name": "曾美麗",
            "sub_type": "nstc",
            "postal_account": "1234567890123",
            "advisor_nycu_id": "P001",
            "advisor_name": "張教授",
            "row_number": 2,
        }
    ]

    from unittest.mock import AsyncMock, patch

    captured = []

    async def _get(model, _id):
        return scholarship

    service.db.get = _get
    with (
        patch.object(service, "_get_or_create_users_bulk", new=AsyncMock(return_value={"413271002": user})),
        patch.object(
            service.student_service,
            "get_student_snapshot",
            new=AsyncMock(return_value={"std_stdcode": "413271002", "std_cname": "曾美麗", "std_pid": "A123456789"}),
        ),
        patch.object(service.db, "add", side_effect=lambda o: captured.append(o)),
        patch.object(service.db, "flush", new=AsyncMock()),
        patch.object(service.db, "execute", new=AsyncMock()),
    ):
        # config lookup + ApplicationSequence lookup both via execute
        cfg_res, seq_res = Mock(), Mock()
        cfg_res.scalar_one_or_none.return_value = config
        seq_res.scalar_one_or_none.return_value = None
        service.db.execute.side_effect = [cfg_res, seq_res]

        created_ids, errors = await service.create_renewals_from_batch(
            batch_import=batch, parsed_rows=parsed, scholarship_type_id=1, academic_year=114, semester="first"
        )

    apps = [o for o in captured if isinstance(o, Application)]
    assert len(apps) == 1
    app = apps[0]
    assert app.is_renewal is True
    assert app.status == ApplicationStatus.approved.value
    assert app.review_stage == ReviewStage.quota_distributed.value
    assert app.sub_scholarship_type == "nstc"
    assert app.allocation_config_id == 7
    assert app.amount == 40000
    assert app.import_source == "renewal_import"
    assert app.app_id.endswith("R")
    assert app.submitted_form_data["postal_account"] == "1234567890123"
    assert errors == []

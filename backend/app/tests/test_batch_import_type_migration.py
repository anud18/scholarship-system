import pytest

from app.models.batch_import import BatchImport


@pytest.mark.asyncio
async def test_batch_import_defaults_import_type_application(db):
    batch = BatchImport(
        importer_id=1,
        college_code="A",
        scholarship_type_id=1,
        academic_year=113,
        file_name="x.xlsx",
        total_records=0,
    )
    db.add(batch)
    await db.flush()
    assert batch.import_type == "application"

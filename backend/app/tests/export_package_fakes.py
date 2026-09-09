"""Shared doubles for the export-package tests (not collected: no test_ prefix).

FakeMinio / FakeMinioResponse mimic the minio-py ``get_object`` surface the
service actually uses — a urllib3-style response with ``headers``, chunked
``stream()``, ``close()`` and ``release_conn()``. ``read()`` is deliberately
absent so a regression back to whole-object reads fails loudly (issue #1376).
``collect_zip`` drains the streaming API into a BytesIO for tests that inspect
the finished archive.
"""

import io
from types import SimpleNamespace
from typing import Dict, FrozenSet, Iterator, List

from app.models.application import Application
from app.services.export_package_service import ExportPackageService, ExportPlan


class FakeMinioResponse:
    def __init__(self, payload: bytes, chunk_size: int, fail_midstream: bool) -> None:
        self._payload = payload
        self._chunk_size = chunk_size
        self._fail_midstream = fail_midstream
        self.headers = {"Content-Length": str(len(payload))}
        self.closed = False
        self.released = False

    def stream(self, amt: int) -> Iterator[bytes]:
        for index, start in enumerate(range(0, len(self._payload), self._chunk_size)):
            if self._fail_midstream and index == 1:
                raise ConnectionError("connection reset by storage")
            yield self._payload[start : start + self._chunk_size]

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class FakeMinio:
    """dict-backed MinIO double; unknown object_name raises like NoSuchKey.

    Objects listed in ``fail_midstream`` deliver their first chunk and then
    raise, mimicking a storage connection dropping half-way through a copy.
    """

    def __init__(
        self, objects: Dict[str, bytes], chunk_size: int = 7, fail_midstream: FrozenSet[str] = frozenset()
    ) -> None:
        self.objects = objects
        self.chunk_size = chunk_size
        self.fail_midstream = fail_midstream

    def get_file_stream(self, object_name: str) -> FakeMinioResponse:
        if object_name not in self.objects:
            raise Exception(f"NoSuchKey: {object_name}")
        return FakeMinioResponse(self.objects[object_name], self.chunk_size, object_name in self.fail_midstream)


def make_file(
    file_type: str, original_filename: str, object_name: str, mime_type: str = "application/pdf"
) -> SimpleNamespace:
    """Duck-typed ApplicationFile stub with the four attributes the export reads."""
    return SimpleNamespace(
        file_type=file_type, original_filename=original_filename, object_name=object_name, mime_type=mime_type
    )


def make_application(
    app_id: int,
    std_code: str,
    files: List[SimpleNamespace],
    cname: str = "甲",
    dep_no: str = "1000",
    dep_name: str = "A系",
) -> Application:
    application = Application(
        user_id=app_id + 10,
        scholarship_type_id=1,
        academic_year=114,
        student_data={
            "trm_depno": dep_no,
            "trm_depname": dep_name,
            "trm_academyname": "某學院",
            "std_stdcode": std_code,
            "std_cname": cname,
        },
        submitted_form_data={},
    )
    application.id = app_id
    # Bypass relationship instrumentation — the file stubs are duck-typed, not
    # mapped ApplicationFile rows.
    application.__dict__["files"] = list(files)
    return application


async def collect_zip(service: ExportPackageService, plan: ExportPlan) -> io.BytesIO:
    """Drain iter_export_zip into a seekable buffer for zipfile inspection."""
    buf = io.BytesIO()
    async for chunk in service.iter_export_zip(plan):
        buf.write(chunk)
    buf.seek(0)
    return buf

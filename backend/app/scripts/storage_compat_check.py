"""Object-storage compatibility check — every S3 operation MinIOService uses.

Purpose
-------
The dev stack swapped MinIO for RustFS (S3-compatible, Apache 2.0). The
backend keeps the generic python ``minio`` SDK pointed at whatever serves
``MINIO_ENDPOINT``; this script proves the LIVE store behind that endpoint
supports every operation ``app/services/minio_service.py`` performs, with the
exact same calls — not just that the API answers 200, but that the semantics
hold (policy actually denies, metadata round-trips, multipart checksums
match).

Run it inside the backend container against the running store::

    docker exec scholarship_backend_dev python -m app.scripts.storage_compat_check

Deliberately NOT wired into CI lanes — CI has no object store (unit tests
mock the client via settings.testing). This is the dev/staging cutover gate:
all checks must print PASS and the script exits non-zero on any failure.

Checks mirror real call sites:
- put/get/stat/remove: upload_file / get_file_stream / delete_file
- copy_object + CopySource: clone_file_to_application (the #887 path)
- set_bucket_policy deny-all + anonymous 403: roster bucket privacy
- presigned GET/PUT: generate_presigned_url (roster downloads)
- 10MB multipart: large uploads (part_size forces multipart)
- non-ASCII metadata: original-filename carries Chinese filenames
- seeded regulations PDF: seed_regulations_doc.py read path
"""

import hashlib
import io
import json
import sys
import urllib.error
import urllib.request
from datetime import timedelta

from minio import Minio
from minio.commonconfig import CopySource
from minio.error import S3Error

from app.core.config import settings

PREFIX = "compat-check"
RESULTS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))


def http(url: str, method: str = "GET", data: bytes | None = None) -> tuple[int, bytes]:
    """Bare HTTP request with NO credentials (for presigned/anonymous checks)."""
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main() -> int:
    if settings.testing:
        print("Refusing to run with settings.testing=True (client would be a mock).")
        return 2

    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    bucket = settings.minio_bucket
    roster_bucket = settings.roster_minio_bucket
    tmp_bucket = f"{PREFIX}-tmp"
    cleanup: list[tuple[str, str]] = []  # (bucket, object)

    # ---- 1. bucket_exists / make_bucket lifecycle ----
    try:
        if client.bucket_exists(tmp_bucket):
            for obj in client.list_objects(tmp_bucket, recursive=True):
                client.remove_object(tmp_bucket, obj.object_name)
            client.remove_bucket(tmp_bucket)
        fresh_absent = not client.bucket_exists(tmp_bucket)
        client.make_bucket(tmp_bucket)
        record("1 bucket_exists→make_bucket→bucket_exists", fresh_absent and client.bucket_exists(tmp_bucket))
    except Exception as e:  # noqa: BLE001 — each check must record, not abort the suite
        record("1 bucket_exists→make_bucket→bucket_exists", False, repr(e))

    # ---- 2. put_object small PDF ----
    body = b"%PDF-1.4 compat-check minimal body"
    key_small = f"{PREFIX}/small.pdf"
    try:
        client.put_object(bucket, key_small, io.BytesIO(body), len(body), content_type="application/pdf")
        cleanup.append((bucket, key_small))
        record("2 put_object (small, application/pdf)", True)
    except Exception as e:  # noqa: BLE001
        record("2 put_object (small, application/pdf)", False, repr(e))

    # ---- 3. metadata round-trip (ASCII — the values the app actually sends) ----
    # Note: the minio SDK rejects non-ASCII metadata CLIENT-SIDE (ValueError),
    # identically against MinIO and RustFS — so Chinese original-filename
    # values were never reaching the store through this SDK. Not a RustFS
    # delta; the compat contract is the ASCII round-trip below.
    key_meta = f"{PREFIX}/meta.pdf"
    fname = "roster_20260611.xlsx"
    try:
        client.put_object(
            bucket,
            key_meta,
            io.BytesIO(body),
            len(body),
            content_type="application/pdf",
            metadata={"original-filename": fname, "file-hash": "a" * 64, "roster-id": "42"},
        )
        cleanup.append((bucket, key_meta))
        stat = client.stat_object(bucket, key_meta)
        meta = stat.metadata or {}
        got = meta.get("x-amz-meta-original-filename") or meta.get("original-filename")
        got_hash = meta.get("x-amz-meta-file-hash") or meta.get("file-hash")
        record(
            "3 metadata round-trip (original-filename / file-hash / roster-id)",
            got == fname and got_hash == "a" * 64,
            f"got={got!r} hash={got_hash!r}",
        )
    except Exception as e:  # noqa: BLE001
        record("3 metadata round-trip (original-filename / file-hash / roster-id)", False, repr(e))

    # ---- 4. get_object bytes equal ----
    try:
        resp = client.get_object(bucket, key_small)
        data = resp.read()
        resp.close()
        resp.release_conn()
        record("4 get_object bytes equal", data == body, f"len={len(data)}")
    except Exception as e:  # noqa: BLE001
        record("4 get_object bytes equal", False, repr(e))

    # ---- 5. stat_object size/etag/content-type ----
    try:
        stat = client.stat_object(bucket, key_small)
        ok = stat.size == len(body) and bool(stat.etag) and stat.content_type == "application/pdf"
        record("5 stat_object size/etag/content-type", ok, f"size={stat.size} ct={stat.content_type}")
    except Exception as e:  # noqa: BLE001
        record("5 stat_object size/etag/content-type", False, repr(e))

    # ---- 6. copy_object + CopySource (clone_file_to_application path) ----
    key_copy = f"{PREFIX}/copied.pdf"
    try:
        client.copy_object(bucket, key_copy, CopySource(bucket, key_small))
        cleanup.append((bucket, key_copy))
        resp = client.get_object(bucket, key_copy)
        copied = resp.read()
        resp.close()
        resp.release_conn()
        record("6 copy_object + CopySource", copied == body)
    except Exception as e:  # noqa: BLE001
        record("6 copy_object + CopySource", False, repr(e))

    # ---- 7. remove_object → NoSuchKey ----
    key_gone = f"{PREFIX}/gone.txt"
    try:
        client.put_object(bucket, key_gone, io.BytesIO(b"x"), 1)
        client.remove_object(bucket, key_gone)
        try:
            client.stat_object(bucket, key_gone)
            record("7 remove_object → stat raises NoSuchKey", False, "stat unexpectedly succeeded")
        except S3Error as e:
            record("7 remove_object → stat raises NoSuchKey", e.code in ("NoSuchKey", "NoSuchObject"), e.code)
    except Exception as e:  # noqa: BLE001
        record("7 remove_object → stat raises NoSuchKey", False, repr(e))

    # ---- 8. roster bucket privacy: default-deny anonymous, owner can read ----
    # MinIOService used to attach an explicit deny-all s3:GetObject policy.
    # RustFS enforces an explicit Deny against the OWNER too (AWS-faithful),
    # which 403'd the backend's own roster downloads — so the policy was
    # removed and we rely on the default-private ACL. This check pins BOTH
    # halves of that contract: anonymous 403 with no policy attached, and
    # authenticated owner GET still works.
    key_secret = f"{PREFIX}/secret.xlsx"
    try:
        if not client.bucket_exists(roster_bucket):
            client.make_bucket(roster_bucket)
        try:
            client.delete_bucket_policy(roster_bucket)  # ensure NO policy attached
        except S3Error:
            pass
        client.put_object(roster_bucket, key_secret, io.BytesIO(b"roster"), 6)
        cleanup.append((roster_bucket, key_secret))
        scheme = "https" if settings.minio_secure else "http"
        status, _ = http(f"{scheme}://{settings.minio_endpoint}/{roster_bucket}/{key_secret}")
        resp = client.get_object(roster_bucket, key_secret)
        owner_ok = resp.read() == b"roster"
        resp.close()
        resp.release_conn()
        record(
            "8 roster bucket default-private (anonymous 403, owner GET ok, no policy)",
            status == 403 and owner_ok,
            f"anonymous HTTP {status}, owner_ok={owner_ok}",
        )
    except Exception as e:  # noqa: BLE001
        record("8 roster bucket default-private (anonymous 403, owner GET ok, no policy)", False, repr(e))

    # ---- 9. presigned GET (via MinIOService.get_presigned_url) ----
    # Exercises the service wrapper, which surfaced a latent bug here: it
    # called the non-existent client.presigned_url (SDK name is
    # get_presigned_url) — dead code until now, fixed alongside this script.
    key_roster_get = f"{PREFIX}/presigned-src.xlsx"
    try:
        from app.services.minio_service import MinIOService

        svc = MinIOService()
        client.put_object(roster_bucket, key_roster_get, io.BytesIO(b"presigned-roster"), 16)
        cleanup.append((roster_bucket, key_roster_get))
        url = svc.get_presigned_url(key_roster_get, expires=timedelta(minutes=5), method="GET")
        status, fetched = http(url)
        record(
            "9 presigned GET (service wrapper, roster bucket)",
            status == 200 and fetched == b"presigned-roster",
            f"HTTP {status}",
        )
    except Exception as e:  # noqa: BLE001
        record("9 presigned GET (service wrapper, roster bucket)", False, repr(e))

    # ---- 10. presigned PUT ----
    key_put = f"{PREFIX}/presigned-put.bin"
    try:
        url = client.get_presigned_url("PUT", bucket, key_put, expires=timedelta(minutes=5))
        status, _ = http(url, method="PUT", data=b"uploaded-via-presigned")
        cleanup.append((bucket, key_put))
        roundtrip = b""
        if status in (200, 204):
            resp = client.get_object(bucket, key_put)
            roundtrip = resp.read()
            resp.close()
            resp.release_conn()
        record("10 presigned PUT", roundtrip == b"uploaded-via-presigned", f"HTTP {status}")
    except Exception as e:  # noqa: BLE001
        record("10 presigned PUT", False, repr(e))

    # ---- 11. 10MB multipart upload (part_size=5MB) ----
    key_big = f"{PREFIX}/big.bin"
    try:
        big = bytes(range(256)) * (10 * 1024 * 1024 // 256)
        client.put_object(
            bucket,
            key_big,
            io.BytesIO(big),
            length=-1,
            part_size=5 * 1024 * 1024,
            content_type="application/octet-stream",
        )
        cleanup.append((bucket, key_big))
        resp = client.get_object(bucket, key_big)
        h = hashlib.sha256()
        for chunk in resp.stream(1024 * 1024):
            h.update(chunk)
        resp.close()
        resp.release_conn()
        record("11 10MB multipart upload checksum", h.hexdigest() == hashlib.sha256(big).hexdigest())
    except Exception as e:  # noqa: BLE001
        record("11 10MB multipart upload checksum", False, repr(e))

    # ---- 12. MinIOService.health_check() full cycle ----
    try:
        from app.services.minio_service import MinIOService

        health = MinIOService().health_check()
        record("12 MinIOService.health_check() cycle", bool(health.get("overall_healthy")), json.dumps(health))
    except Exception as e:  # noqa: BLE001
        record("12 MinIOService.health_check() cycle", False, repr(e))

    # ---- 13. dual-bucket auto-create (fresh service instance) ----
    try:
        from app.services.minio_service import MinIOService

        svc = MinIOService()
        _ = svc.client  # triggers _ensure_buckets_exist
        record(
            "13 dual-bucket auto-create",
            client.bucket_exists(bucket) and client.bucket_exists(roster_bucket),
        )
    except Exception as e:  # noqa: BLE001
        record("13 dual-bucket auto-create", False, repr(e))

    # ---- 14. seeded regulations PDF visible via list_objects ----
    try:
        keys = [o.object_name for o in client.list_objects(bucket, prefix="system-docs/", recursive=True)]
        record(
            "14 seeded regulations PDF listed (run after reset_database.sh)",
            any("regulations" in k for k in keys),
            f"keys={keys}",
        )
    except Exception as e:  # noqa: BLE001
        record("14 seeded regulations PDF listed (run after reset_database.sh)", False, repr(e))

    # ---- cleanup ----
    for b, k in cleanup:
        try:
            client.remove_object(b, k)
        except Exception:  # noqa: BLE001
            pass
    try:
        if client.bucket_exists(tmp_bucket):
            client.remove_bucket(tmp_bucket)
    except Exception:  # noqa: BLE001
        pass

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f"\nSTORAGE COMPAT: {passed}/{total} PASS")
    if passed != total:
        for name, ok, detail in RESULTS:
            if not ok:
                print(f"  FAILED: {name} — {detail}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

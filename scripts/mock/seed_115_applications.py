"""Mock AY115 博士生獎學金 applications on a running DEV stack.

Drives the public API exactly like the student wizard, so the result is
indistinguishable from real submissions (professor auto-assignment, app-id
sequence, application_files in object storage, SIS snapshot):

    mock-SSO login → PUT profile (郵局帳號 + 指導教授) → 存摺封面 upload
    → create draft (form fields) → upload 「所屬」 PDF → submit (or keep draft)

Idempotent: a student who already has a 115 phd application is skipped, so
it can be re-run after every `./scripts/reset_database.sh`.

    python3 scripts/mock/seed_115_applications.py
    MOCK_API_URL=https://localhost:8443 python3 scripts/mock/seed_115_applications.py

DEV ONLY — it relies on mock SSO, which staging/production do not enable.
"""

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from dataclasses import dataclass

API_URL = os.environ.get("MOCK_API_URL", "http://localhost:8000").rstrip("/") + "/api/v1"
ACADEMIC_YEAR = 115
SCHOLARSHIP_CODE = "phd"
DOCUMENT_TYPE = "所屬"
REQUEST_TIMEOUT_SECONDS = 60

# The dev nginx serves a self-signed certificate.
INSECURE_TLS = ssl.create_default_context()
INSECURE_TLS.check_hostname = False
INSECURE_TLS.verify_mode = ssl.CERT_NONE

# 1x1 PNG standing in for a scanned passbook cover.
PASSBOOK_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415408d763f8cfc0f01f0005000201e2f9a3a70000000049454e44ae426082"
)


@dataclass(frozen=True)
class MockApplicant:
    nycu_id: str
    sub_types: tuple
    master_school: str
    phone: str
    advisor_nycu_id: str
    advisor_name: str
    submit: bool = True


APPLICANTS = (
    MockApplicant(
        "314551402", ("nstc",), "國立陽明交通大學/資訊學院/資訊工程學系", "0912111402", "cs_professor", "李資訊教授"
    ),
    MockApplicant(
        "314551404", ("moe_1w",), "國立清華大學/電機資訊學院/資訊工程學系", "0912111404", "cs_professor", "李資訊教授"
    ),
    MockApplicant(
        "315551403",
        ("nstc", "moe_1w"),
        "國立臺灣大學/電機資訊學院/資訊網路與多媒體研究所",
        "0912111403",
        "professor",
        "李教授",
    ),
    MockApplicant(
        "csphd0001", ("nstc",), "國立成功大學/電機資訊學院/資訊工程學系", "0912000001", "cs_professor", "李資訊教授"
    ),
    MockApplicant(
        "csphd0002",
        ("moe_1w",),
        "國立陽明交通大學/資訊學院/人工智慧技術與應用碩士學位學程",
        "0912000002",
        "professor",
        "李教授",
    ),
    MockApplicant(
        "csphd0003",
        ("nstc",),
        "國立中央大學/資訊電機學院/資訊工程學系",
        "0912000003",
        "cs_professor",
        "李資訊教授",
        submit=False,
    ),
    MockApplicant(
        "stuphd001",
        ("nstc", "moe_1w"),
        "國立陽明交通大學/資訊學院/資訊科學與工程研究所",
        "0912000101",
        "cs_professor",
        "李資訊教授",
    ),
    MockApplicant(
        "studirect",
        ("moe_1w",),
        "（學士逕讀博士）國立陽明交通大學/資訊學院/資訊工程學系",
        "0912000102",
        "professor",
        "李教授",
        submit=False,
    ),
)


class ApiError(RuntimeError):
    pass


def _send(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS, context=INSECURE_TLS) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:400]
        raise ApiError(f"{request.get_method()} {request.full_url} → HTTP {exc.code}: {detail}") from exc


def call_json(method: str, path: str, token: str = "", body=None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(API_URL + path, data=data, method=method)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    return _send(request)


def call_upload(path: str, token: str, filename: str, content_type: str, payload: bytes) -> dict:
    boundary = uuid.uuid4().hex
    body = (
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
        + payload
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(API_URL + path, data=body, method="POST")
    request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    request.add_header("Authorization", f"Bearer {token}")
    return _send(request)


def build_pdf(lines: list) -> bytes:
    """One-page PDF with the given ASCII lines, with a correct xref table."""
    text = "BT /F1 14 Tf 50 740 Td 18 TL " + " ".join(f"({line}) '" for line in lines) + " ET"
    objects = [
        "<</Type/Catalog/Pages 2 0 R>>",
        "<</Type/Pages/Kids[3 0 R]/Count 1>>",
        "<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        f"<</Length {len(text)}>>stream\n{text}\nendstream",
        "<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj{obj}endobj\n".encode("latin-1")
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    out += f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return out


def postal_account_for(nycu_id: str) -> str:
    """Deterministic 14-digit 郵局帳號 (局號 7 + 帳號 7); test accounts like
    `stuphd001` are not numeric, so derive the digits from a checksum."""
    return f"0021{zlib.crc32(nycu_id.encode()) % 10**10:010d}"


def field(field_id: str, value: str) -> dict:
    return {"field_id": field_id, "field_type": "text", "value": value, "required": True}


def find_config_id(token: str) -> int:
    eligible = call_json("GET", "/scholarships/eligible", token).get("data") or []
    for item in eligible:
        if item.get("code") == SCHOLARSHIP_CODE and item.get("configuration_id"):
            return item["configuration_id"]
    raise ApiError(f"no eligible {SCHOLARSHIP_CODE} configuration")


def existing_115_applications(token: str) -> list:
    applications = call_json("GET", "/applications", token).get("data") or []
    return [
        app
        for app in applications
        if app.get("academic_year") == ACADEMIC_YEAR and app.get("scholarship_type") == SCHOLARSHIP_CODE
    ]


def is_already_mocked(token: str, applicant: MockApplicant) -> bool:
    """True when the target state already exists. A leftover draft that
    should have been submitted (e.g. an earlier run failed at submit) is
    deleted so it gets rebuilt."""
    for app in existing_115_applications(token):
        if app.get("status") != "draft" or not applicant.submit:
            return True
        call_json("DELETE", f"/applications/{app['id']}", token)
    return False


def save_profile(token: str, applicant: MockApplicant, account_number: str) -> None:
    profile = {
        "account_number": account_number,
        "advisor_name": applicant.advisor_name,
        "advisor_email": f"{applicant.advisor_nycu_id}@nycu.edu.tw",
        "advisor_nycu_id": applicant.advisor_nycu_id,
    }
    try:
        call_json("PUT", "/user-profiles/me", token, profile)
    except ApiError:
        call_json("POST", "/user-profiles/me", token, profile)
    call_upload("/user-profiles/me/bank-document/file", token, "passbook.png", "image/png", PASSBOOK_PNG)


def mock_one(applicant: MockApplicant) -> str:
    login = call_json("POST", "/auth/mock-sso/login", body={"nycu_id": applicant.nycu_id})
    token = login["data"]["access_token"]
    if is_already_mocked(token, applicant):
        return "skipped (already has a 115 application)"

    account_number = postal_account_for(applicant.nycu_id)
    save_profile(token, applicant, account_number)

    created = call_json(
        "POST",
        "/applications?is_draft=true",
        token,
        {
            "scholarship_type": SCHOLARSHIP_CODE,
            "configuration_id": find_config_id(token),
            "scholarship_subtype_list": list(applicant.sub_types),
            "sub_type_preferences": list(applicant.sub_types),
            "agree_terms": True,
            "form_data": {
                "fields": {
                    "master_school_info": field("master_school_info", applicant.master_school),
                    "contact_phone": field("contact_phone", applicant.phone),
                    "postal_account": field("postal_account", account_number),
                    "account_number": field("account_number", account_number),
                    "advisor_name": field("advisor_name", applicant.advisor_name),
                    "advisor_email": field("advisor_email", f"{applicant.advisor_nycu_id}@nycu.edu.tw"),
                    "advisor_nycu_id": field("advisor_nycu_id", applicant.advisor_nycu_id),
                },
                "documents": [],
            },
        },
    )["data"]

    pdf = build_pdf(
        [
            f"AY{ACADEMIC_YEAR} PhD scholarship application (mock data)",
            f"Student: {applicant.nycu_id}",
            f"Sub-types: {', '.join(applicant.sub_types)}",
            f"Advisor: {applicant.advisor_nycu_id}",
        ]
    )
    call_upload(
        f"/applications/{created['id']}/files/upload?file_type={urllib.parse.quote(DOCUMENT_TYPE)}",
        token,
        f"{applicant.nycu_id}-affiliation.pdf",
        "application/pdf",
        pdf,
    )

    if not applicant.submit:
        return f"{created['app_id']} draft"
    submitted = call_json("POST", f"/applications/{created['id']}/submit", token).get("data") or {}
    return f"{created['app_id']} {submitted.get('status', 'submitted')}"


def main() -> int:
    failures = 0
    for applicant in APPLICANTS:
        try:
            outcome = mock_one(applicant)
        except (ApiError, KeyError, urllib.error.URLError) as exc:
            failures += 1
            outcome = f"FAILED: {exc}"
        print(f"{applicant.nycu_id:<10} {'+'.join(applicant.sub_types):<12} {outcome}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

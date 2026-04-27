# College Export Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable college users to download a ZIP file containing all application materials (student summary PDFs + uploaded documents) organized by department.

**Architecture:** New backend service (`ExportPackageService`) generates a ZIP in-memory using `zipfile` + `weasyprint` for PDF generation. A new endpoint in the college review router streams it back. Frontend adds an export button next to the existing "匯出" Excel button, proxied through a new Next.js route.

**Tech Stack:** Python (weasyprint, zipfile, Jinja2), FastAPI StreamingResponse, Next.js API route proxy, React (shadcn Button)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/app/services/export_package_service.py` | ZIP assembly + PDF generation logic |
| Create | `backend/app/templates/student_summary.html` | Jinja2 HTML template for student summary PDF |
| Create | `backend/app/api/v1/endpoints/college_review/export_package.py` | GET endpoint with auth + streaming response |
| Modify | `backend/app/api/v1/endpoints/college_review/__init__.py:14-28` | Register export_package router |
| Modify | `backend/pyproject.toml:110-171` | Add weasyprint dependency |
| Modify | `backend/Dockerfile:15-27` | Add weasyprint system deps + fonts |
| Create | `frontend/app/api/v1/export-package/route.ts` | Next.js proxy route for ZIP download |
| Modify | `frontend/lib/api/modules/college.ts` | Add `exportPackage()` method |
| Modify | `frontend/components/college/review/ApplicationReviewPanel.tsx:452-455` | Add export package button |

---

### Task 1: Add weasyprint dependency and Docker system packages

**Files:**
- Modify: `backend/pyproject.toml:110-171`
- Modify: `backend/Dockerfile:15-27`

- [ ] **Step 1: Add weasyprint to pyproject.toml**

In `backend/pyproject.toml`, add to the `dependencies` list after the `"openpyxl==3.1.2",` line:

```python
    # PDF generation
    "weasyprint==63.1",
```

- [ ] **Step 2: Add system dependencies to Dockerfile**

In `backend/Dockerfile`, update the `apt-get install` block to add weasyprint system deps and CJK fonts. Replace lines 15-27:

```dockerfile
RUN echo "deb http://deb.debian.org/debian bookworm main" > /etc/apt/sources.list && \
    echo "deb http://deb.debian.org/debian-security bookworm-security main" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends --allow-unauthenticated=false \
    curl \
    gcc \
    postgresql-client \
    tesseract-ocr \
    tesseract-ocr-eng \
    libpq-dev \
    libmagic-dev \
    # WeasyPrint dependencies
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libcairo2 \
    # CJK fonts for Chinese PDF generation
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && dpkg --get-selections > /installed-packages.list
```

- [ ] **Step 3: Rebuild backend Docker image to verify deps install**

Run:
```bash
cd /home/howard/scholarship-system/.worktrees/college-export-package
docker compose -f docker-compose.dev.yml build backend
```

Expected: Build succeeds, weasyprint is importable.

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/Dockerfile
git commit -m "chore: add weasyprint dependency and system packages for PDF generation"
```

---

### Task 2: Create the student summary HTML template

**Files:**
- Create: `backend/app/templates/student_summary.html`

- [ ] **Step 1: Create templates directory**

```bash
mkdir -p backend/app/templates
```

- [ ] **Step 2: Create the HTML template**

Create `backend/app/templates/student_summary.html`:

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<style>
  @page {
    size: A4;
    margin: 2cm 1.5cm;
    @top-center {
      content: "{{ scholarship_name }} {{ academic_year }}學年度 {{ semester_label }}";
      font-size: 9pt;
      color: #666;
    }
    @bottom-center {
      content: "匯出時間：{{ export_time }} | 第 " counter(page) " 頁";
      font-size: 8pt;
      color: #999;
    }
  }
  body {
    font-family: "Noto Sans CJK TC", "Noto Sans TC", sans-serif;
    font-size: 10pt;
    line-height: 1.6;
    color: #333;
  }
  h1 {
    font-size: 16pt;
    text-align: center;
    margin-bottom: 20px;
    border-bottom: 2px solid #333;
    padding-bottom: 10px;
  }
  h2 {
    font-size: 12pt;
    background-color: #f0f0f0;
    padding: 5px 10px;
    margin-top: 20px;
    margin-bottom: 10px;
    border-left: 4px solid #333;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 15px;
  }
  th, td {
    border: 1px solid #ccc;
    padding: 6px 10px;
    text-align: left;
    font-size: 10pt;
  }
  th {
    background-color: #f5f5f5;
    font-weight: bold;
    width: 30%;
  }
  .form-field {
    margin-bottom: 4px;
  }
  .form-field-label {
    font-weight: bold;
    display: inline;
  }
  .form-field-value {
    display: inline;
  }
  .doc-list {
    list-style: none;
    padding: 0;
  }
  .doc-list li {
    padding: 3px 0;
    border-bottom: 1px dotted #ddd;
  }
  .doc-list li:last-child {
    border-bottom: none;
  }
</style>
</head>
<body>

<h1>學生資料彙整</h1>

<h2>一、基本資料</h2>
<table>
  <tr><th>學號</th><td>{{ student.std_stdcode | default('—') }}</td></tr>
  <tr><th>姓名</th><td>{{ student.std_cname | default('—') }}</td></tr>
  <tr><th>英文姓名</th><td>{{ student.std_ename | default('—') }}</td></tr>
  <tr><th>學院</th><td>{{ student.trm_academyname | default('—') }}</td></tr>
  <tr><th>系��</th><td>{{ student.trm_depname | default('—') }}</td></tr>
  <tr><th>學位</th><td>{{ degree_label }}</td></tr>
  <tr><th>入學年度</th><td>{{ student.std_enrollyear | default('—') }}</td></tr>
  <tr><th>Email</th><td>{{ student.com_email | default('—') }}</td></tr>
  <tr><th>手機</th><td>{{ student.com_cellphone | default('—') }}</td></tr>
</table>

<h2>二、學業表現</h2>
<table>
  <tr><th>學年 / 學期</th><td>{{ student.trm_year | default('—') }} / {{ student.trm_term | default('—') }}</td></tr>
  <tr><th>GPA</th><td>{{ student.trm_ascore_gpa | default('—') }}</td></tr>
  <tr><th>班排名</th><td>{{ student.trm_placings | default('—') }}{% if student.trm_placingsrate %} ({{ student.trm_placingsrate }}%){% endif %}</td></tr>
  <tr><th>系排名</th><td>{{ student.trm_depplacing | default('—') }}{% if student.trm_depplacingrate %} ({{ student.trm_depplacingrate }}%){% endif %}</td></tr>
  <tr><th>修業學期數</th><td>{{ student.trm_termcount | default('���') }}</td></tr>
</table>

{% if form_fields %}
<h2>三、表單填寫資料</h2>
<table>
  {% for field in form_fields %}
  <tr><th>{{ field.label }}</th><td>{{ field.value | default('—') }}</td></tr>
  {% endfor %}
</table>
{% endif %}

{% if documents %}
<h2>四、上傳文件清單</h2>
<ul class="doc-list">
  {% for doc in documents %}
  <li>{{ doc.name }}（上傳時間：{{ doc.upload_time | default('—') }}）</li>
  {% endfor %}
</ul>
{% endif %}

</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/templates/student_summary.html
git commit -m "feat: add student summary HTML template for PDF generation"
```

---

### Task 3: Create ExportPackageService

**Files:**
- Create: `backend/app/services/export_package_service.py`

- [ ] **Step 1: Create the service file**

Create `backend/app/services/export_package_service.py`:

```python
"""
Export Package Service

Generates ZIP files containing student application materials
organized by department, with auto-generated summary PDFs.
"""

import io
import logging
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import weasyprint
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application import Application, ApplicationFile
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.services.minio_service import MinIOService

logger = logging.getLogger(__name__)

# file_type -> Chinese display name
FILE_TYPE_LABELS: Dict[str, str] = {
    "transcript": "成績單",
    "research_proposal": "��究計畫",
    "recommendation_letter": "推薦信",
    "certificate": "證書",
    "insurance_record": "投保紀錄",
    "agreement": "切結書",
    "bank_account_cover": "存摺封面",
    "other": "其他文件",
}

DEGREE_LABELS: Dict[str, str] = {
    "1": "學士",
    "2": "碩士",
    "3": "博士",
}


def _sanitize_filename(name: str) -> str:
    """Replace characters that are invalid in ZIP file paths."""
    return re.sub(r'[/\\:*?"<>|]', "_", name).strip()


class ExportPackageService:
    def __init__(self, db: AsyncSession, minio_service: MinIOService):
        self.db = db
        self.minio = minio_service
        template_dir = Path(__file__).resolve().parent.parent / "templates"
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=True,
        )

    async def generate_export_zip(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
    ) -> Tuple[io.BytesIO, str]:
        """
        Generate a ZIP file with all application materials.

        Returns:
            Tuple of (BytesIO buffer, suggested filename)
        """
        # 1. Get scholarship info for naming
        scholarship_name, college_name = await self._get_scholarship_and_college_info(
            scholarship_type_id, academic_year, semester, college_code
        )

        # 2. Query applications with files
        applications = await self._query_applications(
            scholarship_type_id, academic_year, semester, college_code
        )

        if not applications:
            raise ValueError("無申請資料可匯出")

        # 3. Group by department
        dept_groups: Dict[str, List[Application]] = defaultdict(list)
        for app in applications:
            student = app.student_data or {}
            dep_no = student.get("trm_depno", "unknown")
            dep_name = student.get("trm_depname", "未知系所")
            key = f"{_sanitize_filename(dep_no)}_{_sanitize_filename(dep_name)}"
            dept_groups[key].append(app)

        # 4. Build ZIP
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for dept_folder, apps in sorted(dept_groups.items()):
                for app in apps:
                    await self._add_application_to_zip(
                        zf, dept_folder, app, scholarship_name, academic_year, semester
                    )

        buf.seek(0)

        # 5. Build filename
        semester_label = {"first": "1", "second": "2"}.get(semester, "0") if semester else "0"
        zip_filename = (
            f"{_sanitize_filename(scholarship_name)}"
            f"_申請資料_{academic_year}_{semester_label}"
            f"_{_sanitize_filename(college_name or '全校')}.zip"
        )

        return buf, zip_filename

    async def _get_scholarship_and_college_info(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
    ) -> Tuple[str, Optional[str]]:
        """Get scholarship name and college name for ZIP filename."""
        stmt = select(ScholarshipType).where(ScholarshipType.id == scholarship_type_id)
        result = await self.db.execute(stmt)
        scholarship = result.scalar_one_or_none()
        if not scholarship:
            raise ValueError(f"找不到獎學金類型 ID={scholarship_type_id}")

        scholarship_name = scholarship.name

        # Get college name from first matching application's student_data
        college_name = None
        if college_code:
            app_stmt = (
                select(Application)
                .where(
                    Application.scholarship_type_id == scholarship_type_id,
                    Application.academic_year == academic_year,
                )
                .limit(1)
            )
            if semester:
                app_stmt = app_stmt.where(Application.semester == semester)
            app_result = await self.db.execute(app_stmt)
            sample_app = app_result.scalar_one_or_none()
            if sample_app and sample_app.student_data:
                college_name = sample_app.student_data.get("trm_academyname")

        return scholarship_name, college_name

    async def _query_applications(
        self,
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
        college_code: Optional[str],
    ) -> List[Application]:
        """Query applications with their files, filtered by college if needed."""
        stmt = (
            select(Application)
            .options(selectinload(Application.files))
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
            )
        )

        if semester:
            stmt = stmt.where(Application.semester == semester)

        result = await self.db.execute(stmt)
        applications = list(result.scalars().all())

        # Filter by college_code using student_data
        if college_code:
            applications = [
                app for app in applications
                if app.student_data and app.student_data.get("std_academyno") == college_code
            ]

        return applications

    async def _add_application_to_zip(
        self,
        zf: zipfile.ZipFile,
        dept_folder: str,
        app: Application,
        scholarship_name: str,
        academic_year: int,
        semester: Optional[str],
    ) -> None:
        """Add one application's files + summary PDF to the ZIP."""
        student = app.student_data or {}
        std_code = _sanitize_filename(student.get("std_stdcode", "unknown"))
        std_name = _sanitize_filename(student.get("std_cname", "未知"))
        student_folder = f"{std_code}_{std_name}"
        base_path = f"{dept_folder}/{student_folder}"

        # Generate summary PDF
        try:
            pdf_bytes = self._generate_summary_pdf(app, scholarship_name, academic_year, semester)
            zf.writestr(f"{base_path}/學生資料���整.pdf", pdf_bytes)
        except Exception as e:
            logger.error(f"Failed to generate summary PDF for app {app.id}: {e}")
            zf.writestr(
                f"{base_path}/_錯誤_彙整PDF生成失敗.txt",
                f"PDF 生成失敗：{str(e)}",
            )

        # Add uploaded files from ApplicationFile records
        file_type_counter: Dict[str, int] = defaultdict(int)
        for af in app.files:
            file_type_counter[af.file_type or "other"] += 1
            count = file_type_counter[af.file_type or "other"]
            label = FILE_TYPE_LABELS.get(af.file_type or "other", "其他文件")

            # Determine file extension from original filename or mime_type
            ext = ""
            if af.original_filename and "." in af.original_filename:
                ext = "." + af.original_filename.rsplit(".", 1)[1]
            elif af.mime_type and "/" in af.mime_type:
                ext_map = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}
                ext = ext_map.get(af.mime_type, "")

            # Add sequence number only if multiple files of same type
            total_of_type = sum(1 for f in app.files if (f.file_type or "other") == (af.file_type or "other"))
            if total_of_type > 1:
                filename = f"{label}_{count}{ext}"
            else:
                filename = f"{label}{ext}"

            try:
                response = self.minio.get_file_stream(af.object_name)
                file_bytes = response.read()
                response.close()
                response.release_conn()
                zf.writestr(f"{base_path}/{_sanitize_filename(filename)}", file_bytes)
            except Exception as e:
                logger.error(f"Failed to fetch file {af.object_name} for app {app.id}: {e}")
                zf.writestr(
                    f"{base_path}/_錯誤_找不到檔案_{_sanitize_filename(label)}.txt",
                    f"檔案下載失敗：{af.original_filename or af.object_name}\n錯���：{str(e)}",
                )

    def _generate_summary_pdf(
        self,
        app: Application,
        scholarship_name: str,
        academic_year: int,
        semester: Optional[str],
    ) -> bytes:
        """Generate a student summary PDF from the HTML template."""
        student = app.student_data or {}
        submitted = app.submitted_form_data or {}

        # Degree label
        degree_raw = str(student.get("trm_degree", ""))
        degree_label = DEGREE_LABELS.get(degree_raw, degree_raw or "—")

        # Semester label
        semester_map = {"first": "第一學期", "second": "第二學���"}
        semester_label = semester_map.get(semester, "全學年") if semester else "全學年"

        # Form fields
        form_fields = []
        fields_data = submitted.get("fields", {})
        for field_id in sorted(fields_data.keys()):
            field = fields_data[field_id]
            form_fields.append({
                "label": field.get("field_id", field_id),
                "value": field.get("value", ""),
            })

        # Document list
        documents = []
        for doc in submitted.get("documents", []):
            documents.append({
                "name": doc.get("document_type") or doc.get("document_id", "未知文件"),
                "upload_time": doc.get("upload_time", ""),
            })

        # Render HTML
        template = self._jinja_env.get_template("student_summary.html")
        html_content = template.render(
            student=student,
            degree_label=degree_label,
            scholarship_name=scholarship_name,
            academic_year=academic_year,
            semester_label=semester_label,
            export_time=datetime.now().strftime("%Y-%m-%d %H:%M"),
            form_fields=form_fields,
            documents=documents,
        )

        # Generate PDF
        pdf = weasyprint.HTML(string=html_content).write_pdf()
        return pdf
```

- [ ] **Step 2: Verify the service compiles in Docker**

```bash
docker compose -f docker-compose.dev.yml exec backend python -c "from app.services.export_package_service import ExportPackageService; print('OK')"
```

Expected: Prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/export_package_service.py
git commit -m "feat: add ExportPackageService for ZIP generation with student summary PDFs"
```

---

### Task 4: Create the API endpoint

**Files:**
- Create: `backend/app/api/v1/endpoints/college_review/export_package.py`
- Modify: `backend/app/api/v1/endpoints/college_review/__init__.py`

- [ ] **Step 1: Create the endpoint file**

Create `backend/app/api/v1/endpoints/college_review/export_package.py`:

```python
"""
Export Package API Endpoint

Generates and streams a ZIP file containing application materials
organized by department for college review.
"""

import logging
from io import BytesIO
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_roles
from app.db.deps import get_db
from app.models.user import User, UserRole
from app.services.export_package_service import ExportPackageService
from app.services.minio_service import MinIOService

from ._helpers import _check_academic_year_permission, _check_scholarship_permission

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/export-package")
async def export_application_package(
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None, description="Semester (first/second/null for annual)"),
    current_user: User = Depends(require_roles(UserRole.college, UserRole.admin, UserRole.super_admin)),
    db: AsyncSession = Depends(get_db),
):
    """Download a ZIP package of all application materials for a scholarship period."""

    # Sanitize semester
    if semester:
        semester = semester.replace("\x00", "").strip()
        if semester not in ("first", "second", "annual"):
            semester = None

    # Permission checks
    if not await _check_scholarship_permission(current_user, scholarship_type_id, db):
        raise HTTPException(status_code=403, detail="無權限存取此獎學金類型")

    if not await _check_academic_year_permission(current_user, academic_year, db):
        raise HTTPException(status_code=403, detail="無權限存取此學年度")

    # Determine college_code for filtering
    college_code = current_user.college_code if current_user.role == UserRole.college else None

    try:
        minio_service = MinIOService()
        service = ExportPackageService(db, minio_service)
        zip_buffer, zip_filename = await service.generate_export_zip(
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
            college_code=college_code,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    encoded_filename = quote(zip_filename)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(zip_buffer.getbuffer().nbytes),
        },
    )
```

- [ ] **Step 2: Register the router in `__init__.py`**

In `backend/app/api/v1/endpoints/college_review/__init__.py`, add the import and include:

After line 19 (`from .utilities import router as utilities_router`), add:
```python
from .export_package import router as export_package_router
```

After line 28 (`router.include_router(utilities_router, tags=["College Review - Utilities"])`), add:
```python
router.include_router(export_package_router, tags=["College Review - Export"])
```

- [ ] **Step 3: Verify endpoint is registered**

```bash
docker compose -f docker-compose.dev.yml restart backend
sleep 3
docker compose -f docker-compose.dev.yml exec backend python -c "
from app.main import app
routes = [r.path for r in app.routes if hasattr(r, 'path') and 'export' in r.path]
print(routes)
"
```

Expected: Shows the `/api/v1/college-review/export-package` route.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/endpoints/college_review/export_package.py backend/app/api/v1/endpoints/college_review/__init__.py
git commit -m "feat: add GET /college-review/export-package endpoint"
```

---

### Task 5: Create Next.js proxy route

**Files:**
- Create: `frontend/app/api/v1/export-package/route.ts`

- [ ] **Step 1: Create the proxy route**

Create `frontend/app/api/v1/export-package/route.ts`:

```typescript
import { NextRequest, NextResponse } from "next/server";
import { logger } from "@/lib/utils/logger";

/**
 * Sanitizes backend URL by validating hostname and reconstructing a clean URL.
 * Prevents SSRF attacks via hostname allowlist.
 */
function getSafeBackendUrl(): URL {
  const envUrl = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL;

  if (!envUrl) {
    throw new Error("Backend URL not configured");
  }

  let parsed: URL;
  try {
    parsed = new URL(envUrl);
  } catch {
    throw new Error("Invalid backend URL format");
  }

  const allowedHosts = [
    "backend",
    "localhost",
    "host.docker.internal",
    "ss.test.nycu.edu.tw",
  ];
  if (!allowedHosts.includes(parsed.hostname)) {
    throw new Error(`Untrusted hostname: ${parsed.hostname}`);
  }

  const protocol = parsed.protocol === "https:" ? "https:" : "http:";
  const port = parsed.port || (protocol === "https:" ? "443" : "8000");

  return new URL(`${protocol}//${parsed.hostname}:${port}`);
}

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const token = searchParams.get("token");
    const scholarshipTypeId = searchParams.get("scholarship_type_id");
    const academicYear = searchParams.get("academic_year");
    const semester = searchParams.get("semester");

    if (!token) {
      return NextResponse.json(
        { error: "Access token is required" },
        { status: 400 }
      );
    }

    if (!scholarshipTypeId || !academicYear) {
      return NextResponse.json(
        { error: "scholarship_type_id and academic_year are required" },
        { status: 400 }
      );
    }

    // Validate numeric parameters
    if (!/^\d+$/.test(scholarshipTypeId) || !/^\d+$/.test(academicYear)) {
      return NextResponse.json(
        { error: "Invalid parameter format" },
        { status: 400 }
      );
    }

    // Validate semester if provided
    if (semester && !["first", "second", "annual"].includes(semester)) {
      return NextResponse.json(
        { error: "Invalid semester value" },
        { status: 400 }
      );
    }

    let backendUrl: URL;
    try {
      backendUrl = getSafeBackendUrl();
    } catch {
      return NextResponse.json(
        { error: "Invalid backend configuration" },
        { status: 500 }
      );
    }

    backendUrl.pathname = "/api/v1/college-review/export-package";
    backendUrl.searchParams.set("scholarship_type_id", scholarshipTypeId);
    backendUrl.searchParams.set("academic_year", academicYear);
    if (semester) {
      backendUrl.searchParams.set("semester", semester);
    }

    const response = await fetch(backendUrl, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });

    if (!response.ok) {
      const errorText = await response.text();
      logger.error("Export package backend error", {
        status: response.status,
      });
      return NextResponse.json(
        { error: errorText || "Failed to generate export package" },
        { status: response.status }
      );
    }

    const fileBuffer = await response.arrayBuffer();
    const contentType =
      response.headers.get("content-type") || "application/zip";
    const contentDisposition =
      response.headers.get("content-disposition") || "attachment";

    return new NextResponse(fileBuffer, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": contentDisposition,
        "Content-Length": fileBuffer.byteLength.toString(),
        "Cache-Control": "no-cache, no-store, must-revalidate",
      },
    });
  } catch (error) {
    logger.error("Export package proxy error", {});
    return NextResponse.json(
      { error: "Failed to download export package" },
      { status: 500 }
    );
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/api/v1/export-package/route.ts
git commit -m "feat: add Next.js proxy route for export package download"
```

---

### Task 6: Add frontend API method and export button

**Files:**
- Modify: `frontend/lib/api/modules/college.ts`
- Modify: `frontend/components/college/review/ApplicationReviewPanel.tsx`

- [ ] **Step 1: Add `exportPackage` method to college API module**

In `frontend/lib/api/modules/college.ts`, add the following method inside the `createCollegeApi()` return object (after the last existing method, before the closing `};`):

```typescript
    /**
     * Download application materials export package as ZIP
     */
    exportPackage: async (params: {
      scholarship_type_id: number;
      academic_year: number;
      semester?: string;
      token: string;
    }): Promise<Blob> => {
      const searchParams = new URLSearchParams();
      searchParams.set("scholarship_type_id", String(params.scholarship_type_id));
      searchParams.set("academic_year", String(params.academic_year));
      if (params.semester) {
        searchParams.set("semester", params.semester);
      }
      searchParams.set("token", params.token);

      const response = await fetch(
        `/api/v1/export-package?${searchParams.toString()}`
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(
          errorData?.error || errorData?.detail || "匯出失敗"
        );
      }

      return response.blob();
    },
```

- [ ] **Step 2: Add the export package button to ApplicationReviewPanel**

In `frontend/components/college/review/ApplicationReviewPanel.tsx`, add the `FileArchive` icon import. Find the existing lucide-react import line and add `FileArchive`:

```typescript
import {
  Search,
  Eye,
  Grid,
  List,
  Download,
  FileArchive,
  GraduationCap,
  School,
  Award,
  Building,
  Info,
} from "lucide-react";
```

Add the export handler function. After the `handleExportApplications` function (around line 408, after its closing `};`), add:

```typescript
  const [isExportingPackage, setIsExportingPackage] = useState(false);

  const handleExportPackage = async () => {
    if (!activeScholarshipTab || !selectedAcademicYear) {
      toast.error(locale === "zh" ? "請先選擇獎學金類型和學年" : "Please select scholarship type and academic year");
      return;
    }

    const activeConfig = availableOptions?.scholarship_types?.find(
      type => type.code === activeScholarshipTab
    );
    if (!activeConfig) {
      toast.error(locale === "zh" ? "找不到獎學金配置" : "Scholarship config not found");
      return;
    }

    setIsExportingPackage(true);
    try {
      // Get token from cookie
      const token = document.cookie
        .split("; ")
        .find(row => row.startsWith("token="))
        ?.split("=")[1];

      if (!token) {
        toast.error(locale === "zh" ? "請重新登入" : "Please re-login");
        return;
      }

      const blob = await apiClient.college.exportPackage({
        scholarship_type_id: activeConfig.id,
        academic_year: selectedAcademicYear,
        semester: selectedSemester,
        token,
      });

      // Trigger browser download
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${activeConfig.name}_申請資料_${selectedAcademicYear}_${selectedSemester || "全"}.zip`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();

      toast.success(locale === "zh" ? "匯出成功" : "Export successful");
    } catch (error) {
      toast.error(
        locale === "zh" ? "匯出申請資料失敗" : "Export failed",
        {
          description: error instanceof Error ? error.message : undefined,
        }
      );
    } finally {
      setIsExportingPackage(false);
    }
  };
```

Add the button in the UI. Find the existing export button (around line 452):
```tsx
          <Button variant="outline" size="sm" onClick={handleExportApplications}>
            <Download className="h-4 w-4 mr-1" />
            {locale === "zh" ? "匯出" : "Export"}
          </Button>
```

Add the new button immediately after it:
```tsx
          <Button
            variant="outline"
            size="sm"
            onClick={handleExportPackage}
            disabled={isExportingPackage || !activeScholarshipTab || !selectedAcademicYear}
          >
            <FileArchive className="h-4 w-4 mr-1" />
            {isExportingPackage
              ? (locale === "zh" ? "匯出中..." : "Exporting...")
              : (locale === "zh" ? "匯出申請資料" : "Export Package")}
          </Button>
```

- [ ] **Step 3: Verify frontend compiles**

```bash
docker compose -f docker-compose.dev.yml exec frontend npx next build --no-lint 2>&1 | tail -5
```

Expected: Build succeeds or only has non-blocking warnings.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/modules/college.ts frontend/components/college/review/ApplicationReviewPanel.tsx
git commit -m "feat: add export package button and API method to college review panel"
```

---

### Task 7: Integration test

**Files:** None (manual testing)

- [ ] **Step 1: Start full stack**

```bash
cd /home/howard/scholarship-system/.worktrees/college-export-package
docker compose -f docker-compose.dev.yml up -d
```

- [ ] **Step 2: Test backend endpoint directly**

```bash
# Login as admin to get token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@nycu.edu.tw","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('data',{}).get('access_token',''))")

# Test export endpoint (adjust scholarship_type_id and academic_year to match seed data)
curl -s -o test_export.zip -w "%{http_code}" \
  "http://localhost:8000/api/v1/college-review/export-package?scholarship_type_id=1&academic_year=114&semester=first" \
  -H "Authorization: Bearer $TOKEN"
```

Expected: HTTP 200 and a valid ZIP file, or 400 if no applications exist for that filter.

- [ ] **Step 3: Verify ZIP contents**

```bash
unzip -l test_export.zip
rm test_export.zip
```

Expected: Shows department folders with student subfolders containing `學生資料彙整.pdf` and attachment files.

- [ ] **Step 4: Test via frontend**

1. Open `http://localhost:3000` and login as college user
2. Navigate to college review panel
3. Select scholarship type, academic year, semester
4. Click "匯出申請資料" button
5. Verify ZIP downloads and contains expected structure

- [ ] **Step 5: Test error cases**

- Test with no matching applications → should get 400 error toast
- Test without selecting filters → button should be disabled
- Test as student role → should get 403

---

### Task 8: Regenerate OpenAPI types

**Files:**
- Modify: `frontend/lib/api/generated/schema.d.ts`

- [ ] **Step 1: Regenerate TypeScript types**

```bash
cd frontend && npm run api:generate
```

Expected: `schema.d.ts` updated with the new export-package endpoint.

- [ ] **Step 2: Commit**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore: regenerate OpenAPI types with export-package endpoint"
```

# Renderer for the security-audit PDFs. A container instead of the runner's
# Python so the self-hosted runner needs nothing but docker, and so the CJK
# font is guaranteed: without it WeasyPrint drops every Chinese glyph and the
# PDF still renders "successfully".
FROM python:3.13-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir weasyprint==66.0 jinja2==3.1.6

COPY render_reports.py /app/render_reports.py
COPY templates /app/templates
ENTRYPOINT ["python", "/app/render_reports.py"]

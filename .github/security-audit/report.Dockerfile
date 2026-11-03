# Renderer for the security-audit PDFs. A container instead of the runner's
# Python so the self-hosted runner needs nothing but docker, and so the CJK
# font is guaranteed: without it WeasyPrint drops every Chinese glyph and the
# PDF still renders "successfully".
FROM python:3.13-slim-bookworm

# Exact versions (Fortify: Unpinned Dependency Version). These are the
# bookworm main-archive versions; if a Debian point release supersedes one,
# the build fails loudly at apt-get install — bump the pin, don't unpin.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libpango-1.0-0=1.50.12+ds-1 \
       libpangoft2-1.0-0=1.50.12+ds-1 \
       libharfbuzz-subset0=6.0.0+dfsg-3 \
       fonts-noto-cjk=1:20220127+repack1-1 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir weasyprint==66.0 jinja2==3.1.6

COPY render_reports.py /app/render_reports.py
COPY templates /app/templates

# Never run as root (Fortify: Default User Privilege). The workflow also
# passes --user "$(id -u):$(id -g)" so /reports is owned by the runner; this
# is the fallback for any other invocation.
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin reporter
USER reporter
ENTRYPOINT ["python", "/app/render_reports.py"]

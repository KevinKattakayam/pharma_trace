# syntax=docker/dockerfile:1.7
# ── build stage: wheels only ──
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ── runtime stage: no compilers, non-root, read-only friendly ──
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PORT=8000 WEB_CONCURRENCY=2
# Pick up OS security fixes published since the base image was built (Trivy flagged libpcre2-8-0).
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/* && rm -rf /wheels \
 && useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser . .
RUN rm -rf tests eval .ruff-baseline && mkdir -p /app/runtime && chown -R appuser:appuser /app/runtime
USER appuser
EXPOSE 8000
# Fails on non-2xx (the previous check passed even on HTTP 500).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status==200 else 1)"
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*' --no-server-header"]

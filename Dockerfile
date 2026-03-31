# ---- builder ----
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime ----
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN useradd --create-home --shell /bin/bash structiq
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy project source
COPY --chown=structiq:structiq . .

# Create data directory with correct ownership
RUN mkdir -p /data/runs && chown structiq:structiq /data/runs

USER structiq

# Runtime environment
ENV APP_MODE=api \
    DATA_DIR=/data/runs \
    MAX_WORKERS=4 \
    MAX_CONCURRENT_RUNS=5 \
    ENABLE_LLM=false \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run from /app so StructIQ package is importable
CMD ["python", "-m", "uvicorn", "StructIQ.api.routes:app", "--host", "0.0.0.0", "--port", "8000"]

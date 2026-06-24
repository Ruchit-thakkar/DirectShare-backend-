# Stage 1: Build dependencies in a temporary container
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Build final lightweight container
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
COPY app /app/app

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Expose port (Railway passes $PORT environment variable)
EXPOSE 8000

# Create a non-root user and set permissions for temp storage
RUN useradd -u 10001 -m appuser && \
    mkdir -p /app/app/storage/temp && \
    chown -R appuser:appuser /app

USER appuser

# Health check using Python's built-in urllib
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Start the FastAPI application
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}

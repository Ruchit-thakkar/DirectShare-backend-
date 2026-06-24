FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app /app/app

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose port (for documentation/local use)
EXPOSE 8000

# Create a non-root user and set permissions for temp storage
RUN useradd -u 10001 -m appuser && \
    mkdir -p /app/app/storage/temp && \
    chown -R appuser:appuser /app

USER appuser

# Start the FastAPI application on the dynamic port assigned by Railway
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

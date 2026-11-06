# Author: François Guillemette
# CrazyVideoGenerator Dockerfile
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8202 \
    HOST=0.0.0.0

WORKDIR /app

# Install system dependencies (ffmpeg is essential for video assembly, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install PyTorch with CUDA support (cu128 for RTX 50-series Blackwell sm_120 support)
ARG CUDA_WHL=cu128
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/${CUDA_WHL}

# Install application dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application assets and source code
COPY brand/ ./brand/
COPY app/ ./app/
COPY cli.py .

# Expose web studio port
EXPOSE 8202

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://127.0.0.1:8202/api/status || exit 1

# Start CrazyVideoGenerator Web Application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8202"]
